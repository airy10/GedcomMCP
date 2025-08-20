#!/usr/bin/env python3

import argparse
import logging
import sys
from typing import Any, Dict, List, Optional, Set
from pathlib import Path
from datetime import datetime
import json
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
    ImageContent
)
from pydantic import BaseModel, Field
from functools import total_ordering
from dataclasses import dataclass, field
import time
import re
from typing import Optional, Tuple, Dict, Any

# Try to import unidecode for text normalization
try:
    from unidecode import unidecode
    UNIDECODE_AVAILABLE = True
except ImportError:
    UNIDECODE_AVAILABLE = False

# Import our new genealogy date utilities
try:
    from .gedcom_date_utils import parse_genealogy_date, validate_date_consistency, get_date_certainty_level, GenealogyDate
    DATE_UTILS_AVAILABLE = True
except ImportError:
    DATE_UTILS_AVAILABLE = False
    print("Warning: gedcom_date_utils not found. Date parsing enhancements will not be available.")

# Import our new genealogy name utilities
try:
    from .gedcom_name_utils import parse_genealogy_name, normalize_name, find_name_variants, GenealogyName
    NAME_UTILS_AVAILABLE = True
except ImportError:
    NAME_UTILS_AVAILABLE = False
    print("Warning: gedcom_name_utils not found. Name parsing enhancements will not be available.")

# Import our new genealogy place utilities
try:
    from .gedcom_place_utils import normalize_place_name, extract_geographic_hierarchy, NormalizedPlace
    PLACE_UTILS_AVAILABLE = True
except ImportError:
    PLACE_UTILS_AVAILABLE = False
    print("Warning: gedcom_place_utils not found. Place normalization enhancements will not be available.")

# Try to import GEDCOM parser
try:
    from gedcom.parser import Parser
    from gedcom.element.individual import IndividualElement
    from gedcom.element.family import FamilyElement
    from gedcom.element.object import ObjectElement
except ImportError:
    print("Error: python-gedcom library not found. Please install it with: pip install python-gedcom")
    sys.exit(1)


# Suppress websockets deprecation warning
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets.legacy")

# Import our modularized components
from .gedcom_context import GedcomContext, get_gedcom_context, _rebuild_lookups
from .gedcom_models import PersonDetails, PersonRelationships, NodePriority
from .gedcom_data_access import (
    get_person_details_internal, find_person_by_name, _get_relationships_internal, 
    _get_events_internal, decode_event_details, _get_places_internal, _get_notes_internal, _get_sources_internal,
    search_gedcom, _get_timeline_internal, _extract_person_details, _get_person_relationships_internal, load_gedcom_file, save_gedcom_file, _get_person_attributes_internal
)
from .gedcom_data_management import (
    _add_person_internal, _create_marriage_internal, _add_child_to_family_internal,
    _remove_child_from_family_internal, _remove_parent_from_family_internal,
    _remove_parents_internal, _update_event_details_internal,
    _remove_event_internal, _add_note_to_entity_internal,
    _create_source_internal, _delete_note_entity_internal, _new_empty_gedcom_internal,
    _update_person_attribute_internal, _update_person_details_internal
)
from .gedcom_search import (
    _dijkstra_bidirectional_search, _get_person_neighbors_lazy, _get_person_neighbors_lazy_reverse,
    _generate_relationship_chain_lazy, _correct_relationship_direction, _generate_relationship_description,
    _format_relationship_with_gender, _format_relationship_description,
    _find_shortest_relationship_path_internal, _find_all_relationship_paths_internal, _find_all_paths_to_ancestor_internal
)
from .gedcom_utils import (
    normalize_string, _get_gedcom_tag_from_event_type, _get_gedcom_tag_from_attribute_type,
    extract_birth_year, _extract_year_from_genealogy_date, _normalize_genealogy_name,
    _normalize_genealogy_date, _normalize_genealogy_place, _extract_year_from_date,
    _matches_criteria
)
from .gedcom_analysis import (
    _get_statistics_internal, _get_timeline_internal, _get_ancestors_internal, _get_descendants_internal,
    _get_family_tree_summary_internal, _get_surname_statistics_internal, _get_date_range_analysis_internal,
    _find_potential_duplicates_internal, get_common_ancestors_internal,
    _get_attribute_statistics_internal # Added this import
)
from .gedcom_constants import EVENT_TYPES, ATTRIBUTE_TYPES

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the FastMCP server instance
mcp = FastMCP("gedcom-mcp-server")

# Register tools with FastMCP
@mcp.tool()
async def add_person(name: str, gender: str, ctx: Context) -> str:
    """Adds a new person to the GEDCOM data."""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
    
    person_id = _add_person_internal(gedcom_ctx, name, gender)
    _rebuild_lookups(gedcom_ctx)
    return f"Successfully added person {name} with ID {person_id}"

@mcp.tool()
async def create_marriage(husband_id: str, wife_id: str, ctx: Context) -> str:
    """Creates a marriage between two people."""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
    
    family_id = _create_marriage_internal(gedcom_ctx, husband_id, wife_id)
    _rebuild_lookups(gedcom_ctx)
    return f"Successfully created marriage between {husband_id} and {wife_id} in family {family_id}"

@mcp.tool()
async def add_child_to_family(child_id: str, family_id: str, ctx: Context) -> str:
    """Adds a child to a family."""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
    
    _add_child_to_family_internal(gedcom_ctx, child_id, family_id)
    _rebuild_lookups(gedcom_ctx)
    return f"Successfully added child {child_id} to family {family_id}"

@mcp.tool()
async def load_gedcom(file_path: str, ctx: Context) -> str:
    """Load and parse a GEDCOM file"""
    gedcom_ctx = get_gedcom_context(ctx)
    success = load_gedcom_file(file_path, gedcom_ctx)
    # Ensure the file path is stored in the context
    if success:
        gedcom_ctx.gedcom_file_path = file_path
    # Note: With the global session store, we don't need to explicitly store the context back
    # as it's already referenced in the global store
    if success:
        return f"Successfully loaded GEDCOM file: {file_path}"
    else:
        return f"Failed to load GEDCOM file: {file_path}"



@mcp.tool()
async def find_person(name: str, ctx: Context) -> str:
    """Find persons matching a name"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
        
    persons = find_person_by_name(name, gedcom_ctx)
    if persons:
        persons_json = [person.model_dump() for person in persons]
        return str(persons_json)
    else:
        return f"No persons found matching: {name}"

@mcp.tool()
async def get_occupation(person_id: str, ctx: Context) -> str:
    """Get the occupation of a person"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
        
    person = get_person_details_internal(person_id, gedcom_ctx)
    if person:
        if person.occupation:
            return f"Occupation for {person.name} ({person.id}): {person.occupation}"
        else:
            return f"No occupation recorded for {person.name} ({person.id})"
    else:
        return f"Person not found: {person_id}"

