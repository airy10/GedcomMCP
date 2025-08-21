
import json
import os
import sys
import unittest
from pathlib import Path

# Add the parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.gedcom_mcp.gedcom_context import GedcomContext
from src.gedcom_mcp.gedcom_data_access import load_gedcom_file
from src.gedcom_mcp.gedcom_search import _dijkstra_bidirectional_search, _get_person_neighbors_lazy, _get_person_neighbors_lazy_reverse, _generate_relationship_chain_lazy, _correct_relationship_direction, _generate_relationship_description, _format_relationship_with_gender, _format_relationship_description, _find_shortest_relationship_path_internal, _find_all_relationship_paths_internal, _find_all_paths_to_ancestor_internal, check_component_connectivity


class TestGedcomSearch(unittest.TestCase):

    def setUp(self):
        self.gedcom_ctx = GedcomContext()
        sample_ged_path = Path(__file__).parent / "sample.ged"
        load_gedcom_file(str(sample_ged_path), self.gedcom_ctx)

    def test_find_shortest_relationship_path_internal(self):
        result = _find_shortest_relationship_path_internal("@I1@", "@I3@", "all", self.gedcom_ctx)
        self.assertIsInstance(result, dict)
        self.assertIn("path", result)
        self.assertEqual(len(result['path']), 2)  # John Smith -> Junior Smith

    def test_find_all_relationship_paths_internal(self):
        result = _find_all_relationship_paths_internal("@I1@", "@I3@", "all", self.gedcom_ctx)
        self.assertIsInstance(result, dict)
        self.assertIn("paths", result)
        self.assertGreater(len(result['paths']), 0)

    def test_find_all_paths_to_ancestor_internal(self):
        paths = _find_all_paths_to_ancestor_internal("@I3@", "@I1@", self.gedcom_ctx)
        self.assertGreater(len(paths), 0)

    def test_get_person_neighbors_lazy(self):
        # Test getting neighbors for a person
        neighbors = _get_person_neighbors_lazy("@I1@", {"parent", "spouse", "child"}, self.gedcom_ctx)
        self.assertIsInstance(neighbors, list)
        # John Smith should have a spouse (Jane Doe) and a child (Junior Smith)
        self.assertGreater(len(neighbors), 0)

    def test_get_person_neighbors_lazy_reverse(self):
        # Test getting reverse neighbors for a person
        neighbors = _get_person_neighbors_lazy_reverse("@I3@", {"parent", "spouse", "child"}, self.gedcom_ctx)
        self.assertIsInstance(neighbors, list)
        # Junior Smith should have parents (John Smith and Jane Doe)
        self.assertGreater(len(neighbors), 0)

    def test_generate_relationship_chain_lazy(self):
        # Test generating relationship chain
        path = ["@I1@", "@I3@"]
        chain = _generate_relationship_chain_lazy(path, {"parent", "spouse", "child"}, self.gedcom_ctx)
        self.assertIsInstance(chain, list)
        self.assertEqual(len(chain), 1)  # One relationship between two people

    def test_correct_relationship_direction(self):
        # Test correcting relationship direction
        corrected = _correct_relationship_direction("parent", "@I3@", "@I1@", self.gedcom_ctx)
        self.assertIn("child", corrected)  # @I3@ is child of @I1@

    def test_generate_relationship_description(self):
        # Test generating relationship description
        path = ["@I1@", "@I3@"]
        chain = ["father_of"]
        description = _generate_relationship_description(path, chain, self.gedcom_ctx)
        self.assertIsInstance(description, str)
        self.assertIn("John Smith", description)
        self.assertIn("Junior Smith", description)

    def test_format_relationship_with_gender(self):
        # Test formatting relationship with gender
        formatted = _format_relationship_with_gender("father_of", "@I1@", "@I3@", self.gedcom_ctx)
        self.assertIsInstance(formatted, str)
        # John Smith (M) is father of Junior Smith, so should be "father of"
        self.assertEqual(formatted, "father of")

    def test_format_relationship_description(self):
        # Test formatting relationship description
        formatted = _format_relationship_description("parent_of")
        self.assertIsInstance(formatted, str)
        self.assertEqual(formatted, "parent of")

    def test_check_component_connectivity(self):
        # Test component connectivity check
        result = check_component_connectivity("@I1@", "@I3@", {"parent", "spouse", "child"}, self.gedcom_ctx)
        # John Smith and Junior Smith should be connected
        self.assertTrue(result is True or result is None)  # True if connected, None if inconclusive


if __name__ == '__main__':
    unittest.main()
