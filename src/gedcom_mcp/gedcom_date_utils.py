"""Genealogy-specific date parsing utilities for GEDCOM files.

This module provides enhanced date parsing capabilities that handle
genealogy-specific date formats commonly found in GEDCOM files.
"""

import re
from typing import Optional, Tuple, Dict, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum


class DateCertainty(Enum):
    """Enumeration of date certainty levels."""
    EXACT = "exact"
    BEFORE = "before"
    AFTER = "after"
    ABOUT = "about"
    BETWEEN = "between"
    CALCULATED = "calculated"
    ESTIMATED = "estimated"


@dataclass
class GenealogyDate:
    """Represents a parsed genealogy date with all relevant information."""
    original_text: str
    certainty: DateCertainty
    year: Optional[int] = None
    month: Optional[int] = None
    day: Optional[int] = None
    year_end: Optional[int] = None  # For date ranges
    month_end: Optional[int] = None
    day_end: Optional[int] = None
    qualifier: Optional[str] = None  # Additional qualifiers like "ABT", "BEF", etc.
    
    def __str__(self) -> str:
        """Return a string representation of the date."""
        if self.certainty == DateCertainty.EXACT:
            if self.year and self.month and self.day:
                return f"{self.day:02d}/{self.month:02d}/{self.year}"
            elif self.year and self.month:
                return f"{self.month:02d}/{self.year}"
            elif self.year:
                return str(self.year)
        elif self.certainty == DateCertainty.BEFORE and self.year:
            return f"Before {self.year}"
        elif self.certainty == DateCertainty.AFTER and self.year:
            return f"After {self.year}"
        elif self.certainty == DateCertainty.ABOUT and self.year:
            return f"About {self.year}"
        elif self.certainty == DateCertainty.BETWEEN and self.year and self.year_end:
            return f"Between {self.year} and {self.year_end}"
        return self.original_text
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "original_text": self.original_text,
            "certainty": self.certainty.value,
            "year": self.year,
            "month": self.month,
            "day": self.day,
            "year_end": self.year_end,
            "month_end": self.month_end,
            "day_end": self.day_end,
            "qualifier": self.qualifier
        }


def parse_genealogy_date(date_string: str) -> GenealogyDate:
    """Parse a genealogy date string and return a GenealogyDate object.
    
    Handles common GEDCOM date formats:
    - Exact dates: "1850", "15 MAR 1850", "03/15/1850"
    - Approximate dates: "ABT 1850", "ABOUT 1850"
    - Before dates: "BEF 1850", "BEFORE 1850"
    - After dates: "AFT 1850", "AFTER 1850"
    - Date ranges: "BET 1850 AND 1860", "BETWEEN 1850 AND 1860"
    - Calculated dates: "CAL 1850"
    - Estimated dates: "EST 1850"
    - Dual dates: "1880 (1881)"
    
    Args:
        date_string: The date string to parse
        
    Returns:
        GenealogyDate object with parsed information
    """
    if not date_string or not isinstance(date_string, str):
        return GenealogyDate(original_text="", certainty=DateCertainty.EXACT)
    
    original = date_string.strip()
    date_string = original.upper()
    
    # Handle dual dates first (e.g., "1880 (1881)")
    dual_match = re.search(r'(\d{4})\s*$$(\d{4})$$', date_string)
    if dual_match:
        # For dual dates, we take the first year as primary
        year = int(dual_match.group(1))
        return GenealogyDate(
            original_text=original,
            certainty=DateCertainty.EXACT,
            year=year,
            qualifier="dual"
        )
    
    # Handle date ranges (BETWEEN/BET)
    bet_match = re.search(r'(?:BETWEEN|BET)\s+(\d{4})\s+(?:AND|&)\s+(\d{4})', date_string)
    if bet_match:
        year1 = int(bet_match.group(1))
        year2 = int(bet_match.group(2))
        return GenealogyDate(
            original_text=original,
            certainty=DateCertainty.BETWEEN,
            year=min(year1, year2),
            year_end=max(year1, year2)
        )
    
    # Handle BEFORE/BEF
    bef_match = re.search(r'(?:BEFORE|BEF)\s*(\d{4})', date_string)
    if bef_match:
        year = int(bef_match.group(1))
        return GenealogyDate(
            original_text=original,
            certainty=DateCertainty.BEFORE,
            year=year,
            qualifier=re.search(r'(?:BEFORE|BEF)', date_string).group(0)
        )
    
    # Handle AFTER/AFT
    aft_match = re.search(r'(?:AFTER|AFT)\s*(\d{4})', date_string)
    if aft_match:
        year = int(aft_match.group(1))
        return GenealogyDate(
            original_text=original,
            certainty=DateCertainty.AFTER,
            year=year,
            qualifier=re.search(r'(?:AFTER|AFT)', date_string).group(0)
        )
    
    # Handle ABOUT/ABT
    abt_match = re.search(r'(?:ABOUT|ABT)\s*(\d{4})', date_string)
    if abt_match:
        year = int(abt_match.group(1))
        return GenealogyDate(
            original_text=original,
            certainty=DateCertainty.ABOUT,
            year=year,
            qualifier=re.search(r'(?:ABOUT|ABT)', date_string).group(0)
        )
    
    # Handle CALCULATED/CAL
    cal_match = re.search(r'(?:CALCULATED|CAL)\s*(\d{4})', date_string)
    if cal_match:
        year = int(cal_match.group(1))
        return GenealogyDate(
            original_text=original,
            certainty=DateCertainty.CALCULATED,
            year=year,
            qualifier=re.search(r'(?:CALCULATED|CAL)', date_string).group(0)
        )
    
    # Handle ESTIMATED/EST
    est_match = re.search(r'(?:ESTIMATED|EST)\s*(\d{4})', date_string)
    if est_match:
        year = int(est_match.group(1))
        return GenealogyDate(
            original_text=original,
            certainty=DateCertainty.ESTIMATED,
            year=year,
            qualifier=re.search(r'(?:ESTIMATED|EST)', date_string).group(0)
        )
    
    # Handle exact dates with various formats
    # Try to extract year, month, day
    year = None
    month = None
    day = None
    
    # Pattern for "DD MMM YYYY" (e.g., "15 MAR 1850")
    dmy_match = re.search(r'(\d{1,2})\s+([A-Z]{3})\s+(\d{4})', date_string)
    if dmy_match:
        day = int(dmy_match.group(1))
        month_str = dmy_match.group(2)
        year = int(dmy_match.group(3))
        month = _month_to_number(month_str)
    
    # Pattern for "MM/DD/YYYY" or "DD/MM/YYYY" (simple heuristics)
    mdy_match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', date_string)
    if mdy_match and not year:  # Only if not already found
        part1 = int(mdy_match.group(1))
        part2 = int(mdy_match.group(2))
        year = int(mdy_match.group(3))
        
        # Simple heuristic: if first part > 12, it's day/month/year
        # Otherwise, assume month/day/year for US format
        if part1 > 12:
            day = part1
            month = part2
        else:
            month = part1
            day = part2
    
    # Pattern for just year (e.g., "1850")
    year_only_match = re.search(r'\b(\d{4})\b', date_string)
    if year_only_match and not year:
        year = int(year_only_match.group(1))
    
    return GenealogyDate(
        original_text=original,
        certainty=DateCertainty.EXACT,
        year=year,
        month=month,
        day=day
    )


