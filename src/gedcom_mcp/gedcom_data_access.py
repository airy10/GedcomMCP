#!/usr/bin/env python3

import logging
from typing import List, Optional, Dict, Any
from pathlib import Path
from gedcom.element.individual import IndividualElement
from gedcom.parser import Parser
from .gedcom_context import GedcomContext, _rebuild_lookups
from .gedcom_models import PersonDetails, PersonRelationships
from .gedcom_utils import normalize_string, _normalize_genealogy_name, _normalize_genealogy_date, _normalize_genealogy_place, PLACE_UTILS_AVAILABLE
from .gedcom_place_utils import normalize_place_name, extract_geographic_hierarchy
from .gedcom_constants import EVENT_TYPES, ATTRIBUTE_TYPES

# Set up logging
logger = logging.getLogger(__name__)

def load_gedcom_file(file_path: str, gedcom_ctx: GedcomContext) -> bool:
    """Load and parse a GEDCOM file into the provided context"""
    try:
        # Check if file exists
        if not Path(file_path).exists():
            logger.error(f"GEDCOM file not found: {file_path}")
            return False
            
        # Parse the GEDCOM file
        gedcom_ctx.gedcom_parser = Parser()
        gedcom_ctx.gedcom_parser.parse_file(file_path, False)
        gedcom_ctx.gedcom_file_path = file_path
        
        _rebuild_lookups(gedcom_ctx)

        logger.info(f"Successfully loaded GEDCOM file: {file_path}")
        return True
    except Exception as e:
        logger.error(f"Error loading GEDCOM file: {e}")
        return False

def save_gedcom_file(file_path: str, gedcom_ctx: GedcomContext) -> str:
    """Saves the in-memory GEDCOM data back to a file.

    Args:
        file_path: The path to save the file to.
        gedcom_ctx: The GEDCOM context.

    Returns:
        A confirmation or error message.
    """
    if not gedcom_ctx.gedcom_parser:
        return "No GEDCOM data in memory to save."

    try:
        # Use the GEDCOM library's built-in save method
        with open(file_path, 'w') as f:
            gedcom_ctx.gedcom_parser.save_gedcom(f)
        
        return f"Successfully saved GEDCOM data to {file_path}"
    except Exception as e:
        return f"Error saving GEDCOM file to {file_path}: {e}"

def get_person_details_internal(person_id: str, gedcom_ctx) -> Optional[PersonDetails]:
    """Get detailed information about a person"""
    if not gedcom_ctx.gedcom_parser:
        return None
    
    # Check cache first for exact ID match
    if person_id in gedcom_ctx.person_details_cache:
        return gedcom_ctx.person_details_cache[person_id]
        
    try:
        # PERFORMANCE OPTIMIZATION: Use lookup dictionary instead of O(n) search
        individual_elem = gedcom_ctx.individual_lookup.get(person_id)
        if individual_elem:
            person_details = _extract_person_details(individual_elem, gedcom_ctx)
            gedcom_ctx.person_details_cache[person_id] = person_details
            return person_details
                
        # If not found by ID, try to find by name using lookup dictionary
        for individual_elem in gedcom_ctx.individual_lookup.values():
            name = individual_elem.get_name()
            # Handle case where get_name() returns a tuple or other structure
            if isinstance(name, tuple):
                name_str = " ".join(str(part) for part in name if part)
            elif name is None:
                name_str = ""
            else:
                name_str = str(name)
            
            if normalize_string(person_id) in normalize_string(name_str):
                person_details = _extract_person_details(individual_elem, gedcom_ctx)
                # Cache using the actual person ID, not the search term
                actual_person_id = individual_elem.get_pointer()
                gedcom_ctx.person_details_cache[actual_person_id] = person_details
                return person_details
                    
        return None
    except Exception as e:
        # We'll need to import logger when this function is used
        # logger.error(f"Error getting person details: {e}")
        return None


