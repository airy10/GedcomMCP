"""Genealogy-specific place name normalization utilities for GEDCOM files.

This module provides enhanced place name normalization capabilities that handle
genealogy-specific place formats.
"""

import re
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass


@dataclass
class NormalizedPlace:
    """Represents a normalized place name with geographic hierarchy."""
    original_text: str
    normalized_name: str
    country: Optional[str] = None
    state_province: Optional[str] = None
    county: Optional[str] = None
    city: Optional[str] = None
    department: Optional[str] = None  # French departments, etc.
    region: Optional[str] = None      # Administrative regions
    postal_code: Optional[str] = None # ZIP/postal codes
    
# Geographic hierarchy patterns for common formats
# Format: regex pattern -> (components...)
GEOGRAPHIC_PATTERNS = [
    # Complex pattern: City, Postal Code, Department, Region, Country
    # Example: "Nancy, 54000, Meurthe-et-Moselle, Grand-Est, France"
    (r'^(.+?),\s*(\d{5}),\s*(.+?),\s*(.+?),\s*(.+?)$', ('city', 'postal_code', 'department', 'region', 'country')),
    
    # Pattern with Department/Region: City, Department, Region, Country
    (r'^(.+?),\s*(.+?),\s*(.+?),\s*(.+?)$', ('city', 'department', 'region', 'country')),
    
    # Pattern with Postal Code: City, Postal Code, State/Province, Country
    (r'^(.+?),\s*(\d{5}),\s*(.+?),\s*(.+?)$', ('city', 'postal_code', 'state_province', 'country')),
    
    # Traditional patterns (preserved for backward compatibility)
    # City, County, State, Country
    (r'^(.+?),\s*(.+?),\s*(.+?),\s*(.+?)$', ('city', 'county', 'state_province', 'country')),
    
    # City, State, Country
    (r'^(.+?),\s*(.+?),\s*(.+?)$', ('city', 'state_province', 'country')),
    
    # City, Country
    (r'^(.+?),\s*(.+?)$', ('city', 'country')),
    
    # State, Country (for places that are states/regions)
    (r'^(.+?),\s*(.+?)$', ('state_province', 'country')),
]


def normalize_place_name(place_string: str) -> NormalizedPlace:
    """Normalize a place name and extract geographic hierarchy.
    
    Args:
        place_string: The place string to normalize
        
    Returns:
        NormalizedPlace object with parsed information
    """
    if not place_string or not isinstance(place_string, str):
        return NormalizedPlace(original_text="", normalized_name="")
    
    original = place_string.strip()
    normalized_name = original
    
    # Try to extract geographic hierarchy
    city = None
    county = None
    state_province = None
    country = None
    department = None
    region = None
    postal_code = None
    
    # Apply geographic patterns
    for pattern, components in GEOGRAPHIC_PATTERNS:
        match = re.match(pattern, normalized_name)
        if match:
            # Map matched groups to components
            values = match.groups()
            if len(values) == len(components):
                component_mapping = dict(zip(components, values))
                
                city = component_mapping.get('city', '').strip() if component_mapping.get('city') else None
                county = component_mapping.get('county', '').strip() if component_mapping.get('county') else None
                state_province = component_mapping.get('state_province', '').strip() if component_mapping.get('state_province') else None
                country = component_mapping.get('country', '').strip() if component_mapping.get('country') else None
                department = component_mapping.get('department', '').strip() if component_mapping.get('department') else None
                region = component_mapping.get('region', '').strip() if component_mapping.get('region') else None
                postal_code = component_mapping.get('postal_code', '').strip() if component_mapping.get('postal_code') else None
                break
    
    # If we couldn't parse with patterns, try heuristic approach for complex names
    if not city and not state_province and not country:
        # Handle complex French-style addresses: "Nancy, 54000, Meurthe-et-Moselle, Grand-Est, France"
        parts = [p.strip() for p in normalized_name.split(',') if p.strip()]
        if parts:
            # Check if second part looks like a postal code (5 digits)
            if len(parts) >= 2 and re.match(r'^\d{5}$', parts[1]):
                # Format: City, Postal Code, Department, Region, Country
                if len(parts) >= 1:
                    city = parts[0]
                if len(parts) >= 2:
                    postal_code = parts[1]
                if len(parts) >= 3:
                    department = parts[2]
                if len(parts) >= 4:
                    region = parts[3]
                if len(parts) >= 5:
                    country = parts[4]
            elif len(parts) >= 4:
                # Format: City, Department, Region, Country
                city = parts[0]
                department = parts[1]
                region = parts[2]
                country = parts[3]
            else:
                # Fall back to simple hierarchical approach
                # Last part is usually country, second to last is state/province, etc.
                if len(parts) >= 1:
                    country = parts[-1]
                if len(parts) >= 2:
                    state_province = parts[-2]
                if len(parts) >= 3:
                    county = parts[-3]
                if len(parts) >= 4:
                    city = parts[-4]
                elif len(parts) == 1:
                    # If only one part, treat as city
                    city = parts[0]
    
    return NormalizedPlace(
        original_text=original,
        normalized_name=normalized_name,
        country=country,
        state_province=state_province,
        county=county,
        city=city,
        department=department,
        region=region,
        postal_code=postal_code
    )


def extract_geographic_hierarchy(place_string: str) -> Dict[str, str]:
    """Extract geographic hierarchy from a place string.
    
    Args:
        place_string: The place string to parse
        
    Returns:
        Dictionary with geographic components (city, county, state_province, country, department, region, postal_code)
    """
    normalized = normalize_place_name(place_string)
    return {
        "city": normalized.city,
        "county": normalized.county,
        "state_province": normalized.state_province,
        "country": normalized.country,
        "department": normalized.department,
        "region": normalized.region,
        "postal_code": normalized.postal_code
    }


# Example usage and testing
if __name__ == "__main__":
    # Test cases
    test_places = [
        "Berlin, Germany",
        "Leningrad, Russia",
        "Prussia, Germany",
        "New York, NY, USA",
        "London, England, United Kingdom",
        "Paris, France",
        "Nancy, 54000, Meurthe-et-Moselle, Grand-Est, France",
        "Nancy, Meurthe-et-Moselle, Grand-Est, France"
    ]
    
    print("Genealogy Place Normalization Examples:")
    print("=" * 50)
    
    for place_str in test_places:
        normalized = normalize_place_name(place_str)
        print(f"Input: {place_str}")
        print(f"  Normalized: {normalized.normalized_name}")
        print(f"  Components: City='{normalized.city}', County='{normalized.county}', "
              f"State/Province='{normalized.state_province}', Country='{normalized.country}', "
              f"Department='{normalized.department}', Region='{normalized.region}', "
              f"Postal Code='{normalized.postal_code}'")
        print()
        
