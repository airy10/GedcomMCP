import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.gedcom_mcp.gedcom_context import GedcomContext
from src.gedcom_mcp.gedcom_data_access import get_person_record, fuzzy_search_records

class TestFuzzySearchInternal(unittest.TestCase):

    def setUp(self):
        self.gedcom_ctx = GedcomContext()
        
    def test_fuzzy_search_with_fuzzywuzzy_unavailable(self):
        """Test when fuzzywuzzy is not installed"""
        # Mock the import to simulate fuzzywuzzy not being available
        with patch.dict('sys.modules', {'fuzzywuzzy': None, 'fuzzywuzzy.fuzz': None, 'fuzzywuzzy.process': None}):
            result = fuzzy_search_records("John Smith", self.gedcom_ctx)
            self.assertIsInstance(result, list)
            self.assertEqual(len(result), 1)
            self.assertIn("error", result[0])
            self.assertIn("fuzzywuzzy library not installed", result[0]["error"])

    def test_fuzzy_search_no_gedcom_loaded(self):
        """Test when no GEDCOM file is loaded"""
        self.gedcom_ctx.gedcom_parser = None
        result = fuzzy_search_records("John Smith", self.gedcom_ctx)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertIn("error", result[0])
        # If fuzzywuzzy is installed, we'll get the GEDCOM error, otherwise the fuzzywuzzy error
        expected_errors = [
            "No GEDCOM file loaded. Please load a GEDCOM file first.",
            "fuzzywuzzy library not installed. Please install it with: pip install fuzzywuzzy python-levenshtein"
        ]
        self.assertIn(result[0]["error"], expected_errors)

    @patch('src.gedcom_mcp.gedcom_data_access.get_person_record')
    def test_fuzzy_search_success(self, mock_get_person):
        """Test successful fuzzy search"""
        # Skip this test if fuzzywuzzy is not installed
        try:
            import fuzzywuzzy
        except ImportError:
            self.skipTest("fuzzywuzzy not installed")
            
        # Set up GEDCOM context with a parser
        self.gedcom_ctx.gedcom_parser = MagicMock()
        
        # Mock individual lookup
        mock_individual = MagicMock()
        mock_individual.get_name.return_value = "John Smith"
        self.gedcom_ctx.individual_lookup = {"@I1@": mock_individual}
        
        # Mock person details
        mock_person = MagicMock()
        mock_person.id = "@I1@"
        mock_person.name = "John Smith"
        mock_person.model_dump.return_value = {"id": "@I1@", "name": "John Smith"}
        mock_get_person.return_value = mock_person
        
        # Mock fuzzywuzzy process.extract
        with patch('fuzzywuzzy.process.extract') as mock_extract:
            mock_extract.return_value = [("John Smith", 95)]
            
            result = fuzzy_search_records("John Smyth", self.gedcom_ctx, threshold=90)
            
            self.assertIsInstance(result, list)
            # Should have one match above threshold
            self.assertEqual(len(result), 1)
            self.assertIn("person", result[0])
            self.assertIn("similarity_score", result[0])
            self.assertEqual(result[0]["similarity_score"], 95)

    def test_fuzzy_search_empty_name_list(self):
        """Test fuzzy search with empty name list"""
        # Skip this test if fuzzywuzzy is not installed
        try:
            import fuzzywuzzy
        except ImportError:
            self.skipTest("fuzzywuzzy not installed")
            
        self.gedcom_ctx.gedcom_parser = MagicMock()
        self.gedcom_ctx.individual_lookup = {}
        
        result = fuzzy_search_records("John Smith", self.gedcom_ctx)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

if __name__ == '__main__':
    unittest.main()