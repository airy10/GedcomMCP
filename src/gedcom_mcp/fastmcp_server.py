#!/usr/bin/env python3

import argparse
import logging
import sys
from typing import Any, Dict, List, Optional, Set
from pathlib import Path
from datetime import datetime
import json
import traceback
import os

# Check if script is being run directly
if __name__ == "__main__" and __package__ is None:
    # Add the parent directory to sys.path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # Set the package name to allow relative imports
    __package__ = "gedcom_mcp"

from fastmcp import FastMCP, Context

from mcp.types import (
    TextContent,
    GetPromptResult,
    GetPromptRequest,
    SamplingMessage,
    Tool,
    Role,
    ImageContent,
)
from pydantic import BaseModel, Field
from functools import total_ordering
from dataclasses import dataclass, field
import time
import re
from typing import Optional, Tuple, Dict, Any, Annotated, Literal

# Try to import unidecode for text normalization
try:
    from unidecode import unidecode

    UNIDECODE_AVAILABLE = True
except ImportError:
    UNIDECODE_AVAILABLE = False

# Import our new genealogy date utilities
try:
    from .gedcom_date_utils import (
        parse_genealogy_date,
        get_date_certainty_level,
        GenealogyDate,
    )

    DATE_UTILS_AVAILABLE = True
except ImportError:
    DATE_UTILS_AVAILABLE = False
    print(
        "Warning: gedcom_date_utils not found. Date parsing enhancements will not be available."
    )

# Import our new genealogy name utilities
try:
    from .gedcom_name_utils import (
        parse_genealogy_name,
        normalize_name,
        find_name_variants,
        GenealogyName,
    )

    NAME_UTILS_AVAILABLE = True
except ImportError:
    NAME_UTILS_AVAILABLE = False
    print(
        "Warning: gedcom_name_utils not found. Name parsing enhancements will not be available."
    )

# Import our new genealogy place utilities
try:
    from .gedcom_place_utils import (
        normalize_place_name,
        extract_geographic_hierarchy,
        NormalizedPlace,
    )

    PLACE_UTILS_AVAILABLE = True
except ImportError:
    PLACE_UTILS_AVAILABLE = False
    print(
        "Warning: gedcom_place_utils not found. Place normalization enhancements will not be available."
    )

# Try to import GEDCOM parser
try:
    from gedcom.parser import Parser
    from gedcom.element.individual import IndividualElement
    from gedcom.element.family import FamilyElement
    from gedcom.element.object import ObjectElement
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.error(
        "python-gedcom library not found. Please install it with: pip install python-gedcom"
    )
    raise ImportError("Required dependency 'python-gedcom' is not installed") from e


# Suppress websockets deprecation warning
import warnings

warnings.filterwarnings(
    "ignore", category=DeprecationWarning, module="websockets.legacy"
)

# Default Configuration
DEFAULT_CONFIG = {
    "fuzzy_threshold": 80,
    "max_results": 50,
    "page_size": 100,
    "max_page_size_person_family": 1000,
    "max_page_size_others": 500,
    "max_distance": 30,
    "max_distance_all_paths": 15,
    "max_paths": 10,
    "max_level": 20,
    "generations": 3,
    "update_interval": 1000,
    "cache_sizes": {
        "person_details": 5000,
        "person_relationships": 2000,
        "neighbor": 10000,
    },
    "logging": {
        "level": "INFO",
        "file": None,
    },
}


# Load configuration from file if it exists
def load_config() -> dict:
    """Load configuration from config.json file if it exists"""
    import json

    config_path = Path("config.json")
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                user_config = json.load(f)
            # Merge with defaults
            config = DEFAULT_CONFIG.copy()
            config.update(user_config)
            return config
        except (json.JSONDecodeError, IOError) as e:
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to load config.json: {e}. Using defaults.")
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG


# Load configuration
CONFIG = load_config()

# Constants (from config)
DEFAULT_FUZZY_THRESHOLD = CONFIG["fuzzy_threshold"]
DEFAULT_MAX_RESULTS = CONFIG["max_results"]
DEFAULT_PAGE_SIZE = CONFIG["page_size"]
MAX_PAGE_SIZE_PERSON_FAMILY = CONFIG["max_page_size_person_family"]
MAX_PAGE_SIZE_OTHERS = CONFIG["max_page_size_others"]
DEFAULT_MAX_DISTANCE = CONFIG["max_distance"]
DEFAULT_MAX_DISTANCE_ALL_PATHS = CONFIG["max_distance_all_paths"]
DEFAULT_MAX_PATHS = CONFIG["max_paths"]
DEFAULT_MAX_LEVEL = CONFIG["max_level"]
DEFAULT_GENERATIONS = CONFIG["generations"]
DEFAULT_UPDATE_INTERVAL = CONFIG["update_interval"]


def handle_gedcom_error(error: Exception) -> str:
    """Convert GedcomError or other exceptions to user-friendly error messages."""
    if isinstance(error, GedcomError):
        return f"Error: {error.message}\nSuggestion: {error.recovery_suggestion}"
    else:
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error: {error}", exc_info=True)
        return f"An unexpected error occurred: {str(error)}"


def create_error_response(
    message: str, suggestion: str = None, error_code: str = None
) -> dict:
    """Create a standardized error response dictionary.

    Parameters:
        message: Error message describing what went wrong
        suggestion: Optional recovery suggestion for the user
        error_code: Optional error code for programmatic handling

    Returns:
        Standardized error response dictionary
    """
    response = {"status": "error", "message": message}
    if suggestion:
        response["recovery_suggestion"] = suggestion
    if error_code:
        response["error_code"] = error_code
    return response


def validate_gedcom_path(file_path: str) -> Path:
    """Validate GEDCOM file path for security"""
    path = Path(file_path).resolve()
    if not path.exists() or not path.is_file():
        raise ValueError(f"Invalid file path: {file_path}")
    if path.suffix.lower() != ".ged":
        raise ValueError("File must have .ged extension")
    return path


# Import our modularized components
from .gedcom_context import GedcomContext, get_gedcom_context, _rebuild_lookups
from .gedcom_models import PersonDetails, PersonRelationships, NodePriority
from .gedcom_data_access import (
    get_person_record,
    find_person_by_name,
    _get_relationships_internal,
    _get_events_internal,
    decode_event_details,
    _get_places_internal,
    _get_notes_internal,
    _get_sources_internal,
    search_gedcom,
    _extract_person_details,
    _get_person_relationships_internal,
    load_gedcom_file,
    save_gedcom_file,
    _get_person_attributes_internal,
    fuzzy_search_records,
)
from .gedcom_data_management import (
    _add_person_internal,
    _create_marriage_internal,
    _add_child_to_family_internal,
    _remove_child_from_family_internal,
    _remove_parent_from_family_internal,
    _remove_parents_internal,
    _update_event_details_internal,
    _remove_event_internal,
    _add_note_to_entity_internal,
    _create_source_internal,
    _delete_note_entity_internal,
    _new_empty_gedcom_internal,
    _update_person_attribute_internal,
    _update_person_details_internal,
    batch_update_person_attributes,
)
from .gedcom_search import (
    _dijkstra_bidirectional_search,
    _get_person_neighbors_lazy,
    _get_person_neighbors_lazy_reverse,
    _generate_relationship_chain_lazy,
    _correct_relationship_direction,
    _generate_relationship_description,
    _format_relationship_with_gender,
    _format_relationship_description,
    find_shortest_relationship_path as compute_shortest_relationship_path,
    _find_all_relationship_paths_internal,
    _find_all_paths_to_ancestor_internal,
)
from .gedcom_utils import (
    normalize_string,
    _get_gedcom_tag_from_event_type,
    _get_gedcom_tag_from_attribute_type,
    extract_birth_year,
    _extract_year_from_genealogy_date,
    _normalize_genealogy_name,
    _normalize_genealogy_date,
    _normalize_genealogy_place,
    _extract_year_from_date,
    _matches_criteria,
)
from .gedcom_analysis import (
    _get_attribute_statistics_internal,
    get_statistics_report,
    _get_timeline_internal,
    _get_ancestors_internal,
    _get_descendants_internal,
    _get_family_tree_summary_internal,
    _get_surname_statistics_internal,
    _get_date_range_analysis_internal,
    _find_potential_duplicates_internal,
    _get_common_ancestors_internal,
)
from .gedcom_constants import (
    EVENT_TYPES,
    ATTRIBUTE_TYPES,
    MAX_REASONABLE_DISTANCE,
    DEFAULT_PAGE_SIZE,
    BIRTH_YEAR_PROXIMITY_THRESHOLD,
    CONNECTIVITY_CHECK_DEPTH,
    DEFAULT_FUZZY_THRESHOLD,
    DEFAULT_MAX_RESULTS,
    MAX_PAGE_SIZE_PERSON_FAMILY,
    MAX_PAGE_SIZE_OTHERS,
    DEFAULT_MAX_DISTANCE,
    DEFAULT_MAX_DISTANCE_ALL_PATHS,
    DEFAULT_MAX_PATHS,
    DEFAULT_MAX_LEVEL,
    DEFAULT_GENERATIONS,
    DEFAULT_UPDATE_INTERVAL,
)


class GedcomConfig(BaseModel):
    """Configuration model for GEDCOM MCP server settings"""

    fuzzy_threshold: int = Field(ge=0, le=100, default=DEFAULT_FUZZY_THRESHOLD)
    max_results: int = Field(ge=1, le=1000, default=DEFAULT_MAX_RESULTS)
    page_size: int = Field(ge=1, le=1000, default=DEFAULT_PAGE_SIZE)
    max_page_size_person_family: int = Field(
        ge=1, le=2000, default=MAX_PAGE_SIZE_PERSON_FAMILY
    )
    max_page_size_others: int = Field(ge=1, le=1000, default=MAX_PAGE_SIZE_OTHERS)
    max_distance: int = Field(ge=1, le=200, default=DEFAULT_MAX_DISTANCE)
    max_distance_all_paths: int = Field(
        ge=1, le=100, default=DEFAULT_MAX_DISTANCE_ALL_PATHS
    )
    max_paths: int = Field(ge=1, le=50, default=DEFAULT_MAX_PATHS)
    max_level: int = Field(ge=1, le=50, default=DEFAULT_MAX_LEVEL)
    generations: int = Field(ge=1, le=10, default=DEFAULT_GENERATIONS)
    update_interval: int = Field(ge=100, le=10000, default=DEFAULT_UPDATE_INTERVAL)


class GedcomError(Exception):
    """Base exception for GEDCOM operations."""

    def __init__(
        self, message: str, error_code: str = None, recovery_suggestion: str = None
    ):
        self.message = message
        self.error_code = error_code or "UNKNOWN_ERROR"
        self.recovery_suggestion = recovery_suggestion
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """Convert error to dictionary format."""
        result = {"error": self.message, "error_code": self.error_code}
        if self.recovery_suggestion:
            result["recovery_suggestion"] = self.recovery_suggestion
        return result


class ProgressTracker:
    """Track progress of long-running operations."""

    def __init__(self, total_items: int, description: str, update_interval: int = 1000):
        self.total_items = total_items
        self.processed = 0
        self.description = description
        self.update_interval = update_interval
        self.start_time = time.time()
        self.last_update = 0

    def update(self, increment: int = 1, force: bool = False) -> None:
        """Update progress counter."""
        self.processed += increment
        current_time = time.time()

        # Update if forced or if enough time has passed
        if force or (current_time - self.last_update) >= 1.0:  # Update every second
            self._report_progress()
            self.last_update = current_time

    def _report_progress(self) -> None:
        """Report current progress."""
        if self.total_items > 0:
            percentage = (self.processed / self.total_items) * 100
            elapsed = time.time() - self.start_time

            # Estimate remaining time
            if self.processed > 0:
                rate = self.processed / elapsed
                remaining = (
                    (self.total_items - self.processed) / rate if rate > 0 else 0
                )
            else:
                remaining = 0

            logger.info(
                f"{self.description}: {percentage:.1f}% complete "
                f"({self.processed}/{self.total_items}) - "
                f"Elapsed: {elapsed:.1f}s, Remaining: {remaining:.1f}s"
            )

    def finish(self) -> None:
        """Mark operation as complete."""
        self.processed = self.total_items
        self._report_progress()
        total_time = time.time() - self.start_time
        logger.info(f"{self.description}: Complete in {total_time:.1f}s")


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the FastMCP server instance
mcp = FastMCP("gedcom-mcp-server")


# Register tools with FastMCP


@mcp.tool()
async def load_gedcom(
    file_path: Annotated[str, Field(description="Path to the GEDCOM file to load")],
    ctx: Context,
) -> dict:
    """Load and parse a GEDCOM file.

    Returns:
        Structured data with file statistics and loading confirmation
    """
    # Validate file path
    if not file_path:
        return {
            "status": "error",
            "message": "File path is required",
            "recovery_suggestion": "Provide a valid file path to a GEDCOM file",
        }

    # Check if file exists
    path = Path(file_path)
    if not path.exists():
        return {
            "status": "error",
            "message": f"File not found: {file_path}",
            "recovery_suggestion": "Check that the file path is correct and the file exists",
        }

    # Check if it's a file (not directory)
    if not path.is_file():
        return {
            "status": "error",
            "message": f"Path is not a file: {file_path}",
            "recovery_suggestion": "Provide a path to a GEDCOM file, not a directory",
        }

    # Try to load the file
    gedcom_ctx = get_gedcom_context(ctx)
    try:
        # Initialize progress tracking for file loading
        progress = ProgressTracker(
            total_items=1, description=f"Loading GEDCOM file: {Path(file_path).name}"
        )
        progress.update(force=True)

        success = load_gedcom_file(file_path, gedcom_ctx)
        if success:
            gedcom_ctx.gedcom_file_path = file_path
            progress.finish()
            return {
                "status": "success",
                "message": f"Successfully loaded GEDCOM file: {file_path}",
                "data": {
                    "file_path": file_path,
                    "individuals": len(gedcom_ctx.individual_lookup),
                    "families": len(gedcom_ctx.family_lookup),
                    "sources": len(gedcom_ctx.source_lookup),
                    "notes": len(gedcom_ctx.note_lookup),
                },
            }
        else:
            return {
                "status": "error",
                "message": f"Failed to parse GEDCOM file: {file_path}",
                "recovery_suggestion": "Check that the file is a valid GEDCOM format",
            }
    except FileNotFoundError:
        logger = logging.getLogger(__name__)
        logger.error(f"GEDCOM file not found: {file_path}")
        return {
            "status": "error",
            "message": f"GEDCOM file not found: {file_path}",
            "recovery_suggestion": "Check that the file path is correct and the file exists",
        }
    except PermissionError:
        logger = logging.getLogger(__name__)
        logger.error(f"Permission denied accessing GEDCOM file: {file_path}")
        return {
            "status": "error",
            "message": f"Permission denied accessing GEDCOM file: {file_path}",
            "recovery_suggestion": "Check file permissions and ensure you have read access",
        }
    except (OSError, IOError) as e:
        logger = logging.getLogger(__name__)
        logger.error(f"File system error loading GEDCOM file: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"File system error loading GEDCOM file: {str(e)}",
            "recovery_suggestion": "Check disk space, file system integrity, and try again",
        }
    except MemoryError:
        logger = logging.getLogger(__name__)
        logger.error("Memory error loading GEDCOM file - file too large")
        return {
            "status": "error",
            "message": "GEDCOM file is too large to load into memory",
            "recovery_suggestion": "Try loading a smaller GEDCOM file or increase system memory",
        }
    except (ValueError, TypeError) as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Data parsing error in GEDCOM file: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Invalid data format in GEDCOM file: {str(e)}",
            "recovery_suggestion": "Check that the file is a valid GEDCOM format and not corrupted",
        }
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error loading GEDCOM file: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Unexpected error loading GEDCOM file: {str(e)}",
            "recovery_suggestion": "Check file format and try again, or contact support if issue persists",
        }

