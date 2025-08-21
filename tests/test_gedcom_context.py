import os
import sys
import unittest
from pathlib import Path

# Add the parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.gedcom_mcp.gedcom_context import GedcomContext, _rebuild_lookups, get_gedcom_context
from src.gedcom_mcp.gedcom_data_access import load_gedcom_file


class TestGedcomContext(unittest.TestCase):

    def setUp(self):
        self.gedcom_ctx = GedcomContext()

    def test_gedcom_context_initialization(self):
        """Test that GedcomContext initializes with correct default values"""
        self.assertIsNone(self.gedcom_ctx.gedcom_parser)
        self.assertIsNone(self.gedcom_ctx.gedcom_file_path)
        self.assertEqual(len(self.gedcom_ctx.individual_lookup), 0)
        self.assertEqual(len(self.gedcom_ctx.family_lookup), 0)
        self.assertEqual(len(self.gedcom_ctx.source_lookup), 0)
        self.assertEqual(len(self.gedcom_ctx.note_lookup), 0)
        self.assertEqual(self.gedcom_ctx.max_time, 60)
        self.assertEqual(self.gedcom_ctx.max_nodes, 250000)

    def test_gedcom_context_caches(self):
        """Test that GedcomContext initializes with caches"""
        self.assertIsNotNone(self.gedcom_ctx.person_details_cache)
        self.assertIsNotNone(self.gedcom_ctx.person_relationships_cache)
        self.assertIsNotNone(self.gedcom_ctx.neighbor_cache)

    def test_clear_caches(self):
        """Test that clear_caches method works"""
        # Add some items to caches
        self.gedcom_ctx.person_details_cache['test'] = 'value1'
        self.gedcom_ctx.person_relationships_cache['test'] = 'value2'
        self.gedcom_ctx.neighbor_cache['test'] = 'value3'
        
        # Verify caches have items
        self.assertGreater(len(self.gedcom_ctx.person_details_cache), 0)
        self.assertGreater(len(self.gedcom_ctx.person_relationships_cache), 0)
        self.assertGreater(len(self.gedcom_ctx.neighbor_cache), 0)
        
        # Clear caches
        self.gedcom_ctx.clear_caches()
        
        # Verify caches are empty
        self.assertEqual(len(self.gedcom_ctx.person_details_cache), 0)
        self.assertEqual(len(self.gedcom_ctx.person_relationships_cache), 0)
        self.assertEqual(len(self.gedcom_ctx.neighbor_cache), 0)

    def test_rebuild_lookups(self):
        """Test that _rebuild_lookups works with a loaded GEDCOM file"""
        # Load a sample GEDCOM file
        sample_ged_path = Path(__file__).parent / "sample.ged"
        load_result = load_gedcom_file(str(sample_ged_path), self.gedcom_ctx)
        self.assertTrue(load_result)
        
        # Rebuild lookups
        _rebuild_lookups(self.gedcom_ctx)
        
        # Verify lookups were populated
        self.assertGreater(len(self.gedcom_ctx.individual_lookup), 0)
        self.assertGreater(len(self.gedcom_ctx.family_lookup), 0)


if __name__ == '__main__':
    unittest.main()