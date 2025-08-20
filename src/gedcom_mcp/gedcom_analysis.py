#!/usr/bin/env python3

import re
import time
from collections import deque
from typing import List, Set, Dict, Any, Optional
from .gedcom_context import GedcomContext
from datetime import datetime
from collections import Counter # Added this import
from gedcom.element.individual import IndividualElement
from .gedcom_data_access import get_person_details_internal
from .gedcom_utils import normalize_string, _get_gedcom_tag_from_attribute_type, _normalize_genealogy_date, _normalize_genealogy_place
from .gedcom_constants import EVENT_TYPES, ATTRIBUTE_TYPES

# New function starts here
def _get_attribute_statistics_internal(gedcom_ctx: GedcomContext, attribute_type: str) -> dict:
    """
    Internal function to retrieve statistics for a given GEDCOM attribute type
    (e.g., 'OCCU' or 'Occupation') across all individuals and families.
    Returns a dictionary where keys are attribute values and values are their counts.
    """
    if not gedcom_ctx.gedcom_parser:
        return {"error": "No GEDCOM file loaded in context."}

    # Resolve the attribute_type to its canonical GEDCOM tag
    attribute_tag = _get_gedcom_tag_from_attribute_type(attribute_type)
    if not attribute_tag:
        return {"error": f"Invalid or unsupported attribute type: '{attribute_type}'."}

    attribute_counts = Counter()

    # Iterate through individuals
    for individual_id in gedcom_ctx.individual_lookup:
        individual_element: IndividualElement = gedcom_ctx.individual_lookup[individual_id]
        for child_element in individual_element.get_child_elements():
            if child_element.get_tag() == attribute_tag:
                attribute_value = child_element.get_value()
                if attribute_value:
                    attribute_counts[attribute_value] += 1

    # Iterate through families (if the attribute can appear in families, though less common for OCCU/RELI)
    for family_id in gedcom_ctx.family_lookup:
        family_element: FamilyElement = gedcom_ctx.family_lookup[family_id]
        for child_element in family_element.get_child_elements():
            if child_element.get_tag() == attribute_tag:
                attribute_value = child_element.get_value()
                if attribute_value:
                    attribute_counts[attribute_value] += 1

    return dict(attribute_counts)