def _extract_person_details(element: IndividualElement, gedcom_ctx) -> PersonDetails:
    """Extract person details from a GEDCOM individual element"""
    person_id = element.get_pointer()
    
    name = ""
    birth_date = None
    birth_place = None
    death_date = None
    death_place = None
    gender = None
    occupation = None

    # Iterate through all child elements to find relevant data
    if hasattr(element, 'get_child_elements'):
        for child_elem in element.get_child_elements():
            tag = child_elem.get_tag()
            value = child_elem.get_value()

            if tag == "NAME":
                # Use our enhanced name parsing
                name = _normalize_genealogy_name(value)

            elif tag == "BIRT":
                for birt_child in child_elem.get_child_elements():
                    if birt_child.get_tag() == "DATE":
                        birth_date = birt_child.get_value()
                        # Enhance with our date parsing
                        birth_date = _normalize_genealogy_date(birth_date) if birth_date else birth_date
                    elif birt_child.get_tag() == "PLAC":
                        birth_place = birt_child.get_value()
                        # Enhance with our place parsing
                        birth_place = _normalize_genealogy_place(birth_place) if birth_place else birth_place
            elif tag == "DEAT":
                for deat_child in child_elem.get_child_elements():
                    if deat_child.get_tag() == "DATE":
                        death_date = deat_child.get_value()
                        # Enhance with our date parsing
                        death_date = _normalize_genealogy_date(death_date) if death_date else death_date
                    elif deat_child.get_tag() == "PLAC":
                        death_place = deat_child.get_value()
                        # Enhance with our place parsing
                        death_place = _normalize_genealogy_place(death_place) if death_place else death_place
            elif tag == "SEX":
                gender = value
            elif tag == "OCCU":
                occupation = value
    
    # Get relationships using cached function for better performance
    parents = []
    spouses = []
    children = []
    
    # Use the cached relationship function instead of duplicating logic
    relationships = _get_person_relationships_internal(person_id, gedcom_ctx)
    if relationships:
        parents = list(relationships.parents)
        spouses = list(relationships.spouses)
        children = list(relationships.children)
    
    return PersonDetails(
        id=person_id,
        name=name,
        birth_date=birth_date,
        birth_place=birth_place,
        death_date=death_date,
        death_place=death_place,
        gender=gender,
        occupation=occupation,
        parents=parents,
        spouses=spouses,
        children=children
    )


def _get_person_relationships_internal(person_id: str, gedcom_ctx) -> Optional[PersonRelationships]:
    """
    Get person relationships (parents, spouses, children) and gender,
    optimized for graph traversal and caching.
    """
    if not gedcom_ctx.gedcom_parser:
        return None

    # Check cache first
    if person_id in gedcom_ctx.person_relationships_cache:
        return gedcom_ctx.person_relationships_cache[person_id]

    try:
        individual_elem = gedcom_ctx.individual_lookup.get(person_id)
        if not individual_elem:
            return None

        gender = individual_elem.get_gender()
        parents = set()
        spouses = set()
        children = set()

        # Use GEDCOM tags directly: FAMC (Family As Child) and FAMS (Family As Spouse)
        if gedcom_ctx.gedcom_parser:
            # We'll need to import logger when this function is used
            # logger.info(f"DEBUG: _get_person_relationships_internal - individual_elem child elements for {person_id}: {[c.get_tag() for c in individual_elem.get_child_elements()]}")
            person_child_elements = individual_elem.get_child_elements()

            famc_families = []
            fams_families = []

            for child_elem in person_child_elements:
                tag = child_elem.get_tag()
                if tag == "FAMC":
                    family_pointer = child_elem.get_value()
                    famc_families.append(family_pointer)
                elif tag == "FAMS":
                    family_pointer = child_elem.get_value()
                    fams_families.append(family_pointer)

            # Process FAMC families (where this person is a child)
            for family_pointer in famc_families:
                family_elem = gedcom_ctx.family_lookup.get(family_pointer)
                if family_elem:
                    family_child_elements = family_elem.get_child_elements()
                    for child_elem in family_child_elements:
                        tag = child_elem.get_tag()
                        if tag == "HUSB":
                            husband_pointer = child_elem.get_value()
                            if husband_pointer:
                                parents.add(husband_pointer)
                        elif tag == "WIFE":
                            wife_pointer = child_elem.get_value()
                            if wife_pointer:
                                parents.add(wife_pointer)

            # Process FAMS families (where this person is a spouse)
            for family_pointer in fams_families:
                family_elem = gedcom_ctx.family_lookup.get(family_pointer)
                if family_elem:
                    family_child_elements = family_elem.get_child_elements()
                    husband_pointer = None
                    wife_pointer = None

                    for child_elem in family_child_elements:
                        tag = child_elem.get_tag()
                        if tag == "HUSB":
                            husband_pointer = child_elem.get_value()
                        elif tag == "WIFE":
                            wife_pointer = child_elem.get_value()
                        elif tag == "CHIL":
                            child_pointer = child_elem.get_value()
                            if child_pointer:
                                children.add(child_pointer)

                    # Add spouse (the other person in this family)
                    if husband_pointer == person_id:
                        if wife_pointer:
                            spouses.add(wife_pointer)
                    elif wife_pointer == person_id:
                        if husband_pointer:
                            spouses.add(husband_pointer)

        person_relationships = PersonRelationships(
            id=person_id,
            gender=gender,
            parents=sorted(parents),  # Convert set to sorted list for deterministic iteration
            spouses=sorted(spouses),  # Convert set to sorted list for deterministic iteration
            children=sorted(children)  # Convert set to sorted list for deterministic iteration
        )
        gedcom_ctx.person_relationships_cache[person_id] = person_relationships
        return person_relationships

    except Exception as e:
        # We'll need to import logger when this function is used
        # logger.error(f"Error getting person relationships for {person_id}: {e}")
        return None