@mcp.tool()
async def get_note_by_id(note_id: str, ctx: Context) -> str:
    """Get the full text content of a specific note by its ID (e.g., @N176@)"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
    
    notes = _get_notes_internal(note_id, gedcom_ctx)
    if notes:
        note = notes[0]  # Should only be one note for a specific ID
        result = f"Note {note_id}:\n\n"
        result += f"Text: {note.get('text', 'No text')}\n"
        result += f"Source: {note.get('source', 'Unknown')}\n"
        if note.get('date'):
            result += f"Date: {note['date']}\n"
        return result
    else:
        return f"Note not found: {note_id}"



@mcp.tool()
async def get_relationships(person_id: str, ctx: Context) -> str:
    """Get family relationships for a person"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
        
    relationships = _get_relationships_internal(person_id, gedcom_ctx)
    if relationships:
        return str(relationships)
    else:
        return f"No relationships found for person: {person_id}"

@mcp.tool()
async def get_events(person_id: str, ctx: Context) -> str:
    """Retrieve events for a person or family"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
        
    events = _get_events_internal(person_id, gedcom_ctx)
    if events:
        return str(events)
    else:
        return f"No events found for person: {person_id}"

@mcp.tool()
async def get_places(ctx: Context, query: Optional[str] = None) -> str:
    """Get information about places mentioned in the GEDCOM file"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
        
    places = _get_places_internal(query, gedcom_ctx)
    if places:
        return str(places)
    else:
        return "No places found" if not query else f"No places found matching: {query}"

@mcp.tool()
async def get_timeline(person_id: str, ctx: Context) -> str:
    """Generate a chronological timeline of events for a person"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
        
    timeline = _get_timeline_internal(person_id, gedcom_ctx)
    if timeline:
        return str(timeline)
    else:
        return f"No timeline found for person: {person_id}"

@mcp.tool()
async def get_notes(entity_id: str, ctx: Context) -> str:
    """Get all notes for a person or family"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
        
    notes = _get_notes_internal(entity_id, gedcom_ctx)
    if notes:
        result = f"Notes for entity {entity_id}:\n\n"
        for i, note in enumerate(notes, 1):
            result += f"Note {i}:\n"
            result += f"Text: {note.get('text', 'No text')}\n"
            result += f"Source: {note.get('source', 'Unknown')}\n"
            if note.get('date'):
                result += f"Date: {note['date']}\n"
            if note.get('reference'):
                result += f"Reference: {note['reference']}\n"
            result += "\n"
        return result
    else:
        return f"No notes found for entity: {entity_id}\n"

@mcp.tool()
async def get_sources(entity_id: str, ctx: Context) -> str:
    """Get all sources for a person or family"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
        
    sources = _get_sources_internal(entity_id, gedcom_ctx)
    if sources:
        return str(sources)
    else:
        return f"No sources found for entity: {entity_id}"

@mcp.tool()
async def gedcom_search(query: str, ctx: Context, search_type: str = "all") -> str:
    """Search across the GEDCOM file for people, places, events, etc.
    
    Args:
        query: The search term
        search_type: Type of search - 'all', 'people', 'places', 'events', 'families'
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
        
    results = search_gedcom(query, gedcom_ctx, search_type)
    if any(results.values()):
        return str(results)
    else:
        return f"No results found for query: {query}"

@mcp.tool()
async def get_statistics(ctx: Context) -> str:
    """Get comprehensive statistics about the GEDCOM file"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
        
    stats = _get_statistics_internal(gedcom_ctx)
    if stats:
        return str(stats)
    else:
        return "No statistics available"

# New tool starts here
@mcp.tool()
async def get_attribute_statistics(attribute_type: str, ctx: Context) -> str:
    """
    Retrieves statistics for a given GEDCOM attribute (e.g., 'OCCU' or 'Occupation')
    across all individuals and families in the loaded GEDCOM file.

    Args:
        attribute_type: The GEDCOM attribute tag (e.g., 'OCCU') or its human-readable
                        name (e.g., 'Occupation').
    Returns:
        A JSON string representing a dictionary where keys are attribute values
        and values are their counts. Returns an error message if no GEDCOM
        file is loaded or if an invalid/unsupported attribute type is provided.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."

    try:
        stats = _get_attribute_statistics_internal(gedcom_ctx, attribute_type)
        # Check if the internal function returned an error dictionary
        if "error" in stats:
            return stats["error"]
        return json.dumps(stats, indent=2)
    except Exception as e:
        return f"Error getting attribute statistics for '{attribute_type}': {e}"
# New tool ends here

@mcp.tool()
async def get_ancestors(person_id: str, ctx: Context, generations: int = 3, format: str = 'nested', page: int = 1, page_size: int = 100) -> str:
    """Get ancestors of a person for specified number of generations, with optional formatting and pagination.
    
    Args:
        person_id: The ID of the person to get ancestors for.
        generations: The number of generations to retrieve.
        format: The format of the output ('nested' for tree structure, 'flat' for a list with levels).
        page: Page number (starting from 1) for 'flat' format.
        page_size: Number of entries per page (default 100, max 500) for 'flat' format.
    
    Returns:
        JSON with ancestors data.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
    
    try:
        ancestors = _get_ancestors_internal(person_id, gedcom_ctx, generations=generations, format=format)
        
        if format == 'flat':
            # Apply pagination for flat format
            if page < 1:
                return "Page number must be 1 or greater"
            if page_size < 1 or page_size > 500:
                return "Page size must be between 1 and 500"
            
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
                "ancestors": [{
                    "id": ancestor_id,
                    "level": level
                } for ancestor_id, level in page_data]
            }
            return json.dumps(result, indent=2)
        else:
            return str(ancestors)
    except Exception as e:
        return f"Error getting ancestors: {e}"

@mcp.tool()
async def get_family_tree_summary(person_id: str, ctx: Context) -> str:
    """Get a concise family tree summary showing parents, spouse(s), and children"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
    
    try:
        result = _get_family_tree_summary_internal(person_id, gedcom_ctx)
        return result
    except Exception as e:
        return f"Error getting family tree summary: {e}"

@mcp.tool()
async def get_surname_statistics(ctx: Context, surname: str = None) -> str:
    """Get statistics about surnames in the GEDCOM file"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
    
    try:
        result = _get_surname_statistics_internal(gedcom_ctx, surname)
        return result
    except Exception as e:
        return f"Error getting surname statistics: {e}"

@mcp.tool()
async def get_date_range_analysis(ctx: Context) -> str:
    """Analyze the date ranges in the GEDCOM file to understand the time period covered"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
    
    try:
        result = _get_date_range_analysis_internal(gedcom_ctx)
        return result
    except Exception as e:
        return f"Error analyzing date ranges: {e}"