def _get_statistics_internal(gedcom_ctx: GedcomContext) -> Dict[str, Any]:
    """Get comprehensive statistics about the GEDCOM file"""
    if not gedcom_ctx.gedcom_parser:
        return {}
    
    try:
        # PERFORMANCE OPTIMIZATION: Use lookup dictionaries for instant counts
        stats = {
            "total_individuals": len(gedcom_ctx.individual_lookup),
            "total_families": len(gedcom_ctx.family_lookup),
            "total_sources": 0,
            "total_notes": 0,
            "total_repositories": 0,
            "living_individuals": 0,
            "deceased_individuals": 0,
            "males": 0,
            "females": 0,
            "unknown_gender": 0,
            "event_counts": {},
            "place_counts": {},
            "surname_counts": {},
            "birth_year_range": {"earliest": None, "latest": None},
            "death_year_range": {"earliest": None, "latest": None}
        }
        
        # Process individuals from lookup dictionary
        for individual_elem in gedcom_ctx.individual_lookup.values():
                
                # Get gender
                if hasattr(individual_elem, 'get_child_elements'):
                    child_elements = individual_elem.get_child_elements()
                    has_death = False
                    
                    for child_elem in child_elements:
                        tag = child_elem.get_tag()
                        value = child_elem.get_value()
                        
                        if tag == "SEX":
                            if value == "M":
                                stats["males"] += 1
                            elif value == "F":
                                stats["females"] += 1
                            else:
                                stats["unknown_gender"] += 1
                        
                        elif tag == "DEAT":
                            has_death = True
                        
                        elif tag in EVENT_TYPES:
                            event_name = EVENT_TYPES[tag]["name"]
                            stats["event_counts"][event_name] = stats["event_counts"].get(event_name, 0) + 1
                            
                            # Extract dates for birth/death ranges
                            if hasattr(child_elem, 'get_child_elements'):
                                event_children = child_elem.get_child_elements()
                                for event_child in event_children:
                                    if event_child.get_tag() == "DATE":
                                        date_str = event_child.get_value()
                                        # Try to extract year
                                        year_match = re.search(r'\b(1[0-9]{3}|20[0-9]{2})\b', date_str)
                                        if year_match:
                                            year = int(year_match.group(0))
                                            
                                            if tag == "BIRT":
                                                if stats["birth_year_range"]["earliest"] is None or year < stats["birth_year_range"]["earliest"]:
                                                    stats["birth_year_range"]["earliest"] = year
                                                if stats["birth_year_range"]["latest"] is None or year > stats["birth_year_range"]["latest"]:
                                                    stats["birth_year_range"]["latest"] = year
                                            
                                            elif tag == "DEAT":
                                                if stats["death_year_range"]["earliest"] is None or year < stats["death_year_range"]["earliest"]:
                                                    stats["death_year_range"]["earliest"] = year
                                                if stats["death_year_range"]["latest"] is None or year > stats["death_year_range"]["latest"]:
                                                    stats["death_year_range"]["latest"] = year
                        
                        elif tag == "PLAC":
                            place = value
                            stats["place_counts"][place] = stats["place_counts"].get(place, 0) + 1
                    
                    if has_death:
                        stats["deceased_individuals"] += 1
                    else:
                        stats["living_individuals"] += 1
                
                # Get surname
                raw_name = individual_elem.get_name()
                if isinstance(raw_name, tuple):
                    name_str = " ".join(str(part) for part in raw_name if part)
                else:
                    name_str = str(raw_name) if raw_name else ""
                
                # Extract surname (usually after /)
                if "/" in name_str:
                    parts = name_str.split("/")
                    if len(parts) > 1:
                        surname = parts[1].strip()
                        if surname:
                            stats["surname_counts"][surname] = stats["surname_counts"].get(surname, 0) + 1
            
        # Process families from lookup dictionary (already counted above)
        # Process other element types that aren't in our lookup dictionaries
        root_elements = gedcom_ctx.gedcom_parser.get_root_child_elements()
        for element in root_elements:
            element_type = element.get_tag()
            
            if element_type == "SOUR":
                stats["total_sources"] += 1
            elif element_type == "NOTE":
                stats["total_notes"] += 1
            elif element_type == "REPO":
                stats["total_repositories"] += 1
        
        # Sort counts by frequency
        stats["surname_counts"] = dict(sorted(stats["surname_counts"].items(), key=lambda x: x[1], reverse=True)[:20])
        stats["place_counts"] = dict(sorted(stats["place_counts"].items(), key=lambda x: x[1], reverse=True)[:20])
        stats["event_counts"] = dict(sorted(stats["event_counts"].items(), key=lambda x: x[1], reverse=True))
        
        return stats
    except Exception as e:
        # We'll need to import logger when this function is used
        # logger.error(f"Error getting statistics: {e}")
        return {}

    """
    Internal function to retrieve statistics for a given GEDCOM attribute type
    (e.g., 'OCCU' or 'Occupation') across all individuals and families.
    Returns a dictionary where keys are attribute values and values are their counts.
    """
    if not gedcom_ctx.gedcom_parser:
        return {"error": "No GEDCOM file loaded in context."}

    # Resolve the attribute_type to its canonical GEDCOM tag
    attribute_tag = _get_gedcom_tag_from_attribute_type(attribute_type)
    if not attribute_tag:
        return {"error": f"Invalid or unsupported attribute type: '{attribute_type}'."}

    attribute_counts = Counter()

    # Iterate through individuals
    for individual_id in gedcom_ctx.individual_lookup:
        individual_element: IndividualElement = gedcom_ctx.individual_lookup[individual_id]
        for child_element in individual_element.get_child_elements():
            if child_element.get_tag() == attribute_tag:
                attribute_value = child_element.get_value()
                if attribute_value:
                    attribute_counts[attribute_value] += 1

    # Iterate through families (if the attribute can appear in families, though less common for OCCU/RELI)
    for family_id in gedcom_ctx.family_lookup:
        family_element: FamilyElement = gedcom_ctx.family_lookup[family_id]
        for child_element in family_element.get_child_elements():
            if child_element.get_tag() == attribute_tag:
                attribute_value = child_element.get_value()
                if attribute_value:
                    attribute_counts[attribute_value] += 1

    return dict(attribute_counts)
