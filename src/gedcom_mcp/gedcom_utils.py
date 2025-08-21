#!/usr/bin/env python3

import re
from typing import Optional, Any, Dict
from .gedcom_models import PersonDetails
from .gedcom_constants import EVENT_TYPES, ATTRIBUTE_TYPES

# Try to import unidecode for text normalization
try:
    from unidecode import unidecode
    UNIDECODE_AVAILABLE = True
except ImportError:
    UNIDECODE_AVAILABLE = False

# Import our new genealogy date utilities
try:
    from .gedcom_date_utils import parse_genealogy_date
    DATE_UTILS_AVAILABLE = True
except ImportError:
    DATE_UTILS_AVAILABLE = False

# Import our new genealogy name utilities
try:
    from .gedcom_name_utils import parse_genealogy_name
    NAME_UTILS_AVAILABLE = True
except ImportError:
    NAME_UTILS_AVAILABLE = False

# Import our new genealogy place utilities
try:
    from .gedcom_place_utils import normalize_place_name
    PLACE_UTILS_AVAILABLE = True
except ImportError:
    PLACE_UTILS_AVAILABLE = False


_HUMAN_EVENT_TO_GEDCOM_TAG = {
    details["name"].lower(): tag for tag, details in EVENT_TYPES.items()
}

_HUMAN_ATTRIBUTE_TO_GEDCOM_TAG = {
    details["name"].lower(): tag for tag, details in ATTRIBUTE_TYPES.items()
}

def normalize_string(text: str) -> str:
    """Normalize string for comparison - removes accents, converts to lowercase, and normalizes whitespace
    
    Uses unidecode if available to handle accented characters (é → e, ñ → n, etc.)
    Falls back to simple case folding if unidecode is not installed.
    
    To install unidecode: pip install unidecode
    """
    if isinstance(text, str):
        # Normalize whitespace to single spaces
        text = re.sub(r'\s+', ' ', text.strip())
        if UNIDECODE_AVAILABLE:
            return unidecode(text).casefold()
        else:
            # Fallback without unidecode - just case normalization
            return text.casefold()
    else:
        return text


def _get_gedcom_tag_from_event_type(event_type_input: str) -> Optional[str]:
    """Converts a human-readable event name or a GEDCOM tag to a standardized GEDCOM tag."""
    # First, check if it's already a valid GEDCOM tag
    if event_type_input.upper() in EVENT_TYPES:
        return event_type_input.upper()
    
    # Then, try to match human-readable name (case-insensitive)
    normalized_input = event_type_input.lower()
    if normalized_input in _HUMAN_EVENT_TO_GEDCOM_TAG:
        return _HUMAN_EVENT_TO_GEDCOM_TAG[normalized_input]
    
    return None  # No matching tag found


def _get_gedcom_tag_from_attribute_type(attribute_type_input: str) -> Optional[str]:
    """Converts a human-readable attribute name or a GEDCOM tag to a standardized GEDCOM tag."""
    # First, check if it's already a valid GEDCOM tag
    if attribute_type_input.upper() in ATTRIBUTE_TYPES:
        return attribute_type_input.upper()
    
    # Then, try to match human-readable name (case-insensitive)
    normalized_input = attribute_type_input.lower()
    if normalized_input in _HUMAN_ATTRIBUTE_TO_GEDCOM_TAG:
        return _HUMAN_ATTRIBUTE_TO_GEDCOM_TAG[normalized_input]
    
    return None  # No matching tag found


def _extract_year_from_genealogy_date(date_str: str) -> Optional[int]:
    """Extract year from a genealogy date string using enhanced parsing.
    
    Args:
        date_str: The date string to parse
        
    Returns:
        The extracted year or None if not found
    """
    if not date_str:
        return None
    
    # Use our enhanced date parsing if available
    if DATE_UTILS_AVAILABLE:
        try:
            parsed_date = parse_genealogy_date(str(date_str))
            if parsed_date.year:
                return parsed_date.year
        except Exception:
            # Fall back to regex if parsing fails
            pass
    
    # Extract year from various date formats using regex as fallback
    # Common GEDCOM date formats: "1850", "ABT 1850", "BEF 1850", "AFT 1850", "BET 1850 AND 1855"
    year_match = re.search(r'\b(1[0-9]{3}|20[0-9]{2})\b', str(date_str))
    if year_match:
        return int(year_match.group(1))
    
    return None


def _normalize_genealogy_name(name_str: str) -> str:
    """Normalize a genealogy name using enhanced parsing.
    
    Args:
        name_str: The name string to normalize
        
    Returns:
        The normalized name string
    """
    if not name_str:
        return ""
    
    # Use our enhanced name parsing if available
    if NAME_UTILS_AVAILABLE:
        try:
            parsed_name = parse_genealogy_name(name_str)
            return str(parsed_name)  # Use standardized name format
        except Exception:
            # Fall back to original if parsing fails
            pass
    
    return name_str


