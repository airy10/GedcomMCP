import os
import sys
import unittest

# Add the parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.gedcom_mcp.gedcom_place_utils import normalize_place_name, extract_geographic_hierarchy, NormalizedPlace

class TestGedcomPlaceUtils(unittest.TestCase):

    def test_normalize_place_name(self):
        normalized_place = normalize_place_name("  London,  England  ")
        self.assertEqual(normalized_place.normalized_name, "London,  England")

    def test_extract_geographic_hierarchy(self):
        hierarchy = extract_geographic_hierarchy("London, Middlesex, England")
        self.assertEqual(hierarchy['city'], "London")
        self.assertEqual(hierarchy['state_province'], "Middlesex")
        self.assertEqual(hierarchy['country'], "England")

if __name__ == '__main__':
    unittest.main()