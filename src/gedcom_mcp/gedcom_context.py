#!/usr/bin/env python3

import logging
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
from threading import RLock
from cachetools import LRUCache

# Try to import GEDCOM parser
try:
    from gedcom.parser import Parser
    from gedcom.element.individual import IndividualElement
    from gedcom.element.family import FamilyElement
    from gedcom.element.object import ObjectElement
except ImportError:
    print(
        "Error: python-gedcom library not found. Please install it with: pip install python-gedcom"
    )
    raise

# Set up logging
logger = logging.getLogger(__name__)

# --- Cache Configuration ---
# Centralized place to configure cache sizes
CACHE_SIZES = {
    "person_details": 5000,
    "person_relationships": 2000,
    "neighbor": 10000,
}


@dataclass
class GedcomContext:
    """Context for managing GEDCOM data and caches"""

    gedcom_parser: Optional[Parser] = None
    gedcom_file_path: Optional[str] = None
    individual_lookup: Dict[str, IndividualElement] = field(default_factory=dict)
    family_lookup: Dict[str, FamilyElement] = field(default_factory=dict)
    source_lookup: Dict[str, ObjectElement] = field(default_factory=dict)
    note_lookup: Dict[str, ObjectElement] = field(default_factory=dict)

    # Use LRUCache with configurable sizes
    person_details_cache: LRUCache = field(
        default_factory=lambda: LRUCache(maxsize=CACHE_SIZES["person_details"])
    )
    person_relationships_cache: LRUCache = field(
        default_factory=lambda: LRUCache(maxsize=CACHE_SIZES["person_relationships"])
    )
    neighbor_cache: LRUCache = field(
        default_factory=lambda: LRUCache(maxsize=CACHE_SIZES["neighbor"])
    )

    max_time: int = 60  # time limit (1 minutes)
    max_nodes: int = 250000  # Much higher limit to find meeting points

    def clear_caches(self):
        """Clear all internal caches to free memory"""
        self.person_relationships_cache.clear()
        self.person_details_cache.clear()
        self.neighbor_cache.clear()
        logger.info("All GEDCOM caches cleared.")


DEFAULT_DATASET_ID = "default"

# FastMCP 4 requests may use fresh protocol connections. Keep application
# state in an explicit, process-owned registry keyed by the caller's dataset ID.
gedcom_contexts: Dict[str, GedcomContext] = {}
gedcom_context: GedcomContext = None  # Backward-compatible alias for default.
_context_registry_lock = RLock()


def _request_metadata_dataset_id(ctx=None) -> Optional[str]:
    """Read an application dataset handle from MCP request metadata."""
    if ctx is None:
        return None
    try:
        request_context = ctx.request_context
        meta = request_context.meta if request_context else None
        if meta is not None:
            dataset_id = getattr(meta, "dataset_id", None)
            if dataset_id is None and isinstance(meta, dict):
                dataset_id = meta.get("dataset_id")
            if isinstance(dataset_id, str) and dataset_id:
                return dataset_id
    except (AttributeError, RuntimeError):
        # Context may be used by direct unit tests or before a request exists.
        pass
    return None


def _session_dataset_id(ctx=None) -> Optional[str]:
    """Return a stable handle when FastMCP exposes a session."""
    if ctx is None:
        return None

    try:
        session = ctx.session
    except (AttributeError, RuntimeError):
        session = None

    if session is not None:
        dataset_id = getattr(session, "_gedcom_dataset_id", None)
        if isinstance(dataset_id, str) and dataset_id:
            return dataset_id

    try:
        session_id = ctx.session_id
    except (AttributeError, RuntimeError):
        session_id = None
    if isinstance(session_id, str) and session_id:
        dataset_id = f"session:{session_id}"
        if session is not None:
            try:
                setattr(session, "_gedcom_dataset_id", dataset_id)
            except Exception:
                logger.debug("Could not attach GEDCOM dataset handle to FastMCP session")
        return dataset_id

    return None


def get_dataset_id(ctx=None, dataset_id: Optional[str] = None) -> str:
    """Resolve the application dataset handle for the current request.

    A session ID is preferred and remains stable across requests. Request
    metadata is used only for genuinely sessionless requests, with the legacy
    default retained for direct calls and single-dataset clients.
    """
    if dataset_id:
        resolved = dataset_id
    else:
        resolved = _session_dataset_id(ctx)
        if not resolved:
            resolved = _request_metadata_dataset_id(ctx)
        if not resolved:
            resolved = DEFAULT_DATASET_ID

    if not isinstance(resolved, str) or not resolved:
        raise ValueError("dataset_id must be a non-empty string")

    return resolved


def get_gedcom_context(ctx=None, dataset_id: Optional[str] = None):
    """Return the live application context for the selected dataset.

    FastMCP request/session objects store only the small dataset handle. The
    registry stores each live parser, lookup dictionaries, caches, and unsaved
    edits across requests while keeping different dataset IDs isolated.
    """
    resolved_id = get_dataset_id(ctx, dataset_id)

    global gedcom_context
    with _context_registry_lock:
        gedcom_ctx = gedcom_contexts.get(resolved_id)
        if gedcom_ctx is None:
            gedcom_ctx = GedcomContext()
            gedcom_contexts[resolved_id] = gedcom_ctx
            logger.info("Created GEDCOM context for dataset %s", resolved_id)

        if resolved_id == DEFAULT_DATASET_ID:
            gedcom_context = gedcom_ctx

        return gedcom_ctx


def clear_gedcom_contexts() -> None:
    """Clear the process-local dataset registry (primarily useful for tests)."""
    global gedcom_context
    with _context_registry_lock:
        gedcom_contexts.clear()
        gedcom_context = None


def _rebuild_lookups(gedcom_ctx: GedcomContext):
    logger.info("Rebuilding lookup dictionaries...")
    gedcom_ctx.individual_lookup.clear()
    gedcom_ctx.family_lookup.clear()
    gedcom_ctx.source_lookup.clear()
    gedcom_ctx.note_lookup.clear()

    root_elements = gedcom_ctx.gedcom_parser.get_root_child_elements()
    for elem in root_elements:
        pointer = elem.get_pointer()
        tag = elem.get_tag()  # Get the tag for logging
        logger.debug(f"Processing element: Pointer={pointer}, Tag={tag}")  # Debug log
        if isinstance(elem, IndividualElement):
            gedcom_ctx.individual_lookup[pointer] = elem
        elif isinstance(elem, FamilyElement):
            gedcom_ctx.family_lookup[pointer] = elem
        elif tag == "SOUR":  # Use the 'tag' variable
            gedcom_ctx.source_lookup[pointer] = elem
        elif tag == "NOTE":  # Use the 'tag' variable
            gedcom_ctx.note_lookup[pointer] = elem
    logger.info(
        f"Rebuilt lookup dictionaries: {len(gedcom_ctx.individual_lookup)} individuals, {len(gedcom_ctx.family_lookup)} families, {len(gedcom_ctx.source_lookup)} sources, {len(gedcom_ctx.note_lookup)} notes"
    )