@mcp.tool()
async def find_potential_duplicates(ctx: Context) -> str:
    """Find potential duplicate people based on similar names and dates"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
    
    try:
        result = _find_potential_duplicates_internal(gedcom_ctx)
        return result
    except Exception as e:
        return f"Error finding duplicates: {e}"

@mcp.tool()
async def get_descendants(person_id: str, ctx: Context, generations: int = 3, format: str = 'nested', page: int = 1, page_size: int = 100) -> str:
    """Get descendants of a person for specified number of generations, with optional formatting and pagination.
    
    Args:
        person_id: The ID of the person to get descendants for.
        generations: The number of generations to retrieve.
        format: The format of the output ('nested' for tree structure, 'flat' for a list with levels).
        page: Page number (starting from 1) for 'flat' format.
        page_size: Number of entries per page (default 100, max 500) for 'flat' format.
    
    Returns:
        JSON with descendants data.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
    
    try:
        descendants = _get_descendants_internal(person_id, gedcom_ctx, generations=generations, format=format)
        
        if format == 'flat':
            # Apply pagination for flat format
            if page < 1:
                return "Page number must be 1 or greater"
            if page_size < 1 or page_size > 500:
                return "Page size must be between 1 and 500"
            
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
                "descendants": [{
                    "id": descendant_id,
                    "level": level
                } for descendant_id, level in page_data]
            }
            return json.dumps(result, indent=2)
        else:
            return str(descendants)
    except Exception as e:
        return f"Error getting descendants: {e}"





@mcp.tool()
async def find_all_paths_to_ancestor(start_person_id: str, ancestor_id: str, ctx: Context, max_paths: int = 10) -> str:
    """Find all paths from a person to a specific ancestor, following only parent relationships.
    
    Args:
        start_person_id: The ID of the person to start from
        ancestor_id: The ID of the ancestor to search for
        max_paths: Maximum number of paths to return (default: 10)
        
    Returns:
        JSON with all paths from start_person_id to ancestor_id
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
    
    try:
        paths = _find_all_paths_to_ancestor_internal(start_person_id, ancestor_id, gedcom_ctx, max_paths)
        
        if not paths:
            return f"No paths found from {start_person_id} to ancestor {ancestor_id}"
        
        # Enrich paths with person names
        enriched_paths = []
        for path in paths:
            enriched_path = []
            for person_id in path:
                person = get_person_details_internal(person_id, gedcom_ctx)
                person_name = person.name if person else "Unknown"
                enriched_path.append({
                    "id": person_id,
                    "name": person_name
                })
            enriched_paths.append(enriched_path)
        
        result = {
            "start_person": {
                "id": start_person_id,
                "name": get_person_details_internal(start_person_id, gedcom_ctx).name
            },
            "ancestor": {
                "id": ancestor_id,
                "name": get_person_details_internal(ancestor_id, gedcom_ctx).name
            },
            "total_paths": len(paths),
            "paths": enriched_paths
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return f"Error finding paths to ancestor: {e}\n{traceback.format_exc()}"

@mcp.tool()
async def get_persons_batch(person_ids: str, ctx: Context, include_fields: str = "basic") -> str:
    """Get details for one or multiple persons by their IDs. This is the primary tool for retrieving person details.
    
    Args:
        person_ids: Comma-separated list of person IDs (e.g., "@I1@,@I2@,@I3@") or a single person ID.
        include_fields: Fields to include - "basic", "extended", "full", or custom comma-separated list
                       - basic: id, name, birth_date, death_date
                       - extended: basic + birth_place, death_place, gender, occupation
                       - full: all available fields including relationships
                       - custom: specify fields like "id,name,occupation,parents"
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
    
    try:
        # Parse the person IDs
        ids = [pid.strip() for pid in person_ids.split(',') if pid.strip()]
        if not ids:
            return "No valid person IDs provided"
        
        # Define field sets
        basic_fields = {"id", "name", "birth_date", "death_date"}
        extended_fields = basic_fields | {"birth_place", "death_place", "gender", "occupation"}
        full_fields = {"id", "name", "birth_date", "birth_place", "death_date", "death_place", 
                      "gender", "occupation", "parents", "spouses", "children"}
        
        # Determine which fields to include
        if include_fields.lower() == "basic":
            fields_to_include = basic_fields
        elif include_fields.lower() == "extended":
            fields_to_include = extended_fields
        elif include_fields.lower() == "full":
            fields_to_include = full_fields
        else:
            # Custom field list
            custom_fields = {field.strip() for field in include_fields.split(',') if field.strip()}
            # Validate custom fields against available fields
            valid_fields = full_fields
            fields_to_include = custom_fields & valid_fields
            if not fields_to_include:
                return f"No valid fields specified. Available fields: {', '.join(sorted(valid_fields))}"
        
        # Collect person details
        persons_data = []
        not_found = []
        
        for person_id in ids:
            person = get_person_details_internal(person_id, gedcom_ctx)
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
                        elif value is not None and value != "":  # Only include non-empty values
                            person_data[field] = value
                
                persons_data.append(person_data)
            else:
                not_found.append(person_id)
        
        # Format the result
        result = "{\n"
        result += f'  "total_requested": {len(ids)},\n'
        result += f'  "found": {len(persons_data)},\n'
        result += f'  "not_found": {len(not_found)},\n'
        result += f'  "fields_included": {sorted(fields_to_include)},\n'
        
        if not_found:
            result += f'  "not_found_ids": {not_found},\n'
        
        result += '  "persons": [\n'
        
        for i, person_data in enumerate(persons_data):
            result += '    {\n'
            for j, (key, value) in enumerate(person_data.items()):
                if isinstance(value, list):
                    result += f'      "{key}": {value}'
                else:
                    result += f'      "{key}": "{value}"'
                if j < len(person_data) - 1:
                    result += ','
                result += '\n'
            result += '    }'
            if i < len(persons_data) - 1:
                result += ','
            result += '\n'
        
        result += '  ]\n'
        result += '}'
        
        return result
    
    except Exception as e:
        return f"Error getting persons batch: {e}"