@mcp.tool()
async def find_person(
    name: Annotated[
        str, Field(description="Name to search for (partial matches supported)")
    ],
    ctx: Context,
) -> dict:
    """Search for persons by name.

    Returns:
        Dictionary with search results containing count and person details.

    Examples:
        find_person("John")
        find_person("Smith")
    """
    if not name:
        return {
            "status": "error",
            "message": "Search name is required",
            "recovery_suggestion": "Provide a name to search for",
        }

    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    persons = find_person_by_name(name, gedcom_ctx)
    if persons:
        return {
            "status": "success",
            "message": f"Found {len(persons)} persons matching '{name}'",
            "data": {
                "persons": [person.model_dump() for person in persons],
                "count": len(persons),
            },
        }
    else:
        return {
            "status": "success",
            "message": f"No persons found matching '{name}'",
            "data": {"persons": [], "count": 0},
        }


@mcp.tool()
async def query_people_by_criteria(
    ctx: Context,
    occupation: Annotated[
        Optional[str],
        Field(description="Exact match for occupation (e.g., 'farmer', 'teacher')"),
    ] = None,
    birth_year_range: Annotated[
        Optional[str],
        Field(
            description="Year range as 'min_year,max_year' or single year (e.g., '1800,1850' or '1800')"
        ),
    ] = None,
    death_year_range: Annotated[
        Optional[str],
        Field(
            description="Year range as 'min_year,max_year' or 'min_year-max_year' or single year, or 'null' for living people"
        ),
    ] = None,
    birth_place_contains: Annotated[
        Optional[str],
        Field(
            description="Substring match in birth place (case insensitive, e.g., 'London')"
        ),
    ] = None,
    death_place_contains: Annotated[
        Optional[str],
        Field(
            description="Substring match in death place (case insensitive, e.g., 'Paris')"
        ),
    ] = None,
    name_contains: Annotated[
        Optional[str],
        Field(
            description="Substring match in person name (case insensitive, e.g., 'Smith')"
        ),
    ] = None,
    gender: Annotated[
        Optional[str],
        Field(description="'M' for male, 'F' for female, or None for any"),
    ] = None,
    has_children: Annotated[
        Optional[bool],
        Field(
            description="True for people with children, False for childless, None for any"
        ),
    ] = None,
    has_parents: Annotated[
        Optional[bool],
        Field(
            description="True for people with known parents, False for orphans, None for any"
        ),
    ] = None,
    has_spouses: Annotated[
        Optional[bool],
        Field(
            description="True for people with spouses, False for unmarried, None for any"
        ),
    ] = None,
    is_living: Annotated[
        Optional[bool],
        Field(
            description="True for living people (no death date), False for deceased, None for any"
        ),
    ] = None,
    page: Annotated[int, Field(description="Page number (starting from 1)")] = 1,
    page_size: Annotated[
        int, Field(description="Number of people per page (default 100, max 500)")
    ] = DEFAULT_PAGE_SIZE,
) -> dict:
    """Query people using flexible criteria with pagination

    Returns:
        Dictionary with search results and pagination information.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return create_error_response(
            "No family tree file is currently loaded",
            "Use the load_gedcom tool to open a GEDCOM file first",
        )

    # Validate parameters
    if page < 1:
        return create_error_response("Page number must be 1 or greater")
    if page_size < 1 or page_size > MAX_PAGE_SIZE_OTHERS:
        return create_error_response(
            f"Page size must be between 1 and {MAX_PAGE_SIZE_OTHERS}"
        )

    try:
        # Build filter criteria from individual parameters
        filter_criteria = {}

        # Handle occupation filter
        if occupation is not None:
            filter_criteria["occupation"] = occupation

        # Handle birth_year_range filter
        if birth_year_range is not None:
            if "," in birth_year_range or "-" in birth_year_range:
                # Range format: "min_year,max_year" or "min_year-max_year"
                parts = birth_year_range.split(",")
                if len(parts) != 2:
                    parts = birth_year_range.split("-")

                if len(parts) == 2:
                    try:
                        min_year = int(parts[0].strip())
                        max_year = int(parts[1].strip())
                        filter_criteria["birth_year_range"] = [min_year, max_year]
                    except ValueError:
                        return create_error_response(
                            f"Invalid birth_year_range format: {birth_year_range}. Use 'min_year,max_year' or 'min_year-max_year' or single year"
                        )
                else:
                    return create_error_response(
                        f"Invalid birth_year_range format: {birth_year_range}. Use 'min_year,max_year' or 'min_year-max_year' or single year"
                    )
            else:
                # Single year format
                try:
                    year = int(birth_year_range.strip())
                    filter_criteria["birth_year_range"] = [year, year]
                except ValueError:
                    return create_error_response(
                        f"Invalid birth_year_range format: {birth_year_range}. Use 'min_year,max_year' or 'min_year-max_year' or single year"
                    )

        # Handle death_year_range filter
        if death_year_range is not None:
            if death_year_range.lower() == "null":
                # Special case: null means living people (no death date)
                filter_criteria["death_year_range"] = None
            elif "," in death_year_range:
                # Range format: "min_year,max_year"
                parts = death_year_range.split(",")
                if len(parts) == 2:
                    try:
                        min_year = int(parts[0].strip())
                        max_year = int(parts[1].strip())
                        filter_criteria["death_year_range"] = [min_year, max_year]
                    except ValueError:
                        return create_error_response(
                            f"Invalid death_year_range format: {death_year_range}. Use 'min_year,max_year', single year, or 'null'"
                        )
                else:
                    return create_error_response(
                        f"Invalid death_year_range format: {death_year_range}. Use 'min_year,max_year', single year, or 'null'"
                    )
            else:
                # Single year format
                try:
                    year = int(death_year_range.strip())
                    filter_criteria["death_year_range"] = [year, year]
                except ValueError:
                    return create_error_response(
                        f"Invalid death_year_range format: {death_year_range}. Use 'min_year,max_year', single year, or 'null'"
                    )

        # Handle place filters
        if birth_place_contains is not None:
            filter_criteria["birth_place_contains"] = birth_place_contains
        if death_place_contains is not None:
            filter_criteria["death_place_contains"] = death_place_contains

        # Handle name filter
        if name_contains is not None:
            filter_criteria["name_contains"] = name_contains

        # Handle gender filter
        if gender is not None:
            if gender.upper() in ["M", "F"]:
                filter_criteria["gender"] = gender.upper()
            else:
                return create_error_response(
                    f"Invalid gender: {gender}. Must be 'M' or 'F'"
                )

        # Handle boolean filters
        if has_children is not None:
            filter_criteria["has_children"] = has_children
        if has_parents is not None:
            filter_criteria["has_parents"] = has_parents
        if has_spouses is not None:
            filter_criteria["has_spouses"] = has_spouses
        if is_living is not None:
            filter_criteria["is_living"] = is_living

        # PERFORMANCE OPTIMIZATION: Use lookup dictionary instead of iterating through all elements
        # Get all people
        matching_people = []

        for individual_elem in gedcom_ctx.individual_lookup.values():
            person = _extract_person_details(individual_elem, gedcom_ctx)
            if person and _matches_criteria(person, filter_criteria):
                matching_people.append(person)

        # Sort by ID for consistent ordering
        matching_people.sort(key=lambda p: p.id)

        # Calculate pagination
        total_count = len(matching_people)
        total_pages = (total_count + page_size - 1) // page_size
        start_index = (page - 1) * page_size
        end_index = min(start_index + page_size, total_count)

        # Get the page of people
        page_people = matching_people[start_index:end_index]

        # Format result as a dictionary
        people_data = []
        for person in page_people:
            person_data = {
                "id": person.id,
                "name": person.name,
                "has_children": len(person.children) > 0,
                "has_parents": len(person.parents) > 0,
                "has_spouses": len(person.spouses) > 0,
                "is_living": person.death_date is None,
            }

            # Add optional fields if they exist
            if person.birth_date:
                person_data["birth_date"] = person.birth_date
            if person.birth_place:
                person_data["birth_place"] = person.birth_place
            if person.death_date:
                person_data["death_date"] = person.death_date
            if person.death_place:
                person_data["death_place"] = person.death_place
            if person.gender:
                person_data["gender"] = person.gender
            if person.occupation:
                person_data["occupation"] = person.occupation

            people_data.append(person_data)

        result = {
            "filters_applied": filter_criteria,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "total_count": total_count,
            "has_next_page": page < total_pages,
            "has_previous_page": page > 1,
            "current_page_count": len(page_people),
            "people": people_data,
        }

        return result

    except Exception as e:
        return create_error_response(f"Error querying people by criteria: {e}")


@mcp.tool()
async def get_person_details(
    person_id: Annotated[
        str, Field(description="GEDCOM person ID (e.g., '@I1@', '@I123@')")
    ],
    ctx: Context,
) -> dict:
    """Get detailed information about a person.

    Returns:
        Comprehensive person details including name, events, attributes, and relationships

    Examples:
        get_person_details("@I1@")
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    person = get_person_record(person_id, gedcom_ctx)
    if person:
        return {
            "status": "success",
            "message": f"Found person details for {person.name}",
            "data": person,
        }
    else:
        return {
            "status": "error",
            "message": f"Person {person_id} was not found in the family tree",
        }


@mcp.tool()
async def get_all_entity_ids(
    entity_type: Annotated[
        Literal["person", "family", "place", "note", "source"],
        Field(
            description="The type of entity to retrieve IDs for ('person', 'family', 'place', 'note', 'source')"
        ),
    ],
    ctx: Context,
    page: Annotated[int, Field(description="Page number (starting from 1)")] = 1,
    page_size: Annotated[
        int,
        Field(
            description="Number of IDs per page (default 100, max 1000 for person/family, max 500 for others)"
        ),
    ] = 100,
) -> dict:
    """Get all IDs for a specific entity type (person, family, place, note, source) with pagination.

    Parameters:
        entity_type: The type of entity to retrieve IDs for ('person', 'family', 'place', 'note', 'source').
        page: Page number (starting from 1).
        page_size: Number of IDs per page (default 100, max 1000 for person/family, max 500 for others).
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return create_error_response(
            "No GEDCOM file loaded. Please load a GEDCOM file first.",
            "Use the load_gedcom tool to open a GEDCOM file",
        )

    all_ids = []
    total_count = 0
    max_page_size = 1000  # Default max for person/family

    try:
        if entity_type == "person":
            all_ids = list(gedcom_ctx.individual_lookup.keys())
        elif entity_type == "family":
            all_ids = list(gedcom_ctx.family_lookup.keys())
        elif entity_type == "note":
            all_ids = list(gedcom_ctx.note_lookup.keys())
            max_page_size = 500  # Max page size for notes
        elif entity_type == "source":
            all_ids = list(gedcom_ctx.source_lookup.keys())
            max_page_size = 500  # Max page size for sources
        elif entity_type == "place":
            # For places, we need to use the internal function to get unique places
            # and then extract their names/IDs.
            # _get_places_internal returns a list of dicts, each with a 'name' key
            places_data = _get_places_internal(query=None, gedcom_ctx=gedcom_ctx)
            all_ids = [place["name"] for place in places_data]
            max_page_size = 500  # Max page size for places
        else:
            return create_error_response(
                "Invalid entity_type. Must be 'person', 'family', 'place', 'note', or 'source'."
            )

        # Validate parameters
        if page < 1:
            return create_error_response("Page number must be 1 or greater")
        if page_size < 1 or page_size > max_page_size:
            return create_error_response(
                f"Page size must be between 1 and {max_page_size}"
            )

        all_ids.sort()  # Sort for consistent ordering
        total_count = len(all_ids)
        total_pages = (total_count + page_size - 1) // page_size  # Ceiling division
        start_index = (page - 1) * page_size
        end_index = min(start_index + page_size, total_count)

        page_ids = all_ids[start_index:end_index]

        result = {
            "entity_type": entity_type,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "total_count": total_count,
            "has_next_page": page < total_pages,
            "has_previous_page": page > 1,
            "current_page_count": len(page_ids),
            f"{entity_type}_ids": page_ids,  # Dynamic key
        }

        return result

    except Exception as e:
        return create_error_response(f"Error getting all {entity_type} IDs: {e}")

@mcp.tool()
async def get_events(
    person_id: Annotated[
        str, Field(description="GEDCOM person ID (e.g., '@I1@', '@I123@')")
    ],
    ctx: Context,
) -> dict:
    """Get all life events for a person.

    Returns:
        Comprehensive list of life events (birth, death, marriage, etc.) with dates and places

    Examples:
        get_events("@I1@")
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    events = _get_events_internal(person_id, gedcom_ctx)
    if events:
        return {
            "status": "success",
            "message": f"Found {len(events)} life events for person {person_id}",
            "data": events,
        }
    else:
        return {
            "status": "success",
            "message": f"No life events found for person {person_id}",
            "data": [],
        }


