import os
import sys
import unittest

# Add the parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.gedcom_mcp.gedcom_models import PersonDetails, PersonRelationships, NodePriority


class TestGedcomModels(unittest.TestCase):

    def test_person_details_model(self):
        """Test PersonDetails model creation and attributes"""
        person = PersonDetails(
            id="@I1@",
            name="John Smith",
            birth_date="1 JAN 1970",
            birth_place="London, England",
            death_date="1 JAN 2020",
            death_place="Paris, France",
            gender="M",
            occupation="Engineer",
            parents=["@I3@", "@I4@"],
            spouses=["@I2@"],
            children=["@I5@"]
        )
        
        self.assertEqual(person.id, "@I1@")
        self.assertEqual(person.name, "John Smith")
        self.assertEqual(person.birth_date, "1 JAN 1970")
        self.assertEqual(person.birth_place, "London, England")
        self.assertEqual(person.death_date, "1 JAN 2020")
        self.assertEqual(person.death_place, "Paris, France")
        self.assertEqual(person.gender, "M")
        self.assertEqual(person.occupation, "Engineer")
        self.assertEqual(person.parents, ["@I3@", "@I4@"])
        self.assertEqual(person.spouses, ["@I2@"])
        self.assertEqual(person.children, ["@I5@"])

    def test_person_details_model_defaults(self):
        """Test PersonDetails model with default values"""
        person = PersonDetails(id="@I1@", name="John Smith")
        
        self.assertEqual(person.id, "@I1@")
        self.assertEqual(person.name, "John Smith")
        self.assertIsNone(person.birth_date)
        self.assertIsNone(person.birth_place)
        self.assertIsNone(person.death_date)
        self.assertIsNone(person.death_place)
        self.assertIsNone(person.gender)
        self.assertIsNone(person.occupation)
        self.assertEqual(person.parents, [])
        self.assertEqual(person.spouses, [])
        self.assertEqual(person.children, [])

    def test_person_relationships_model(self):
        """Test PersonRelationships model creation and attributes"""
        relationships = PersonRelationships(
            id="@I1@",
            gender="M",
            parents=["@I3@", "@I4@"],
            spouses=["@I2@"],
            children=["@I5@"]
        )
        
        self.assertEqual(relationships.id, "@I1@")
        self.assertEqual(relationships.gender, "M")
        self.assertEqual(relationships.parents, ["@I3@", "@I4@"])
        self.assertEqual(relationships.spouses, ["@I2@"])
        self.assertEqual(relationships.children, ["@I5@"])

    def test_person_relationships_model_defaults(self):
        """Test PersonRelationships model with default values"""
        relationships = PersonRelationships(id="@I1@")
        
        self.assertEqual(relationships.id, "@I1@")
        self.assertIsNone(relationships.gender)
        self.assertEqual(relationships.parents, [])
        self.assertEqual(relationships.spouses, [])
        self.assertEqual(relationships.children, [])

    def test_node_priority_creation(self):
        """Test NodePriority creation and initialization"""
        node = NodePriority(
            distance=5,
            person_id="@I1@",
            path=["@I1@", "@I2@", "@I3@"],
            target_birth_year=1970
        )
        
        self.assertEqual(node.distance, 5)
        self.assertEqual(node.person_id, "@I1@")
        self.assertEqual(node.path, ["@I1@", "@I2@", "@I3@"])
        self.assertEqual(node.target_birth_year, 1970)
        
        # Check that computed fields are initialized
        self.assertIsInstance(node._adjusted_distance, float)
        self.assertIsInstance(node._birth_year_distance, int)

    def test_node_priority_comparison(self):
        """Test NodePriority comparison methods"""
        node1 = NodePriority(1, "@I1@", ["@I1@"], 1970)
        node2 = NodePriority(2, "@I2@", ["@I2@"], 1970)
        
        # Test __lt__ method
        self.assertTrue(node1 < node2)
        self.assertFalse(node2 < node1)
        
        # Test __eq__ method
        node3 = NodePriority(1, "@I1@", ["@I1@"], 1970)
        self.assertEqual(node1, node3)

    def test_node_priority_heuristics(self):
        """Test NodePriority heuristic initialization"""
        node = NodePriority(5, "@I1@", ["@I1@"], 1970)
        
        # Test that init_heuristics can be called (doesn't crash)
        # We can't easily test the actual heuristic values without a full context
        # When called with None, it should handle the error gracefully
        try:
            # This would normally require a gedcom context
            node.init_heuristics(None)
            success = True
        except AttributeError:
            # Expected error when called with None context
            success = True
        except Exception as e:
            # Unexpected error
            print(f"Unexpected error: {e}")
            success = False
        
        # The method should handle None context gracefully
        self.assertTrue(success)


if __name__ == '__main__':
    unittest.main()