@mcp.tool()
async def query_people_by_criteria(ctx: Context, filters: str = "", page: int = 1, page_size: int = 100) -> str:
    """Query people using flexible criteria with pagination
    
    Args:
        filters: JSON string with filter criteria. Examples:
                '{"occupation": "farmer"}' - People with specific occupation
                '{"birth_year_range": [1800, 1850]}' - Born between years
                '{"birth_place_contains": "London"}' - Birth place contains text
                '{"has_children": true}' - People with children
                '{"death_year": null}' - Living people (no death date)
                '{"gender": "M"}' - Male individuals
                '{"name_contains": "Smith"}' - Name contains text
                Multiple criteria: '{"occupation": "farmer", "birth_year_range": [1800, 1900], "gender": "M"}'
        page: Page number (starting from 1)
        page_size: Number of people per page (default 100, max 500)
    
    Available filter criteria:
        - occupation: exact match or null
        - birth_year_range: [min_year, max_year] or single year
        - death_year_range: [min_year, max_year] or single year or null
        - birth_place_contains: substring match (case insensitive)
        - death_place_contains: substring match (case insensitive)
        - name_contains: substring match in name (case insensitive)
        - gender: "M", "F", or null
        - has_children: true/false
        - has_parents: true/false
        - has_spouses: true/false
        - is_living: true (no death date), false (has death date)
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
    
    # Validate parameters
    if page < 1:
        return "Page number must be 1 or greater"
    if page_size < 1 or page_size > 500:
        return "Page size must be between 1 and 500"
    
    try:
        # Parse filters
        filter_criteria = {}
        if filters.strip():
            try:
                filter_criteria = json.loads(filters)
            except json.JSONDecodeError:
                return f"Invalid JSON in filters parameter: {filters}"
        
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
        
        # Format result
        result = "{\n"
        result += f'  "filters_applied": {json.dumps(filter_criteria)},\n'
        result += f'  "page": {page},\n'
        result += f'  "page_size": {page_size},\n'
        result += f'  "total_pages": {total_pages},\n'
        result += f'  "total_count": {total_count},\n'
        result += f'  "has_next_page": {page < total_pages},\n'
        result += f'  "has_previous_page": {page > 1},\n'
        result += f'  "current_page_count": {len(page_people)},\n'
        result += '  "people": [\n'
        
        for i, person in enumerate(page_people):
            result += '    {\n'
            result += f'      "id": "{person.id}",\n'
            result += f'      "name": "{person.name}",\n'
            if person.birth_date:
                result += f'      "birth_date": "{person.birth_date}",\n'
            if person.birth_place:
                result += f'      "birth_place": "{person.birth_place}",\n'
            if person.death_date:
                result += f'      "death_date": "{person.death_date}",\n'
            if person.death_place:
                result += f'      "death_place": "{person.death_place}",\n'
            if person.gender:
                result += f'      "gender": "{person.gender}",\n'
            if person.occupation:
                result += f'      "occupation": "{person.occupation}",\n'
            result += f'      "has_children": {len(person.children) > 0},\n'
            result += f'      "has_parents": {len(person.parents) > 0},\n'
            result += f'      "has_spouses": {len(person.spouses) > 0},\n'
            result += f'      "is_living": {person.death_date is None}\n'
            result += '    }'
            if i < len(page_people) - 1:
                result += ','
            result += '\n'
        
        result += '  ]\n'
        result += '}'
        
        return result
    
    except Exception as e:
        return f"Error querying people by criteria: {e}"

@mcp.tool()
async def get_all_entity_ids(entity_type: str, ctx: Context, page: int = 1, page_size: int = 100) -> str:
    """Get all IDs for a specific entity type (person, family, place, note, source) with pagination.

    Args:
        entity_type: The type of entity to retrieve IDs for ('person', 'family', 'place', 'note', 'source').
        page: Page number (starting from 1).
        page_size: Number of IDs per page (default 100, max 1000 for person/family, max 500 for others).
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."

    all_ids = []
    total_count = 0
    max_page_size = 1000 # Default max for person/family

    try:
        if entity_type == 'person':
            all_ids = list(gedcom_ctx.individual_lookup.keys())
        elif entity_type == 'family':
            all_ids = list(gedcom_ctx.family_lookup.keys())
        elif entity_type == 'note':
            all_ids = list(gedcom_ctx.note_lookup.keys())
            max_page_size = 500 # Max page size for notes
        elif entity_type == 'source':
            all_ids = list(gedcom_ctx.source_lookup.keys())
            max_page_size = 500 # Max page size for sources
        elif entity_type == 'place':
            # For places, we need to use the internal function to get unique places
            # and then extract their names/IDs.
            # _get_places_internal returns a list of dicts, each with a 'name' key
            places_data = _get_places_internal(query=None, gedcom_ctx=gedcom_ctx)
            all_ids = [place['name'] for place in places_data]
            max_page_size = 500 # Max page size for places
        else:
            return "Error: Invalid entity_type. Must be 'person', 'family', 'place', 'note', or 'source'."

        # Validate parameters
        if page < 1:
            return "Page number must be 1 or greater"
        if page_size < 1 or page_size > max_page_size:
            return f"Page size must be between 1 and {max_page_size}"

        all_ids.sort() # Sort for consistent ordering
        total_count = len(all_ids)
        total_pages = (total_count + page_size - 1) // page_size # Ceiling division
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
            f"{entity_type}_ids": page_ids # Dynamic key
        }
        
        import json
        return json.dumps(result, indent=2)

    except Exception as e:
        return f"Error getting all {entity_type} IDs: {e}"

@mcp.tool()
async def find_shortest_relationship_path(person1_id: str, person2_id: str, ctx: Context, allowed_relationships: str = "default", max_distance: int = 30, exclude_initial_spouse_children: bool = False, min_distance: int = 0) -> str:
    """Find the shortest relationship path between two people
    
    Args:
        person1_id: First person's ID
        person2_id: Second person's ID  
        allowed_relationships: Comma-separated list of allowed relationship types:
                              - "spouse" (marriage relationships)
                              - "mother" (mother-child relationships only)
                              - "father" (father-child relationships only)  
                              - "parents" (both mother and father relationships)
                              - "children" (parent-child relationships, person -> children)
                              - "blood" (both parents and children, no spouse)
                              - "sibling" (siblings through common parents)
                              - "all" (all relationship types)
                              - "default" (spouse, parents, children - typical family relationships)
                              Examples: "parents", "blood", "parents,sibling", "all"
        max_distance: Maximum relationship distance to search (default: 30)
                     Stops searching if no path found within this distance
                     If path exists but exceeds max_distance, returns "path too long" result
        exclude_initial_spouse_children: If True, excludes spouse and children links for the two initial people
                                       This allows finding relationships like cousins without considering direct marriage/children
                                       (default: False)
        min_distance: Minimum relationship distance required (default: 0)
                     If > 0, will find the shortest path that is at least this distance long
                     Useful for finding distant relationships while avoiding immediate family
    
    Returns:
        JSON with shortest path, relationship chain, and distance
        If path exceeds max_distance, returns result with "path_too_long": true
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
    
    # Validate that both people exist
    person1 = get_person_details_internal(person1_id, gedcom_ctx)
    person2 = get_person_details_internal(person2_id, gedcom_ctx)
    
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
            allowed = {"parent", "spouse", "child"}  # Default: spouse, parents, children
        elif allowed_relationships_lower == "blood":
            allowed = {"parent", "child"}  # Blood relationships only
        elif allowed_relationships_lower == "parents":
            allowed = {"parent"}  # Parents only (both mother and father)
        elif allowed_relationships_lower == "children":
            allowed = {"child"}  # Children only
        else:
            # Parse comma-separated list and expand special types
            raw_relationships = {rel.strip().lower() for rel in allowed_relationships.split(",")}
            allowed = set()
            
            for rel in raw_relationships:
                if rel == "spouse":
                    allowed.add("spouse")
                elif rel == "mother":
                    allowed.add("mother")  # Will be handled specially in neighbor function
                elif rel == "father":
                    allowed.add("father")  # Will be handled specially in neighbor function
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
        logger.info(f"PERF: Relationship parsing took {parse_time:.3f}s, allowed: {allowed}")
        
        # Call the internal function instead of duplicating the logic
        result = _find_shortest_relationship_path_internal(person1_id, person2_id, allowed_relationships, gedcom_ctx, max_distance, exclude_initial_spouse_children, min_distance)
        return result
        
    except Exception as e:
        return f"Error finding relationship path: {e}"




@mcp.tool()
async def find_all_relationship_paths(person1_id: str, person2_id: str, ctx: Context, allowed_relationships: str = "all", max_distance: int = 15, max_paths: int = 10) -> str:
    """Find all relationship paths between two people, sorted by distance
    
    Args:
        person1_id: First person's ID
        person2_id: Second person's ID  
        allowed_relationships: Comma-separated list of allowed relationship types:
                              - "parent" (parent-child relationships)
                              - "spouse" (marriage relationships)
                              - "sibling" (siblings through common parents)
                              - "all" (default: all relationship types)
        max_distance: Maximum relationship distance to search (default: 15)
        max_paths: Maximum number of paths to return (default: 10)
    
    Returns:
        JSON with all paths found, sorted from shortest to longest
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
    
    # Validate that both people exist
    person1 = get_person_details_internal(person1_id, gedcom_ctx)
    person2 = get_person_details_internal(person2_id, gedcom_ctx)
    
    if not person1:
        return f"Person not found: {person1_id}"
    if not person2:
        return f"Person not found: {person2_id}"
    
    if person1_id == person2_id:
        return f'{"paths": [{"path": ["{person1_id}"], "distance": 0, "relationship_chain": ["self"], "description": "Same person"}], "total_paths": 1}'
    
    # Validate parameters
    if max_distance < 1:
        max_distance = 15
    if max_paths < 1:
        max_paths = 10
    
    try:
        # Call the internal function instead of duplicating the logic
        result = _find_all_relationship_paths_internal(person1_id, person2_id, allowed_relationships, gedcom_ctx, max_distance, max_paths)
        return result
    except Exception as e:
        import traceback
        return f"Error finding all relationship paths: {e}\n{traceback.format_exc()}"