@mcp.tool()
async def get_notes(
    entity_id: Annotated[
        str, Field(description="GEDCOM entity ID (person '@I1@' or family '@F1@')")
    ],
    ctx: Context,
) -> dict:
    """Get all notes and research comments for a person or family.

    Returns:
        List of notes with text, sources, dates, and references

    Examples:
        get_notes("@I1@")  # Person notes
        get_notes("@F1@")  # Family notes
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    notes = _get_notes_internal(entity_id, gedcom_ctx)
    if notes:
        return {
            "status": "success",
            "message": f"Found {len(notes)} notes for {entity_id}",
            "data": notes,
        }
    else:
        return {
            "status": "success",
            "message": f"No notes found for {entity_id}",
            "data": [],
        }


@mcp.tool()
async def get_sources(
    entity_id: Annotated[
        str, Field(description="GEDCOM entity ID (person '@I1@' or family '@F1@')")
    ],
    ctx: Context,
) -> dict:
    """Get all source citations and references for a person or family.

    Returns:
        List of sources with citations, titles, authors, and publication info

    Examples:
        get_sources("@I1@")  # Person sources
        get_sources("@F1@")  # Family sources
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    sources = _get_sources_internal(entity_id, gedcom_ctx)
    if sources:
        return {
            "status": "success",
            "message": f"Found {len(sources)} sources for {entity_id}",
            "data": sources,
        }
    else:
        return {
            "status": "success",
            "message": f"No sources found for {entity_id}",
            "data": [],
        }


@mcp.tool()
async def gedcom_search(
    query: Annotated[str, Field(description="The search term to look for")],
    ctx: Context,
    search_type: Annotated[
        str,
        Field(
            description="Type of search - 'all', 'people', 'places', 'events', 'families'"
        ),
    ] = "all",
) -> dict:
    """Search across the GEDCOM file for people, places, events, etc.

    Returns:
        Search results organized by category

    Examples:
        gedcom_search("Smith", "all")      # Search all categories for "Smith"
        gedcom_search("John", "people")    # Search only people for "John"
        gedcom_search("London", "places")  # Search places for "London"
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    try:
        results = search_gedcom(query, gedcom_ctx, search_type)
        if any(results.values()):
            return {
                "status": "success",
                "message": f"Found search results for '{query}' in {search_type} categories",
                "data": results,
            }
        else:
            return {
                "status": "success",
                "message": f"No results found for query '{query}'",
                "data": {},
            }
    except (ValueError, TypeError) as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Invalid search parameters: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Invalid search parameters: {str(e)}",
            "recovery_suggestion": "Check search query format and try again",
        }
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error during search: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Search failed due to unexpected error: {str(e)}",
            "recovery_suggestion": "Try a different search query or contact support if issue persists",
        }


@mcp.tool()
async def get_statistics(ctx: Context) -> dict:
    """Get comprehensive statistics about the GEDCOM file.

    Returns:
        Detailed statistics about the loaded GEDCOM file including counts,
        date ranges, surname analysis, and data completeness metrics

    Examples:
        get_statistics()
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    try:
        stats = get_statistics_report(gedcom_ctx)
        return {
            "status": "success",
            "message": "Generated comprehensive statistics for the family tree",
            "data": stats,
        }
    except (KeyError, AttributeError) as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Data structure error generating statistics: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Data structure error generating statistics: {str(e)}",
            "recovery_suggestion": "The GEDCOM file may be corrupted or have an unusual format",
        }
    except (ValueError, TypeError) as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Data processing error generating statistics: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Data processing error generating statistics: {str(e)}",
            "recovery_suggestion": "Check GEDCOM file integrity and try reloading",
        }
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error generating statistics: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Unexpected error generating statistics: {str(e)}",
            "recovery_suggestion": "Try reloading the GEDCOM file or contact support",
        }


@mcp.tool()
async def get_occupation(
    person_id: Annotated[
        str, Field(description="GEDCOM person ID (e.g., '@I1@', '@I123@')")
    ],
    ctx: Context,
) -> dict:
    """Get the occupation of a person.

    Returns:
        Occupation information if available.

    Examples:
        get_occupation("@I1@")
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    person = get_person_record(person_id, gedcom_ctx)
    if person:
        if person.occupation:
            return {
                "status": "success",
                "message": f"Found occupation for {person.name}",
                "data": {
                    "person_id": person_id,
                    "person_name": person.name,
                    "occupation": person.occupation,
                },
            }
        else:
            return {
                "status": "success",
                "message": f"No occupation recorded for {person.name}",
                "data": {
                    "person_id": person_id,
                    "person_name": person.name,
                    "occupation": None,
                },
            }
    else:
        return {
            "status": "error",
            "message": f"Person {person_id} was not found in the family tree",
        }


@mcp.tool()
async def get_places(
    ctx: Context,
    query: Annotated[
        Optional[str],
        Field(description="Optional search term to filter places (case insensitive)"),
    ] = None,
) -> dict:
    """Get information about places mentioned in the GEDCOM file.

    Returns:
        List of places with their associated events and people.

    Examples:
        get_places()              # All places
        get_places("London")      # Places containing "London"
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    places = _get_places_internal(query, gedcom_ctx)
    if places:
        return {
            "status": "success",
            "message": f"Found {len(places)} places"
            + (f" matching '{query}'" if query else ""),
            "data": places,
        }
    else:
        return {
            "status": "success",
            "message": "No places found" + (f" matching '{query}'" if query else ""),
            "data": [],
        }


@mcp.tool()
async def get_relationships(
    person_id: Annotated[
        str, Field(description="GEDCOM person ID (e.g., '@I1@', '@I123@')")
    ],
    ctx: Context,
) -> dict:
    """Get family relationships for a person.

    Returns:
        Family relationship information including parents, spouses, and children.

    Examples:
        get_relationships("@I1@")
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    relationships = _get_relationships_internal(person_id, gedcom_ctx)
    if relationships:
        return {
            "status": "success",
            "message": f"Found family relationships for person {person_id}",
            "data": relationships,
        }
    else:
        return {
            "status": "success",
            "message": f"No family relationships found for person {person_id}",
            "data": [],
        }


@mcp.tool()
async def get_timeline(
    person_id: Annotated[
        str, Field(description="GEDCOM person ID (e.g., '@I1@', '@I123@')")
    ],
    ctx: Context,
) -> dict:
    """Generate a chronological timeline of life events for a person.

    Returns:
        Chronologically ordered list of life events with dates and places.

    Examples:
        get_timeline("@I1@")
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    timeline = _get_timeline_internal(person_id, gedcom_ctx)
    if timeline:
        return {
            "status": "success",
            "message": f"Generated timeline with {len(timeline)} events for person {person_id}",
            "data": timeline,
        }
    else:
        return {
            "status": "success",
            "message": f"No life events found for person {person_id}",
            "data": [],
        }


@mcp.tool()
async def fuzzy_search_person(
    name: Annotated[
        str, Field(description="Search term to match against person names")
    ],
    ctx: Context,
    threshold: Annotated[
        int, Field(description="Minimum similarity score (0-100, default: 80)")
    ] = 80,
    max_results: Annotated[
        int, Field(description="Maximum number of results to return (default: 50)")
    ] = 50,
) -> dict:
    """Search for persons with fuzzy name matching.

    Returns:
        List of persons with similar names.

    Examples:
        fuzzy_search_person("Jon", 70, 20)
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    try:
        results = fuzzy_search_records(name, gedcom_ctx, threshold, max_results)
        return {
            "status": "success",
            "message": f"Found {len(results)} fuzzy matches for '{name}'",
            "data": results,
        }
    except ImportError as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Missing fuzzy search dependency: {e}")
        return {
            "status": "error",
            "message": "Fuzzy search library not installed",
            "recovery_suggestion": "Install fuzzywuzzy with: pip install fuzzywuzzy python-levenshtein",
        }
    except (ValueError, TypeError) as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Invalid fuzzy search parameters: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Invalid search parameters: {str(e)}",
            "recovery_suggestion": "Check threshold (0-100) and max_results values",
        }
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error during fuzzy search: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Fuzzy search failed: {str(e)}",
            "recovery_suggestion": "Try a different search term or contact support",
        }


@mcp.tool()
async def add_person(
    name: Annotated[
        str,
        Field(
            description="Full name of the person (e.g., 'John Smith', 'Mary Johnson')"
        ),
    ],
    gender: Annotated[
        str, Field(description="Gender of the person ('M' for male, 'F' for female)")
    ],
    ctx: Context,
) -> dict:
    """Add a new person to the GEDCOM data.

    Returns:
        Success message with the new person's ID.

    Examples:
        Add a male person: add_person("John Smith", "M")
        Add a female person: add_person("Mary Johnson", "F")
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    person_id = _add_person_internal(gedcom_ctx, name, gender)
    _rebuild_lookups(gedcom_ctx)
    return {
        "status": "success",
        "message": f"Added {name} to the family tree with ID {person_id}",
        "data": {"person_id": person_id, "name": name, "gender": gender},
    }


# New tool starts here
@mcp.tool()
async def get_attribute_statistics(
    attribute_type: Annotated[
        str,
        Field(
            description="The GEDCOM attribute tag (e.g., 'OCCU') or its human-readable name (e.g., 'Occupation')"
        ),
    ],
    ctx: Context,
) -> dict:
    """
    Retrieves statistics for a given GEDCOM attribute (e.g., 'OCCU' or 'Occupation')
    across all individuals and families in the loaded GEDCOM file.

    Returns:
        A dictionary where keys are attribute values and values are their counts.
        Returns an error message if no GEDCOM file is loaded or if an invalid/unsupported attribute type is provided.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    try:
        stats = _get_attribute_statistics_internal(gedcom_ctx, attribute_type)
        # Check if the internal function returned an error dictionary
        if "error" in stats:
            return create_error_response(stats["error"])
        return {
            "status": "success",
            "message": f"Generated statistics for attribute '{attribute_type}'",
            "data": stats,
        }
    except (KeyError, AttributeError) as e:
        logger = logging.getLogger(__name__)
        logger.error(
            f"Data structure error getting attribute statistics: {e}", exc_info=True
        )
        return {
            "status": "error",
            "message": f"Data structure error processing attribute '{attribute_type}': {str(e)}",
            "recovery_suggestion": "The GEDCOM file may have an unusual format",
        }
    except (ValueError, TypeError) as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Invalid attribute type or data: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Invalid attribute type '{attribute_type}': {str(e)}",
            "recovery_suggestion": "Check the attribute type spelling and format",
        }
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(
            f"Unexpected error getting attribute statistics: {e}", exc_info=True
        )
        return {
            "status": "error",
            "message": f"Unexpected error processing attribute '{attribute_type}': {str(e)}",
            "recovery_suggestion": "Try a different attribute type or contact support",
        }


# New tool ends here


@mcp.tool()
async def get_ancestors(
    person_id: Annotated[
        str, Field(description="The ID of the person to get ancestors for")
    ],
    ctx: Context,
    generations: Annotated[
        int, Field(description="The number of generations to retrieve")
    ] = 3,
    format: Annotated[
        str,
        Field(
            description="The format of the output ('nested' for tree structure, 'flat' for a list with levels)"
        ),
    ] = "nested",
    page: Annotated[
        int, Field(description="Page number (starting from 1) for 'flat' format")
    ] = 1,
    page_size: Annotated[
        int,
        Field(
            description="Number of entries per page (default 100, max 500) for 'flat' format"
        ),
    ] = 100,
) -> dict:
    """Get ancestors of a person for specified number of generations, with optional formatting and pagination.

    Returns:
        Dictionary with ancestors data.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return create_error_response(
            "No GEDCOM file loaded. Please load a GEDCOM file first.",
            "Use the load_gedcom tool to open a GEDCOM file",
        )

    try:
        ancestors = _get_ancestors_internal(
            person_id, gedcom_ctx, generations=generations, format=format
        )

        if format == "flat":
            # Apply pagination for flat format
            if page < 1:
                return create_error_response("Page number must be 1 or greater")
            if page_size < 1 or page_size > 500:
                return create_error_response("Page size must be between 1 and 500")

            total_count = len(ancestors)
            total_pages = (total_count + page_size - 1) // page_size
            start_index = (page - 1) * page_size
            end_index = min(start_index + page_size, total_count)
            page_data = ancestors[start_index:end_index]

            result = {
                "person_id": person_id,
                "levels": generations,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "total_count": total_count,
                "has_next_page": page < total_pages,
                "has_previous_page": page > 1,
                "current_page_count": len(page_data),
                "ancestors": [
                    {"id": ancestor_id, "level": level}
                    for ancestor_id, level in page_data
                ],
            }
            return result
        else:
            # For nested format, return the ancestors directly
            if isinstance(ancestors, dict):
                return ancestors
            else:
                return {"ancestors": str(ancestors)}
    except Exception as e:
        return create_error_response(f"Error getting ancestors: {e}")


@mcp.tool()
async def get_family_tree_summary(
    person_id: Annotated[
        str, Field(description="GEDCOM person ID (e.g., '@I1@', '@I123@')")
    ],
    ctx: Context,
) -> dict:
    """Get a concise family tree summary showing parents, spouse(s), and children"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    try:
        result = _get_family_tree_summary_internal(person_id, gedcom_ctx)
        return {
            "status": "success",
            "message": f"Generated family tree summary for {person_id}",
            "data": result,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to generate family tree summary: {str(e)}",
        }


@mcp.tool()
async def get_surname_statistics(
    ctx: Context,
    surname: Annotated[
        Optional[str], Field(description="Optional surname to filter statistics for")
    ] = None,
) -> dict:
    """Get statistics about surnames in the GEDCOM file"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    try:
        result = _get_surname_statistics_internal(gedcom_ctx, surname)
        return {
            "status": "success",
            "message": f"Generated surname statistics"
            + (f" for '{surname}'" if surname else ""),
            "data": result,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to generate surname statistics: {str(e)}",
        }