def _normalize_genealogy_date(date_str: str) -> str:
    """Normalize a genealogy date using enhanced parsing.
    
    Args:
        date_str: The date string to normalize
        
    Returns:
        The normalized date string
    """
    if not date_str:
        return ""
    
    # Use our enhanced date parsing if available
    if DATE_UTILS_AVAILABLE:
        try:
            parsed_date = parse_genealogy_date(date_str)
            if parsed_date.original_text:
                return parsed_date.original_text
        except Exception:
            # Fall back to original if parsing fails
            pass
    
    return date_str


def _normalize_genealogy_place(place_str: str) -> str:
    """Normalize a genealogy place name using enhanced parsing.
    
    Args:
        place_str: The place string to normalize
        
    Returns:
        The normalized place string
    """
    if not place_str:
        return ""
    
    # Use our enhanced place parsing if available
    if PLACE_UTILS_AVAILABLE:
        try:
            normalized_place = normalize_place_name(place_str)
            if normalized_place.normalized_name:
                return normalized_place.normalized_name
        except Exception:
            # Fall back to original if parsing fails
            pass
    
    return place_str


def _extract_year_from_date(date_str):
    """Extract year from a date string"""
    if not date_str:
        return None
    
    # Use our enhanced date parsing function
    return _extract_year_from_genealogy_date(date_str)


def extract_birth_year(person_id: str, gedcom_ctx):
    """Extract birth year from a person's birth date"""
    from gedcom.element.individual import IndividualElement
    
    if not gedcom_ctx.gedcom_parser or person_id not in gedcom_ctx.individual_lookup:
        return None
    
    try:
        element = gedcom_ctx.individual_lookup[person_id]
        birth_facts = element.get_birth_data()
        if not birth_facts:
            return None
            
        birth_date = None
        if isinstance(birth_facts, tuple):
            birth_date = birth_facts[0] if len(birth_facts) > 0 else None
        else:
            try:
                birth_date = birth_facts.get_date()
            except AttributeError:
                birth_date = str(birth_facts)
        
        if birth_date:
            return _extract_year_from_genealogy_date(str(birth_date))
    except Exception:
        # We'll need to import logger when this function is used
        # logger.debug(f"Error extracting birth year for {person_id}: {e}")
        pass
    
    return None


def _matches_criteria(person: PersonDetails, criteria: Dict[str, Any]) -> bool:
    """Check if a person matches the given criteria"""
    import re
    
    for key, value in criteria.items():
        if key == "occupation":
            if value is None:
                if person.occupation is not None:
                    return False
            else:
                if not person.occupation or normalize_string(value) not in normalize_string(person.occupation):
                    return False
        
        elif key == "birth_year_range":
            if not person.birth_date:
                return False
            birth_year = _extract_year_from_date(person.birth_date)
            if not birth_year:
                return False
            if isinstance(value, list) and len(value) == 2:
                if not (value[0] <= birth_year <= value[1]):
                    return False
            elif isinstance(value, int):
                if birth_year != value:
                    return False
        
        elif key == "death_year_range":
            if value is None:
                if person.death_date is not None:
                    return False
            else:
                if not person.death_date:
                    return False
                death_year = _extract_year_from_date(person.death_date)
                if not death_year:
                    return False
                if isinstance(value, list) and len(value) == 2:
                    if not (value[0] <= death_year <= value[1]):
                        return False
                elif isinstance(value, int):
                    if death_year != value:
                        return False
        
        elif key == "birth_place_contains":
            if not person.birth_place or normalize_string(value) not in normalize_string(person.birth_place):
                return False
        
        elif key == "death_place_contains":
            if not person.death_place or normalize_string(value) not in normalize_string(person.death_place):
                return False
        
        elif key == "name_contains":
            if not person.name or normalize_string(value) not in normalize_string(person.name):
                return False
        
        elif key == "gender":
            if value is None:
                if person.gender is not None:
                    return False
            else:
                if person.gender != value:
                    return False
        
        elif key == "has_children":
            has_children = len(person.children) > 0
            if has_children != value:
                return False
        
        elif key == "has_parents":
            has_parents = len(person.parents) > 0
            if has_parents != value:
                return False
        
        elif key == "has_spouses":
            has_spouses = len(person.spouses) > 0
            if has_spouses != value:
                return False
        
        elif key == "is_living":
            is_living = person.death_date is None
            if is_living != value:
                return False
    
    return True
