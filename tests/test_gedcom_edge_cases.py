import os
import sys
import unittest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.gedcom_mcp.gedcom_context import GedcomContext
from src.gedcom_mcp.gedcom_data_access import load_gedcom_file
from src.gedcom_mcp.gedcom_data_management import _find_next_available_id, _add_person_internal
from src.gedcom_mcp.gedcom_search import find_shortest_relationship_path, _find_all_relationship_paths_internal, _get_person_neighbors_lazy
from src.gedcom_mcp.gedcom_analysis import get_statistics_report, get_living_status


class TestGedcomEdgeCases(unittest.TestCase):

    def setUp(self):
        self.gedcom_ctx = GedcomContext()
        sample_ged_path = Path(__file__).parent / "sample.ged"
        load_gedcom_file(str(sample_ged_path), self.gedcom_ctx)

    def test_find_next_available_id_edge_cases(self):
        """Test edge cases for finding next available ID"""
        # Test with empty lookup dict
        empty_dict = {}
        next_id = _find_next_available_id("@I", empty_dict)
        self.assertEqual(next_id, "@I1@")
        
        # Test with some existing IDs
        existing_dict = {"@I1@": "person1", "@I2@": "person2"}
        next_id = _find_next_available_id("@I", existing_dict)
        self.assertEqual(next_id, "@I3@")
        
        # Test with non-sequential IDs (function finds next available ID that doesn't exist)
        gap_dict = {"@I1@": "person1", "@I5@": "person5"}
        next_id = _find_next_available_id("@I", gap_dict)
        # Should return an ID that doesn't exist in the dict
        self.assertNotIn(next_id, gap_dict)
        # Should have the correct format
        self.assertTrue(next_id.startswith("@I"))
        self.assertTrue(next_id.endswith("@"))

    def test_add_person_edge_cases(self):
        """Test edge cases for adding persons"""
        # Test adding person with empty name
        person_id = _add_person_internal(self.gedcom_ctx, "", "M")
        person = self.gedcom_ctx.individual_lookup[person_id]
        # get_name() returns a tuple, so we need to handle that
        name = person.get_name()
        if isinstance(name, tuple):
            name_str = " ".join(str(part) for part in name if part)
        else:
            name_str = str(name) if name else ""
        self.assertEqual(name_str, "")
        self.assertEqual(person.get_child_value_by_tag("SEX"), "M")

    def test_search_with_invalid_person_ids(self):
        """Test search functions with invalid person IDs"""
        # Test with non-existent person IDs
        result = find_shortest_relationship_path("@INVALID@", "@I1@", "all", self.gedcom_ctx)
        self.assertIsInstance(result, dict)
        self.assertIn("error", result)
        self.assertIn("Person not found: @INVALID@", result["error"])
        
        result = find_shortest_relationship_path("@I1@", "@INVALID@", "all", self.gedcom_ctx)
        self.assertIsInstance(result, dict)
        self.assertIn("error", result)
        self.assertIn("Person not found: @INVALID@", result["error"])
        
        # Test with same person ID
        result = find_shortest_relationship_path("@I1@", "@I1@", "all", self.gedcom_ctx)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["distance"], 0)
        
        # Test all paths with invalid IDs
        result = _find_all_relationship_paths_internal("@INVALID@", "@I1@", "all", self.gedcom_ctx)
        self.assertIsInstance(result, dict)
        self.assertIn("error", result)
        self.assertIn("Person not found: @INVALID@", result["error"])

    def test_search_with_empty_context(self):
        """Test search functions with empty context"""
        empty_ctx = GedcomContext()
        
        # Test with empty context
        result = find_shortest_relationship_path("@I1@", "@I2@", "all", empty_ctx)
        self.assertIsInstance(result, dict)
        self.assertIn("error", result)
        self.assertIn("Person not found: @I1@", result["error"])

    def test_analysis_with_empty_context(self):
        """Test analysis functions with empty context"""
        empty_ctx = GedcomContext()
        stats = get_statistics_report(empty_ctx)
        self.assertEqual(stats, {})

    def test_living_status_with_invalid_person(self):
        """Test living status with invalid person ID"""
        status = get_living_status("@INVALID@", self.gedcom_ctx)
        self.assertIn("Person not found: @INVALID@", status)

    def test_search_with_invalid_relationship_types(self):
        """Test search with invalid relationship types"""
        # Test with unknown relationship type
        result = find_shortest_relationship_path("@I1@", "@I3@", "unknown_type", self.gedcom_ctx)
        # Should still work but with no relationships allowed
        self.assertIsInstance(result, dict)
        # If no relationships are allowed, it should not find a path
        self.assertIn("distance", result)

    def test_large_distance_limits(self):
        """Test search with large distance limits"""
        # Test with very large max_distance
        result = find_shortest_relationship_path("@I1@", "@I3@", "all", self.gedcom_ctx, max_distance=1000)
        self.assertIsInstance(result, dict)
        # Should find the path (distance 1 in sample data)
        self.assertIn("distance", result)
        self.assertEqual(result["distance"], 1)

    def test_get_person_neighbors_lazy_structure(self):
        """Test that _get_person_neighbors_lazy returns the correct data structure"""
        # Test getting neighbors for a person with all relationship types
        neighbors = _get_person_neighbors_lazy("@I1@", {"parent", "spouse", "child"}, self.gedcom_ctx)
        
        # Should return a list
        self.assertIsInstance(neighbors, list)
        
        # Each neighbor should be a tuple of (person_id, weight, relationship_type)
        if neighbors:
            for neighbor in neighbors:
                self.assertIsInstance(neighbor, tuple)
                self.assertEqual(len(neighbor), 3)
                person_id, weight, relationship_type = neighbor
                self.assertIsInstance(person_id, str)
                self.assertIsInstance(weight, int)
                self.assertIsInstance(relationship_type, str)
        
        # John Smith (@I1@) should have a spouse (Jane Doe @I2@) and a child (Junior Smith @I3@)
        neighbor_ids = [neighbor[0] for neighbor in neighbors]
        self.assertIn("@I2@", neighbor_ids)  # Spouse
        self.assertIn("@I3@", neighbor_ids)  # Child

    def test_get_person_neighbors_lazy_empty_relationships(self):
        """Test _get_person_neighbors_lazy with empty relationship types"""
        # Test with no allowed relationship types
        neighbors = _get_person_neighbors_lazy("@I1@", set(), self.gedcom_ctx)
        self.assertIsInstance(neighbors, list)
        self.assertEqual(len(neighbors), 0)

    def test_get_person_neighbors_lazy_single_relationship_type(self):
        """Test _get_person_neighbors_lazy with single relationship type"""
        # Test with only spouse relationships
        neighbors = _get_person_neighbors_lazy("@I1@", {"spouse"}, self.gedcom_ctx)
        self.assertIsInstance(neighbors, list)
        
        # Should only include spouse relationships
        for neighbor in neighbors:
            self.assertEqual(neighbor[2], "spouse")


class TestGedcomErrorHandling(unittest.TestCase):

    def setUp(self):
        self.gedcom_ctx = GedcomContext()
        sample_ged_path = Path(__file__).parent / "sample.ged"
        load_gedcom_file(str(sample_ged_path), self.gedcom_ctx)

    @patch('src.gedcom_mcp.gedcom_data_access.get_person_record')
    def test_search_with_person_details_exception(self, mock_get_person_details):
        """Test search functions when get_person_record raises an exception"""
        # Mock get_person_record to raise an exception
        mock_get_person_details.side_effect = Exception("Test exception")
        
        # This should be handled gracefully
        result = find_shortest_relationship_path("@I1@", "@I3@", "all", self.gedcom_ctx)
        # Should return a dict (either with error or successful result)
        self.assertIsInstance(result, dict)

    def test_search_with_missing_parser(self):
        """Test search functions with missing parser"""
        ctx = GedcomContext()  # Empty context without parser
        result = find_shortest_relationship_path("@I1@", "@I3@", "all", ctx)
        self.assertIsInstance(result, dict)
        self.assertIn("error", result)
        self.assertIn("Person not found", result["error"])


if __name__ == '__main__':
    unittest.main()