@mcp.tool()
async def get_date_range_analysis(ctx: Context) -> dict:
    """Analyze the date ranges in the GEDCOM file to understand the time period covered"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    try:
        result = _get_date_range_analysis_internal(gedcom_ctx)
        return {
            "status": "success",
            "message": "Analyzed date ranges in the family tree",
            "data": result,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to analyze date ranges: {str(e)}",
        }


@mcp.tool()
async def find_potential_duplicates(ctx: Context) -> dict:
    """Find potential duplicate people based on similar names and dates"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    try:
        result = _find_potential_duplicates_internal(gedcom_ctx)
        return {
            "status": "success",
            "message": "Analyzed family tree for potential duplicate entries",
            "data": result,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to find potential duplicates: {str(e)}",
        }

    # Calculate cache statistics
    cache_stats = {
        "person_details_cache": {
            "size": len(gedcom_ctx.person_details_cache),
            "max_size": gedcom_ctx.person_details_cache.maxsize,
            "utilization_percent": (
                len(gedcom_ctx.person_details_cache)
                / gedcom_ctx.person_details_cache.maxsize
            )
            * 100
            if gedcom_ctx.person_details_cache.maxsize > 0
            else 0,
        },
        "person_relationships_cache": {
            "size": len(gedcom_ctx.person_relationships_cache),
            "max_size": gedcom_ctx.person_relationships_cache.maxsize,
            "utilization_percent": (
                len(gedcom_ctx.person_relationships_cache)
                / gedcom_ctx.person_relationships_cache.maxsize
            )
            * 100
            if gedcom_ctx.person_relationships_cache.maxsize > 0
            else 0,
        },
        "neighbor_cache": {
            "size": len(gedcom_ctx.neighbor_cache),
            "max_size": gedcom_ctx.neighbor_cache.maxsize,
            "utilization_percent": (
                len(gedcom_ctx.neighbor_cache) / gedcom_ctx.neighbor_cache.maxsize
            )
            * 100
            if gedcom_ctx.neighbor_cache.maxsize > 0
            else 0,
        },
        "total_individuals": len(gedcom_ctx.individual_lookup),
        "total_families": len(gedcom_ctx.family_lookup),
        "total_sources": len(gedcom_ctx.source_lookup),
        "total_notes": len(gedcom_ctx.note_lookup),
    }

    # Calculate memory estimates (rough approximation)
    # Each cache entry is roughly 1-2KB, but this is very approximate
    estimated_memory_kb = (
        len(gedcom_ctx.person_details_cache) * 1.5  # ~1.5KB per person details
        + len(gedcom_ctx.person_relationships_cache) * 0.5  # ~0.5KB per relationships
        + len(gedcom_ctx.neighbor_cache) * 0.3  # ~0.3KB per neighbor entry
    )

    cache_stats["estimated_memory_usage_kb"] = round(estimated_memory_kb, 1)

    # Performance recommendations
    recommendations = []
    if cache_stats["person_details_cache"]["utilization_percent"] > 90:
        recommendations.append(
            "Consider increasing person_details_cache size for better performance"
        )
    if cache_stats["person_relationships_cache"]["utilization_percent"] > 90:
        recommendations.append(
            "Consider increasing person_relationships_cache size for better performance"
        )
    if cache_stats["neighbor_cache"]["utilization_percent"] > 90:
        recommendations.append(
            "Consider increasing neighbor_cache size for better performance"
        )

    cache_stats["recommendations"] = recommendations

    return cache_stats


@mcp.tool()
async def get_configuration(ctx: Context) -> dict:
    """Get current configuration settings.

    Returns the current configuration values, including defaults and any user overrides.
    """
    return {
        "current_config": CONFIG,
        "config_file_path": "config.json",
        "config_file_exists": Path("config.json").exists(),
        "description": "Configuration can be customized by creating a config.json file in the working directory",
    }


@mcp.tool()
async def update_configuration(
    ctx: Context,
    config_updates: Annotated[
        str, Field(description="JSON string with configuration updates")
    ],
) -> dict:
    """Update configuration settings.

    Parameters:
        config_updates: JSON string with configuration updates. Valid keys include:
                        - fuzzy_threshold: Similarity threshold for fuzzy search (0-100, default: 80)
                        - max_results: Maximum results for fuzzy search (default: 50)
                        - page_size: Default page size for paginated results (default: 100)
                        - max_page_size_person_family: Max page size for person/family queries (default: 1000)
                        - max_page_size_others: Max page size for other queries (default: 500)
                        - max_distance: Default max relationship distance (default: 30)
                        - max_distance_all_paths: Default max distance for all paths search (default: 15)
                        - max_paths: Default max paths to return (default: 10)
                        - max_level: Default max ancestor level (default: 20)
                        - generations: Default generations for ancestor/descendant queries (default: 3)
                        - update_interval: Progress update interval in milliseconds (default: 1000)

    Returns:
        Success/error status with details about what was updated.

    Examples:
        Update fuzzy search threshold:
        '{"fuzzy_threshold": 85}'

        Update multiple settings:
        '{"fuzzy_threshold": 85, "max_results": 100, "page_size": 50}'

    Note: This updates the in-memory configuration but does not persist to file.
    To persist changes, manually edit config.json.
    """
    import json

    try:
        updates = json.loads(config_updates)

        # Validate updates (basic validation)
        valid_keys = set(DEFAULT_CONFIG.keys())
        for key in updates.keys():
            if key not in valid_keys:
                return {
                    "status": "error",
                    "message": f"Invalid configuration key: {key}",
                    "valid_keys": list(valid_keys),
                }

        # Apply updates
        CONFIG.update(updates)

        # Update constants that depend on config
        global DEFAULT_FUZZY_THRESHOLD, DEFAULT_MAX_RESULTS, DEFAULT_PAGE_SIZE
        global MAX_PAGE_SIZE_PERSON_FAMILY, MAX_PAGE_SIZE_OTHERS, DEFAULT_MAX_DISTANCE
        global DEFAULT_MAX_DISTANCE_ALL_PATHS, DEFAULT_MAX_PATHS, DEFAULT_MAX_LEVEL
        global DEFAULT_GENERATIONS, DEFAULT_UPDATE_INTERVAL

        DEFAULT_FUZZY_THRESHOLD = CONFIG["fuzzy_threshold"]
        DEFAULT_MAX_RESULTS = CONFIG["max_results"]
        DEFAULT_PAGE_SIZE = CONFIG["page_size"]
        MAX_PAGE_SIZE_PERSON_FAMILY = CONFIG["max_page_size_person_family"]
        MAX_PAGE_SIZE_OTHERS = CONFIG["max_page_size_others"]
        DEFAULT_MAX_DISTANCE = CONFIG["max_distance"]
        DEFAULT_MAX_DISTANCE_ALL_PATHS = CONFIG["max_distance_all_paths"]
        DEFAULT_MAX_PATHS = CONFIG["max_paths"]
        DEFAULT_MAX_LEVEL = CONFIG["max_level"]
        DEFAULT_GENERATIONS = CONFIG["generations"]
        DEFAULT_UPDATE_INTERVAL = CONFIG["update_interval"]

        return {
            "status": "success",
            "message": "Configuration updated successfully",
            "updated_keys": list(updates.keys()),
            "note": "Changes are in-memory only. To persist, update config.json manually.",
        }

    except json.JSONDecodeError as e:
        return create_error_response(
            f"Invalid JSON in config_updates: {e}",
            'Example: {"fuzzy_threshold": 85, "max_results": 100}',
        )
    except Exception as e:
        return create_error_response(f"Failed to update configuration: {e}")


@mcp.tool()
async def get_descendants(
    person_id: Annotated[
        str, Field(description="The ID of the person to get descendants for")
    ],
    ctx: Context,
    generations: Annotated[
        int, Field(description="The number of generations to retrieve")
    ] = 3,
    format: Annotated[
        str,
        Field(
            description="The format of the output ('nested' for tree structure, 'flat' for a list with levels)"
        ),
    ] = "nested",
    page: Annotated[
        int, Field(description="Page number (starting from 1) for 'flat' format")
    ] = 1,
    page_size: Annotated[
        int,
        Field(
            description="Number of entries per page (default 100, max 500) for 'flat' format"
        ),
    ] = 100,
) -> dict:
    """Get descendants of a person for specified number of generations, with optional formatting and pagination.

    Returns:
        Dictionary with descendants data.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return create_error_response(
            "No GEDCOM file loaded. Please load a GEDCOM file first.",
            "Use the load_gedcom tool to open a GEDCOM file",
        )

    try:
        descendants = _get_descendants_internal(
            person_id, gedcom_ctx, generations=generations, format=format
        )

        if format == "flat":
            # Apply pagination for flat format
            if page < 1:
                return create_error_response("Page number must be 1 or greater")
            if page_size < 1 or page_size > 500:
                return create_error_response("Page size must be between 1 and 500")

            total_count = len(descendants)
            total_pages = (total_count + page_size - 1) // page_size
            start_index = (page - 1) * page_size
            end_index = min(start_index + page_size, total_count)
            page_data = descendants[start_index:end_index]

            result = {
                "person_id": person_id,
                "levels": generations,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "total_count": total_count,
                "has_next_page": page < total_pages,
                "has_previous_page": page > 1,
                "current_page_count": len(page_data),
                "descendants": [
                    {"id": descendant_id, "level": level}
                    for descendant_id, level in page_data
                ],
            }
            return result
        else:
            # For nested format, return the descendants directly
            if isinstance(descendants, dict):
                return descendants
            else:
                return {"descendants": str(descendants)}
    except Exception as e:
        return create_error_response(f"Error getting descendants: {e}")


@mcp.tool()
async def find_all_paths_to_ancestor(
    start_person_id: Annotated[
        str, Field(description="The ID of the person to start from")
    ],
    ancestor_id: Annotated[
        str, Field(description="The ID of the ancestor to search for")
    ],
    ctx: Context,
    max_paths: Annotated[
        int, Field(description="Maximum number of paths to return (default: 10)")
    ] = 10,
) -> dict:
    """Find all paths from a person to a specific ancestor, following only parent relationships.

    Parameters:
        start_person_id: The ID of the person to start from
        ancestor_id: The ID of the ancestor to search for
        max_paths: Maximum number of paths to return (default: 10)

    Returns:
        Dictionary with all paths from start_person_id to ancestor_id
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return create_error_response(
            "No GEDCOM file loaded. Please load a GEDCOM file first.",
            "Use the load_gedcom tool to open a GEDCOM file",
        )

    try:
        paths = _find_all_paths_to_ancestor_internal(
            start_person_id, ancestor_id, gedcom_ctx, max_paths
        )

        if not paths:
            return create_error_response(
                f"No paths found from {start_person_id} to ancestor {ancestor_id}"
            )

        # Enrich paths with person names
        enriched_paths = []
        for path in paths:
            enriched_path = []
            for person_id in path:
                person = get_person_record(person_id, gedcom_ctx)
                person_name = person.name if person else "Unknown"
                enriched_path.append({"id": person_id, "name": person_name})
            enriched_paths.append(enriched_path)

        result = {
            "start_person": {
                "id": start_person_id,
                "name": get_person_record(start_person_id, gedcom_ctx).name,
            },
            "ancestor": {
                "id": ancestor_id,
                "name": get_person_record(ancestor_id, gedcom_ctx).name,
            },
            "total_paths": len(paths),
            "paths": enriched_paths,
        }

        return result

    except Exception as e:
        return create_error_response(f"Error finding paths to ancestor: {e}")


@mcp.tool()
async def get_persons_batch(
    person_ids: Annotated[
        str,
        Field(
            description="Comma-separated list of person IDs (e.g., '@I1@,@I2@,@I3@') or a single person ID"
        ),
    ],
    ctx: Context,
    include_fields: Annotated[
        str,
        Field(
            description="Fields to include - 'basic', 'extended', 'full', or custom comma-separated list"
        ),
    ] = "basic",
) -> dict:
    """Get details for one or multiple persons by their IDs. This is the primary tool for retrieving person details.

    Returns:
        Dictionary with person details and metadata about the request.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return create_error_response(
            "No GEDCOM file loaded. Please load a GEDCOM file first.",
            "Use the load_gedcom tool to open a GEDCOM file",
        )

    try:
        # Parse the person IDs
        ids = [pid.strip() for pid in person_ids.split(",") if pid.strip()]
        if not ids:
            return create_error_response("No valid person IDs provided")

        # Define field sets
        basic_fields = {"id", "name", "birth_date", "death_date"}
        extended_fields = basic_fields | {
            "birth_place",
            "death_place",
            "gender",
            "occupation",
        }
        full_fields = {
            "id",
            "name",
            "birth_date",
            "birth_place",
            "death_date",
            "death_place",
            "gender",
            "occupation",
            "parents",
            "spouses",
            "children",
        }

        # Determine which fields to include
        if include_fields.lower() == "basic":
            fields_to_include = basic_fields
        elif include_fields.lower() == "extended":
            fields_to_include = extended_fields
        elif include_fields.lower() == "full":
            fields_to_include = full_fields
        else:
            # Custom field list
            custom_fields = {
                field.strip() for field in include_fields.split(",") if field.strip()
            }
            # Validate custom fields against available fields
            valid_fields = full_fields
            fields_to_include = custom_fields & valid_fields
            if not fields_to_include:
                return create_error_response(
                    f"No valid fields specified. Available fields: {', '.join(sorted(valid_fields))}"
                )

        # Collect person details
        persons_data = []
        not_found = []

        for person_id in ids:
            person = get_person_record(person_id, gedcom_ctx)
            if person:
                # Create filtered person data
                person_data = {}
                person_dict = person.model_dump()

                for field in fields_to_include:
                    if field in person_dict:
                        value = person_dict[field]
                        # Format list fields nicely
                        if isinstance(value, list):
                            if value:  # Only include non-empty lists
                                person_data[field] = value
                        elif (
                            value is not None and value != ""
                        ):  # Only include non-empty values
                            person_data[field] = value

                persons_data.append(person_data)
            else:
                not_found.append(person_id)

        # Format the result as a dictionary
        result = {
            "total_requested": len(ids),
            "found": len(persons_data),
            "not_found": len(not_found),
            "fields_included": sorted(fields_to_include),
            "persons": persons_data,
        }

        if not_found:
            result["not_found_ids"] = not_found

        return result

    except Exception as e:
        return create_error_response(f"Error getting persons batch: {e}")


@mcp.tool()
async def find_shortest_relationship_path(
    person1_id: Annotated[str, Field(description="GEDCOM person ID for first person")],
    person2_id: Annotated[str, Field(description="GEDCOM person ID for second person")],
    ctx: Context,
    allowed_relationships: Annotated[
        str,
        Field(
            description="Relationship types to include: 'all', 'default', 'blood', 'parents', 'children', or comma-separated list"
        ),
    ] = "default",
    max_distance: Annotated[
        int, Field(description="Maximum relationship distance to search (default: 30)")
    ] = 30,
    exclude_initial_spouse_children: Annotated[
        bool,
        Field(description="Whether to exclude spouse/children from initial search"),
    ] = False,
    min_distance: Annotated[
        int, Field(description="Minimum relationship distance (default: 0)")
    ] = 0,
) -> str:
    """Find the shortest relationship path between two people

    Returns:
        JSON string containing the path information with distance and relationship description.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."

    # Validate that both people exist
    person1 = get_person_record(person1_id, gedcom_ctx)
    person2 = get_person_record(person2_id, gedcom_ctx)

    if not person1:
        return f"Person not found: {person1_id}"
    if not person2:
        return f"Person not found: {person2_id}"

    if person1_id == person2_id:
        return f'{{"path": ["{person1_id}"], "distance": 0, "relationship_chain": ["self"], "description": "Same person"}}'

    # Validate max_distance
    if max_distance < 1:
        max_distance = 30

    try:
        import time

        start_time = time.time()

        # Parse allowed relationships
        parse_start = time.time()
        allowed = set()
        allowed_relationships_lower = allowed_relationships.lower()

        if allowed_relationships_lower == "all":
            allowed = {"parent", "spouse", "sibling"}
        elif allowed_relationships_lower == "default":
            allowed = {
                "parent",
                "spouse",
                "child",
            }  # Default: spouse, parents, children
        elif allowed_relationships_lower == "blood":
            allowed = {"parent", "child"}  # Blood relationships only
        elif allowed_relationships_lower == "parents":
            allowed = {"parent"}  # Parents only (both mother and father)
        elif allowed_relationships_lower == "children":
            allowed = {"child"}  # Children only
        else:
            # Parse comma-separated list and expand special types
            raw_relationships = {
                rel.strip().lower() for rel in allowed_relationships.split(",")
            }
            allowed = set()

            for rel in raw_relationships:
                if rel == "spouse":
                    allowed.add("spouse")
                elif rel == "mother":
                    allowed.add(
                        "mother"
                    )  # Will be handled specially in neighbor function
                elif rel == "father":
                    allowed.add(
                        "father"
                    )  # Will be handled specially in neighbor function
                elif rel == "parents":
                    allowed.add("parent")  # Both mother and father
                elif rel == "children":
                    allowed.add("child")
                elif rel == "blood":
                    allowed.update({"parent", "child"})
                elif rel == "sibling":
                    allowed.add("sibling")
                elif rel == "parent":
                    allowed.add("parent")
                elif rel == "child":
                    allowed.add("child")
                elif rel == "all":
                    allowed.update({"parent", "spouse", "sibling", "child"})
                else:
                    logger.warning(f"Unknown relationship type: {rel}")

        parse_time = time.time() - parse_start
        logger.info(
            f"PERF: Relationship parsing took {parse_time:.3f}s, allowed: {allowed}"
        )

        # Call the internal function instead of duplicating the logic
        result = compute_shortest_relationship_path(
            person1_id,
            person2_id,
            allowed_relationships,
            gedcom_ctx,
            max_distance,
            exclude_initial_spouse_children,
            min_distance,
        )
        # Convert dict to JSON string for the tool response
        if isinstance(result, dict):
            return json.dumps(result, indent=2)
        return result

    except Exception as e:
        return create_error_response(f"Error finding relationship path: {e}")


