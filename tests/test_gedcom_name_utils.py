import os
import sys
import unittest

# Add the parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.gedcom_mcp.gedcom_name_utils import parse_genealogy_name, normalize_name, find_name_variants, GenealogyName, format_gedcom_name, format_gedcom_name_from_string


class TestGedcomNameUtils(unittest.TestCase):

    def test_parse_genealogy_name(self):
        name = parse_genealogy_name("John /Smith/")
        self.assertEqual(name.given_names, ["John"])
        self.assertEqual(name.surname, "Smith")

    def test_normalize_name(self):
        normalized_name = normalize_name("  John  /Smith/  ")
        self.assertEqual(normalized_name, "john smith")

    def test_find_name_variants(self):
        variants = find_name_variants("John Smith")
        self.assertIn("John Smith", variants)
        # The function creates "J. Smith" abbreviation, not just "John"
        self.assertIn("J. Smith", variants)
        self.assertIn("Smith", variants)

    def test_format_gedcom_name(self):
        # Test basic name formatting
        name_obj = GenealogyName(
            original_text="John Smith",
            given_names=["John"],
            surname="Smith"
        )
        formatted = format_gedcom_name(name_obj)
        self.assertEqual(formatted, "John /Smith/")
        
        # Test name with prefix and suffix
        name_obj = GenealogyName(
            original_text="Mr. John Smith Jr.",
            given_names=["John"],
            surname="Smith",
            prefix="Mr.",
            suffix="Jr."
        )
        formatted = format_gedcom_name(name_obj)
        self.assertEqual(formatted, "Mr. John /Smith/ Jr.")

    def test_format_gedcom_name_from_string(self):
        # Test basic name formatting
        formatted = format_gedcom_name_from_string("John Smith")
        self.assertEqual(formatted, "John /Smith/")
        
        # Test name with prefix and suffix
        formatted = format_gedcom_name_from_string("Mr. John Smith Jr.")
        self.assertEqual(formatted, "Mr. John /Smith/ Jr.")
        
        # Test already formatted name
        formatted = format_gedcom_name_from_string("Mary /Smith/")
        self.assertEqual(formatted, "Mary /Smith/")
        
        # Test complex multi-word surnames - NOW WORKING CORRECTLY!
        # With nameparser integration, these are now parsed correctly:
        formatted = format_gedcom_name_from_string("Dr. Jane de la Cruz")
        self.assertEqual(formatted, "Dr. Jane /de la Cruz/")
        
        formatted = format_gedcom_name_from_string("Dr. Carol van Buren")
        self.assertEqual(formatted, "Dr. Carol /van Buren/")


if __name__ == '__main__':
    unittest.main()