# New function ends here

def _get_statistics_internal(gedcom_ctx: GedcomContext) -> Dict[str, Any]:
    """Get comprehensive statistics about the GEDCOM file"""
    if not gedcom_ctx.gedcom_parser:
        return {}
    
    try:
        # PERFORMANCE OPTIMIZATION: Use lookup dictionaries for instant counts
        stats = {
            "total_individuals": len(gedcom_ctx.individual_lookup),
            "total_families": len(gedcom_ctx.family_lookup),
            "total_sources": 0,
            "total_notes": 0,
            "total_repositories": 0,
            "living_individuals": 0,
            "deceased_individuals": 0,
            "males": 0,
            "females": 0,
            "unknown_gender": 0,
            "event_counts": {},
            "place_counts": {},
            "surname_counts": {},
            "birth_year_range": {"earliest": None, "latest": None},
            "death_year_range": {"earliest": None, "latest": None}
        }
        
        # Process individuals from lookup dictionary
        for individual_elem in gedcom_ctx.individual_lookup.values():
                
                # Get gender
                if hasattr(individual_elem, 'get_child_elements'):
                    child_elements = individual_elem.get_child_elements()
                    has_death = False
                    
                    for child_elem in child_elements:
                        tag = child_elem.get_tag()
                        value = child_elem.get_value()
                        
                        if tag == "SEX":
                            if value == "M":
                                stats["males"] += 1
                            elif value == "F":
                                stats["females"] += 1
                            else:
                                stats["unknown_gender"] += 1
                        
                        elif tag == "DEAT":
                            has_death = True
                        
                        elif tag in EVENT_TYPES:
                            event_name = EVENT_TYPES[tag]["name"]
                            stats["event_counts"][event_name] = stats["event_counts"].get(event_name, 0) + 1
                            
                            # Extract dates for birth/death ranges
                            if hasattr(child_elem, 'get_child_elements'):
                                event_children = child_elem.get_child_elements()
                                for event_child in event_children:
                                    if event_child.get_tag() == "DATE":
                                        date_str = event_child.get_value()
                                        # Try to extract year
                                        year_match = re.search(r'\b(1[0-9]{3}|20[0-9]{2})\b', date_str)
                                        if year_match:
                                            year = int(year_match.group(0))
                                            
                                            if tag == "BIRT":
                                                if stats["birth_year_range"]["earliest"] is None or year < stats["birth_year_range"]["earliest"]:
                                                    stats["birth_year_range"]["earliest"] = year
                                                if stats["birth_year_range"]["latest"] is None or year > stats["birth_year_range"]["latest"]:
                                                    stats["birth_year_range"]["latest"] = year
                                            
                                            elif tag == "DEAT":
                                                if stats["death_year_range"]["earliest"] is None or year < stats["death_year_range"]["earliest"]:
                                                    stats["death_year_range"]["earliest"] = year
                                                if stats["death_year_range"]["latest"] is None or year > stats["death_year_range"]["latest"]:
                                                    stats["death_year_range"]["latest"] = year
                        
                        elif tag == "PLAC":
                            place = value
                            stats["place_counts"][place] = stats["place_counts"].get(place, 0) + 1
                    
                    if has_death:
                        stats["deceased_individuals"] += 1
                    else:
                        stats["living_individuals"] += 1
                
                # Get surname
                raw_name = individual_elem.get_name()
                if isinstance(raw_name, tuple):
                    name_str = " ".join(str(part) for part in raw_name if part)
                else:
                    name_str = str(raw_name) if raw_name else ""
                
                # Extract surname (usually after /)
                if "/" in name_str:
                    parts = name_str.split("/")
                    if len(parts) > 1:
                        surname = parts[1].strip()
                        if surname:
                            stats["surname_counts"][surname] = stats["surname_counts"].get(surname, 0) + 1
            
        # Process families from lookup dictionary (already counted above)
        # Process other element types that aren't in our lookup dictionaries
        root_elements = gedcom_ctx.gedcom_parser.get_root_child_elements()
        for element in root_elements:
            element_type = element.get_tag()
            
            if element_type == "SOUR":
                stats["total_sources"] += 1
            elif element_type == "NOTE":
                stats["total_notes"] += 1
            elif element_type == "REPO":
                stats["total_repositories"] += 1
        
        # Sort counts by frequency
        stats["surname_counts"] = dict(sorted(stats["surname_counts"].items(), key=lambda x: x[1], reverse=True)[:20])
        stats["place_counts"] = dict(sorted(stats["place_counts"].items(), key=lambda x: x[1], reverse=True)[:20])
        stats["event_counts"] = dict(sorted(stats["event_counts"].items(), key=lambda x: x[1], reverse=True))
        
        return stats
    except Exception as e:
        # We'll need to import logger when this function is used
        # logger.error(f"Error getting statistics: {e}")
        return {}


