"""Genealogy-specific name parsing utilities for GEDCOM files.

This module provides enhanced name parsing capabilities that handle
genealogy-specific name formats commonly found in GEDCOM files.
"""

import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from nameparser import HumanName


@dataclass
class GenealogyName:
    """Represents a parsed genealogy name with all components."""
    original_text: str
    given_names: List[str]
    surname: str
    prefix: Optional[str] = None  # Name prefixes like "Mr.", "Mrs.", "Rev."
    suffix: Optional[str] = None  # Name suffixes like "Jr.", "Sr.", "III"
    nickname: Optional[str] = None  # Nicknames in quotes
    title: Optional[str] = None  # Titles like "Dr.", "Sir"
    
    def __str__(self) -> str:
        """Return a standardized string representation of the name."""
        parts = []
        if self.prefix and self.prefix not in self.given_names:
            parts.append(self.prefix)
        if self.given_names:
            parts.append(" ".join(self.given_names))
        if self.surname:
            parts.append(self.surname)
        if self.suffix and self.suffix not in self.given_names:
            parts.append(self.suffix)
        return " ".join(parts)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "original_text": self.original_text,
            "given_names": self.given_names,
            "surname": self.surname,
            "prefix": self.prefix,
            "suffix": self.suffix,
            "nickname": self.nickname,
            "title": self.title,
            "standardized": str(self)
        }


def parse_genealogy_name(name_string: str) -> GenealogyName:
    """Parse a genealogy name string and return a GenealogyName object.
    
    Uses the nameparser library for robust name parsing that correctly
    handles multi-word surnames like "van Buren" and "de la Cruz".
    
    Handles common GEDCOM name formats:
    - Standard names: "John Smith", "Mary /Smith/"
    - Names with prefixes: "Mr. John Smith", "Rev. John Smith"
    - Names with suffixes: "John Smith Jr.", "John Smith III"
    - Names with titles: "Dr. John Smith", "Sir John Smith"
    - Names with nicknames: "John "Jack" Smith"
    - Multi-part surnames: "John /de la Cruz/", "Mary /Van Buren/"
    
    Args:
        name_string: The name string to parse
        
    Returns:
        GenealogyName object with parsed information
    """
    if not name_string or not isinstance(name_string, str):
        return GenealogyName(original_text="", given_names=[], surname="")
    
    original = name_string.strip()
    name_string = original
    
    # Extract nickname (text in quotes)
    nickname = None
    nickname_match = re.search(r'"([^"]+)"', name_string)
    if nickname_match:
        nickname = nickname_match.group(1)
        # Remove nickname from name string for further processing
        name_string = re.sub(r'"[^"]+"', '', name_string).strip()
    
    # Extract surname (text between //)
    surname = ""
    surname_match = re.search(r'/([^/]+)/', name_string)
    if surname_match:
        surname = surname_match.group(1).strip()
    
    # Handle GEDCOM format names (surname in slashes)
    if surname:
        # Remove surname from name string for further processing
        name_without_surname = re.sub(r'/[^/]+/', '', name_string).strip()
        
        # For GEDCOM format, treat ALL words before the surname as given names
        # regardless of what nameparser thinks
        if name_without_surname:
            given_names = name_without_surname.split()
        else:
            given_names = []
            
        # Extract title and suffix by parsing the name without the surname part
        temp_parsed = HumanName(name_without_surname)
        title = temp_parsed.title if temp_parsed.title else None
        suffix = temp_parsed.suffix if temp_parsed.suffix else None
        
        # Remove title and suffix from given_names if they exist there
        if title and title in given_names:
            given_names.remove(title)
        if suffix and suffix in given_names:
            given_names.remove(suffix)
    else:
        # Use nameparser for regular name parsing
        parsed = HumanName(name_string)
        
        # Extract components from nameparser result
        title = parsed.title if parsed.title else None
        first = parsed.first if parsed.first else ""
        middle = parsed.middle if parsed.middle else ""
        surname = parsed.last if parsed.last else ""
        suffix = parsed.suffix if parsed.suffix else None
        
        # Combine given names (first + middle)
        given_names = []
        if first:
            given_names.append(first)
        if middle:
            given_names.extend(middle.split())
    
    return GenealogyName(
        original_text=original,
        given_names=given_names,
        surname=surname,
        prefix=title,  # Using title as prefix to match our existing convention
        suffix=suffix,
        nickname=nickname,
        title=title
    )


