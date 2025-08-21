import os
import sys
import unittest

# Add the parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.gedcom_mcp.gedcom_date_utils import parse_genealogy_date, validate_date_consistency, get_date_certainty_level, _month_to_number, GenealogyDate


class TestGedcomDateUtils(unittest.TestCase):

    def test_parse_genealogy_date(self):
        date = parse_genealogy_date("1 JAN 1970")
        self.assertEqual(date.year, 1970)
        self.assertEqual(date.month, 1)
        self.assertEqual(date.day, 1)

    def test_validate_date_consistency(self):
        is_valid, error_msg = validate_date_consistency("1 JAN 1970", "1 JAN 2020")
        self.assertTrue(is_valid)

        is_valid, error_msg = validate_date_consistency("1 JAN 2020", "1 JAN 1970")
        self.assertFalse(is_valid)

    def test_get_date_certainty_level(self):
        certainty = get_date_certainty_level("ABT 1970")
        self.assertEqual(certainty, "About 1970 (approximate)")

        certainty = get_date_certainty_level("1970")
        self.assertEqual(certainty, "Exact date")

        certainty = get_date_certainty_level("JAN 1970")
        self.assertEqual(certainty, "Exact date")

        certainty = get_date_certainty_level("1 JAN 1970")
        self.assertEqual(certainty, "Exact date")

    def test_month_to_number(self):
        """Test the internal _month_to_number helper function"""
        self.assertEqual(_month_to_number("JAN"), 1)
        self.assertEqual(_month_to_number("FEB"), 2)
        self.assertEqual(_month_to_number("MAR"), 3)
        self.assertEqual(_month_to_number("APR"), 4)
        self.assertEqual(_month_to_number("MAY"), 5)
        self.assertEqual(_month_to_number("JUN"), 6)
        self.assertEqual(_month_to_number("JUL"), 7)
        self.assertEqual(_month_to_number("AUG"), 8)
        self.assertEqual(_month_to_number("SEP"), 9)
        self.assertEqual(_month_to_number("OCT"), 10)
        self.assertEqual(_month_to_number("NOV"), 11)
        self.assertEqual(_month_to_number("DEC"), 12)
        self.assertIsNone(_month_to_number("INVALID"))
        self.assertIsNone(_month_to_number(""))


if __name__ == '__main__':
    unittest.main()