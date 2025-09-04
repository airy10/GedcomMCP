#!/usr/bin/env python3

import logging
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
from cachetools import LRUCache

# Try to import GEDCOM parser
try:
    from gedcom.parser import Parser
    from gedcom.element.individual import IndividualElement
    from gedcom.element.family import FamilyElement
    from gedcom.element.object import ObjectElement
except ImportError:
    print("Error: python-gedcom library not found. Please install it with: pip install python-gedcom")
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
    person_details_cache: LRUCache = field(default_factory=lambda: LRUCache(maxsize=CACHE_SIZES["person_details"]))
    person_relationships_cache: LRUCache = field(default_factory=lambda: LRUCache(maxsize=CACHE_SIZES["person_relationships"]))
    neighbor_cache: LRUCache = field(default_factory=lambda: LRUCache(maxsize=CACHE_SIZES["neighbor"]))

    max_time: int = 60  # time limit (1 minutes)
    max_nodes: int = 250000  # Much higher limit to find meeting points

    def clear_caches(self):
        """Clear all internal caches to free memory"""
        self.person_relationships_cache.clear()
        self.person_details_cache.clear()
        self.neighbor_cache.clear()
        logger.info("All GEDCOM caches cleared.")


gedcom_context : GedcomContext = None

def get_gedcom_context(ctx):
    global gedcom_context
    
    # Try to get the session from the FastMCP context
    session = ctx.session
    if session:
        logger.info(f"session:{session} id:{ctx.session_id}")
        gedcom_ctx = getattr(session, "_gedcom_context", None)
    else:
        gedcom_ctx = getattr(session, "_gedcom_context", None)
        if gedcom_ctx is None:
            gedcom_ctx = gedcom_context
        logger.info("No session - using global context")
    
    # If we don't one associated to the session, create a new context
    if gedcom_ctx is None:
        gedcom_ctx = GedcomContext()
        if session:
            setattr(session, "_gedcom_context", gedcom_ctx)
        else:
            gedcom_context = gedcom_ctx
    
    return gedcom_ctx


def _rebuild_lookups(gedcom_ctx: GedcomContext):
    logger.info("Rebuilding lookup dictionaries...")
    gedcom_ctx.individual_lookup.clear()
    gedcom_ctx.family_lookup.clear()
    gedcom_ctx.source_lookup.clear()
    gedcom_ctx.note_lookup.clear()
    
    root_elements = gedcom_ctx.gedcom_parser.get_root_child_elements()
    for elem in root_elements:
        pointer = elem.get_pointer()
        tag = elem.get_tag() # Get the tag for logging
        logger.debug(f"Processing element: Pointer={pointer}, Tag={tag}") # Debug log
        if isinstance(elem, IndividualElement):
            gedcom_ctx.individual_lookup[pointer] = elem
        elif isinstance(elem, FamilyElement):
            gedcom_ctx.family_lookup[pointer] = elem
        elif tag == "SOUR": # Use the 'tag' variable
            gedcom_ctx.source_lookup[pointer] = elem
        elif tag == "NOTE": # Use the 'tag' variable
            gedcom_ctx.note_lookup[pointer] = elem
    logger.info(f"Rebuilt lookup dictionaries: {len(gedcom_ctx.individual_lookup)} individuals, {len(gedcom_ctx.family_lookup)} families, {len(gedcom_ctx.source_lookup)} sources, {len(gedcom_ctx.note_lookup)} notes")