def find_person_by_name(name: str, gedcom_ctx) -> List[PersonDetails]:
    """Find persons matching a name"""
    if not gedcom_ctx.gedcom_parser:
        return []
        
    try:
        # PERFORMANCE OPTIMIZATION: Use lookup dictionary instead of O(n) search
        matches = []
        
        for individual_elem in gedcom_ctx.individual_lookup.values():
            person_name = individual_elem.get_name()
            
            # Handle case where get_name() returns a tuple or other structure
            if isinstance(person_name, tuple):
                # If it's a tuple, join the parts or take the first part
                person_name_str = " ".join(str(part) for part in person_name if part)
            elif person_name is None:
                person_name_str = ""
            else:
                person_name_str = str(person_name)
            
            if normalize_string(name) in normalize_string(person_name_str):
                matches.append(_extract_person_details(individual_elem, gedcom_ctx))
                    
        return matches
    except Exception as e:
        # We'll need to import logger when this function is used
        # logger.error(f"Error finding person by name: {e}")
        return []


def _get_relationships_internal(person_id: str, gedcom_ctx) -> Dict[str, Any]:
    """Get family relationships for a person"""
    # Use cached relationships to get IDs, then get details efficiently
    person_relationships = _get_person_relationships_internal(person_id, gedcom_ctx)
    if not person_relationships:
        return {}
        
    relationships = {
        "parents": [],
        "spouses": [],
        "children": []
    }
    
    # Get parent details
    for parent_id in person_relationships.parents:
        parent = get_person_details_internal(parent_id, gedcom_ctx)
        if parent:
            relationships["parents"].append(parent.model_dump())
    
    # Get spouse details
    for spouse_id in person_relationships.spouses:
        spouse = get_person_details_internal(spouse_id, gedcom_ctx)
        if spouse:
            relationships["spouses"].append(spouse.model_dump())
    
    # Get child details
    for child_id in person_relationships.children:
        child = get_person_details_internal(child_id, gedcom_ctx)
        if child:
            relationships["children"].append(child.model_dump())
            
    return relationships