@mcp.tool()
async def get_common_ancestors(person_ids: str, ctx: Context, max_level: int = 20) -> str:
    """Find common ancestors for a list of people
    
    Args:
        person_ids: Comma-separated list of person IDs (e.g., "@I1@,@I2@,@I3@")
        max_level: Maximum ancestor level to search (default: 20)
    
    Returns:
        JSON with common ancestors, their levels for each person, and statistics
    """
    gedcom_ctx = get_gedcom_context(ctx)
    try:
        # Parse person IDs
        person_id_list = [pid.strip() for pid in person_ids.split(",") if pid.strip()]
        
        result = get_common_ancestors_internal(person_id_list, gedcom_ctx, max_level)
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return f"Error finding common ancestors: {e}\n{traceback.format_exc()}"



@mcp.tool()
async def update_person(person_id: str, ctx: Context, name: str = None, gender: str = None, birth_date: str = None, birth_place: str = None, death_date: str = None, death_place: str = None) -> str:
    """Updates the details for an existing person.

    Args:
        person_id: The ID of the person to update (e.g., "@I123@").
        name: The new full name. Only updated if explicitly provided (not None).
        gender: The new gender ('M' or 'F'). Only updated if explicitly provided (not None).
        birth_date: The new birth date. Only updated if explicitly provided (not None).
        birth_place: The new birth place. Only updated if explicitly provided (not None).
        death_date: The new death date. Only updated if explicitly provided (not None).
        death_place: The new death place. Only updated if explicitly provided (not None).

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser or person_id not in gedcom_ctx.individual_lookup:
        return f"Error: Person with ID {person_id} not found."

    try:
        # Update name and gender using the new internal function
        if name is not None or gender is not None:
            result = _update_person_details_internal(gedcom_ctx, person_id, name, gender)
            if "Error" in result:
                return result

        # Update birth event
        if birth_date is not None or birth_place is not None:
            result = _update_person_details_internal(gedcom_ctx, person_id, 'BIRT', birth_date, birth_place)
            if "Error" in result:
                return result

        # Update death event
        if death_date is not None or death_place is not None:
            result = _update_person_details_internal(gedcom_ctx, person_id, 'DEAT', death_date, death_place)
            if "Error" in result:
                return result

        # Clear relevant caches and rebuild lookups
        gedcom_ctx.clear_caches()
        _rebuild_lookups(gedcom_ctx)

        return f"Successfully updated details for person {person_id}."
    except Exception as e:
        return f"Error updating person {person_id}: {e}"

@mcp.tool()
async def find_person_families(person_id: str, ctx: Context) -> str:
    """Finds the families a person is associated with (as a spouse or child).

    Args:
        person_id: The ID of the person to look up.

    Returns:
        A JSON string detailing the families where the person is a spouse (FAMS)
        and where they are a child (FAMC).
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser or person_id not in gedcom_ctx.individual_lookup:
        return f"Error: Person with ID {person_id} not found."

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

    return str({
        "person_id": person_id,
        "families_as_spouse": fams,
        "family_as_child": famc
    })


@mcp.tool()
async def remove_child_from_family(child_id: str, family_id: str, ctx: Context) -> str:
    """Removes the link between a child and their family.

    Args:
        child_id: The ID of the child.
        family_id: The ID of the family from which to remove the child.

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser or child_id not in gedcom_ctx.individual_lookup:
        return f"Error: Child with ID {child_id} not found."
    if family_id not in gedcom_ctx.family_lookup:
        return f"Error: Family with ID {family_id} not found."

    result = _remove_child_from_family_internal(gedcom_ctx, child_id, family_id)
    
    # If successful, clear caches and rebuild lookups
    if result.startswith("Successfully"):
        gedcom_ctx.clear_caches()
        _rebuild_lookups(gedcom_ctx)
    
    return result





@mcp.tool()
async def remove_parents(person_id: str, ctx: Context) -> str:
    """Removes a person's parents by removing the person from their family of origin.
    
    This function takes a person's FAMC value (family of origin) and calls the internal version
    of remove_child_from_family with that information.
    
    Args:
        person_id: The ID of the person whose parents should be removed.

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser or person_id not in gedcom_ctx.individual_lookup:
        return f"Error: Person with ID {person_id} not found."

    result = _remove_parents_internal(gedcom_ctx, person_id)
    
    # If successful, clear caches and rebuild lookups
    if result.startswith("Successfully"):
        gedcom_ctx.clear_caches()
        _rebuild_lookups(gedcom_ctx)
    
    return result





@mcp.tool()
async def remove_parent_from_family(parent_id: str, family_id: str, ctx: Context) -> str:
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
        return f"Error: Parent with ID {parent_id} not found."
    if family_id not in gedcom_ctx.family_lookup:
        return f"Error: Family with ID {family_id} not found."

    result = _remove_parent_from_family_internal(gedcom_ctx, parent_id, family_id)
    
    # If successful, clear caches and rebuild lookups
    if result.startswith("Successfully"):
        gedcom_ctx.clear_caches()
        _rebuild_lookups(gedcom_ctx)
    
    return result