@mcp.tool()
async def find_all_relationship_paths(
    person1_id: Annotated[str, Field(description="GEDCOM person ID for first person")],
    person2_id: Annotated[str, Field(description="GEDCOM person ID for second person")],
    ctx: Context,
    allowed_relationships: Annotated[
        str,
        Field(
            description="Relationship types to include: 'all', 'default', 'blood', or comma-separated list"
        ),
    ] = "all",
    max_distance: Annotated[
        int, Field(description="Maximum relationship distance to search (default: 15)")
    ] = 15,
    max_paths: Annotated[
        int, Field(description="Maximum number of paths to return (default: 10)")
    ] = 10,
) -> str:
    """Find all relationship paths between two people

    Returns:
        JSON string containing all paths found between the two people.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."

    # Validate that both people exist
    person1 = get_person_record(person1_id, gedcom_ctx)
    person2 = get_person_record(person2_id, gedcom_ctx)

    if not person1:
        return create_error_response(f"Person not found: {person1_id}")
    if not person2:
        return create_error_response(f"Person not found: {person2_id}")

    if person1_id == person2_id:
        return f'{"paths": [{"path": ["{person1_id}"], "distance": 0, "relationship_chain": ["self"], "description": "Same person"}], "total_paths": 1}'

    # Validate parameters
    if max_distance < 1:
        max_distance = 15
    if max_paths < 1:
        max_paths = 10

    try:
        # Call the internal function instead of duplicating the logic
        result = _find_all_relationship_paths_internal(
            person1_id,
            person2_id,
            allowed_relationships,
            gedcom_ctx,
            max_distance,
            max_paths,
        )
        # Convert dict to JSON string for the tool response
        if isinstance(result, dict):
            return json.dumps(result, indent=2)
        return result
    except Exception as e:
        return create_error_response(f"Error finding all relationship paths: {e}")


@mcp.tool()
async def get_common_ancestors(
    person_ids: Annotated[
        str,
        Field(
            description="Comma-separated list of person IDs (e.g., '@I1@,@I2@,@I3@')"
        ),
    ],
    ctx: Context,
    max_level: Annotated[
        int, Field(description="Maximum ancestor level to search (default: 20)")
    ] = 20,
) -> dict:
    """Find common ancestors for a list of people

    Parameters:
        person_ids: Comma-separated list of person IDs (e.g., "@I1@,@I2@,@I3@")
        max_level: Maximum ancestor level to search (default: 20)

    Returns:
        Dictionary with common ancestors, their levels for each person, and statistics
    """
    gedcom_ctx = get_gedcom_context(ctx)
    try:
        # Parse person IDs
        person_id_list = [pid.strip() for pid in person_ids.split(",") if pid.strip()]

        result = _get_common_ancestors_internal(person_id_list, gedcom_ctx, max_level)

        return result

    except Exception as e:
        return create_error_response(f"Error finding common ancestors: {e}")


@mcp.tool()
async def update_person(
    person_id: Annotated[
        str, Field(description="The ID of person to update (e.g., '@I123@')")
    ],
    ctx: Context,
    name: Annotated[Optional[str], Field(description="The new full name")] = None,
    gender: Annotated[
        Optional[str], Field(description="The new gender ('M' or 'F')")
    ] = None,
    birth_date: Annotated[
        Optional[str], Field(description="The new birth date")
    ] = None,
    birth_place: Annotated[
        Optional[str], Field(description="The new birth place")
    ] = None,
    death_date: Annotated[
        Optional[str], Field(description="The new death date")
    ] = None,
    death_place: Annotated[
        Optional[str], Field(description="The new death place")
    ] = None,
) -> str:
    """Updates the details for an existing person.

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser or person_id not in gedcom_ctx.individual_lookup:
        return create_error_response(f"Person with ID {person_id} not found.")

    try:
        # Update name and gender using the new internal function
        if name is not None or gender is not None:
            result = _update_person_details_internal(
                gedcom_ctx, person_id, name, gender
            )
            if "Error" in result:
                return result

        # Update birth event
        if birth_date is not None or birth_place is not None:
            result = _update_event_details_internal(
                gedcom_ctx, person_id, "BIRT", birth_date, birth_place
            )
            if "Error" in result:
                return result

        # Update death event
        if death_date is not None or death_place is not None:
            result = _update_event_details_internal(
                gedcom_ctx, person_id, "DEAT", death_date, death_place
            )
            if "Error" in result:
                return result

        # Clear relevant caches and rebuild lookups
        gedcom_ctx.clear_caches()
        _rebuild_lookups(gedcom_ctx)

        return f"Successfully updated details for person {person_id}."
    except Exception as e:
        return f"Error updating person {person_id}: {e}"


@mcp.tool()
async def find_person_families(
    person_id: Annotated[str, Field(description="The ID of person to look up")],
    ctx: Context,
) -> dict:
    """Finds the families a person is associated with (as a spouse or child).

    Args:
        person_id: The ID of the person to look up.

    Returns:
        A dictionary detailing the families where the person is a spouse (FAMS)
        and where they are a child (FAMC).
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser or person_id not in gedcom_ctx.individual_lookup:
        return create_error_response(f"Person with ID {person_id} not found.")

    person = gedcom_ctx.individual_lookup[person_id]

    # Find FAMS elements
    fams = []
    for elem in person.get_child_elements():
        if elem.get_tag() == "FAMS":
            fams.append(elem.get_value())

    # Find FAMC elements
    famc = []
    for elem in person.get_child_elements():
        if elem.get_tag() == "FAMC":
            famc.append(elem.get_value())

    return {"person_id": person_id, "families_as_spouse": fams, "family_as_child": famc}


@mcp.tool()
async def remove_child_from_family(
    child_id: Annotated[str, Field(description="The ID of child")],
    family_id: Annotated[
        str, Field(description="The ID of family from which to remove child")
    ],
    ctx: Context,
) -> dict:
    """Removes the link between a child and their family.

    Args:
        child_id: The ID of the child.
        family_id: The ID of the family from which to remove the child.

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    if child_id not in gedcom_ctx.individual_lookup:
        return {
            "status": "error",
            "message": f"Child with ID {child_id} was not found in the family tree",
        }

    if family_id not in gedcom_ctx.family_lookup:
        return {
            "status": "error",
            "message": f"Family with ID {family_id} was not found in the family tree",
        }

    result = _remove_child_from_family_internal(gedcom_ctx, child_id, family_id)

    # If successful, clear caches and rebuild lookups
    if result.startswith("Successfully"):
        gedcom_ctx.clear_caches()
        _rebuild_lookups(gedcom_ctx)
        return {
            "status": "success",
            "message": f"Removed child {child_id} from family {family_id}",
            "data": {"child_id": child_id, "family_id": family_id},
        }
    else:
        return {
            "status": "error",
            "message": f"Failed to remove child from family: {result}",
        }


@mcp.tool()
async def remove_parent_from_family(
    parent_id: Annotated[str, Field(description="The ID of parent")],
    family_id: Annotated[
        str, Field(description="The ID of family from which to remove parent")
    ],
    ctx: Context,
) -> str:
    """Removes the link between a parent and their family.

    This function removes the parent from the family record (removes HUSB/WIFE tag)
    and removes the FAMS tag from the parent's record.

    Args:
        parent_id: The ID of the parent.
        family_id: The ID of the family from which to remove the parent.

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser or parent_id not in gedcom_ctx.individual_lookup:
        return create_error_response(f"Parent with ID {parent_id} not found.")
    if family_id not in gedcom_ctx.family_lookup:
        return create_error_response(f"Family with ID {family_id} not found.")

    result = _remove_parent_from_family_internal(gedcom_ctx, parent_id, family_id)

    # If successful, clear caches and rebuild lookups
    if result.startswith("Successfully"):
        gedcom_ctx.clear_caches()
        _rebuild_lookups(gedcom_ctx)

    return result


@mcp.tool()
async def dissolve_marriage(
    family_id: Annotated[
        str, Field(description="The ID of family where marriage exists")
    ],
    ctx: Context,
) -> dict:
    """Dissolves a marriage by removing the spouse links from a family.

    This does not delete the family record itself, in case children are attached.

    Args:
        family_id: The ID of the family where the marriage exists.

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    if family_id not in gedcom_ctx.family_lookup:
        return {
            "status": "error",
            "message": f"Family with ID {family_id} was not found in the family tree",
        }

    family = gedcom_ctx.family_lookup[family_id]

    try:
        spouses = []
        # Find and remove spouse elements (HUSB/WIFE)
        elements_to_remove = []
        for child in family.get_child_elements():
            if child.get_tag() in ["HUSB", "WIFE"]:
                spouses.append(child.get_value())
                elements_to_remove.append(child)

        # Remove the elements
        for element in elements_to_remove:
            family.get_child_elements().remove(element)

        if not spouses:
            return create_error_response(
                f"No spouses found in family {family_id} to dissolve."
            )

        # Remove FAMS from each spouse
        for spouse_id in spouses:
            if spouse_id in gedcom_ctx.individual_lookup:
                spouse = gedcom_ctx.individual_lookup[spouse_id]
                elements_to_remove = []
                for fams in spouse.get_child_elements():
                    if fams.get_tag() == "FAMS" and fams.get_value() == family_id:
                        elements_to_remove.append(fams)
                # Remove the elements
                for element in elements_to_remove:
                    spouse.get_child_elements().remove(element)

        gedcom_ctx.clear_caches()
        return f"Successfully dissolved marriage in family {family_id}."
    except Exception as e:
        return f"Error dissolving marriage: {e}"


@mcp.tool()
async def delete_person(
    person_id: Annotated[str, Field(description="The ID of person to delete")],
    ctx: Context,
) -> str:
    """Deletes a person and removes them from all family relationships.

    This is a destructive operation. It will remove the person and update
    any families they were a part of.

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser or person_id not in gedcom_ctx.individual_lookup:
        return create_error_response(f"Person with ID {person_id} not found.")

    try:
        # Remove from all families
        for family in gedcom_ctx.family_lookup.values():
            # Use a copy of child elements to avoid modification issues during iteration
            elements_to_remove = []
            for child in family.get_child_elements():
                if child.get_value() == person_id:
                    elements_to_remove.append(child)
            # Remove the elements
            for element in elements_to_remove:
                family.get_child_elements().remove(element)

        # Remove the person element itself
        person_element = gedcom_ctx.individual_lookup[person_id]
        gedcom_ctx.gedcom_parser.get_root_element().get_child_elements().remove(
            person_element
        )

        # Remove from lookup
        del gedcom_ctx.individual_lookup[person_id]

        gedcom_ctx.clear_caches()
        return f"Successfully deleted person {person_id} and all related family links."
    except Exception as e:
        return f"Error deleting person {person_id}: {e}"


@mcp.tool()
async def update_event_details(
    entity_id: Annotated[str, Field(description="The ID of person or family")],
    event_type: Annotated[
        str,
        Field(description="The type of event to update (e.g., 'BIRT', 'MARR', 'RESI')"),
    ],
    ctx: Context,
    new_date: Annotated[
        Optional[str], Field(description="The new date for event")
    ] = None,
    new_place: Annotated[
        Optional[str], Field(description="The new place for event")
    ] = None,
    old_date_to_match: Annotated[
        Optional[str],
        Field(description="Required if there could be multiple events of same type"),
    ] = None,
) -> str:
    """Updates the date and/or place for an event associated with a person or family.

    If the event doesn't exist, it will be created. Family events (Marriage, divorce, etc.)
    should be associated with Family entities, not Person entities.

    Args:
        entity_id: The ID of the person or family.
        event_type: The type of event to update (e.g., 'BIRT', 'MARR', 'RESI').
                    Use `get_supported_types()` to see all valid options.
        new_date: The new date for the event.
        new_place: The new place for the event.
        old_date_to_match: Required if there could be multiple events of the same type.
                           This specifies the date of the exact event to update.

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return create_error_response("No GEDCOM file loaded.")

    result = _update_event_details_internal(
        gedcom_ctx, entity_id, event_type, new_date, new_place, old_date_to_match
    )

    # If successful, clear caches and rebuild lookups
    if result.startswith("Successfully"):
        gedcom_ctx.clear_caches()
        _rebuild_lookups(gedcom_ctx)

    return result

    return result