def decode_event_details(element, event_tag: str) -> Dict[str, Any]:
    """Decode detailed event information from a GEDCOM element"""
    event_info = EVENT_TYPES.get(event_tag, {"name": event_tag, "description": f"Event type: {event_tag}"})
    
    event_data = {
        "type": event_tag,
        "name": event_info["name"],
        "description": event_info["description"],
        "date": None,
        "place": None,
        "notes": [],
        "sources": [],
        "age": None,
        "agency": None,
        "cause": None,
        "address": None
    }
    
    # Get child elements of the event
    if hasattr(element, 'get_child_elements'):
        child_elements = element.get_child_elements()
        for child in child_elements:
            tag = child.get_tag()
            value = child.get_value()
            
            if tag == "DATE":
                date_value = value
                # Enhance with our date parsing
                date_value = _normalize_genealogy_date(date_value) if date_value else date_value
                event_data["date"] = date_value
            elif tag == "PLAC":
                place_value = value
                # Enhance with our place parsing
                place_value = _normalize_genealogy_place(place_value) if place_value else place_value
                event_data["place"] = place_value
            elif tag == "NOTE":
                event_data["notes"].append(value)
            elif tag == "SOUR":
                event_data["sources"].append(value)
            elif tag == "AGE":
                event_data["age"] = value
            elif tag == "AGNC":
                event_data["agency"] = value
            elif tag == "CAUS":
                event_data["cause"] = value
            elif tag == "ADDR":
                event_data["address"] = value
    
    return event_data


def _get_events_internal(person_id: str, gedcom_ctx) -> List[Dict[str, Any]]:
    """Get comprehensive events for a person"""
    if not gedcom_ctx.gedcom_parser:
        return []
        
    try:
        root_child_elements = gedcom_ctx.gedcom_parser.get_root_child_elements()
        events = []
        
        # Find the person with the given ID
        for element in root_child_elements:
            if element.get_pointer() == person_id and isinstance(element, IndividualElement):
                # Get person name for descriptions
                raw_name = element.get_name()
                if isinstance(raw_name, tuple):
                    name_str = " ".join(str(part) for part in raw_name if part)
                else:
                    name_str = str(raw_name) if raw_name else ""
                
                # Get all child elements to find events and attributes
                person_child_elements = element.get_child_elements()
                
                for child_elem in person_child_elements:
                    tag = child_elem.get_tag()
                    
                    if tag in EVENT_TYPES:
                        event_data = decode_event_details(child_elem, tag)
                        event_data["person_name"] = name_str
                        events.append(event_data)
                    
                    # Handle attributes that are also events
                    elif tag in ATTRIBUTE_TYPES:
                        attr_info = ATTRIBUTE_TYPES[tag]
                        value = child_elem.get_value()
                        
                        event_data = {
                            "type": tag,
                            "name": attr_info["name"],
                            "description": attr_info["description"],
                            "value": value,
                            "person_name": name_str,
                            "date": None,
                            "place": None,
                            "notes": [],
                            "sources": []
                        }
                        
                        # Get additional details for attributes
                        if hasattr(child_elem, 'get_child_elements'):
                            attr_children = child_elem.get_child_elements()
                            for attr_child in attr_children:
                                attr_tag = attr_child.get_tag()
                                attr_value = attr_child.get_value()
                                
                                if attr_tag == "DATE":
                                    event_data["date"] = attr_value
                                elif attr_tag == "PLAC":
                                    event_data["place"] = attr_value
                                elif attr_tag == "NOTE":
                                    event_data["notes"].append(attr_value)
                                elif attr_tag == "SOUR":
                                    event_data["sources"].append(attr_value)
                        
                        events.append(event_data)
                
                # Get family events (marriages, divorces, etc.)
                person_child_elements = element.get_child_elements()
                fams_families = []
                
                for child_elem in person_child_elements:
                    if child_elem.get_tag() == "FAMS":
                        fams_families.append(child_elem.get_value())
                
                # PERFORMANCE OPTIMIZATION: Use lookup dictionary instead of O(n) search
                # Process family events
                for family_pointer in fams_families:
                    family_elem = gedcom_ctx.family_lookup.get(family_pointer)
                    if family_elem:
                        # Get family events
                        family_child_elements = family_elem.get_child_elements()
                        
                        for family_child in family_child_elements:
                            family_tag = family_child.get_tag()
                            
                            if family_tag in EVENT_TYPES:
                                event_data = decode_event_details(family_child, family_tag)
                                event_data["person_name"] = name_str
                                event_data["family_id"] = family_pointer
                                events.append(event_data)
                
                return events
        
        return []
    except Exception as e:
        # We'll need to import logger when this function is used
        # logger.error(f"Error getting events: {e}")
        return []