@mcp.tool()
async def dissolve_marriage(family_id: str, ctx: Context) -> str:
    """Dissolves a marriage by removing the spouse links from a family.

    This does not delete the family record itself, in case children are attached.

    Args:
        family_id: The ID of the family where the marriage exists.

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser or family_id not in gedcom_ctx.family_lookup:
        return f"Error: Family with ID {family_id} not found."

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
            return f"Error: No spouses found in family {family_id} to dissolve."

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
async def delete_person(person_id: str, ctx: Context) -> str:
    """Deletes a person and removes them from all family relationships.

    This is a destructive operation. It will remove the person and update
    any families they were a part of.

    Args:
        person_id: The ID of the person to delete.

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser or person_id not in gedcom_ctx.individual_lookup:
        return f"Error: Person with ID {person_id} not found."

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
        gedcom_ctx.gedcom_parser.get_root_element().get_child_elements().remove(person_element)

        # Remove from lookup
        del gedcom_ctx.individual_lookup[person_id]
        
        gedcom_ctx.clear_caches()
        return f"Successfully deleted person {person_id} and all related family links."
    except Exception as e:
        return f"Error deleting person {person_id}: {e}"

@mcp.tool()
async def update_event_details(entity_id: str, event_type: str, ctx: Context, new_date: str = None, new_place: str = None, old_date_to_match: str = None) -> str:
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
        return "Error: No GEDCOM file loaded."
    
    result = _update_event_details_internal(gedcom_ctx, entity_id, event_type, new_date, new_place, old_date_to_match)
    
    # If successful, clear caches and rebuild lookups
    if result.startswith("Successfully"):
        gedcom_ctx.clear_caches()
        _rebuild_lookups(gedcom_ctx)
    
    return result



@mcp.tool()
async def get_person_attributes(person_id: str, ctx: Context) -> str:
    """Retrieves all attributes for a person.
    Args:
        person_id (str): The ID of the person.
    Returns:
        dict: A dictionary of attributes.
    """
    try:
        gedcom_ctx = get_gedcom_context(ctx)
        attributes = _get_person_attributes_internal(person_id, gedcom_ctx)
        if attributes:
            return json.dumps({"attributes": attributes})
        return json.dumps({"error": f"Person with ID {person_id} not found or has no attributes."})
    except Exception as e:
        return json.dumps({"error": f"Error retrieving attributes: {e}"})

@mcp.tool()
async def update_person_attribute(person_id: str, attribute_tag: str, new_value: str, ctx: Context) -> str:
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
        result = _update_person_attribute_internal(gedcom_ctx, person_id, attribute_tag, new_value)
        if "Error" in result:
            return result

        # Clear caches and rebuild lookups after successful update
        gedcom_ctx.clear_caches()
        _rebuild_lookups(gedcom_ctx)
        
        return result
    except Exception as e:
        return f"Error updating attribute: {e}"

@mcp.tool()
async def remove_person_attribute(person_id: str, attribute_type: str, ctx: Context, value_to_match: str) -> str:
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
        return f"Error: Person with ID {person_id} not found."

    attribute_tag = _get_gedcom_tag_from_attribute_type(attribute_type)
    if not attribute_tag:
        return f"Error: Invalid attribute type '{attribute_type}'."

    try:
        print(f"DEBUG: gedcom_ctx in remove_person_attribute: {gedcom_ctx}")
        result = _remove_person_attribute_internal(gedcom_ctx, person_id, attribute_tag, value_to_match)
        if "Error" in result:
            return result
        gedcom_ctx.clear_caches()
        _rebuild_lookups(gedcom_ctx)
        return result
    except Exception as e:
        return f"Error removing attribute: {e}"

@mcp.tool()
async def create_source(title: str, ctx: Context, author: str = "", publication: str = "") -> str:
    """Creates a new source with a unique ID.
    
    Args:
        title: The title of the source.
        author: The author of the source (optional).
        publication: Publication information (optional).
        
    Returns:
        The ID of the newly created source.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "Error: No GEDCOM file loaded."
    
    try:
        source_id = _create_source_internal(gedcom_ctx, title, author, publication)
        _rebuild_lookups(gedcom_ctx)
        return f"Successfully created source with ID {source_id}"
    except Exception as e:
        return f"Error creating source: {e}"

@mcp.tool()
async def add_note_to_entity(entity_id: str, ctx: Context, note_text: str = None) -> str:
    """Adds a new note to a person or family. Creates note references, not inline notes.

    Args:
        entity_id: The ID of the person or family to add the note to.
        note_text: The full text of the note.

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "Error: No GEDCOM file loaded."

    result = _add_note_to_entity_internal(gedcom_ctx, entity_id, note_text)
    
    # If successful, clear caches and rebuild lookups
    if result.startswith("Successfully"):
        gedcom_ctx.clear_caches()
        _rebuild_lookups(gedcom_ctx)
    
    return result

@mcp.tool()
async def delete_note_entity(note_id: str, ctx: Context) -> str:
    """Deletes a note entity by its ID and removes all references to it.
    
    Args:
        note_id: The ID of the note to delete (e.g., '@N123@').

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "Error: No GEDCOM file loaded."
    
    if note_id not in gedcom_ctx.note_lookup:
        return f"Error: Note with ID {note_id} not found."

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
async def delete_note_from_entity(entity_id: str, ctx: Context, note_starts_with: str = None, note_id: str = None) -> str:
    """Deletes a note from a person or family.

    This function can either:
    1. Delete an inline note based on the beginning of its text
    2. Remove a reference to a note entity (but not delete the note entity itself)
    
    Args:
        entity_id: The ID of the person or family.
        note_starts_with: The first few words of an inline note to identify it.
        note_id: The ID of a note entity to remove the reference to (e.g., '@N123@').

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "Error: No GEDCOM file loaded."

    # Handle note reference removal
    if note_id:
        entity = gedcom_ctx.individual_lookup.get(entity_id) or gedcom_ctx.family_lookup.get(entity_id)
        if not entity:
            return f"Error: Entity with ID {entity_id} not found."
            
        if note_id not in gedcom_ctx.note_lookup:
            return f"Error: Note with ID {note_id} not found."

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
                return f"Error: No reference to note {note_id} found in {entity_id}."
        except Exception as e:
            return f"Error removing note reference: {e}"

    # Handle inline note deletion
    if note_starts_with:
        entity = gedcom_ctx.individual_lookup.get(entity_id) or gedcom_ctx.family_lookup.get(entity_id)
        if not entity:
            return f"Error: Entity with ID {entity_id} not found."

        try:
            note_to_delete = None
            # Find NOTE elements
            for note in entity.get_child_elements():
                if note.get_tag() == "NOTE":
                    note_value = note.get_value()
                    # Ensure it's an inline note and not a reference
                    if note_value and not note_value.startswith('@'):
                        if note_value.strip().startswith(note_starts_with):
                            note_to_delete = note
                            break
            
            if note_to_delete:
                entity.get_child_elements().remove(note_to_delete)
                gedcom_ctx.clear_caches()
                return f"Successfully deleted note starting with '{note_starts_with}' from {entity_id}."
            else:
                return f"Error: No inline note found for {entity_id} that starts with '{note_starts_with}'."
        except Exception as e:
            return f"Error deleting note: {e}"
    
    return "Error: Either note_starts_with or note_id must be provided."