@mcp.tool()
async def remove_event(
    entity_id: Annotated[str, Field(description="The ID of person or family")],
    event_type: Annotated[
        str,
        Field(description="The type of event to remove (e.g., 'BIRT', 'MARR', 'RESI')"),
    ],
    ctx: Context,
    date_to_match: Annotated[
        Optional[str],
        Field(description="Optional date to match for identifying specific event"),
    ] = None,
) -> str:
    """Removes an event from a person or family.

    Args:
        entity_id: The ID of the person or family.
        event_type: The type of event to remove (e.g., 'BIRT', 'MARR', 'RESI').
                    Use `get_supported_types()` to see all valid options.
        date_to_match: Optional date to match for identifying the specific event.
                      Required if there could be multiple events of the same type.

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return create_error_response("No GEDCOM file loaded.")

    result = _remove_event_internal(gedcom_ctx, entity_id, event_type, date_to_match)

    # If successful, clear caches and rebuild lookups
    if result.startswith("Successfully"):
        gedcom_ctx.clear_caches()
        _rebuild_lookups(gedcom_ctx)

    return result


@mcp.tool()
async def get_person_attributes(
    person_id: Annotated[
        str, Field(description="GEDCOM person ID (e.g., '@I1@', '@I123@')")
    ],
    ctx: Context,
) -> dict:
    """Get all attributes for a person.

    Returns:
        List of all attributes associated with the person

    Examples:
        get_person_attributes("@I1@")
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {
            "status": "error",
            "message": "No family tree file is currently loaded",
            "recovery_suggestion": "Use the load_gedcom tool to open a GEDCOM file first",
        }

    try:
        attributes = _get_person_attributes_internal(person_id, gedcom_ctx)
        return {
            "status": "success",
            "message": f"Found {len(attributes)} attributes for person {person_id}",
            "data": attributes,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to get attributes for person {person_id}: {str(e)}",
        }

@mcp.tool()
async def update_person_attribute(
    person_id: Annotated[str, Field(description="The ID of person")],
    attribute_tag: Annotated[
        str,
        Field(
            description="The tag of attribute to update (e.g., 'OCCU' for occupation)"
        ),
    ],
    new_value: Annotated[str, Field(description="The new value for attribute")],
    ctx: Context,
) -> str:
    """Updates a person's attribute.
    Args:
        person_id (str): The ID of the person.
        attribute_tag (str): The tag of the attribute to update (e.g., 'OCCU' for occupation).
        new_value (str): The new value for the attribute.
    Returns:
        str: Success or error message.
    """
    try:
        gedcom_ctx = get_gedcom_context(ctx)
        result = _update_person_attribute_internal(
            gedcom_ctx, person_id, attribute_tag, new_value
        )
        if "Error" in result:
            return result

        # Clear caches and rebuild lookups after successful update
        gedcom_ctx.clear_caches()
        _rebuild_lookups(gedcom_ctx)

        return result
    except Exception as e:
        return f"Error updating attribute: {e}"


@mcp.tool()
async def batch_update_person_attributes(
    updates: Annotated[
        str, Field(description="JSON string containing an array of update objects")
    ],
    ctx: Context,
) -> dict:
    """Update multiple person attributes in a single operation.

    Returns:
        Dictionary with batch operation results:
        - total_updates: Total number of updates attempted
        - successful: Number of successful updates
        - failed: Number of failed updates
        - errors: Array of error details for failed updates

    Examples:
        Single update:
        '[{"person_id": "@I1@", "attribute_tag": "OCCU", "new_value": "farmer"}]'

        Multiple updates:
        '''[
            {"person_id": "@I1@", "attribute_tag": "OCCU", "new_value": "farmer"},
            {"person_id": "@I2@", "attribute_tag": "RESI", "new_value": "Springfield"},
            {"person_id": "@I3@", "attribute_tag": "TITL", "new_value": "Dr."}
        ]'''

    Common attribute tags:
        - OCCU: Occupation
        - RESI: Residence/Place of residence
        - TITL: Title/Noble title
        - EDUC: Education
        - RELI: Religion
        - NATI: Nationality
    """
    import json

    gedcom_ctx = get_gedcom_context(ctx)

    try:
        update_list = json.loads(updates) if updates else []
    except json.JSONDecodeError as e:
        return create_error_response(f"Invalid JSON in updates parameter: {e}")

    if not isinstance(update_list, list):
        return create_error_response("Updates parameter must be a JSON array")

    return _batch_update_person_attributes_internal(gedcom_ctx, update_list)


@mcp.tool()
async def remove_person_attribute(
    person_id: Annotated[str, Field(description="The ID of person")],
    attribute_type: Annotated[
        str,
        Field(
            description="The type of attribute (GEDCOM tag or human name, e.g., 'OCCU' or 'Occupation')"
        ),
    ],
    ctx: Context,
    value_to_match: Annotated[
        str,
        Field(
            description="The exact value of attribute to remove, for precise identification"
        ),
    ],
) -> str:
    """Removes a specific attribute from a person.

    Args:
        person_id: The ID of the person.
        attribute_type: The type of attribute (GEDCOM tag or human name, e.g., 'OCCU' or 'Occupation').
                        Use `get_supported_types()` to see all valid options.
        value_to_match: The exact value of the attribute to remove, for precise identification.

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser or person_id not in gedcom_ctx.individual_lookup:
        return create_error_response(f"Person with ID {person_id} not found.")

    attribute_tag = _get_gedcom_tag_from_attribute_type(attribute_type)
    if not attribute_tag:
        return create_error_response(f"Invalid attribute type '{attribute_type}'.")

    try:
        result = _remove_person_attribute_internal(
            gedcom_ctx, person_id, attribute_tag, value_to_match
        )
        if "Error" in result:
            return result
        gedcom_ctx.clear_caches()
        _rebuild_lookups(gedcom_ctx)
        return result
    except Exception as e:
        return f"Error removing attribute: {e}"


@mcp.tool()
async def create_source(
    title: Annotated[str, Field(description="The title of source")],
    ctx: Context,
    author: Annotated[str, Field(description="The author of source (optional)")] = "",
    publication: Annotated[
        str, Field(description="Publication information (optional)")
    ] = "",
) -> str:
    """Creates a new source with a unique ID.

    Returns:
        The ID of the newly created source.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return create_error_response("No GEDCOM file loaded.")

    try:
        source_id = _create_source_internal(gedcom_ctx, title, author, publication)
        _rebuild_lookups(gedcom_ctx)
        return f"Successfully created source with ID {source_id}"
    except Exception as e:
        return f"Error creating source: {e}"


@mcp.tool()
async def add_note_to_entity(
    entity_id: Annotated[
        str, Field(description="The ID of person or family to add note to")
    ],
    ctx: Context,
    note_text: Annotated[Optional[str], Field(description="The full text of note")],
) -> str:
    """Adds a new note to a person or family. Creates note references, not inline notes.

    Args:
        entity_id: The ID of the person or family to add the note to.
        note_text: The full text of the note.

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return create_error_response("No GEDCOM file loaded.")

    result = _add_note_to_entity_internal(gedcom_ctx, entity_id, note_text)

    # If successful, clear caches and rebuild lookups
    if result.startswith("Successfully"):
        gedcom_ctx.clear_caches()
        _rebuild_lookups(gedcom_ctx)

    return result


@mcp.tool()
async def delete_note_entity(
    note_id: Annotated[
        str, Field(description="The ID of note to delete (e.g., '@N123@')")
    ],
    ctx: Context,
) -> str:
    """Deletes a note entity by its ID and removes all references to it.

    Args:
        note_id: The ID of the note to delete (e.g., '@N123@').

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return create_error_response("No GEDCOM file loaded.")

        if note_id not in gedcom_ctx.note_lookup:
            return create_error_response(f"Note with ID {note_id} not found.")

    # First, remove all references to this note from all entities
    entities_to_update = []

    # Check individuals
    for indi_id, individual in gedcom_ctx.individual_lookup.items():
        notes_to_remove = []
        for child in individual.get_child_elements():
            if child.get_tag() == "NOTE" and child.get_value() == note_id:
                notes_to_remove.append(child)

        for note_elem in notes_to_remove:
            individual.get_child_elements().remove(note_elem)
            entities_to_update.append(indi_id)

    # Check families
    for fam_id, family in gedcom_ctx.family_lookup.items():
        notes_to_remove = []
        for child in family.get_child_elements():
            if child.get_tag() == "NOTE" and child.get_value() == note_id:
                notes_to_remove.append(child)

        for note_elem in notes_to_remove:
            family.get_child_elements().remove(note_elem)
            entities_to_update.append(fam_id)

    # Now delete the note entity itself
    result = _delete_note_entity_internal(gedcom_ctx, note_id)

    if result.startswith("Successfully"):
        if entities_to_update:
            return f"Successfully deleted note {note_id} and removed references from {len(entities_to_update)} entities."
        else:
            return f"Successfully deleted note {note_id}. No references found."
    else:
        return result


@mcp.tool()
async def delete_note_from_entity(
    entity_id: Annotated[str, Field(description="The ID of person or family")],
    ctx: Context,
    note_starts_with: Annotated[
        Optional[str],
        Field(description="The first few words of an inline note to identify it"),
    ] = None,
    note_id: Annotated[
        Optional[str],
        Field(
            description="The ID of a note entity to remove reference to (e.g., '@N123@')"
        ),
    ] = None,
) -> str:
    """Deletes a note from a person or family.

    This function can either:
    1. Delete an inline note based on the beginning of its text
    2. Remove a reference to a note entity (but Not delete the note entity itself)

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return create_error_response("No GEDCOM file loaded.")

    # Handle note reference removal
    if note_id:
        entity = gedcom_ctx.individual_lookup.get(
            entity_id
        ) or gedcom_ctx.family_lookup.get(entity_id)
        if not entity:
            return create_error_response(f"Entity with ID {entity_id} not found.")

        if note_id not in gedcom_ctx.note_lookup:
            return create_error_response(f"Note with ID {note_id} not found.")

        try:
            note_to_remove = None
            # Find NOTE reference elements
            for note in entity.get_child_elements():
                if note.get_tag() == "NOTE" and note.get_value() == note_id:
                    note_to_remove = note
                    break

            if note_to_remove:
                entity.get_child_elements().remove(note_to_remove)
                gedcom_ctx.clear_caches()
                return f"Successfully removed reference to note {note_id} from {entity_id}. Note entity still exists."
            else:
                return create_error_response(
                    f"No reference to note {note_id} found in {entity_id}."
                )
        except Exception as e:
            return f"Error removing note reference: {e}"

    # Handle inline note deletion
    if note_starts_with:
        entity = gedcom_ctx.individual_lookup.get(
            entity_id
        ) or gedcom_ctx.family_lookup.get(entity_id)
        if not entity:
            return create_error_response(f"Entity with ID {entity_id} not found.")

        try:
            note_to_delete = None
            # Find NOTE elements
            for note in entity.get_child_elements():
                if note.get_tag() == "NOTE":
                    note_value = note.get_value()
                    # Ensure it's an inline note and not a reference
                    if note_value and not note_value.startswith("@"):
                        if note_value.strip().startswith(note_starts_with):
                            note_to_delete = note
                            break

            if note_to_delete:
                entity.get_child_elements().remove(note_to_delete)
                gedcom_ctx.clear_caches()
                return f"Successfully deleted note starting with '{note_starts_with}' from {entity_id}."
            else:
                return create_error_response(
                    f"No inline note found for {entity_id} that starts with '{note_starts_with}'."
                )
        except Exception as e:
            return f"Error deleting note: {e}"

    return create_error_response("Either note_starts_with or note_id must be provided.")


@mcp.tool()
async def new_empty_gedcom(ctx: Context) -> str:
    """Create a new empty GEDCOM context with an empty parser and reset all attributes."""
    gedcom_ctx = get_gedcom_context(ctx)
    return _new_empty_gedcom_internal(gedcom_ctx)


@mcp.tool()
async def save_gedcom(
    ctx: Context,
    file_path: Annotated[
        Optional[str],
        Field(
            description="The path to save file to. If not provided, it will overwrite the original file"
        ),
    ] = None,
) -> str:
    """Saves the in-memory GEDCOM data back to a file.

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM data in memory to save."

    save_path = file_path or gedcom_ctx.gedcom_file_path
    if not save_path:
        return create_error_response(
            "No file path specified and no original file path is known. Please provide a file_path."
        )

    return save_gedcom_file(save_path, gedcom_ctx)


# Register prompt templates
@mcp.prompt(name="genealogy/family_tree")
def family_tree_template(
    person_name: str,
    generation_count: int,
    person_data: str = "",
    family_data: str = "",
) -> str:
    """Generate a family tree visualization for a person"""
    with open("prompts/family_tree_query.tmpl", "r") as f:
        template = f.read()
    return (
        template.replace("{{person_name}}", str(person_name))
        .replace("{{generation_count}}", str(generation_count))
        .replace("{{person_data}}", str(person_data))
        .replace("{{family_data}}", str(family_data))
    )


@mcp.prompt(name="genealogy/biography")
def biography_template(
    person_name: str,
    person_data: str = "",
    family_data: str = "",
    event_data: str = "",
    historical_context: str = "",
) -> str:
    """Generate a biographical summary for a person"""
    with open("prompts/biography_summary.tmpl", "r") as f:
        template = f.read()
    return (
        template.replace("{{person_name}}", str(person_name))
        .replace("{{person_data}}", str(person_data))
        .replace("{{family_data}}", str(family_data))
        .replace("{{event_data}}", str(event_data))
        .replace("{{historical_context}}", str(historical_context))
    )


