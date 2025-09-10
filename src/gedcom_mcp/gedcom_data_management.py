#!/usr/bin/env python3

from typing import List, Set, Dict, Any, Optional
from gedcom.element.individual import IndividualElement
from gedcom.element.family import FamilyElement
from gedcom.element.object import ObjectElement
from gedcom.parser import Parser
from gedcom.element.element import Element
from .gedcom_models import PersonDetails, PersonRelationships
from .gedcom_utils import _get_gedcom_tag_from_event_type
from .gedcom_context import _rebuild_lookups
from .gedcom_name_utils import format_gedcom_name_from_string



def _find_next_available_id(prefix: str, lookup_dict: Dict[str, Any]) -> str:
    """Find the next available ID that doesn't exist in any of the lookup dictionaries."""
    # Start with the length of the lookup dict + 1 for better performance
    id_num = len(lookup_dict) + 1
    new_id = f"{prefix}{id_num}@"
    
    # If this ID is already taken (e.g., due to deletions), increment until we find an unused one
    while new_id in lookup_dict:
        id_num += 1
        new_id = f"{prefix}{id_num}@"

    return new_id


def _add_person_internal(context, name: str, gender: str) -> str:
    """Add a new person to the GEDCOM data."""
    # Generate a new unique ID that doesn't exist in any lookup dictionary
    new_id = _find_next_available_id("@I", context.individual_lookup)

    # Format the name properly for GEDCOM storage
    formatted_name = format_gedcom_name_from_string(name)

    # Create new IndividualElement
    person = IndividualElement(level=0, pointer=new_id, tag="INDI", value="")
    person.new_child_element("NAME", value=formatted_name)
    person.new_child_element("SEX", value=gender)

    # Add the new person to the parser and lookups
    context.gedcom_parser.get_root_element().add_child_element(person)
    context.individual_lookup[new_id] = person
    return new_id


def _create_marriage_internal(context, husband_id: str, wife_id: str) -> str:
    """Create a marriage between two people."""
    # Generate a new unique family ID that doesn't exist in any lookup dictionary
    new_family_id = _find_next_available_id("@F", context.family_lookup)

    # Create the new family element
    family = FamilyElement(level=0, pointer=new_family_id, tag="FAM", value="")
    family.new_child_element("HUSB", value=husband_id)
    family.new_child_element("WIFE", value=wife_id)

    # Add family to parser and lookup
    context.gedcom_parser.get_root_element().add_child_element(family)
    context.family_lookup[new_family_id] = family

    # Update the FAMS tag on both individuals
    husband = context.individual_lookup[husband_id]
    wife = context.individual_lookup[wife_id]
    husband.new_child_element("FAMS", value=new_family_id)
    wife.new_child_element("FAMS", value=new_family_id)
    return new_family_id


def _add_child_to_family_internal(context, child_id: str, family_id: str) -> None:
    """Add a child to a family."""
    child = context.individual_lookup[child_id]
    family = context.family_lookup[family_id]

    # Add CHIL tag to family and FAMC tag to child
    family.new_child_element("CHIL", value=child_id)
    child.new_child_element("FAMC", value=family_id)

def _remove_child_from_family_internal(context, child_id: str, family_id: str) -> str:
    """Internal function to remove the link between a child and their family.

    Args:
        context: The GEDCOM context.
        child_id: The ID of the child.
        family_id: The ID of the family from which to remove the child.

    Returns:
        A confirmation or error message.
    """
    if not context.gedcom_parser or child_id not in context.individual_lookup:
        return f"Error: Child with ID {child_id} not found."
    if family_id not in context.family_lookup:
        return f"Error: Family with ID {family_id} not found."

    child = context.individual_lookup[child_id]
    family = context.family_lookup[family_id]

    try:
        # Remove CHIL tag from family
        child_element_to_remove = None
        for fam_child in family.get_child_elements():
            if fam_child.get_tag() == "CHIL" and fam_child.get_value() == child_id:
                child_element_to_remove = fam_child
                break
        if child_element_to_remove:
            family.get_child_elements().remove(child_element_to_remove)
        else:
            return f"Error: {child_id} is not a child in family {family_id}."

        # Remove FAMC tag from child
        famc_element_to_remove = None
        for famc in child.get_child_elements():
            if famc.get_tag() == "FAMC" and famc.get_value() == family_id:
                famc_element_to_remove = famc
                break
        if famc_element_to_remove:
            child.get_child_elements().remove(famc_element_to_remove)

        return f"Successfully removed {child_id} from family {family_id}."
    except Exception as e:
        return f"Error removing child from family: {e}"