@mcp.tool()
async def new_empty_gedcom(ctx: Context) -> str:
    """Create a new empty GEDCOM context with an empty parser and reset all attributes."""
    gedcom_ctx = get_gedcom_context(ctx)
    return _new_empty_gedcom_internal(gedcom_ctx)

@mcp.tool()
async def save_gedcom(ctx: Context, file_path: Optional[str] = None) -> str:
    """Saves the in-memory GEDCOM data back to a file.

    Args:
        file_path: The path to save the file to. If not provided, it will
                   overwrite the original file that was loaded.

    Returns:
        A confirmation or error message.
    """
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM data in memory to save."

    save_path = file_path or gedcom_ctx.gedcom_file_path
    if not save_path:
        return "Error: No file path specified and no original file path is known. Please provide a file_path."

    return save_gedcom_file(save_path, gedcom_ctx)

# Register prompt templates
@mcp.prompt(name="genealogy/family_tree")
def family_tree_template(person_name: str, generation_count: int, person_data: str = "", family_data: str = "") -> str:
    """Generate a family tree visualization for a person"""
    with open("prompts/family_tree_query.tmpl", "r") as f:
        template = f.read()
    return template.replace("{{person_name}}", str(person_name)).replace("{{generation_count}}", str(generation_count)).replace("{{person_data}}", str(person_data)).replace("{{family_data}}", str(family_data))

@mcp.prompt(name="genealogy/biography")
def biography_template(person_name: str, person_data: str = "", family_data: str = "", event_data: str = "", historical_context: str = "") -> str:
    """Generate a biographical summary for a person"""
    with open("prompts/biography_summary.tmpl", "r") as f:
        template = f.read()
    return template.replace("{{person_name}}", str(person_name)).replace("{{person_data}}", str(person_data)).replace("{{family_data}}", str(family_data)).replace("{{event_data}}", str(event_data)).replace("{{historical_context}}", str(historical_context))

@mcp.prompt(name="genealogy/relationship")
def relationship_template(person1_name: str, person2_name: str, person1_data: str = "", person2_data: str = "", family_data: str = "") -> str:
    """Find and describe the relationship path between two people"""
    with open("prompts/relationship_finder.tmpl", "r") as f:
        template = f.read()
    return template.replace("{{person1_name}}", str(person1_name)).replace("{{person2_name}}", str(person2_name)).replace("{{person1_data}}", str(person1_data)).replace("{{person2_data}}", str(person2_data)).replace("{{family_data}}", str(family_data))

# Register resource templates
@mcp.resource("genealogy://person/{person_id}")
async def get_person_resource(person_id: str, ctx: Context) -> str:
    """Get detailed information about a person as a resource"""
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM file loaded. Please load a GEDCOM file first."
    
    person = get_person_details_internal(person_id, gedcom_ctx)
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
    if hasattr(family_elem, 'get_child_elements'):
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
        "marriage_place": marriage_place
    }
    
    # Get person details for family members
    if husband_id:
        husband = get_person_details_internal(husband_id, gedcom_ctx)
        if husband:
            family_info["husband"] = husband.model_dump()
    
    if wife_id:
        wife = get_person_details_internal(wife_id, gedcom_ctx)
        if wife:
            family_info["wife"] = wife.model_dump()
    
    children_details = []
    for child_id in children_ids:
        child = get_person_details_internal(child_id, gedcom_ctx)
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
                text=f"Generate a biographical summary for the following person data:\n\n{person_data}"
            )
        )
    ]
    
    try:
        result = await context.sample(
            messages=messages,
            system_prompt="You are a genealogy expert. Generate a well-written biographical summary based on the provided genealogical data. Include key life events in chronological order, mention family relationships, highlight any notable occupations or achievements, and keep the tone engaging but factual."
        )
        return result.text if hasattr(result, 'text') else str(result)
    except Exception as e:
        return f"Error generating biography: {e}"

async def generate_family_history(context: Context, person_data: str, family_data: str, generations: int = 3) -> str:
    """Generate a family history narrative using LLM sampling"""
    from mcp.types import SamplingMessage, TextContent, Role
    
    messages = [
        SamplingMessage(
            role=Role.user,
            content=TextContent(
                type="text",
                text=f"Generate a family history narrative for the following person and their ancestors/descendants for {generations} generations:\n\nPerson Data:\n{person_data}\n\nFamily Data:\n{family_data}"
            )
        )
    ]
    
    try:
        result = await context.sample(
            messages=messages,
            system_prompt=f"You are a genealogy expert. Generate a comprehensive family history narrative that traces {generations} generations of this family. Include key life events, family relationships, migrations, and historical context. Organize the narrative chronologically and thematically. Make it engaging but factual."
        )
        return result.text if hasattr(result, 'text') else str(result)
    except Exception as e:
        return f"Error generating family history: {e}"

async def generate_historical_context(context: Context, time_periods: str, locations: str) -> str:
    """Generate historical context for time periods and locations using LLM sampling"""
    from mcp.types import SamplingMessage, TextContent, Role
    
    messages = [
        SamplingMessage(
            role=Role.user,
            content=TextContent(
                type="text",
                text=f"Provide historical context for the following time periods and locations relevant to genealogical research:\n\nTime Periods:\n{time_periods}\n\nLocations:\n{locations}"
            )
        )
    ]
    
    try:
        result = await context.sample(
            messages=messages,
            system_prompt="You are a history expert specializing in genealogical research contexts. Provide relevant historical context for the given time periods and locations. Focus on major events, social conditions, migration patterns, and cultural aspects that would be relevant for understanding family histories. Be concise but informative."
        )
        return result.text if hasattr(result, 'text') else str(result)
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
        response_type=PersonDetailsInput
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
        response_type=FamilyDetailsInput
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
        return "Family Details:\n" + "\n".join(details) if details else "No family details provided"
    elif result.action == "decline":
        return "Family details not provided"
    else:  # cancel
        return "Operation cancelled"

