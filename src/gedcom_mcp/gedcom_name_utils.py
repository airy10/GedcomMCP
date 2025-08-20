"""Genealogy-specific name parsing utilities for GEDCOM files.

This module provides enhanced name parsing capabilities that handle
genealogy-specific name formats commonly found in GEDCOM files.
"""

import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass


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
        if self.prefix:
            parts.append(self.prefix)
        if self.given_names:
            parts.append(" ".join(self.given_names))
        if self.surname:
            parts.append(self.surname)
        if self.suffix:
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
        # Remove surname from name string for further processing
        name_string = re.sub(r'/[^/]+/', '', name_string).strip()
    
    # Extract prefixes (Mr., Mrs., Ms., Dr., Rev., Sir, Lady, etc.)
    prefix = None
    prefix_match = re.match(r'(Mr\.?|Mrs\.?|Ms\.?|Miss|Mister|Madam|Dr\.?|Prof\.?|Rev\.?|Reverend|Sir|Lady|Lord|Dame)\s+', name_string, re.IGNORECASE)
    if prefix_match:
        prefix = prefix_match.group(1)
        # Remove prefix from name string
        name_string = name_string[len(prefix_match.group(0)):].strip()
    
    # Extract suffixes (Jr., Sr., II, III, IV, etc.)
    suffix = None
    suffix_pattern = r'\s+(Jr\.?|Sr\.?|II|III|IV|V|VI|Esq\.?|Esquire)$'
    suffix_match = re.search(suffix_pattern, name_string, re.IGNORECASE)
    if suffix_match:
        suffix = suffix_match.group(1)
        # Remove suffix from name string
        name_string = name_string[:suffix_match.start()].strip()
    
    # Extract titles (different from prefixes - more professional/academic)
    title = None
    title_match = re.match(r'(Dr\.?|Doctor|Prof\.?|Professor|Sir|Dame|Lord|Lady|Rev\.?|Reverend)\s+', name_string, re.IGNORECASE)
    if title_match and not prefix:
        title = title_match.group(1)
        # Remove title from name string
        name_string = name_string[len(title_match.group(0)):].strip()
    
    # Split remaining text into given names
    given_names = []
    if name_string:
        # Handle multiple given names
        given_names = name_string.split()
    
    # If we still don't have a surname but we have given names, 
    # and the last given name might be a surname (if no // were used)
    if not surname and given_names and not re.search(r'/[^/]+/', original):
        # Heuristic: if the last word is capitalized and not a known prefix/title,
        # treat it as surname
        last_word = given_names[-1]
        if (last_word.isupper() or 
            (len(last_word) > 1 and last_word[0].isupper() and last_word[1:].islower())):
            # Check if it's not a known prefix or title
            if not _is_prefix_or_title(last_word):
                surname = given_names.pop()
    
    return GenealogyName(
        original_text=original,
        given_names=given_names,
        surname=surname,
        prefix=prefix,
        suffix=suffix,
        nickname=nickname,
        title=title
    )


def _is_prefix_or_title(word: str) -> bool:
    """Check if a word is a known prefix or title."""
    prefixes_titles = {
        'MR', 'MRS', 'MS', 'MISS', 'MISTER', 'MADAM', 'DR', 'DOCTOR',
        'PROF', 'PROFESSOR', 'REV', 'REVEREND', 'SIR', 'LADY', 'LORD', 'DAME',
        'JR', 'SR', 'ESQ', 'ESQUIRE'
    }
    return word.upper() in prefixes_titles


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
        print(f"  Variants: {find_name_variants(name_str)}")
        print()