def _get_timeline_internal(person_id: str, gedcom_ctx: GedcomContext) -> List[Dict[str, Any]]:
    """Generate a chronological timeline of events for a person"""
    events = _get_events_internal(person_id, gedcom_ctx)
    
    # Sort events by date if possible
    # This is a simple implementation - a more robust solution would parse dates properly
    def extract_year(date_str):
        if not date_str:
            return 9999  # Put events with no date at the end
        # Try to extract a 4-digit year from the date string
        year_match = re.search(r'\b(1[89]|20)\d{2}\b', date_str)
        if year_match:
            return int(year_match.group(0))
        return 9999  # Put events with no parseable date at the end
    
    events.sort(key=lambda x: extract_year(x.get("date", "")))
    return events


def _get_ancestors_internal(pid: str, gedcom_ctx: GedcomContext, generations: int = 3, format: str = 'nested'):
    """
    Get ancestors of a person for a specified number of generations.

    Args:
        pid: The ID of the person to get ancestors for.
        gedcom_ctx: The GEDCOM context.
        generations: The number of generations to retrieve.
        format: The format of the output ('nested' or 'flat').

    Returns:
        A dictionary or a list of ancestors, depending on the format.
    """
    if format == 'flat':
        ancestors = []
        _collect_ancestors_recursive(pid, 1, generations, ancestors, gedcom_ctx)
        return ancestors
    else:
        return _get_ancestors_recursive(pid, 1, generations, gedcom_ctx)

def _get_descendants_internal(pid: str, gedcom_ctx: GedcomContext, generations: int = 3, format: str = 'nested'):
    """
    Get descendants of a person for a specified number of generations.

    Args:
        pid: The ID of the person to get descendants for.
        gedcom_ctx: The GEDCOM context.
        generations: The number of generations to retrieve.
        format: The format of the output ('nested' or 'flat').

    Returns:
        A dictionary or a list of descendants, depending on the format.
    """
    if format == 'flat':
        descendants = []
        _collect_descendants_recursive(pid, 1, generations, descendants, gedcom_ctx)
        return descendants
    else:
        return _get_descendants_recursive(pid, 1, generations, gedcom_ctx)



    if current_level > max_levels:
        return
    
    # Add current person to the list with their level
    person_entry = (pid, current_level)
    if person_entry not in collected:
        collected.append(person_entry)
    
    # Get children and recurse
    if current_level < max_levels:
        person = get_person_details_internal(pid, gedcom_ctx)
        if person and person.children:
            for child_id in person.children:
                collect_descendants_recursive(child_id, current_level + 1, max_levels, collected, gedcom_ctx)