def _remove_parent_from_family_internal(context, parent_id: str, family_id: str) -> str:
    """Internal function to remove the link between a parent and their family.
    
    This function removes the parent from the family record (removes HUSB/WIFE tag)
    and removes the FAMS tag from the parent's record.

    Args:
        context: The GEDCOM context.
        parent_id: The ID of the parent.
        family_id: The ID of the family from which to remove the parent.

    Returns:
        A confirmation or error message.
    """
    if not context.gedcom_parser or parent_id not in context.individual_lookup:
        return f"Error: Parent with ID {parent_id} not found."
    if family_id not in context.family_lookup:
        return f"Error: Family with ID {family_id} not found."

    parent = context.individual_lookup[parent_id]
    family = context.family_lookup[family_id]

    try:
        # Determine if this is a husband or wife in the family
        parent_role = None
        parent_element_to_remove = None
        
        # Find HUSB or WIFE tag in family that points to this parent
        for child in family.get_child_elements():
            if child.get_tag() in ["HUSB", "WIFE"] and child.get_value() == parent_id:
                parent_role = child.get_tag()
                parent_element_to_remove = child
                break
        
        if not parent_element_to_remove:
            return f"Error: {parent_id} is not a parent (husband or wife) in family {family_id}."

        # Remove the HUSB/WIFE tag from family
        family.get_child_elements().remove(parent_element_to_remove)

        # Remove FAMS tag from parent
        fams_element_to_remove = None
        for fams in parent.get_child_elements():
            if fams.get_tag() == "FAMS" and fams.get_value() == family_id:
                fams_element_to_remove = fams
                break
        
        if fams_element_to_remove:
            parent.get_child_elements().remove(fams_element_to_remove)

        return f"Successfully removed {parent_id} as {parent_role.lower()} from family {family_id}."
    except Exception as e:
        return f"Error removing parent from family: {e}"


def _remove_event_internal(context, entity_id: str, event_type: str, date_to_match: str) -> str:
    """Internal function to remove an event from a person or family.

    Args:
        context: The GEDCOM context.
        entity_id: The ID of the person or family.
        event_type: The type of event to remove (e.g., 'RESI').
        date_to_match: The date of the event to remove, for precise identification.

    Returns:
        A confirmation or error message.
    """
    if not context.gedcom_parser:
        return "Error: No GEDCOM file loaded."
    
    # Determine if this is a person or family entity
    is_person = entity_id in context.individual_lookup
    is_family = entity_id in context.family_lookup
    
    if not is_person and not is_family:
        return f"Error: Entity with ID {entity_id} not found."
    
    entity = context.individual_lookup.get(entity_id) if is_person else context.family_lookup.get(entity_id)
    
    event_type_tag = _get_gedcom_tag_from_event_type(event_type)
    if not event_type_tag:
        return f"Error: Invalid event type '{event_type}'. Please use a valid GEDCOM tag or human-readable name."

    try:
        # Find the event element to remove
        event_to_remove = None
        for child in entity.get_child_elements():
            if child.get_tag() == event_type_tag:
                # If a date was specified, check if it matches
                if date_to_match:
                    # Use get_child_value_by_tag instead of get_child_element_by_tag
                    date_value = child.get_child_value_by_tag("DATE")
                    if date_value and date_value == date_to_match:
                        event_to_remove = child
                        break
                else:
                    # If no date specified, remove the first matching event
                    event_to_remove = child
                    break
        
        if not event_to_remove:
            if date_to_match:
                return f"Error: No {event_type} event found with date '{date_to_match}' for entity {entity_id}."
            else:
                return f"Error: No {event_type} event found for entity {entity_id}."

        # Remove the event element
        entity.get_child_elements().remove(event_to_remove)
        
        return f"Successfully removed {event_type} event from entity {entity_id}."
    except Exception as e:
        return f"Error removing event: {e}"