def _get_places_internal(query: Optional[str] = None, gedcom_ctx = None) -> List[Dict[str, Any]]:
    """Get information about places mentioned in the GEDCOM file"""
    if not gedcom_ctx or not gedcom_ctx.gedcom_parser:
        return []
        
    try:
        root_child_elements = gedcom_ctx.gedcom_parser.get_root_child_elements()
        places = {}
        
        # Iterate through all elements to find places
        for element in root_child_elements:
            if isinstance(element, IndividualElement):
                # Get birth place
                birth_facts = element.get_birth_data()
                if birth_facts:
                    birth_place = None
                    if isinstance(birth_facts, tuple):
                        birth_place = birth_facts[1] if len(birth_facts) > 1 else None
                    else:
                        try:
                            birth_place = birth_facts.get_place()
                        except AttributeError:
                            birth_place = None
                    
                    if birth_place:
                        # Normalize place name using our helper
                        normalized_name = _normalize_genealogy_place(birth_place)
                        
                        if normalized_name not in places:
                            places[normalized_name] = {
                                "name": normalized_name,
                                "original_names": set(),
                                "occurrences": 0,
                                "event_types": set()
                            }
                        places[normalized_name]["original_names"].add(birth_place)
                        places[normalized_name]["occurrences"] += 1
                        places[normalized_name]["event_types"].add("birth")
                
                # Get death place
                death_facts = element.get_death_data()
                if death_facts:
                    death_place = None
                    if isinstance(death_facts, tuple):
                        death_place = death_facts[1] if len(death_facts) > 1 else None
                    else:
                        try:
                            death_place = death_facts.get_place()
                        except AttributeError:
                            death_place = None
                    
                    if death_place:
                        # Normalize place name using our helper
                        normalized_name = _normalize_genealogy_place(death_place)
                        
                        if normalized_name not in places:
                            places[normalized_name] = {
                                "name": normalized_name,
                                "original_names": set(),
                                "occurrences": 0,
                                "event_types": set()
                            }
                        places[normalized_name]["original_names"].add(death_place)
                        places[normalized_name]["occurrences"] += 1
                        places[normalized_name]["event_types"].add("death")
            
            # Check for family events (marriages)
            elif element.get_tag() == "FAM":
                marriages = element.get_marriages()
                if marriages:
                    for marriage in marriages:
                        marriage_place = None
                        if isinstance(marriage, tuple):
                            marriage_place = marriage[1] if len(marriage) > 1 else None
                        else:
                            try:
                                marriage_place = marriage.get_place()
                            except AttributeError:
                                marriage_place = None
                        
                        if marriage_place:
                            # Normalize place name using our helper
                            normalized_name = _normalize_genealogy_place(marriage_place)
                            
                            if normalized_name not in places:
                                places[normalized_name] = {
                                    "name": normalized_name,
                                    "original_names": set(),
                                    "occurrences": 0,
                                    "event_types": set()
                                }
                            places[normalized_name]["original_names"].add(marriage_place)
                            places[normalized_name]["occurrences"] += 1
                            places[normalized_name]["event_types"].add("marriage")
        
        # Convert to list and filter if query provided
        places_list = []
        for place_name, place_info in places.items():
            # Convert sets to lists for JSON serialization
            place_info["original_names"] = list(place_info["original_names"])
            place_info["event_types"] = list(place_info["event_types"])
            
            # Add geographic hierarchy if utilities are available
            if PLACE_UTILS_AVAILABLE:
                hierarchy = extract_geographic_hierarchy(place_name)
                place_info.update(hierarchy)
            
            # Filter by query if provided
            if query is None or normalize_string(query) in normalize_string(place_name):
                places_list.append(place_info)
        
        return places_list
    except Exception as e:
        logger.error(f"Error getting places: {e}")
        return []