def get_living_status(person_id: str, gedcom_ctx: GedcomContext) -> str:
    """Determine if a person is likely living or deceased based on available data"""
    person = get_person_details_internal(person_id, gedcom_ctx)
    if not person:
        return f"Person not found: {person_id}"
    
    result = f"Living status for {person.name} ({person.id}):\\n"
    
    if person.death_date:
        result += f"Status: Deceased (died {person.death_date})"
        if person.death_place:
            result += f" in {person.death_place}"
    elif person.birth_date:
        # Try to estimate age if birth date is available
        # Extract year from birth date (simple regex)
        year_match = re.search(r'\b(1[0-9]\d{2}|20\d{2})\b', person.birth_date)
        if year_match:
            birth_year = int(year_match.group(1))
            current_year = datetime.now().year
            estimated_age = current_year - birth_year
            
            if estimated_age > 120:
                result += f"Status: Likely deceased (would be ~{estimated_age} years old)"
            elif estimated_age > 100:
                result += f"Status: Possibly living but very elderly (~{estimated_age} years old)"
            else:
                result += f"Status: Possibly living (~{estimated_age} years old)"
        else:
            result += "Status: Unknown (birth date format unclear)"
    else:
        result += "Status: Unknown (no birth or death information available)"
    
    return result


def _get_family_tree_summary_internal(person_id: str, gedcom_ctx: GedcomContext) -> str:
    """Get a concise family tree summary showing parents, spouse(s), and children"""
    person = get_person_details_internal(person_id, gedcom_ctx)
    if not person:
        return f"Person not found: {person_id}"
    
    result = f"Family Tree Summary for {person.name} ({person.id}):\n"

    
    # Add basic info
    if person.birth_date or person.birth_place:
        result += f"Born: {person.birth_date or 'Unknown date'}"
        if person.birth_place:
            result += f" in {person.birth_place}"
        result += "\n"
    
    if person.death_date or person.death_place:
        result += f"Died: {person.death_date or 'Unknown date'}"
        if person.death_place:
            result += f" in {person.death_place}"
        result += "\n"
    
    if person.occupation:
        result += f"Occupation: {person.occupation}\n"
    
    result += "\n"
    
    # Parents
    if person.parents:
        result += "Parents:\n"
        for parent_id in person.parents:
            parent = get_person_details_internal(parent_id, gedcom_ctx)
            if parent:
                result += f"  - {parent.name} ({parent.id})\n"
    else:
        result += "Parents: Unknown\n"
    
    # Spouses
    if person.spouses:
        result += "\nSpouse(s):\n"
        for spouse_id in person.spouses:
            spouse = get_person_details_internal(spouse_id, gedcom_ctx)
            if spouse:
                result += f"  - {spouse.name} ({spouse.id})\n"
    else:
        result += "\nSpouse(s): None recorded\n"
    
    # Children
    if person.children:
        result += f"\nChildren ({len(person.children)}):\n"
        for child_id in person.children:
            child = get_person_details_internal(child_id, gedcom_ctx)
            if child:
                result += f"  - {child.name} ({child.id})\n"
    else:
        result += "\nChildren: None recorded\n"
    
    return result