def _remove_parents_internal(context, person_id: str) -> str:
    """Internal function to remove a person's parents by removing the person from their family of origin.
    
    This function takes a person's FAMC value (family of origin) and removes the person from that family.
    If a person has multiple FAMC tags (unusual but possible), it will remove them from the first one.
    
    Args:
        context: The GEDCOM context.
        person_id: The ID of the person whose parents should be removed.

    Returns:
        A confirmation or error message.
    """
    if not context.gedcom_parser or person_id not in context.individual_lookup:
        return f"Error: Person with ID {person_id} not found."

    person = context.individual_lookup[person_id]
    
    try:
        # Find the person's family of origin (FAMC)
        famc_element = None
        family_id = None
        for child in person.get_child_elements():
            if child.get_tag() == "FAMC":
                famc_element = child
                family_id = child.get_value()
                break
        
        if not famc_element:
            return f"Error: {person_id} does not have a family of origin (no FAMC tag)."
        
        if family_id not in context.family_lookup:
            return f"Error: Family with ID {family_id} not found."
        
        family = context.family_lookup[family_id]
        
        # Remove CHIL tag from family (using list remove as remove_child_element doesn't work with element objects)
        child_element_to_remove = None
        for fam_child in family.get_child_elements():
            if fam_child.get_tag() == "CHIL" and fam_child.get_value() == person_id:
                child_element_to_remove = fam_child
                break
        if child_element_to_remove:
            family.get_child_elements().remove(child_element_to_remove)
        else:
            return f"Error: {person_id} is not a child in family {family_id}."

        # Remove FAMC tag from person (using list remove as remove_child_element doesn't work with element objects)
        person.get_child_elements().remove(famc_element)
        
        return f"Successfully removed {person_id} from family {family_id} (removing their parents)."
    except Exception as e:
        return f"Error removing parents from person {person_id}: {e}"


def _update_event_details_internal(context, entity_id: str, event_type: str, new_date: str = None, new_place: str = None, old_date_to_match: str = None) -> str:
    """Internal function to update the date and/or place for an event associated with a person or family.
    
    If the event doesn't exist, it will be created. Family events (Marriage, divorce, etc.) 
    should be associated with Family entities, not Person entities.

    Args:
        context: The GEDCOM context.
        entity_id: The ID of the person or family.
        event_type: The type of event to update (e.g., 'BIRT', 'MARR', 'RESI').
        new_date: The new date for the event.
        new_place: The new place for the event.
        old_date_to_match: Required if there could be multiple events of the same type.
                           This specifies the date of the exact event to update.

    Returns:
        A confirmation or error message.
    """
    if not context.gedcom_parser:
        return "Error: No GEDCOM file loaded."
    
    # Determine if this is a person or family entity
    is_person = entity_id in context.individual_lookup
    is_family = entity_id in context.family_lookup
    
    if not is_person and not is_family:
        return f"Error: Entity with ID {entity_id} not found."
    
    entity = context.individual_lookup.get(entity_id) if is_person else context.family_lookup.get(entity_id)
    
    event_type_tag = _get_gedcom_tag_from_event_type(event_type)
    if not event_type_tag:
        return f"Error: Invalid event type '{event_type}'. Please use a valid GEDCOM tag or human-readable name."

    # Validate that family events are on family entities and person events on person entities
    family_events = {"MARR", "DIV", "ANUL", "ENGA", "MARB", "MARL", "MARC", "MARS"}
    if event_type_tag in family_events and is_person:
        return f"Error: Family event '{event_type}' must be associated with a family entity, not a person."
    elif event_type_tag not in family_events and not is_person and is_family:
        # This is a bit more complex - some events can be on either (e.g., RESI)
        # For now, we'll allow it but note that certain events should typically be on persons
        pass

    try:
        event_to_update = None
        # Find events with matching tag
        events = []
        for child in entity.get_child_elements():
            if child.get_tag() == event_type_tag:
                events.append(child)
        
        # If no events exist and we have data to set, create a new event
        if not events:
            if (new_date is not None and new_date != "") or (new_place is not None and new_place != ""):
                # Create new event
                event_to_update = entity.new_child_element(event_type_tag, value="")
                # Add to events list for consistent handling
                events.append(event_to_update)
            else:
                return f"Error: No '{event_type_tag}' event found for {entity_id} and no new data provided to create one."

        if len(events) > 1 and not old_date_to_match:
            return f"Error: Multiple '{event_type}' events exist. Please specify 'old_date_to_match' to identify which one to update."
        
        if old_date_to_match:
            for event in events:
                # Find DATE element within this event
                date_value = None
                for date_el in event.get_child_elements():
                    if date_el.get_tag() == "DATE":
                        date_value = date_el.get_value()
                        break
                if date_value == old_date_to_match:
                    event_to_update = event
                    break
        else:
            event_to_update = events[0]

        if not event_to_update:
            # If we still don't have an event to update but have new data, create one
            if (new_date is not None and new_date != "") or (new_place is not None and new_place != ""):
                event_to_update = entity.new_child_element(event_type_tag, value="")
            else:
                return f"Error: Could not find an '{event_type}' event with date '{old_date_to_match}'."

        # Update date if provided
        if new_date is not None:
            # Find existing DATE element or create new one
            date_el = None
            for child in event_to_update.get_child_elements():
                if child.get_tag() == "DATE":
                    date_el = child
                    break
            if date_el:
                date_el.set_value(new_date)
            else:
                event_to_update.new_child_element("DATE", value=new_date)
        
        # Update place if provided
        if new_place is not None:
            # Find existing PLAC element or create new one
            place_el = None
            for child in event_to_update.get_child_elements():
                if child.get_tag() == "PLAC":
                    place_el = child
                    break
            if place_el:
                place_el.set_value(new_place)
            else:
                event_to_update.new_child_element("PLAC", value=new_place)

        return f"Successfully updated event '{event_type}' for entity {entity_id}."
    except Exception as e:
        return f"Error updating event: {e}"


