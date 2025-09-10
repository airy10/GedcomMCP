import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Add the parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.gedcom_mcp.gedcom_context import GedcomContext
from src.gedcom_mcp.gedcom_data_access import load_gedcom_file, save_gedcom_file, get_person_record, find_person_by_name, _get_relationships_internal, decode_event_details, _get_events_internal, _get_places_internal, _get_person_attributes_internal, _get_notes_internal, _get_sources_internal, search_gedcom
from src.gedcom_mcp.gedcom_analysis import _get_timeline_internal

class TestGedcomDataAccess(unittest.TestCase):

    def setUp(self):
        self.gedcom_ctx = GedcomContext()
        self.sample_ged_path = Path(__file__).parent / "sample.ged"
        load_gedcom_file(str(self.sample_ged_path), self.gedcom_ctx)

    def test_load_gedcom_file(self):
        self.assertIsNotNone(self.gedcom_ctx.gedcom_parser)

    def test_save_gedcom_file(self):
        save_path = Path(__file__).parent / "temp_sample.ged"
        save_gedcom_file(str(save_path), self.gedcom_ctx)
        self.assertTrue(save_path.exists())
        os.remove(save_path)

    def test_get_person_details_internal(self):
        person = get_person_record("@I1@", self.gedcom_ctx)
        self.assertEqual(person.name, "John Smith")

    def test_find_person_by_name(self):
        persons = find_person_by_name("John Smith", self.gedcom_ctx)
        self.assertEqual(len(persons), 1)
        self.assertEqual(persons[0].name, "John Smith")

    def test_get_relationships_internal(self):
        relationships = _get_relationships_internal("@I1@", self.gedcom_ctx)
        self.assertEqual(len(relationships['spouses']), 1)
        self.assertEqual(relationships['spouses'][0]['id'], '@I2@')
        self.assertEqual(len(relationships['children']), 1)
        self.assertEqual(relationships['children'][0]['id'], '@I3@')

    def test_get_events_internal(self):
        events = _get_events_internal("@I1@", self.gedcom_ctx)
        self.assertEqual(len(events), 4)

    @patch('gedcom.element.individual.IndividualElement.get_birth_data')
    def test_get_places_internal(self, mock_get_birth_data):
        mock_get_birth_data.return_value = ('1 JAN 1970', 'London, England')
        places = _get_places_internal(gedcom_ctx=self.gedcom_ctx)
        self.assertGreater(len(places), 0)

    def test_get_person_attributes_internal(self):
        attributes = _get_person_attributes_internal("@I1@", self.gedcom_ctx)
        self.assertEqual(attributes['OCCU'], 'Engineer')

    def test_search_gedcom(self):
        results = search_gedcom("John Smith", self.gedcom_ctx)
        self.assertGreater(len(results['people']), 0)

if __name__ == '__main__':
    unittest.main()