def _get_surname_statistics_internal(gedcom_ctx: GedcomContext, surname: str = None) -> str:
    """Get statistics about surnames in the GEDCOM file"""
    try:
        # PERFORMANCE OPTIMIZATION: Use lookup dictionary instead of iterating through all elements
        surname_counts = {}
        total_people = len(gedcom_ctx.individual_lookup)
        
        for individual_elem in gedcom_ctx.individual_lookup.values():
            
            raw_name = individual_elem.get_name()
            
            if isinstance(raw_name, tuple):
                name_str = " ".join(str(part) for part in raw_name if part)
            elif raw_name:
                name_str = str(raw_name)
            else:
                continue
                
                # Extract surname (typically after the last space or in //)
                surname_match = re.search(r'/([^/]+)/', name_str)
                if surname_match:
                    surname_found = surname_match.group(1).strip()
                else:
                    # Fallback: assume last word is surname
                    parts = name_str.split()
                    surname_found = parts[-1] if parts else "Unknown"
                
                surname_counts[surname_found] = surname_counts.get(surname_found, 0) + 1
        
        if surname:
            # Return info about specific surname
            count = surname_counts.get(surname, 0)
            return f"Surname '{surname}': {count} individuals ({count/total_people*100:.1f}% of total)"
        else:
            # Return top surnames
            sorted_surnames = sorted(surname_counts.items(), key=lambda x: x[1], reverse=True)
            result = f"Surname Statistics (Total: {total_people} individuals):\n"
            
            for i, (surname, count) in enumerate(sorted_surnames[:20], 1):
                percentage = count / total_people * 100
                result += f"{i:2d}. {surname}: {count} individuals ({percentage:.1f}%)\n"
            
            if len(sorted_surnames) > 20:
                result += f"\n... and {len(sorted_surnames) - 20} more surnames"
            
            return result
    
    except Exception as e:
        return f"Error getting surname statistics: {e}"


def _get_date_range_analysis_internal(gedcom_ctx: GedcomContext) -> str:
    """Analyze the date ranges in the GEDCOM file to understand the time period covered"""
    try:
        # PERFORMANCE OPTIMIZATION: Use lookup dictionary instead of iterating through all elements
        birth_years = []
        death_years = []
        marriage_years = []
        
        for individual_elem in gedcom_ctx.individual_lookup.values():
            # Extract birth year
            birth_facts = individual_elem.get_birth_data()
            if birth_facts:
                birth_date = birth_facts[0] if isinstance(birth_facts, tuple) else str(birth_facts)
                if birth_date:
                    year_match = re.search(r'\b(1[0-9]\d{2}|20\d{2})\b', str(birth_date))
                    if year_match:
                        birth_years.append(int(year_match.group(1)))
            
            # Extract death year
            death_facts = individual_elem.get_death_data()
            if death_facts:
                death_date = death_facts[0] if isinstance(death_facts, tuple) else str(death_facts)
                if death_date:
                    year_match = re.search(r'\b(1[0-9]\d{2}|20\d{2})\b', str(death_date))
                    if year_match:
                        death_years.append(int(year_match.group(1)))
        
        # Process family elements for marriage years using family lookup dictionary
        for family_elem in gedcom_ctx.family_lookup.values():
            # Extract marriage year
            marriage_data = family_elem.get_marriage_data()
            if marriage_data:
                marriage_date = marriage_data[0] if isinstance(marriage_data, tuple) else str(marriage_data)
                if marriage_date:
                    year_match = re.search(r'\b(1[0-9]\d{2}|20\d{2})\b', str(marriage_date))
                    if year_match:
                        marriage_years.append(int(year_match.group(1)))
        
        result = "Date Range Analysis:\n"
        
        if birth_years:
            result += f"Birth Years: {min(birth_years)} - {max(birth_years)} ({len(birth_years)} records)\n"
            result += f"  Average birth year: {sum(birth_years) // len(birth_years)}\n"
        
        if death_years:
            result += f"Death Years: {min(death_years)} - {max(death_years)} ({len(death_years)} records)\n"
            result += f"  Average death year: {sum(death_years) // len(death_years)}\n"
        
        if marriage_years:
            result += f"Marriage Years: {min(marriage_years)} - {max(marriage_years)} ({len(marriage_years)} records)\n"
            result += f"  Average marriage year: {sum(marriage_years) // len(marriage_years)}\n"
        
        # Calculate generations
        if birth_years:
            span = max(birth_years) - min(birth_years)
            estimated_generations = span // 25  # Rough estimate: 25 years per generation
            result += f"\nEstimated time span: {span} years (~{estimated_generations} generations)\n"
        
        return result
    
    except Exception as e:
        return f"Error analyzing date ranges: {e}"