@mcp.prompt(name="genealogy/relationship")
def relationship_template(
    person1_name: str,
    person2_name: str,
    person1_data: str = "",
    person2_data: str = "",
    family_data: str = "",
) -> str:
    """Find and describe the relationship path between two people"""
    with open("prompts/relationship_finder.tmpl", "r") as f:
        template = f.read()
    return (
        template.replace("{{person1_name}}", str(person1_name))
        .replace("{{person2_name}}", str(person2_name))
        .replace("{{person1_data}}", str(person1_data))
        .replace("{{person2_data}}", str(person2_data))
        .replace("{{family_data}}", str(family_data))
    )


# Register resource templates
@mcp.resource("genealogy://person/{person_id}")
async def get_person_resource(person_id: str, ctx: Context) -> str:
    """Get detailed information about a person as a resource"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."

    person = get_person_record(person_id, gedcom_ctx)
    if person:
        return person.json()
    else:
        return f"Person not found: {person_id}"


@mcp.resource("genealogy://family/{family_id}")
async def get_family_resource(family_id: str, ctx: Context) -> str:
    """Get detailed information about a family as a resource"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."

    # Use the family lookup to get the family element
    family_elem = gedcom_ctx.family_lookup.get(family_id)
    if not family_elem:
        return f"Family not found: {family_id}"

    # Extract family details
    husband_id = None
    wife_id = None
    children_ids = []

    # Get family details from child elements
    if hasattr(family_elem, "get_child_elements"):
        for child_elem in family_elem.get_child_elements():
            tag = child_elem.get_tag()
            value = child_elem.get_value()

            if tag == "HUSB":
                husband_id = value
            elif tag == "WIFE":
                wife_id = value
            elif tag == "CHIL":
                children_ids.append(value)

    # Get marriage data
    marriage_data = family_elem.get_marriage_data()
    marriage_date = None
    marriage_place = None

    if marriage_data:
        if isinstance(marriage_data, tuple):
            marriage_date = marriage_data[0] if len(marriage_data) > 0 else None
            marriage_place = marriage_data[1] if len(marriage_data) > 1 else None
        else:
            try:
                marriage_date = marriage_data.get_date()
                marriage_place = marriage_data.get_place()
            except AttributeError:
                pass

    # Build family information
    family_info = {
        "id": family_id,
        "husband_id": husband_id,
        "wife_id": wife_id,
        "children_ids": children_ids,
        "marriage_date": marriage_date,
        "marriage_place": marriage_place,
    }

    # Get person details for family members
    if husband_id:
        husband = get_person_record(husband_id, gedcom_ctx)
        if husband:
            family_info["husband"] = husband.model_dump()

    if wife_id:
        wife = get_person_record(wife_id, gedcom_ctx)
        if wife:
            family_info["wife"] = wife.model_dump()

    children_details = []
    for child_id in children_ids:
        child = get_person_record(child_id, gedcom_ctx)
        if child:
            children_details.append(child.model_dump())

    family_info["children"] = children_details

    import json

    return json.dumps(family_info, indent=2)


@mcp.resource("genealogy://search/{query}")
async def gedcom_search_resource(query: str, ctx: Context) -> str:
    """Search across the GEDCOM file as a resource"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."

    results = search_gedcom(query, gedcom_ctx, "all")
    if any(results.values()):
        import json

        return json.dumps(results, indent=2)
    else:
        return f"No results found for query: {query}"


# LLM Sampling Integration Functions
async def generate_biography(context: Context, person_data: str) -> str:
    """Generate a biographical summary for a person using LLM sampling"""
    from mcp.types import SamplingMessage, TextContent, Role

    messages = [
        SamplingMessage(
            role=Role.user,
            content=TextContent(
                type="text",
                text=f"Generate a biographical summary for the following person data:\n\n{person_data}",
            ),
        )
    ]

    try:
        result = await context.sample(
            messages=messages,
            system_prompt="You are a genealogy expert. Generate a well-written biographical summary based on the provided genealogical data. Include key life events in chronological order, mention family relationships, highlight any notable occupations or achievements, and keep the tone engaging but factual.",
        )
        return result.text if hasattr(result, "text") else str(result)
    except Exception as e:
        return f"Error generating biography: {e}"


async def generate_family_history(
    context: Context, person_data: str, family_data: str, generations: int = 3
) -> str:
    """Generate a family history narrative using LLM sampling"""
    from mcp.types import SamplingMessage, TextContent, Role

    messages = [
        SamplingMessage(
            role=Role.user,
            content=TextContent(
                type="text",
                text=f"Generate a family history narrative for the following person and their ancestors/descendants for {generations} generations:\n\nPerson Data:\n{person_data}\n\nFamily Data:\n{family_data}",
            ),
        )
    ]

    try:
        result = await context.sample(
            messages=messages,
            system_prompt=f"You are a genealogy expert. Generate a comprehensive family history narrative that traces {generations} generations of this family. Include key life events, family relationships, migrations, and historical context. Organize the narrative chronologically and thematically. Make it engaging but factual.",
        )
        return result.text if hasattr(result, "text") else str(result)
    except Exception as e:
        return f"Error generating family history: {e}"


async def generate_historical_context(
    context: Context, time_periods: str, locations: str
) -> str:
    """Generate historical context for time periods and locations using LLM sampling"""
    from mcp.types import SamplingMessage, TextContent, Role

    messages = [
        SamplingMessage(
            role=Role.user,
            content=TextContent(
                type="text",
                text=f"Provide historical context for the following time periods and locations relevant to genealogical research:\n\nTime Periods:\n{time_periods}\n\nLocations:\n{locations}",
            ),
        )
    ]

    try:
        result = await context.sample(
            messages=messages,
            system_prompt="You are a history expert specializing in genealogical research contexts. Provide relevant historical context for the given time periods and locations. Focus on major events, social conditions, migration patterns, and cultural aspects that would be relevant for understanding family histories. Be concise but informative.",
        )
        return result.text if hasattr(result, "text") else str(result)
    except Exception as e:
        return f"Error generating historical context: {e}"


# Structured User Elicitation Functions
from dataclasses import dataclass
from typing import Optional, Literal


@dataclass
class PersonDetailsInput:
    """Schema for collecting person details"""

    name: str
    birth_year: Optional[int] = None
    birth_place: Optional[str] = None
    death_year: Optional[int] = None
    death_place: Optional[str] = None
    gender: Optional[Literal["M", "F"]] = None
    occupation: Optional[str] = None


@dataclass
class FamilyDetailsInput:
    """Schema for collecting family details"""

    marriage_date: Optional[str] = None
    marriage_place: Optional[str] = None
    husband_name: Optional[str] = None
    wife_name: Optional[str] = None
    children_count: Optional[int] = None


@dataclass
class EventDetailsInput:
    """Schema for collecting event details"""

    event_type: Literal["birth", "death", "marriage", "baptism", "burial", "other"]
    date: Optional[str] = None
    place: Optional[str] = None
    description: Optional[str] = None


async def request_person_details(context: Context) -> str:
    """Request detailed person information through structured elicitation"""
    result = await context.elicit(
        message="Please provide details about the person",
        response_type=PersonDetailsInput,
    )

    if result.action == "accept":
        person = result.data
        details = []
        details.append(f"Name: {person.name}")
        if person.birth_year:
            details.append(f"Birth Year: {person.birth_year}")
        if person.birth_place:
            details.append(f"Birth Place: {person.birth_place}")
        if person.death_year:
            details.append(f"Death Year: {person.death_year}")
        if person.death_place:
            details.append(f"Death Place: {person.death_place}")
        if person.gender:
            details.append(f"Gender: {person.gender}")
        if person.occupation:
            details.append(f"Occupation: {person.occupation}")
        return "Person Details:\n" + "\n".join(details)
    elif result.action == "decline":
        return "Person details not provided"
    else:  # cancel
        return "Operation cancelled"


async def request_family_details(context: Context) -> str:
    """Request family details through structured elicitation"""
    result = await context.elicit(
        message="Please provide details about the family",
        response_type=FamilyDetailsInput,
    )

    if result.action == "accept":
        family = result.data
        details = []
        if family.marriage_date:
            details.append(f"Marriage Date: {family.marriage_date}")
        if family.marriage_place:
            details.append(f"Marriage Place: {family.marriage_place}")
        if family.husband_name:
            details.append(f"Husband: {family.husband_name}")
        if family.wife_name:
            details.append(f"Wife: {family.wife_name}")
        if family.children_count is not None:
            details.append(f"Number of Children: {family.children_count}")
        return (
            "Family Details:\n" + "\n".join(details)
            if details
            else "No family details provided"
        )
    elif result.action == "decline":
        return "Family details not provided"
    else:  # cancel
        return "Operation cancelled"


async def request_event_details(context: Context) -> str:
    """Request event details through structured elicitation"""
    result = await context.elicit(
        message="Please provide details about the event",
        response_type=EventDetailsInput,
    )

    if result.action == "accept":
        event = result.data
        details = [f"Event Type: {event.event_type}"]
        if event.date:
            details.append(f"Date: {event.date}")
        if event.place:
            details.append(f"Place: {event.place}")
        if event.description:
            details.append(f"Description: {event.description}")
        return "Event Details:\n" + "\n".join(details)
    elif result.action == "decline":
        return "Event details not provided"
    else:  # cancel
        return "Operation cancelled"


# Genealogy Date Parsing Tools
if DATE_UTILS_AVAILABLE:
    @mcp.tool()
    async def get_date_certainty(
        ctx: Context,
        date_string: Annotated[str, Field(description="The date string to analyze")],
    ) -> str:
        """Get a textual description of the certainty level of a date.

        Args:
            date_string: The date string to analyze

        Returns:
            A description of the date's certainty level
        """
        try:
            certainty = get_date_certainty_level(date_string)
            return f"Date certainty for '{date_string}': {certainty}"
        except Exception as e:
            return f"Error analyzing date certainty: {e}"


# Genealogy Name Parsing Tools
if NAME_UTILS_AVAILABLE:

    @mcp.tool()
    async def normalize_name(
        ctx: Context,
        name_string: Annotated[str, Field(description="The name string to normalize")],
    ) -> str:
        """Normalize a name for comparison purposes.

        Returns:
            A normalized version of name
        """
        try:
            normalized = normalize_name(name_string)
            return f"Normalized name for '{name_string}': {normalized}"
        except Exception as e:
            return f"Error normalizing name: {e}"

    @mcp.tool()
    async def find_name_variants(
        ctx: Context,
        name_string: Annotated[
            str, Field(description="The name string to find variants for")
        ],
    ) -> str:
        """Find common variants of a name.

        Returns:
            A list of common name variants
        """
        try:
            variants = find_name_variants(name_string)
            return f"Name variants for '{name_string}': {variants}"
        except Exception as e:
            return f"Error finding name variants: {e}"


# Genealogy Place Parsing Tools
if PLACE_UTILS_AVAILABLE:

    @mcp.tool()
    async def normalize_place_name(
        ctx: Context,
        place_string: Annotated[
            str, Field(description="The place string to normalize")
        ],
    ) -> str:
        """Normalize a place name.

        Returns:
            A detailed breakdown of normalized place information
        """
        try:
            normalized_place = normalize_place_name(place_string)
            import json

            return json.dumps(
                {
                    "original_text": normalized_place.original_text,
                    "normalized_name": normalized_place.normalized_name,
                    "country": normalized_place.country,
                    "state_province": normalized_place.state_province,
                    "county": normalized_place.county,
                    "city": normalized_place.city,
                },
                indent=2,
            )
        except Exception as e:
            return f"Error normalizing place name: {e}"

    @mcp.tool()
    async def extract_geographic_hierarchy(
        ctx: Context,
        place_string: Annotated[str, Field(description="The place string to parse")],
    ) -> str:
        """Extract geographic hierarchy from a place string.

        Returns:
            Dictionary with geographic components (city, county, state_province, country)
        """
        try:
            hierarchy = extract_geographic_hierarchy(place_string)
            import json

            return json.dumps(hierarchy, indent=2)
        except Exception as e:
            return f"Error extracting geographic hierarchy: {e}"


# Register the prompt handler
@mcp.prompt(name="gedcom-help")
def gedcom_help() -> str:
    """Provide help information for using the GEDCOM MCP server"""
    return """I can help you query genealogical data from GEDCOM files with comprehensive tools.

## Prompt Templates:
- **genealogy/family_tree**(person_name, generation_count, person_data, family_data) - Generate family tree visualizations
- **genealogy/biography**(person_name, person_data, family_data, event_data, historical_context) - Generate biographical summaries
- **genealogy/relationship**(person1_name, person2_name, person1_data, person2_data, family_data) - Find relationship paths between people

## Dynamic Resources:
- **genealogy://person/{person_id}** - Get detailed information about a person
- **genealogy://family/{family_id}** - Get detailed information about a family
- **genealogy://search/{query}** - Search across people, places, events, families

## LLM Sampling Functions:
- **generate_biography**(context, person_data) - Generate biographical summaries from person data
- **generate_family_history**(context, person_data, family_data, generations) - Generate family history narratives
- **generate_historical_context**(context, time_periods, locations) - Generate historical context for genealogical research

## Structured User Elicitation Functions:
- **request_person_details**(context) - Request detailed person information through structured forms
- **request_family_details**(context) - Request family details through structured forms
- **request_event_details**(context) - Request event details through structured forms

## Basic Tools:
- **load_gedcom**(file_path) - Load a GEDCOM file (returns structured data with statistics)
  - Parameters: file_path (string) - Path to GEDCOM file to load
- **find_person**(name) - Search for people by name (most basic search tool)
  - Parameters: name (string) - Name to search for (partial matches supported)
- **query_people_by_criteria**(occupation, birth_year_range, death_year_range, birth_place_contains, death_place_contains, name_contains, gender, has_children, has_parents, has_spouses, is_living, page, page_size) - Flexible people search with multiple criteria (most practical for research)
  - Parameters:
    - occupation (string, optional) - Exact match for occupation (e.g., 'farmer', 'teacher')
    - birth_year_range (string, optional) - Year range as 'min_year,max_year' or single year
    - death_year_range (string, optional) - Year range, single year, or 'null' for living people
    - birth_place_contains (string, optional) - Substring match in birth place (case insensitive)
    - death_place_contains (string, optional) - Substring match in death place (case insensitive)
    - name_contains (string, optional) - Substring match in person name (case insensitive)
    - gender (string, optional) - 'M' for male, 'F' for female, or None for any
    - has_children (boolean, optional) - True for people with children, False for childless, None for any
    - has_parents (boolean, optional) - True for people with known parents, False for orphans, None for any
    - has_spouses (boolean, optional) - True for people with spouses, False for unmarried, None for any
    - is_living (boolean, optional) - True for living people (no death date), False for deceased, None for any
    - page (integer) - Page number (starting from 1)
    - page_size (integer) - Number of people per page (default 100, max 500)
