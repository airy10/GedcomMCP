import os
import sys
import unittest

# Add the parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.gedcom_mcp.gedcom_name_utils import parse_genealogy_name, normalize_name, find_name_variants, _is_prefix_or_title, GenealogyName


class TestGedcomNameUtils(unittest.TestCase):

    def test_parse_genealogy_name(self):
        name = parse_genealogy_name("John /Smith/")
        self.assertEqual(name.given_names, ["John"])
        self.assertEqual(name.surname, "Smith")

    def test_normalize_name(self):
        normalized_name = normalize_name("  John  /Smith/  ")
        self.assertEqual(normalized_name, "john smith")

    def test_find_name_variants(self):
        variants = find_name_variants("John /Smith/")
        self.assertIn("John /Smith/", variants)  # Original is included
        self.assertIn("J. Smith", variants)

    def test_is_prefix_or_title(self):
        """Test the internal _is_prefix_or_title helper function"""
        # Test known prefixes and titles
        self.assertTrue(_is_prefix_or_title("MR"))
        self.assertTrue(_is_prefix_or_title("MRS"))
        self.assertTrue(_is_prefix_or_title("MS"))
        self.assertTrue(_is_prefix_or_title("DR"))
        self.assertTrue(_is_prefix_or_title("PROF"))
        self.assertTrue(_is_prefix_or_title("REV"))
        self.assertTrue(_is_prefix_or_title("SIR"))
        self.assertTrue(_is_prefix_or_title("LADY"))
        self.assertTrue(_is_prefix_or_title("JR"))
        self.assertTrue(_is_prefix_or_title("SR"))
        self.assertTrue(_is_prefix_or_title("ESQ"))
        
        # Test case insensitivity
        self.assertTrue(_is_prefix_or_title("mr"))
        self.assertTrue(_is_prefix_or_title("Mr"))
        
        # Test non-prefixes
        self.assertFalse(_is_prefix_or_title("JOHN"))
        self.assertFalse(_is_prefix_or_title("SMITH"))
        self.assertFalse(_is_prefix_or_title(""))
        self.assertFalse(_is_prefix_or_title("TEST"))


if __name__ == '__main__':
    unittest.main()