def _get_person_attributes_internal(person_id: str, gedcom_ctx) -> Dict[str, str]:
    """Retrieves all attributes for a person.
    Args:
        person_id (str): The ID of the person.
    Returns:
        dict: A dictionary of attributes.
    """
    if not gedcom_ctx.gedcom_parser:
        return {}
    
    try:
        individual = gedcom_ctx.individual_lookup.get(person_id)
        if individual:
            attributes = {}
            # Iterate through child elements to find attributes
            for child_elem in individual.get_child_elements():
                tag = child_elem.get_tag()
                if tag in ATTRIBUTE_TYPES:
                    attributes[tag] = child_elem.get_value()
            return attributes
        return {}
    except Exception as e:
        return {}

def _get_notes_internal(entity_id: str, gedcom_ctx) -> List[Dict[str, Any]]:
    """Get all notes for a person, family, or get a specific note by ID"""
    if not gedcom_ctx.gedcom_parser:
        return []
    
    try:
        root_elements = gedcom_ctx.gedcom_parser.get_root_child_elements()
        notes = []
        
        # Check if entity_id is a note reference (starts with @N)
        if entity_id.startswith("@N"):
            # Find the specific note by ID
            for element in root_elements:
                if element.get_pointer() == entity_id and element.get_tag() == "NOTE":
                    # Get the note text - it might be in the value or in child CONT/CONC elements
                    note_text = ""
                    
                    # First try to get the main value
                    if hasattr(element, 'get_value'):
                        main_value = element.get_value()
                        if main_value:
                            note_text = str(main_value)
                    
                    # Then check for CONT (continuation) and CONC (concatenation) elements
                    if hasattr(element, 'get_child_elements'):
                        child_elements = element.get_child_elements()
                        for child_elem in child_elements:
                            tag = child_elem.get_tag()
                            value = child_elem.get_value()
                            if tag == "CONT":
                                # CONT adds a new line
                                note_text += "\n" + str(value) if value else ""
                            elif tag == "CONC":
                                # CONC continues on the same line
                                note_text += str(value) if value else ""
                    
                    notes.append({
                        "text": note_text.strip(),
                        "source": "direct",
                        "reference": entity_id,
                        "date": None
                    })
                    break
        else:
            # PERFORMANCE OPTIMIZATION: Use lookup dictionaries for entity lookup
            # Find the entity (person or family) and get its notes
            element = gedcom_ctx.individual_lookup.get(entity_id) or gedcom_ctx.family_lookup.get(entity_id)
            if element:
                    # Get all child elements to find notes
                    if hasattr(element, 'get_child_elements'):
                        child_elements = element.get_child_elements()
                        
                        for child_elem in child_elements:
                            if child_elem.get_tag() == "NOTE":
                                note_value = child_elem.get_value()
                                
                                # Check if it's an inline note or a reference
                                if note_value and note_value.startswith("@"):
                                    # PERFORMANCE OPTIMIZATION: Use note lookup dictionary
                                    # It's a reference - find the referenced note
                                    note_ref = note_value
                                    note_elem = gedcom_ctx.note_lookup.get(note_ref)
                                    if note_elem:
                                            # Get the referenced note text
                                            ref_note_text = ""
                                            if hasattr(note_elem, 'get_value'):
                                                main_value = note_elem.get_value()
                                                if main_value:
                                                    ref_note_text = str(main_value)
                                            
                                            # Check for CONT/CONC in referenced note
                                            if hasattr(note_elem, 'get_child_elements'):
                                                ref_child_elements = note_elem.get_child_elements()
                                                for ref_child in ref_child_elements:
                                                    ref_tag = ref_child.get_tag()
                                                    ref_value = ref_child.get_value()
                                                    if ref_tag == "CONT":
                                                        ref_note_text += "\n" + str(ref_value) if ref_value else ""
                                                    elif ref_tag == "CONC":
                                                        ref_note_text += str(ref_value) if ref_value else ""
                                            
                                            notes.append({
                                                "text": ref_note_text.strip(),
                                                "source": "reference",
                                                "reference": note_ref,
                                                "date": None
                                            })
                                            break
                                else:
                                    # It's an inline note
                                    note_data = {
                                        "text": str(note_value) if note_value else "",
                                        "source": "inline",
                                        "date": None
                                    }
                                    
                                    # Check for note details
                                    if hasattr(child_elem, 'get_child_elements'):
                                        note_children = child_elem.get_child_elements()
                                        for note_child in note_children:
                                            if note_child.get_tag() == "DATE":
                                                note_data["date"] = note_child.get_value()
                                    
                                    notes.append(note_data)

        return notes
    except Exception as e:
        logger.error(f"Error getting notes: {e}")
        return []