async def request_event_details(context: Context) -> str:
    """Request event details through structured elicitation"""
    result = await context.elicit(
        message="Please provide details about the event",
        response_type=EventDetailsInput
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
    async def validate_dates(ctx: Context, birth_date: str = None, death_date: str = None) -> str:
        """Validate that birth and death dates are consistent.
        
        Args:
            birth_date: Birth date string to validate
            death_date: Death date string to validate
            
        Returns:
            Validation result with any error messages
        """
        try:
            is_valid, error_msg = validate_date_consistency(birth_date, death_date)
            result = {
                "birth_date": birth_date,
                "death_date": death_date,
                "is_valid": is_valid,
                "error_message": error_msg
            }
            import json
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error validating dates: {e}"

    @mcp.tool()
    async def get_date_certainty(ctx: Context, date_string: str) -> str:
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
    async def normalize_name(ctx: Context, name_string: str) -> str:
        """Normalize a name for comparison purposes.
        
        Args:
            name_string: The name string to normalize
            
        Returns:
            A normalized version of the name
        """
        try:
            normalized = normalize_name(name_string)
            return f"Normalized name for '{name_string}': {normalized}"
        except Exception as e:
            return f"Error normalizing name: {e}"

    @mcp.tool()
    async def find_name_variants(ctx: Context, name_string: str) -> str:
        """Find common variants of a name.
        
        Args:
            name_string: The name string to find variants for
            
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
    async def normalize_place_name(ctx: Context, place_string: str) -> str:
        """Normalize a place name.
        
        Args:
            place_string: The place string to normalize
            
        Returns:
            A detailed breakdown of the normalized place information
        """
        try:
            normalized_place = normalize_place_name(place_string)
            import json
            return json.dumps({
                "original_text": normalized_place.original_text,
                "normalized_name": normalized_place.normalized_name,
                "country": normalized_place.country,
                "state_province": normalized_place.state_province,
                "county": normalized_place.county,
                "city": normalized_place.city
            }, indent=2)
        except Exception as e:
            return f"Error normalizing place name: {e}"

    

    @mcp.tool()
    async def extract_geographic_hierarchy(ctx: Context, place_string: str) -> str:
        """Extract geographic hierarchy from a place string.
        
        Args:
            place_string: The place string to parse
            
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
- **load_gedcom**(file_path) - Load a GEDCOM file
- **find_person**(name) - Search for people by name
- **get_person_details**(person_id) - Get detailed person information (now includes occupation)
- **get_persons_batch**(person_ids, include_fields) - Get details for multiple people at once
- **get_occupation**(person_id) - Get a person's occupation
- **get_relationships_tool**(person_id) - Get family relationships
- **new_empty_gedcom**() - Create a new empty GEDCOM context
- **add_person**(name, gender) - Add a new person to the GEDCOM data
- **create_marriage**(husband_id, wife_id) - Create a marriage between two people
- **add_child_to_family**(child_id, family_id) - Add a child to a family
- **create_source**(title, author, publication) - Create a new source with a unique ID

## Event & Information Tools:
- **get_events**(person_id) - Get comprehensive events with full details
- **get_notes**(entity_id) - Get all notes with full text for a person or family
- **get_note_by_id**(note_id) - Get the full text content of a specific note (e.g., @N176@)
- **get_sources_tool**(entity_id) - Get all sources for a person or family
- **get_timeline_tool**(person_id) - Generate chronological timeline

## Analysis Tools:
- **gedcom_search**(query, search_type) - Search across people, places, events, families
- **get_statistics_tool**() - Get comprehensive GEDCOM file statistics
- **get_attribute_statistics**(attribute_type) - Get statistics for a specific GEDCOM attribute (e.g., OCCU, RELI)
- **get_places_tool**(query) - Get information about places
- **get_surname_statistics**(surname) - Analyze surname frequency and distribution
- **get_date_range_analysis**() - Analyze time periods and generations covered
- **find_potential_duplicates**() - Find possible duplicate person records

- **validate_dates_tool**(birth_date, death_date) - Validate consistency between birth and death dates
- **get_date_certainty_tool**(date_string) - Get certainty level description for a date

- **normalize_name_tool**(name_string) - Normalize a name for comparison purposes
- **find_name_variants_tool**(name_string) - Find common variants of a name
- **normalize_place_name_tool**(place_string) - Normalize place names

- **extract_geographic_hierarchy_tool**(place_string) - Extract geographic hierarchy from place strings

## Bulk Data Tools:
- **get_all_people_ids**(page, page_size) - Get all person IDs with pagination
- **get_all_places_list**(page, page_size) - Get all unique places with pagination
- **get_all_families_ids**(page, page_size) - Get all family IDs with pagination
- **get_all_entity_ids**(entity_type, page, page_size) - Get all entity IDs (person, family, place, note, source) with pagination
- **query_people_by_criteria**(filters, page, page_size) - Flexible people search with multiple criteria

## Genealogy Tools:
- **get_ancestors**(person_id, generations) - Get ancestors tree with full details
- **get_descendants**(person_id, generations) - Get descendants tree with full details
- **get_family_tree_summary**(person_id) - Concise family overview with parents, spouse, children
- **find_shortest_relationship_path**(person1_id, person2_id, allowed_relationships, max_distance, exclude_initial_spouse_children, min_distance) - Find shortest path between two people (max distance: 30)
- **get_common_ancestors**(person_ids, max_level) - Find common ancestors for multiple people (comma-separated IDs, max level: 20)

- **find_all_relationship_paths**(person1_id, person2_id, allowed_relationships, max_distance, max_paths) - Find all relationship paths between two people
- **find_all_paths_to_ancestor**(start_person_id, ancestor_id, max_paths) - Find all paths from a person to a specific ancestor (parent links only)

## Data Management Tools:
- **update_person**(person_id, name, gender, birth_date, birth_place, death_date, death_place) - Updates the details for an existing person
- **find_person_families**(person_id) - Finds the families a person is associated with (as a spouse or child)
- **remove_child_from_family**(child_id, family_id) - Removes the link between a child and their family
- **remove_parent_from_family**(parent_id, family_id) - Removes the link between a parent and their family
- **dissolve_marriage**(family_id) - Dissolves a marriage by removing the spouse links from a family
- **delete_person**(person_id) - Deletes a person and removes them from all family relationships
- **update_event_details**(entity_id, event_type, new_date, new_place, old_date_to_match) - Updates the date and/or place for an event associated with a person or family
- **remove_event**(entity_id, event_type, date_to_match) - Removes an event from a person or family
- **get_person_attributes**(person_id) - Returns a list of all attributes for a person
- **update_person_attribute**(person_id, attribute_type, new_value, old_value_to_match) - Updates the value of a person's attribute
- **remove_person_attribute**(person_id, attribute_type, value_to_match) - Removes a specific attribute from a person
- **add_note_to_entity**(entity_id, note_text) - Adds a new note to a person or family. Create references to note entities. A new note is created
- **delete_note_from_entity**(entity_id, note_starts_with, note_id) - Deletes an inline note from a person or family, or removes a reference to a note entity
- **delete_note_entity**(note_id) - Deletes a note entity by its ID and removes all references to it
- **save_gedcom**(file_path) - Saves the in-memory GEDCOM data back to a file

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
2. get_statistics() - Overview of the file
3. search(query="Smith", search_type="people")
4. get_person_details(person_id="@I123@")

### Deep genealogy research:
1. get_ancestors(person_id="@I123@", generations=4)
2. get_events(person_id="@I123@") - All life events
3. get_notes(entity_id="@I123@") - Research notes
4. get_sources(entity_id="@I123@") - Documentation

### Place and event research:
1. search(query="London", search_type="places")
2. search(query="marriage", search_type="events")
3. get_places(query="England")"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GEDCOM MCP Server")
    parser.add_argument(
        "--transport", 
        choices=["stdio", "streamable-http"], 
        default="streamable-http",
        help="Transport method for the MCP server (default: streamable-http)"
    )
    parser.add_argument(
        "--host", 
        default="127.0.0.1",
        help="Host for streamable-http transport (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", 
        type=int, 
        default=8000,
        help="Port for streamable-http transport (default: 8000)"
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