def _find_potential_duplicates_internal(gedcom_ctx: GedcomContext) -> str:
    """Find potential duplicate people based on similar names and dates"""
    try:
        # PERFORMANCE OPTIMIZATION: Use lookup dictionary instead of iterating through all elements
        # Collect all people with their basic info
        people = []
        
        for person_id, individual_elem in gedcom_ctx.individual_lookup.items():
            raw_name = individual_elem.get_name()
            
            if isinstance(raw_name, tuple):
                name_str = " ".join(str(part) for part in raw_name if part)
            elif raw_name:
                name_str = str(raw_name)
            else:
                name_str = "Unknown"
            
            # Get birth year
            birth_year = None
            birth_facts = individual_elem.get_birth_data()
            if birth_facts:
                birth_date = birth_facts[0] if isinstance(birth_facts, tuple) else str(birth_facts)
                if birth_date:
                    year_match = re.search(r'\b(1[0-9]\d{2}|20\d{2})\b', str(birth_date))
                    if year_match:
                        birth_year = int(year_match.group(1))
            
            people.append({
                'id': person_id,
                'name': name_str,
                'birth_year': birth_year
            })
        
        # Find potential duplicates
        duplicates = []
        for i, person1 in enumerate(people):
            for person2 in people[i+1:]:
                # Compare names (simple similarity)
                name1_clean = normalize_string(person1['name'].replace('/', '').strip())
                name2_clean = normalize_string(person2['name'].replace('/', '').strip())
                
                # Check if names are very similar
                if name1_clean == name2_clean:
                    similarity_score = 100
                elif len(name1_clean) > 3 and len(name2_clean) > 3:
                    # Simple substring check
                    if name1_clean in name2_clean or name2_clean in name1_clean:
                        similarity_score = 80
                    else:
                        continue
                else:
                    continue
                
                # Check birth years
                year_diff = None
                if person1['birth_year'] and person2['birth_year']:
                    year_diff = abs(person1['birth_year'] - person2['birth_year'])
                
                # Consider it a potential duplicate if names match and birth years are close
                if similarity_score >= 80 and (year_diff is None or year_diff <= 2):
                    duplicates.append({
                        'person1': person1,
                        'person2': person2,
                        'similarity': similarity_score,
                        'year_diff': year_diff
                    })
        
        if duplicates:
            result = f"Potential Duplicates Found ({len(duplicates)}):\n"

            for i, dup in enumerate(duplicates[:20], 1):  # Limit to first 20
                result += f"{i}. {dup['person1']['name']} ({dup['person1']['id']})\n"
                result += f"   {dup['person2']['name']} ({dup['person2']['id']})\n"
                if dup['year_diff'] is not None:
                    result += f"   Birth year difference: {dup['year_diff']} years\n"
                result += f"   Name similarity: {dup['similarity']}%\n"

            
            if len(duplicates) > 20:
                result += f"... and {len(duplicates) - 20} more potential duplicates"
        else:
            result = "No potential duplicates found."
        
        return result
    
    except Exception as e:
        return f"Error finding duplicates: {e}"