def _create_note_internal(context, note_text: str) -> str:
    """Create a new note with a unique ID."""
    # Generate a new unique note ID that doesn't exist in any lookup dictionary
    new_note_id = _find_next_available_id("@N", context.note_lookup)

    # Create new note element using Element (not ObjectElement which has default tag OBJE)
    note = Element(level=0, pointer=new_note_id, tag="NOTE", value=note_text)

    # Add note to parser and lookup
    context.gedcom_parser.get_root_element().add_child_element(note)
    context.note_lookup[new_note_id] = note
    
    return new_note_id


def batch_update_person_attributes(context, updates: list) -> dict:
    """Update multiple person attributes in a single operation.
    
    Args:
        context: The GEDCOM context
        updates: List of dictionaries containing person_id, attribute_tag, and new_value
        
    Returns:
        Dictionary with results of the batch operation
    """
    if not context.gedcom_parser:
        return {"error": "No GEDCOM file loaded. Please load a GEDCOM file first."}
    
    results = {
        "total_updates": len(updates),
        "successful": 0,
        "failed": 0,
        "errors": []
    }
    
    # Process updates
    for i, update in enumerate(updates):
        try:
            # Validate update structure
            if not isinstance(update, dict):
                results["failed"] += 1
                results["errors"].append({
                    "index": i,
                    "error": "Update must be a dictionary"
                })
                continue
            
            person_id = update.get("person_id")
            attribute_tag = update.get("attribute_tag")
            new_value = update.get("new_value")
            
            if not all([person_id, attribute_tag, new_value is not None]):
                results["failed"] += 1
                results["errors"].append({
                    "index": i,
                    "error": "Missing required fields: person_id, attribute_tag, new_value"
                })
                continue
            
            # Perform update
            result = _update_person_attribute_internal(context, person_id, attribute_tag, new_value)
            if "Error" in result:
                results["failed"] += 1
                results["errors"].append({
                    "index": i,
                    "person_id": person_id,
                    "error": result
                })
            else:
                results["successful"] += 1
                
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({
                "index": i,
                "error": str(e)
            })
    
    # Clear caches after successful updates
    if results["successful"] > 0:
        context.clear_caches()
        _rebuild_lookups(context)
    
    return results

    return new_note_id