- **get_person_details**(person_id) - Get detailed person information (now includes occupation)
  - Parameters: person_id (string) - GEDCOM person ID (e.g., '@I1@', '@I123@')
- **get_persons_batch**(person_ids, include_fields) - Get details for multiple people at once
  - Parameters: 
    - person_ids (string) - Comma-separated list of person IDs or single ID
    - include_fields (string) - Fields to include: 'basic', 'extended', 'full', or custom list
- **get_occupation**(person_id) - Get a person's occupation
  - Parameters: person_id (string) - GEDCOM person ID (e.g., '@I1@', '@I123@')
- **get_relationships**(person_id) - Get family relationships
  - Parameters: person_id (string) - GEDCOM person ID (e.g., '@I1@', '@I123@')
- **new_empty_gedcom**() - Create a new empty GEDCOM context
- **add_person**(name, gender) - Add a new person to the GEDCOM data
  - Parameters:
    - name (string) - Full name of the person (e.g., 'John Smith', 'Mary Johnson')
    - gender (string) - Gender of the person ('M' for male, 'F' for female)
- **create_marriage**(husband_id, wife_id) - Create a marriage between two people
  - Parameters:
    - husband_id (string) - GEDCOM person ID for the husband
    - wife_id (string) - GEDCOM person ID for the wife
- **add_child_to_family**(child_id, family_id) - Add a child to a family
  - Parameters:
    - child_id (string) - GEDCOM person ID for the child
    - family_id (string) - GEDCOM family ID (e.g., '@F1@', '@F123@')
- **create_source**(title, author, publication) - Create a new source with a unique ID
  - Parameters:
    - title (string) - Title of the source
    - author (string) - Author of the source
    - publication (string) - Publication information

## Event & Information Tools:
- **get_events**(person_id) - Get comprehensive events with full details
  - Parameters: person_id (string) - GEDCOM person ID (e.g., '@I1@', '@I123@')
- **get_notes**(entity_id) - Get all notes with full text for a person or family
  - Parameters: entity_id (string) - GEDCOM entity ID (person '@I1@' or family '@F1@')
- **get_note_by_id**(note_id) - Get the full text content of a specific note (e.g., @N176@)
  - Parameters: note_id (string) - GEDCOM note ID (e.g., '@N1@', '@N123@')
- **get_sources**(entity_id) - Get all sources for a person or family
  - Parameters: entity_id (string) - GEDCOM entity ID (person '@I1@' or family '@F1@')
- **get_timeline**(person_id) - Generate chronological timeline
  - Parameters: person_id (string) - GEDCOM person ID (e.g., '@I1@', '@I123@')

## Analysis Tools:
- **gedcom_search**(query, search_type) - Search across people, places, events, families
  - Parameters:
    - query (string) - The search term to look for
    - search_type (string) - Type of search: 'all', 'people', 'places', 'events', 'families'
- **get_statistics**() - Get comprehensive GEDCOM file statistics
- **get_attribute_statistics**(attribute_type) - Get statistics for a specific GEDCOM attribute (e.g., OCCU, RELI)
  - Parameters: attribute_type (string) - GEDCOM attribute tag or human-readable name
- **get_places**(query) - Get information about places
  - Parameters: query (string, optional) - Search term to filter places (case insensitive)
- **get_surname_statistics**(surname) - Analyze surname frequency and distribution
  - Parameters: surname (string, optional) - Optional surname to filter statistics for
- **get_date_range_analysis**() - Analyze time periods and generations covered
- **find_potential_duplicates**() - Find possible duplicate person records

- **get_date_certainty**(date_string) - Get certainty level description for a date
  - Parameters: date_string (string) - Date string to analyze

- **normalize_name**(name_string) - Normalize a name for comparison purposes
  - Parameters: name_string (string) - Name to normalize
- **find_name_variants**(name_string) - Find common variants of a name
  - Parameters: name_string (string) - Name to find variants for
- **normalize_place_name**(place_string) - Normalize place names
  - Parameters: place_string (string) - Place name to normalize

- **extract_geographic_hierarchy**(place_string) - Extract geographic hierarchy from place strings
  - Parameters: place_string (string) - Place string to analyze

## Bulk Data Tools:
- **get_all_entity_ids**(entity_type, page, page_size) - Get all entity IDs (person, family, place, note, source) with pagination
  - Parameters:
    - entity_type (string) - Type of entity: 'person', 'family', 'place', 'note', 'source'
    - page (integer) - Page number (starting from 1)
    - page_size (integer) - Number of entries per page (default 100, max 500)

## Genealogy Tools:
- **get_ancestors**(person_id, generations, format, page, page_size) - Get ancestors tree with full details
  - Parameters:
    - person_id (string) - GEDCOM person ID (e.g., '@I1@', '@I123@')
    - generations (integer) - Number of generations to retrieve (default: 3)
    - format (string) - Output format: 'nested' for tree structure, 'flat' for list with levels
    - page (integer) - Page number for 'flat' format (starting from 1)
    - page_size (integer) - Entries per page for 'flat' format (default 100, max 500)
- **get_descendants**(person_id, generations, format, page, page_size) - Get descendants tree with full details
  - Parameters:
    - person_id (string) - GEDCOM person ID (e.g., '@I1@', '@I123@')
    - generations (integer) - Number of generations to retrieve (default: 3)
    - format (string) - Output format: 'nested' for tree structure, 'flat' for list with levels
    - page (integer) - Page number for 'flat' format (starting from 1)
    - page_size (integer) - Entries per page for 'flat' format (default 100, max 500)
- **get_family_tree_summary**(person_id) - Concise family overview with parents, spouse, children
  - Parameters: person_id (string) - GEDCOM person ID (e.g., '@I1@', '@I123@')
- **find_shortest_relationship_path**(person1_id, person2_id, allowed_relationships, max_distance, exclude_initial_spouse_children, min_distance) - Find shortest path between two people (max distance: 30)
  - Parameters:
    - person1_id (string) - GEDCOM person ID for the first person
    - person2_id (string) - GEDCOM person ID for the second person
    - allowed_relationships (string, optional) - Comma-separated list of allowed relationship types
    - max_distance (integer) - Maximum relationship distance to search (default: 30)
    - exclude_initial_spouse_children (boolean) - Whether to exclude initial spouse/children relationships
    - min_distance (integer) - Minimum relationship distance (default: 1)
- **get_common_ancestors**(person_ids, max_level) - Find common ancestors for multiple people (comma-separated IDs, max level: 20)
  - Parameters:
    - person_ids (string) - Comma-separated list of GEDCOM person IDs
    - max_level (integer) - Maximum ancestor level to search (default: 20)

- **find_all_relationship_paths**(person1_id, person2_id, allowed_relationships, max_distance, max_paths) - Find all relationship paths between two people
  - Parameters:
    - person1_id (string) - GEDCOM person ID for the first person
    - person2_id (string) - GEDCOM person ID for the second person
    - allowed_relationships (string, optional) - Comma-separated list of allowed relationship types
    - max_distance (integer) - Maximum relationship distance to search (default: 30)
    - max_paths (integer) - Maximum number of paths to return (default: 10)
- **find_all_paths_to_ancestor**(start_person_id, ancestor_id, max_paths) - Find all paths from a person to a specific ancestor (parent links only)
  - Parameters:
    - start_person_id (string) - GEDCOM person ID to start from
    - ancestor_id (string) - GEDCOM person ID of the ancestor to search for
    - max_paths (integer) - Maximum number of paths to return (default: 10)

## Enhanced Search Tools:
- **fuzzy_search_person**(name, threshold, max_results) - Search for persons with fuzzy name matching
  - Parameters:
    - name (string) - Search term to match against person names
    - threshold (integer) - Minimum similarity score (0-100, default: 80)
    - max_results (integer) - Maximum number of results to return (default: 50)

## Data Management Tools:
- **update_person**(person_id, name, gender, birth_date, birth_place, death_date, death_place) - Updates details for an existing person
  - Parameters:
    - person_id (string) - GEDCOM person ID (e.g., '@I1@', '@I123@')
    - name (string, optional) - New full name for the person
    - gender (string, optional) - New gender ('M' for male, 'F' for female)
    - birth_date (string, optional) - New birth date
    - birth_place (string, optional) - New birth place
    - death_date (string, optional) - New death date
    - death_place (string, optional) - New death place
- **find_person_families**(person_id) - Finds families a person is associated with (as a spouse or child)
  - Parameters: person_id (string) - GEDCOM person ID (e.g., '@I1@', '@I123@')
- **remove_child_from_family**(child_id, family_id) - Removes link between a child and their family
  - Parameters:
    - child_id (string) - GEDCOM person ID for the child
    - family_id (string) - GEDCOM family ID (e.g., '@F1@', '@F123@')
- **remove_parent_from_family**(parent_id, family_id) - Removes link between a parent and their family
  - Parameters:
    - parent_id (string) - GEDCOM person ID for the parent
    - family_id (string) - GEDCOM family ID (e.g., '@F1@', '@F123@')
- **dissolve_marriage**(family_id) - Dissolves a marriage by removing spouse links from a family
  - Parameters: family_id (string) - GEDCOM family ID (e.g., '@F1@', '@F123@')
- **delete_person**(person_id) - Deletes a person and removes them from all family relationships
  - Parameters: person_id (string) - GEDCOM person ID (e.g., '@I1@', '@I123@')
- **update_event_details**(entity_id, event_type, new_date, new_place, old_date_to_match) - Updates date and/or place for an event associated with a person or family
  - Parameters:
    - entity_id (string) - GEDCOM entity ID (person '@I1@' or family '@F1@')
    - event_type (string) - Type of event to update (e.g., 'BIRT', 'DEAT', 'MARR')
    - new_date (string, optional) - New date for the event
    - new_place (string, optional) - New place for the event
    - old_date_to_match (string, optional) - Old date to match for identification
- **remove_event**(entity_id, event_type, date_to_match) - Removes an event from a person or family
  - Parameters:
    - entity_id (string) - GEDCOM entity ID (person '@I1@' or family '@F1@')
    - event_type (string) - Type of event to remove (e.g., 'BIRT', 'DEAT', 'MARR')
    - date_to_match (string, optional) - Date to match for identification
- **get_person_attributes**(person_id) - Returns a list of all attributes for a person
  - Parameters: person_id (string) - GEDCOM person ID (e.g., '@I1@', '@I123@')
- **update_person_attribute**(person_id, attribute_type, new_value, old_value_to_match) - Updates value of a person's attribute
  - Parameters:
    - person_id (string) - GEDCOM person ID (e.g., '@I1@', '@I123@')
    - attribute_type (string) - GEDCOM attribute tag (e.g., 'OCCU', 'RELI')
    - new_value (string) - New value for the attribute
    - old_value_to_match (string, optional) - Old value to match for identification
- **remove_person_attribute**(person_id, attribute_type, value_to_match) - Removes a specific attribute from a person
  - Parameters:
    - person_id (string) - GEDCOM person ID (e.g., '@I1@', '@I123@')
    - attribute_type (string) - GEDCOM attribute tag (e.g., 'OCCU', 'RELI')
    - value_to_match (string, optional) - Value to match for identification
- **batch_update_person_attributes**(updates) - Update multiple person attributes in a single operation
  - Parameters: updates (string) - JSON string with batch update operations
- **add_note_to_entity**(entity_id, note_text) - Adds a new note to a person or family. Create references to note entities. A new note is created
  - Parameters:
    - entity_id (string) - GEDCOM entity ID (person '@I1@' or family '@F1@')
    - note_text (string) - Text content of the note to add
- **delete_note_from_entity**(entity_id, note_starts_with, note_id) - Deletes an inline note from a person or family, or removes a reference to a note entity
  - Parameters:
    - entity_id (string) - GEDCOM entity ID (person '@I1@' or family '@F1@')
    - note_starts_with (string, optional) - Text that the note starts with (for identification)
    - note_id (string, optional) - GEDCOM note ID (e.g., '@N1@', '@N123@')
- **delete_note_entity**(note_id) - Deletes a note entity by its ID and removes all references to it
  - Parameters: note_id (string) - GEDCOM note ID (e.g., '@N1@', '@N123@')
- **save_gedcom**(file_path) - Saves in-memory GEDCOM data back to a file
  - Parameters: file_path (string) - Path where to save the GEDCOM file

## Enhanced Features:
- **Comprehensive event decoding**: Birth, Death, Marriage, Baptism, Education, Occupation, etc.
- **Detailed attributes**: Religion, Nationality, Caste, Property, etc.
- **Rich metadata**: Notes, sources, dates, places, agencies, causes
- **Smart search**: Search across all entity types with flexible queries
- **Statistics**: Population analysis, surname frequency, date ranges
- **Multi-generation trees**: Configurable ancestor/descendant exploration

## Example workflows:

### Basic exploration:
1. load_gedcom(file_path="family.ged")
2. get_statistics() - Overview of file
3. find_person(name="Smith") - Find people by name (most basic search)
4. query_people_by_criteria(occupation="farmer") - Find all farmers in the database
5. get_person_details(person_id="@I123@") - Get full details for a specific person

### Practical research examples:
1. query_people_by_criteria(death_year_range="1855") - Find everyone who died in 1855
2. query_people_by_criteria(birth_place_contains="London", occupation="merchant") - Find merchants born in London
3. query_people_by_criteria(gender="F", has_children=True) - Find women who had children
4. query_people_by_criteria(is_living=True) - Find all living people

### Deep genealogy research:
1. get_ancestors(person_id="@I123@", generations=4)
2. get_events(person_id="@I123@") - All life events
3. get_notes(entity_id="@I123@") - Research notes
4. get_sources(entity_id="@I123@") - Documentation

### Place and event research:
1. gedcom_search(query="London", search_type="places")
2. query_people_by_criteria(birth_place_contains="London") - Find people born in London
3. get_places(query="England")"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GEDCOM MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="streamable-http",
        help="Transport method for the MCP server (default: streamable-http)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for streamable-http transport (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for streamable-http transport (default: 8080)",
    )

    args = parser.parse_args()

    if args.transport == "stdio":
        # Run server with stdio transport
        mcp.run(transport="stdio")
    else:
        # Run server with streamable_http transport
        mcp.run(transport="http", host=args.host, port=args.port)

# For compatibility with the __init__.py file
app = mcp