def normalize_name(name_string: str) -> str:
    """Normalize a name for comparison purposes.
    
    Args:
        name_string: The name string to normalize
        
    Returns:
        A normalized version of the name
    """
    if not name_string:
        return ""
    
    # Parse the name
    parsed = parse_genealogy_name(name_string)
    
    # Create a normalized version
    parts = []
    if parsed.given_names:
        parts.extend([name.lower() for name in parsed.given_names])
    if parsed.surname:
        parts.append(parsed.surname.lower())
    
    return " ".join(parts)


def find_name_variants(name_string: str) -> List[str]:
    """Find common variants of a name.
    
    Args:
        name_string: The name string to find variants for
        
    Returns:
        A list of common name variants
    """
    parsed = parse_genealogy_name(name_string)
    variants = [name_string]  # Include original
    
    # Add nickname as variant if present
    if parsed.nickname:
        # Create variant with nickname instead of given name
        if parsed.given_names:
            variant_parts = []
            if parsed.prefix:
                variant_parts.append(parsed.prefix)
            variant_parts.append(parsed.nickname)
            if parsed.surname:
                variant_parts.append(parsed.surname)
            if parsed.suffix:
                variant_parts.append(parsed.suffix)
            variants.append(" ".join(variant_parts))
    
    # Add abbreviated given names variant
    if parsed.given_names:
        abbreviated = []
        for name in parsed.given_names:
            if len(name) > 0:
                abbreviated.append(name[0] + ".")
        if abbreviated or parsed.surname:
            variant_parts = []
            if parsed.prefix:
                variant_parts.append(parsed.prefix)
            variant_parts.extend(abbreviated)
            if parsed.surname:
                variant_parts.append(parsed.surname)
            if parsed.suffix:
                variant_parts.append(parsed.suffix)
            variants.append(" ".join(variant_parts))
    
    # Add surname-only variant
    if parsed.surname:
        variants.append(parsed.surname)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_variants = []
    for variant in variants:
        if variant.lower() not in seen:
            seen.add(variant.lower())
            unique_variants.append(variant)
    
    return unique_variants


def format_gedcom_name(genealogy_name: GenealogyName) -> str:
    """Format a GenealogyName object into proper GEDCOM name format.
    
    Args:
        genealogy_name: The GenealogyName object to format
        
    Returns:
        A GEDCOM-formatted name string (e.g., "John /Smith/" or "Mr. John /Smith/ Jr.")
    """
    if not genealogy_name:
        return ""
    
    parts = []
    
    # Add prefix if present
    if genealogy_name.prefix:
        parts.append(genealogy_name.prefix)
    
    # Add given names
    if genealogy_name.given_names:
        parts.append(" ".join(genealogy_name.given_names))
    
    # Add surname in GEDCOM format (enclosed in slashes)
    if genealogy_name.surname:
        parts.append(f"/{genealogy_name.surname}/")
    
    # Add suffix if present
    if genealogy_name.suffix:
        parts.append(genealogy_name.suffix)
    
    return " ".join(parts)


def format_gedcom_name_from_string(name_string: str) -> str:
    """Format a name string into proper GEDCOM name format.
    
    Args:
        name_string: The name string to format (e.g., "John Smith")
        
    Returns:
        A GEDCOM-formatted name string (e.g., "John /Smith/")
    """
    if not name_string:
        return ""
    
    # Parse the name first
    parsed_name = parse_genealogy_name(name_string)
    return format_gedcom_name(parsed_name)


# Example usage and testing
if __name__ == "__main__":
    # Test cases
    test_names = [
        "John Smith",
        "Mary /Smith/",
        "Mr. John Smith",
        "John Smith Jr.",
        "Dr. John Smith",
        "Rev. John Smith III",
        'John "Jack" Smith',
        "Maria /de la Cruz/",
        "James /Van Buren/",
        "Sir John Smith",
        "Mary /O'Connor/"
    ]
    
    print("Genealogy Name Parsing Examples:")
    print("=" * 40)
    
    for name_str in test_names:
        parsed = parse_genealogy_name(name_str)
        print(f"Input: {name_str}")
        print(f"  Parsed: {parsed}")
        print(f"  Components: {parsed.to_dict()}")
        print(f"  GEDCOM Format: {format_gedcom_name(parsed)}")
        print(f"  Variants: {find_name_variants(name_str)}")
        print()