def _add_note_to_entity_internal(context, entity_id: str, note_text: str = None, note_id: str = None) -> str:
    """Internal function to add a note to a person or family.
    
    If note_text is provided, creates a new note and adds a reference to it.
    If note_id is provided, creates a reference to an existing note.
    
    Args:
        context: The GEDCOM context.
        entity_id: The ID of the person or family to add the note to.
        note_text: The full text of the note.
        note_id: Optional. If provided, creates a reference to an existing note.
                 If None, creates a new note and references it.

    Returns:
        A confirmation or error message.
    """
    if not context.gedcom_parser:
        return "Error: No GEDCOM file loaded."

    entity = context.individual_lookup.get(entity_id) or context.family_lookup.get(entity_id)
    if not entity:
        return f"Error: Entity with ID {entity_id} not found."

    try:
        # If no note_id provided, create a new note
        if not note_id:
            note_id = _create_note_internal(context, note_text)
        else:
            # If note_id is provided, we're referencing an existing note
            # In this case, we should append the note_text to the existing note if provided
            if note_id in context.note_lookup and note_text:
                note = context.note_lookup[note_id]
                if note.get_value():
                    note.set_value(note.get_value() + "\n" + note_text)
                else:
                    note.set_value(note_text)

        # Create a reference to the note
        if note_id not in context.note_lookup:
            return f"Error: Note with ID {note_id} not found."
            
        entity.new_child_element("NOTE", value=note_id)
        return f"Successfully added note reference {note_id} to entity {entity_id}."
    except Exception as e:
        return f"Error adding note: {e}"


def _update_person_attribute_internal(context, person_id: str, attribute_tag: str, new_value: str) -> str:
    """Internal function to update a person's attribute.
    Args:
        context: The GEDCOM context.
        person_id (str): The ID of the person.
        attribute_tag (str): The tag of the attribute to update (e.g., 'OCCU' for occupation).
        new_value (str): The new value for the attribute.
    Returns:
        str: Success or error message.
    """
    if person_id not in context.individual_lookup:
        return f"Error: Person with ID {person_id} not found."

    individual = context.individual_lookup[person_id]
    
    try:
        found = False
        # Iterate through child elements to find the attribute
        for child in individual.get_child_elements():
            if child.get_tag() == attribute_tag:
                child.set_value(new_value)
                found = True
                break
        if not found:
            # Add new attribute if not found
            individual.new_child_element(attribute_tag, value=new_value)
        
        return f"Successfully updated attribute {attribute_tag} for person {person_id}."
    except Exception as e:
        return f"Error updating person attribute: {e}"

def _remove_person_attribute_internal(context, person_id: str, attribute_tag: str) -> str:
    """Internal function to remove an attribute from a person.
    Args:
        context: The GEDCOM context.
        person_id (str): The ID of the person.
        attribute_tag (str): The tag of the attribute to remove.
    Returns:
        str: Success or error message.
    """
    if person_id not in context.individual_lookup:
        return f"Error: Person with ID {person_id} not found."

    individual = context.individual_lookup[person_id]
    
    try:
        # Find and remove the attribute by iterating through child elements
        elements_to_remove = []
        for child in individual.get_child_elements():
            if child.get_tag() == attribute_tag:
                elements_to_remove.append(child)
        
        # Remove the elements
        for element in elements_to_remove:
            individual.get_child_elements().remove(element)
        
        if elements_to_remove:
            return f"Successfully removed attribute {attribute_tag} from person {person_id}."
        else:
            return f"Attribute {attribute_tag} not found for person {person_id}."
    except Exception as e:
        return f"Error removing person attribute: {e}"