def _get_sources_internal(entity_id: str, gedcom_ctx) -> List[Dict[str, Any]]:
    """Get all sources for a person or family"""
    if not gedcom_ctx.gedcom_parser:
        return []
    
    try:
        sources = []
        
        # PERFORMANCE OPTIMIZATION: Use lookup dictionaries for entity lookup
        # Find the entity (person or family)
        element = gedcom_ctx.individual_lookup.get(entity_id) or gedcom_ctx.family_lookup.get(entity_id)
        if element:
            # Get all child elements to find sources
            if hasattr(element, 'get_child_elements'):
                child_elements = element.get_child_elements()
                
                for child_elem in child_elements:
                    if child_elem.get_tag() == "SOUR":
                        source_ref = child_elem.get_value()
                        
                        # PERFORMANCE OPTIMIZATION: Use source lookup dictionary
                        # Find the referenced source
                        source_elem = gedcom_ctx.source_lookup.get(source_ref)
                        if source_elem:
                            source_data = {
                                "reference": source_ref,
                                "title": "",
                                "author": "",
                                "publication": "",
                                "repository": "",
                                "page": "",
                                "quality": ""
                            }
                            
                            # Get source details
                            if hasattr(source_elem, 'get_child_elements'):
                                source_children = source_elem.get_child_elements()
                                for source_child in source_children:
                                    tag = source_child.get_tag()
                                    value = source_child.get_value()
                                    
                                    if tag == "TITL":
                                        source_data["title"] = value
                                    elif tag == "AUTH":
                                        source_data["author"] = value
                                    elif tag == "PUBL":
                                        source_data["publication"] = value
                                    elif tag == "REPO":
                                        source_data["repository"] = value
                            
                            # Get citation details from the reference
                            if hasattr(child_elem, 'get_child_elements'):
                                citation_children = child_elem.get_child_elements()
                                for citation_child in citation_children:
                                    tag = citation_child.get_tag()
                                    value = citation_child.get_value()
                                    
                                    if tag == "PAGE":
                                        source_data["page"] = value
                                    elif tag == "QUAY":
                                        source_data["quality"] = value
                            
                            sources.append(source_data)
        
        return sources
    except Exception as e:
        logger.error(f"Error getting sources: {e}")
        return []

