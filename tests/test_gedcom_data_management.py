import os
import sys
import unittest
from pathlib import Path

# Add the parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.gedcom_mcp.gedcom_context import GedcomContext
from src.gedcom_mcp.gedcom_data_access import load_gedcom_file, get_person_record
from src.gedcom_mcp.gedcom_data_management import _add_person_internal, _create_marriage_internal, _add_child_to_family_internal, _remove_child_from_family_internal, _remove_parent_from_family_internal, _remove_event_internal, _remove_parents_internal, _update_event_details_internal, _create_note_internal, _add_note_to_entity_internal, _update_person_attribute_internal, _remove_person_attribute_internal, _update_person_details_internal, _create_source_internal, _delete_note_entity_internal, _new_empty_gedcom_internal, _find_next_available_id


class TestGedcomDataManagement(unittest.TestCase):

    def setUp(self):
        self.gedcom_ctx = GedcomContext()
        sample_ged_path = Path(__file__).parent / "sample.ged"
        load_gedcom_file(str(sample_ged_path), self.gedcom_ctx)

    def test_add_person_internal(self):
        person_id = _add_person_internal(self.gedcom_ctx, "Test User", "M")
        person = get_person_record(person_id, self.gedcom_ctx)
        self.assertEqual(person.name, "Test User")

    def test_create_marriage_internal(self):
        family_id = _create_marriage_internal(self.gedcom_ctx, "@I1@", "@I2@")
        self.assertIsNotNone(family_id)

    def test_add_child_to_family_internal(self):
        _add_child_to_family_internal(self.gedcom_ctx, "@I3@", "@F1@")
        child = self.gedcom_ctx.individual_lookup["@I3@"]
        famc_tags = [el.get_value() for el in child.get_child_elements() if el.get_tag() == "FAMC"]
        self.assertIn("@F1@", famc_tags)

    def test_remove_child_from_family_internal(self):
        _remove_child_from_family_internal(self.gedcom_ctx, "@I3@", "@F1@")
        child = self.gedcom_ctx.individual_lookup["@I3@"]
        famc_tags = [el.get_value() for el in child.get_child_elements() if el.get_tag() == "FAMC"]
        self.assertNotIn("@F1@", famc_tags)

    def test_remove_parent_from_family_internal(self):
        _remove_parent_from_family_internal(self.gedcom_ctx, "@I1@", "@F1@")
        person = get_person_record("@I1@", self.gedcom_ctx)
        self.assertNotIn("@F1@", person.spouses)

    def test_update_event_details_internal(self):
        _update_event_details_internal(self.gedcom_ctx, "@I1@", "BIRT", new_date="2 JAN 1970")
        person = get_person_record("@I1@", self.gedcom_ctx)
        self.assertEqual(person.birth_date, "2 JAN 1970")

    def test_update_person_attribute_internal(self):
        _update_person_attribute_internal(self.gedcom_ctx, "@I1@", "OCCU", "Doctor")
        person = get_person_record("@I1@", self.gedcom_ctx)
        self.assertEqual(person.occupation, "Doctor")

    def test_update_person_details_internal(self):
        _update_person_details_internal(self.gedcom_ctx, "@I1@", name="John Doe")
        person = get_person_record("@I1@", self.gedcom_ctx)
        self.assertEqual(person.name, "John Doe")

    def test_new_empty_gedcom_internal(self):
        _new_empty_gedcom_internal(self.gedcom_ctx)
        self.assertEqual(len(self.gedcom_ctx.individual_lookup), 0)
        self.assertEqual(len(self.gedcom_ctx.family_lookup), 0)
        # Reset context for other tests
        sample_ged_path = Path(__file__).parent / "sample.ged"
        load_gedcom_file(str(sample_ged_path), self.gedcom_ctx)

    def test_remove_event_internal(self):
        # Test removing an event
        result = _remove_event_internal(self.gedcom_ctx, "@I1@", "BIRT", "1 JAN 1970")
        self.assertIn("successfully", result.lower())

    def test_remove_parents_internal(self):
        # Test removing parents
        result = _remove_parents_internal(self.gedcom_ctx, "@I3@")
        self.assertIn("successfully", result.lower())

    def test_create_note_internal(self):
        # Test creating a note
        note_id = _create_note_internal(self.gedcom_ctx, "This is a test note")
        self.assertIsNotNone(note_id)
        self.assertTrue(note_id.startswith("@N"))

    def test_add_note_to_entity_internal(self):
        # Test adding a note to an entity
        result = _add_note_to_entity_internal(self.gedcom_ctx, "@I1@", "This is a test note for John Smith")
        self.assertIn("successfully", result.lower())

    def test_remove_person_attribute_internal(self):
        # First add an attribute to remove
        _update_person_attribute_internal(self.gedcom_ctx, "@I1@", "OCCU", "Engineer")
        # Then remove it
        result = _remove_person_attribute_internal(self.gedcom_ctx, "@I1@", "OCCU")
        self.assertIn("successfully", result.lower())

    def test_create_source_internal(self):
        # Test creating a source
        source_id = _create_source_internal(self.gedcom_ctx, "Test Source", "Test Author", "Test Publication")
        self.assertIsNotNone(source_id)
        self.assertTrue(source_id.startswith("@S"))

    def test_delete_note_entity_internal(self):
        # First create a note to delete
        note_id = _create_note_internal(self.gedcom_ctx, "This is a test note to delete")
        # Then delete it
        result = _delete_note_entity_internal(self.gedcom_ctx, note_id)
        self.assertIn("successfully", result.lower())

    def test_find_next_available_id(self):
        # Test finding next available ID
        next_id = _find_next_available_id("@I", self.gedcom_ctx.individual_lookup)
        self.assertIsNotNone(next_id)
        self.assertTrue(next_id.startswith("@I"))
        self.assertTrue(next_id.endswith("@"))


if __name__ == '__main__':
    unittest.main()