def _update_person_details_internal(context, person_id: str, name: Optional[str] = None, gender: Optional[str] = None) -> str:
    """Internal function to update a person's name and gender.
    Args:
        context: The GEDCOM context.
        person_id (str): The ID of the person to update.
        name (Optional[str]): The new name of the person.
        gender (Optional[str]): The new gender of the person.
    Returns:
        str: Success or error message.
    """
    if person_id not in context.individual_lookup:
        return f"Error: Person with ID {person_id} not found."

    person = context.individual_lookup[person_id]

    try:
        if name is not None:
            name_element = None
            for child in person.get_child_elements():
                if child.get_tag() == "NAME":
                    name_element = child
                    break
            
            if name_element:
                givn_element = None
                surn_element = None
                for child_of_name in name_element.get_child_elements():
                    if child_of_name.get_tag() == "GIVN":
                        givn_element = child_of_name
                    elif child_of_name.get_tag() == "SURN":
                        surn_element = child_of_name
                
                if givn_element and surn_element:
                    parts = name.split('/')
                    if len(parts) == 3 and parts[0].strip() and parts[1].strip():
                        given_name = parts[0].strip()
                        surname = parts[1].strip()
                    elif len(parts) == 1:
                        name_parts = name.rsplit(' ', 1)
                        if len(name_parts) == 2:
                            given_name = name_parts[0].strip()
                            surname = name_parts[1].strip()
                        else:
                            given_name = name.strip()
                            surname = ""

                    givn_element.set_value(given_name)
                    surn_element.set_value(surname)
                    name_element.set_value("") 
                else:
                    formatted_name = format_gedcom_name_from_string(name)
                    name_element.set_value(formatted_name)
            else:
                formatted_name = format_gedcom_name_from_string(name)
                person.new_child_element("NAME", value=formatted_name)
        elif name == "":
            name_element = None
            for child in person.get_child_elements():
                if child.get_tag() == "NAME":
                    name_element = child
                    break
            if name_element:
                name_element.set_value("")
        
        if gender is not None:
            if gender.upper() not in ['M', 'F']:
                return "Error: Gender must be 'M' or 'F'."
            sex_element = None
            for child in person.get_child_elements():
                if child.get_tag() == "SEX":
                    sex_element = child
                    break
            if sex_element:
                sex_element.set_value(gender.upper())
            else:
                person.new_child_element("SEX", value=gender.upper())
        
        return f"Successfully updated details for person {person_id}."
    except Exception as e:
        return f"Error updating person details: {e}"

def _create_source_internal(context, title: str = "", author: str = "", publication: str = ""):

    """Create a new source with a unique ID."""
    # Generate a new unique source ID that doesn't exist in any lookup dictionary
    new_source_id = _find_next_available_id("@S", context.source_lookup)

    # Create new source element using Element (not ObjectElement which has default tag OBJE)
    source = Element(level=0, pointer=new_source_id, tag="SOUR", value=title)

    # Add optional details
    if author:
        source.new_child_element("AUTH", value=author)
    if publication:
        source.new_child_element("PUBL", value=publication)

    # Add source to parser and lookup
    context.gedcom_parser.get_root_element().add_child_element(source)
    context.source_lookup[new_source_id] = source
    return new_source_id


def _delete_note_entity_internal(context, note_id: str) -> str:
    """Internal function to delete a note entity by its ID.
    
    Args:
        context: The GEDCOM context.
        note_id: The ID of the note to delete (e.g., '@N123@').

    Returns:
        A confirmation or error message.
    """
    if not context.gedcom_parser:
        return "Error: No GEDCOM file loaded."
    
    if note_id not in context.note_lookup:
        return f"Error: Note with ID {note_id} not found."

    try:
        # Remove the note element from the parser
        note_element = context.note_lookup[note_id]
        context.gedcom_parser.get_root_element().get_child_elements().remove(note_element)
        
        # Remove from note lookup
        del context.note_lookup[note_id]
        
        return f"Successfully deleted note entity {note_id}."
    except Exception as e:
        return f"Error deleting note entity {note_id}: {e}"


def _new_empty_gedcom_internal(context) -> str:
    """Internal function to create a new empty GEDCOM context with a proper HEAD element."""
    # Create a new empty parser
    context.gedcom_parser = Parser()
    
    # Create a proper HEAD element as the first root child
    head_element = context.gedcom_parser.get_root_element().new_child_element("HEAD")
    
    # Add required HEAD sub-elements
    # GEDCOM version
    gedc_element = head_element.new_child_element("GEDC")
    gedc_element.new_child_element("VERS", value="5.5.1")
    gedc_element.new_child_element("FORM", value="LINEAGE-LINKED")
    
    # Character set
    head_element.new_child_element("CHAR", value="UTF-8")
    
    # Add source information for this software
    sour_element = head_element.new_child_element("SOUR", value="GedcomMCP")
    sour_element.new_child_element("VERS", value="1.0a1")
    sour_element.new_child_element("NAME", value="GedcomMCP - Genealogy MCP Server")
    
    # Reset all other attributes to their default values
    context.gedcom_file_path = None
    context.individual_lookup.clear()
    context.family_lookup.clear()
    context.source_lookup.clear()
    context.note_lookup.clear()
    context.person_relationships_cache.clear()
    context.person_details_cache.clear()
    context.neighbor_cache.clear()
    
    return "Successfully created new empty GEDCOM context"