def search_gedcom(query: str, gedcom_ctx: GedcomContext, search_type: str = "all", event_types: Dict[str, Any] = EVENT_TYPES) -> Dict[str, Any]:
    """Search across the GEDCOM file for people, places, events, etc."""
    if not gedcom_ctx.gedcom_parser:
        return {"people": [], "places": [], "events": [], "families": []}
    
    try:
        results = {"people": [], "places": [], "events": [], "families": []}
        query_lower = query.lower()
        
        # Search people
        if search_type in ["all", "people"]:
            for element_id, individual_elem in gedcom_ctx.individual_lookup.items():
                raw_name = individual_elem.get_name()
                name_str = " ".join(str(part) for part in raw_name if part) if isinstance(raw_name, tuple) else str(raw_name or "")
                if normalize_string(query) in normalize_string(name_str):
                    results["people"].append({"id": element_id, "name": name_str, "type": "person"})

        # Search families
        if search_type in ["all", "families"]:
            for element_id, family_elem in gedcom_ctx.family_lookup.items():
                if hasattr(family_elem, 'get_child_elements'):
                    family_text = ""
                    for child_elem in family_elem.get_child_elements():
                        if child_elem.get_tag() in ["NOTE", "PLAC"]:
                            family_text += " " + str(child_elem.get_value())
                    if query_lower in family_text.lower():
                        results["families"].append({"id": element_id, "type": "family", "match": "content"})

        # Search places and events
        if search_type in ["all", "places", "events"]:
            root_elements = gedcom_ctx.gedcom_parser.get_root_child_elements()
            for element in root_elements:
                element_type = element.get_tag()
                element_id = element.get_pointer()

                if hasattr(element, 'get_child_elements'):
                    for child_elem in element.get_child_elements():
                        tag = child_elem.get_tag()
                        value = child_elem.get_value()

                        # Search places
                        if search_type in ["all", "places"] and tag == "PLAC" and value and query_lower in value.lower():
                            results["places"].append({
                                "place": value,
                                "entity_id": element_id,
                                "entity_type": element_type
                            })

                        # Search events
                        if search_type in ["all", "events"] and tag in event_types:
                            event_info = event_types[tag]
                            # Search in event name and description
                            if (normalize_string(query) in normalize_string(event_info["name"]) or
                                normalize_string(query) in normalize_string(event_info["description"])):
                                results["events"].append({
                                    "event_type": tag,
                                    "event_name": event_info["name"],
                                    "entity_id": element_id,
                                    "entity_type": element_type
                                })
                            # Also search in event details (date, place, note)
                            else:
                                event_text = ""
                                if hasattr(child_elem, 'get_child_elements'):
                                    for event_detail in child_elem.get_child_elements():
                                        if event_detail.get_tag() in ["DATE", "PLAC", "NOTE"]:
                                            event_text += " " + str(event_detail.get_value())
                                if query_lower in event_text.lower():
                                    results["events"].append({
                                        "event_type": tag,
                                        "event_name": event_info["name"],
                                        "entity_id": element_id,
                                        "entity_type": element_type,
                                        "match_in": "details"
                                    })
        return results
    except Exception as e:
        # logger.error(f"Error searching GEDCOM: {e}")
        return {"people": [], "places": [], "events": [], "families": []}


def fuzzy_search_person_internal(name: str, gedcom_ctx, threshold: int = 80, max_results: int = 50) -> list:
    """Search for persons with fuzzy name matching.
    
    Args:
        name: Search term to match against person names
        gedcom_ctx: GEDCOM context
        threshold: Minimum similarity score (0-100)
        max_results: Maximum number of results to return
    """
    # Import fuzzy matching library
    try:
        from fuzzywuzzy import fuzz, process
    except ImportError:
        return [{"error": "fuzzywuzzy library not installed. Please install it with: pip install fuzzywuzzy python-levenshtein"}]
    
    if not gedcom_ctx.gedcom_parser:
        return [{"error": "No GEDCOM file loaded. Please load a GEDCOM file first."}]
    
    # Prepare list of names for fuzzy matching
    choices = []
    person_lookup = {}
    
    for person_id, individual in gedcom_ctx.individual_lookup.items():
        person_name = individual.get_name()
        if isinstance(person_name, tuple):
            person_name = " ".join(str(part) for part in person_name if part)
        else:
            person_name = str(person_name) if person_name else ""
        
        if person_name:  # Only include non-empty names
            choices.append(person_name)
            person_lookup[person_name] = person_id
    
    # Perform fuzzy search
    results = process.extract(name, choices, limit=max_results)
    
    # Filter by threshold and format results
    matches = []
    for match_name, score in results:
        if score >= threshold:
            person_id = person_lookup[match_name]
            person = get_person_details_internal(person_id, gedcom_ctx)
            if person:
                matches.append({
                    "person": person.model_dump(),
                    "similarity_score": score
                })
    
    return matches