def get_common_ancestors_internal(person_ids_list: List[str], gedcom_ctx: GedcomContext, max_level: int = 20) -> Dict[str, Any]:
    """Internal function to find common ancestors for a list of people"""
    if not gedcom_ctx.gedcom_parser:
        raise ValueError("No GEDCOM file loaded")
    
    if len(person_ids_list) < 2:
        raise ValueError("At least 2 person IDs are required to find common ancestors")
    
    start_time = time.time()
    
    # Validate all people exist
    people = []
    for person_id in person_ids_list:
        person = get_person_details_internal(person_id, gedcom_ctx)
        if not person:
            raise ValueError(f"Person not found: {person_id}")
        people.append(person)
    
    # We'll need to import logger when this function is used
    # logger.info(f"Finding common ancestors for {len(person_ids_list)} people up to level {max_level}")
    
    # Get ancestors for each person using BFS
    def get_all_ancestors_bfs(person_id, max_depth):
        """Get all ancestors using BFS with level tracking"""
        ancestors = {}  # person_id -> level
        queue = deque([(person_id, 0)])
        visited = set()
        
        while queue:
            current_id, level = queue.popleft()
            
            if current_id in visited or level > max_depth:
                continue
                
            visited.add(current_id)
            ancestors[current_id] = level
            
            person = get_person_details_internal(current_id, gedcom_ctx)
            if person and person.parents:
                for parent_id in person.parents:
                    if parent_id not in visited:
                        queue.append((parent_id, level + 1))
        
        return ancestors
    
    # Get ancestors for all people
    all_ancestors = {}
    ancestor_counts = []
    
    for person_id in person_ids_list:
        ancestors = get_all_ancestors_bfs(person_id, max_level)
        all_ancestors[person_id] = ancestors
        ancestor_counts.append(len(ancestors))
        # We'll need to import logger when this function is used
        # logger.info(f"Found {len(ancestors)} ancestors for {person_id}")
    
    # Find common ancestors (intersection of all ancestor sets)
    if not all_ancestors:
        raise ValueError("No ancestors found for any person")
    
    # Start with first person's ancestors, then intersect with others
    common_ancestor_ids = set(all_ancestors[person_ids_list[0]].keys())
    for person_id in person_ids_list[1:]:
        common_ancestor_ids &= set(all_ancestors[person_id].keys())
    
    # Build detailed common ancestor information
    common_ancestors = []
    for ancestor_id in common_ancestor_ids:
        ancestor = get_person_details_internal(ancestor_id, gedcom_ctx)
        if ancestor:
            ancestor_info = {
                "id": ancestor_id,
                "name": ancestor.name,
                "birth_date": ancestor.birth_date,
                "death_date": ancestor.death_date,
                "levels": {}  # person_id -> level
            }
            
            # Get the level for each person
            for person_id in person_ids_list:
                ancestor_info["levels"][person_id] = all_ancestors[person_id][ancestor_id]
            
            # Calculate minimum and maximum levels
            levels = list(ancestor_info["levels"].values())
            ancestor_info["min_level"] = min(levels)
            ancestor_info["max_level"] = max(levels)
            ancestor_info["level_range"] = max(levels) - min(levels)
            
            common_ancestors.append(ancestor_info)
    
    # Sort by minimum level (closest common ancestors first)
    common_ancestors.sort(key=lambda x: (x["min_level"], x["max_level"]))
    
    search_time = time.time() - start_time
    
    # Build result
    result = {
        "people": [
            {
                "id": person_id,
                "name": get_person_details_internal(person_id, gedcom_ctx).name
            } for person_id in person_ids_list
        ],
        "common_ancestors": common_ancestors,
        "total_common_ancestors": len(common_ancestors),
        "statistics": {
            "people_count": len(person_ids_list),
            "max_level_searched": max_level,
            "ancestor_counts": dict(zip(person_ids_list, ancestor_counts)),
            "search_time": search_time,
            "closest_common_ancestor_level": common_ancestors[0]["min_level"] if common_ancestors else None
        }
    }
    
    # We'll need to import logger when this function is used
    # logger.info(f"Found {len(common_ancestors)} common ancestors in {search_time:.3f}s")
    
    return result