def _month_to_number(month_str: str) -> Optional[int]:
    """Convert a 3-letter month abbreviation to a number."""
    months = {
        'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4,
        'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8,
        'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
    }
    return months.get(month_str)


def validate_date_consistency(birth_date: Optional[str], death_date: Optional[str]) -> Tuple[bool, str]:
    """Validate that birth and death dates are consistent.
    
    Args:
        birth_date: Birth date string
        death_date: Death date string
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not birth_date and not death_date:
        return True, ""
    
    birth_parsed = parse_genealogy_date(birth_date) if birth_date else None
    death_parsed = parse_genealogy_date(death_date) if death_date else None
    
    # If we can't parse either date, we can't validate
    if (birth_date and not birth_parsed.year) or (death_date and not death_parsed.year):
        return True, ""
    
    # Check if death date is before birth date
    if birth_parsed and death_parsed and birth_parsed.year and death_parsed.year:
        if death_parsed.year < birth_parsed.year:
            return False, f"Death date ({death_parsed.year}) is before birth date ({birth_parsed.year})"
        
        # Also check if they're the same year but death month/day is before birth
        if death_parsed.year == birth_parsed.year:
            if death_parsed.month and birth_parsed.month and death_parsed.month < birth_parsed.month:
                return False, f"Death date is before birth date in the same year"
            if (death_parsed.month == birth_parsed.month and 
                death_parsed.day and birth_parsed.day and 
                death_parsed.day < birth_parsed.day):
                return False, f"Death date is before birth date in the same month"
    
    return True, ""


def get_date_certainty_level(date_string: str) -> str:
    """Get a textual description of the certainty level of a date.
    
    Args:
        date_string: The date string to analyze
        
    Returns:
        A description of the date's certainty level
    """
    parsed = parse_genealogy_date(date_string)
    
    if parsed.certainty == DateCertainty.EXACT:
        return "Exact date"
    elif parsed.certainty == DateCertainty.BEFORE:
        return f"Before {parsed.year} (approximate)"
    elif parsed.certainty == DateCertainty.AFTER:
        return f"After {parsed.year} (approximate)"
    elif parsed.certainty == DateCertainty.ABOUT:
        return f"About {parsed.year} (approximate)"
    elif parsed.certainty == DateCertainty.BETWEEN:
        return f"Between {parsed.year} and {parsed.year_end} (approximate range)"
    elif parsed.certainty == DateCertainty.CALCULATED:
        return f"Calculated date: {parsed.year}"
    elif parsed.certainty == DateCertainty.ESTIMATED:
        return f"Estimated date: {parsed.year}"
    
    return "Unknown certainty level"


# Example usage and testing
if __name__ == "__main__":
    # Test cases
    test_dates = [
        "1850",
        "15 MAR 1850",
        "03/15/1850",
        "ABT 1850",
        "ABOUT 1850",
        "BEF 1850",
        "BEFORE 1850",
        "AFT 1850",
        "AFTER 1850",
        "BET 1850 AND 1860",
        "BETWEEN 1850 AND 1860",
        "CAL 1850",
        "CALCULATED 1850",
        "EST 1850",
        "ESTIMATED 1850",
        "1880 (1881)",
        "JAN 1850",
        "1850-1860"  # This should be parsed as a range
    ]
    
    print("Genealogy Date Parsing Examples:")
    print("=" * 40)
    
    for date_str in test_dates:
        parsed = parse_genealogy_date(date_str)
        print(f"Input: {date_str:<20} -> {parsed}")
    
    print("\nValidation Examples:")
    print("=" * 20)
    
    # Test validation
    valid, msg = validate_date_consistency("1850", "1900")
    print(f"Valid dates (1850, 1900): {valid} - {msg}")
    
    valid, msg = validate_date_consistency("1900", "1850")
    print(f"Invalid dates (1900, 1850): {valid} - {msg}")
    
    valid, msg = validate_date_consistency("ABT 1850", "BEF 1840")
    print(f"Invalid approximate dates (ABT 1850, BEF 1840): {valid} - {msg}")