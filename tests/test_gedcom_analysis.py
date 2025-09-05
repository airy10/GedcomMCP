import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Add the parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.gedcom_mcp.gedcom_context import GedcomContext
from src.gedcom_mcp.gedcom_analysis import get_statistics_report, _get_attribute_statistics_internal, _get_timeline_internal, _get_ancestors_internal, _get_descendants_internal, _get_family_tree_summary_internal, _get_surname_statistics_internal, _get_date_range_analysis_internal, _find_potential_duplicates_internal, get_common_ancestors, get_living_status
from src.gedcom_mcp.gedcom_data_access import load_gedcom_file, _get_events_internal


class TestGedcomAnalysis(unittest.TestCase):

    def setUp(self):
        self.gedcom_ctx = GedcomContext()
        sample_ged_path = Path(__file__).parent / "sample.ged"
        load_gedcom_file(str(sample_ged_path), self.gedcom_ctx)

    def test_get_statistics_internal(self):
        stats = get_statistics_report(self.gedcom_ctx)
        self.assertEqual(stats['total_individuals'], 3)
        self.assertEqual(stats['total_families'], 1)
        self.assertEqual(stats['males'], 2)
        self.assertEqual(stats['females'], 1)
        # Check that both Birth and Death events are counted
        self.assertIn('Birth', stats['event_counts'])
        self.assertEqual(stats['event_counts']['Birth'], 3)
        self.assertIn('Death', stats['event_counts'])
        self.assertEqual(stats['event_counts']['Death'], 1)
        self.assertIn('Occupation', stats['event_counts'])
        self.assertEqual(stats['event_counts']['Occupation'], 1)

    def test_get_attribute_statistics_internal(self):
        stats = _get_attribute_statistics_internal(self.gedcom_ctx, 'OCCU')
        self.assertEqual(stats['Engineer'], 1)

    def test_get_timeline_internal(self):
        timeline = _get_timeline_internal('@I1@', self.gedcom_ctx)
        self.assertEqual(len(timeline), 4)
        # Check that we have the expected event types, but order may vary due to sorting
        event_types = [event['type'] for event in timeline]
        self.assertIn('BIRT', event_types)
        self.assertIn('DEAT', event_types)

    def test_get_ancestors_internal(self):
        ancestors = _get_ancestors_internal('@I3@', self.gedcom_ctx, format='flat')
        self.assertIn(('@I1@', 2), ancestors)
        self.assertIn(('@I2@', 2), ancestors)

    def test_get_descendants_internal(self):
        descendants = _get_descendants_internal('@I1@', self.gedcom_ctx, format='flat')
        self.assertIn(('@I3@', 2), descendants)

    def test_get_family_tree_summary_internal(self):
        summary = _get_family_tree_summary_internal('@I1@', self.gedcom_ctx)
        self.assertIn('John Smith', summary)
        self.assertIn('Jane Doe', summary)
        self.assertIn('Junior Smith', summary)

    def test_get_surname_statistics_internal(self):
        stats = _get_surname_statistics_internal(self.gedcom_ctx)
        self.assertIn('Smith', stats)

    @patch('gedcom.element.family.FamilyElement.get_marriages')
    def test_get_date_range_analysis_internal(self, mock_get_marriages):
        mock_get_marriages.return_value = [('1 JUN 1995', 'Las Vegas, USA')]
        analysis = _get_date_range_analysis_internal(self.gedcom_ctx)
        self.assertIn('1970', analysis)
        self.assertIn('2020', analysis)

    def test_find_potential_duplicates_internal(self):
        duplicates = _find_potential_duplicates_internal(self.gedcom_ctx)
        self.assertIsInstance(duplicates, str)

    def test_get_common_ancestors_internal(self):
        common_ancestors = get_common_ancestors(['@I3@', '@I1@'], self.gedcom_ctx)
        self.assertIsInstance(common_ancestors, dict)
        # Should find John Smith (@I1@) as common ancestor
        self.assertIn('common_ancestors', common_ancestors)
        self.assertGreater(len(common_ancestors['common_ancestors']), 0)
        # Check that the common ancestor has the right info
        found_ancestor = False
        for ancestor in common_ancestors['common_ancestors']:
            if ancestor['id'] == '@I1@':
                found_ancestor = True
                self.assertEqual(ancestor['name'], 'John Smith')
                break
        self.assertTrue(found_ancestor, "Should find John Smith as common ancestor")

    def test_get_living_status(self):
        # Test living status for John Smith (has death date)
        status = get_living_status('@I1@', self.gedcom_ctx)
        self.assertIn("Deceased", status)
        
        # Test living status for Junior Smith (no death date in sample)
        status = get_living_status('@I3@', self.gedcom_ctx)
        self.assertIn("Possibly living", status)


if __name__ == '__main__':
    unittest.main()