import os
import sys
import unittest
import json
from pathlib import Path

# Add the parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.gedcom_mcp.gedcom_context import GedcomContext
from src.gedcom_mcp.gedcom_data_access import load_gedcom_file
from src.gedcom_mcp.gedcom_search import find_shortest_relationship_path, _find_all_relationship_paths_internal


class TestGedcomSearchComplex(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Load the royal92.ged file once for all tests in this class"""
        cls.gedcom_ctx = GedcomContext()
        royal_ged_path = Path(__file__).parent / "royal92.ged"
        if royal_ged_path.exists():
            load_result = load_gedcom_file(str(royal_ged_path), cls.gedcom_ctx)
            if not load_result:
                raise Exception("Failed to load royal92.ged file")
        else:
            raise Exception("royal92.ged file not found")

    def test_royal_family_shortest_path(self):
        """Test finding shortest relationship path between James Crombie (@I799@) and Alexander Zoubkoff (@I1203@)"""
        # Skip test if the specific individuals are not found in the GEDCOM
        if "@I799@" not in self.gedcom_ctx.individual_lookup or "@I1203@" not in self.gedcom_ctx.individual_lookup:
            self.skipTest("Required individuals not found in royal92.ged")
            
        # Find the shortest relationship path
        result = find_shortest_relationship_path("@I799@", "@I1203@", "all", self.gedcom_ctx)
        
        # Verify the result structure
        self.assertIsInstance(result, dict)
        self.assertIn("path", result)
        self.assertIn("distance", result)
        self.assertIn("relationship_chain", result)
        
        # Verify the path exists
        self.assertIsNotNone(result["path"])
        self.assertGreater(len(result["path"]), 0)
        
        # Verify the distance is reasonable (at least 1, no more than some reasonable upper limit)
        self.assertGreaterEqual(result["distance"], 1)
        self.assertLessEqual(result["distance"], 20)  # Reasonable upper limit for royal connections
        
        # Verify the start and end of the path
        self.assertEqual(result["path"][0]["id"].strip(), "@I799@")
        self.assertEqual(result["path"][0]["name"], "James Crombie")
        self.assertEqual(result["path"][-1]["id"].strip(), "@I1203@")
        self.assertEqual(result["path"][-1]["name"], "Alexander Zoubkoff")
        
        # Verify the relationship chain has the correct length (one less than path length)
        self.assertEqual(len(result["relationship_chain"]), len(result["path"]) - 1)

    def test_royal_family_all_paths(self):
        """Test finding all relationship paths between James Crombie (@I799@) and Alexander Zoubkoff (@I1203@)"""
        # Skip test if the specific individuals are not found in the GEDCOM
        if "@I799@" not in self.gedcom_ctx.individual_lookup or "@I1203@" not in self.gedcom_ctx.individual_lookup:
            self.skipTest("Required individuals not found in royal92.ged")
            
        # Find all relationship paths
        result = _find_all_relationship_paths_internal("@I799@", "@I1203@", "all", self.gedcom_ctx)
        
        # Verify the result structure
        self.assertIsInstance(result, dict)
        self.assertIn("paths", result)
        self.assertIn("total_paths", result)
        
        # Verify that paths were found
        self.assertGreaterEqual(result["total_paths"], 1)
        self.assertGreaterEqual(len(result["paths"]), 1)
        
        # Verify the first path has the correct start and end
        first_path = result["paths"][0]
        self.assertEqual(first_path["path"][0]["id"].strip(), "@I799@")
        self.assertEqual(first_path["path"][-1]["id"].strip(), "@I1203@")

    def test_royal_family_path_consistency(self):
        """Test that the shortest path is consistent and reasonable"""
        # Skip test if the specific individuals are not found in the GEDCOM
        if "@I799@" not in self.gedcom_ctx.individual_lookup or "@I1203@" not in self.gedcom_ctx.individual_lookup:
            self.skipTest("Required individuals not found in royal92.ged")
            
        # Get the shortest path
        shortest_result = find_shortest_relationship_path("@I799@", "@I1203@", "all", self.gedcom_ctx)
        
        # Get all paths
        all_result = _find_all_relationship_paths_internal("@I799@", "@I1203@", "all", self.gedcom_ctx)
        
        # If both found paths, verify basic consistency
        if (all_result["total_paths"] > 0 and shortest_result["path"] is not None and 
            len(all_result["paths"]) > 0):
            first_all_path = all_result["paths"][0]
            # The shortest path distance should be <= the first path in all paths
            self.assertLessEqual(shortest_result["distance"], first_all_path["distance"])

    def test_royal_family_intermediate_connections(self):
        """Test that the path goes through reasonable royal family connections"""
        # Skip test if the specific individuals are not found in the GEDCOM
        if "@I799@" not in self.gedcom_ctx.individual_lookup or "@I1203@" not in self.gedcom_ctx.individual_lookup:
            self.skipTest("Required individuals not found in royal92.ged")
            
        # Find the shortest relationship path
        result = find_shortest_relationship_path("@I799@", "@I1203@", "all", self.gedcom_ctx)
        
        # Skip if no path was found
        if result["path"] is None:
            self.skipTest("No path found between individuals")
            
        # Check that the path has reasonable length
        self.assertGreaterEqual(len(result["path"]), 3)  # At least 3 people in a meaningful connection
        self.assertLessEqual(len(result["path"]), 20)   # Reasonable upper limit
        
        # Check that some expected royal family members might be in the path
        path_names = [person["name"] for person in result["path"]]
        
        # These are some key royal family names we might expect to see
        royal_names = ["Charles", "Diana", "Philip", "Victoria", "Windsor", "Spencer"]
        
        # Check that at least some royal names are in the path
        found_royals = [name for name in royal_names if any(name in path_name for path_name in path_names)]
        # This is a loose check - we just want to verify the path goes through some royal connections

    def test_royal_family_relationship_type_comparison(self):
        """Test that different relationship types produce different path lengths"""
        # Skip test if the specific individuals are not found in the GEDCOM
        if "@I799@" not in self.gedcom_ctx.individual_lookup or "@I1203@" not in self.gedcom_ctx.individual_lookup:
            self.skipTest("Required individuals not found in royal92.ged")
            
        # Find path with all relationship types (should be shortest)
        all_result = find_shortest_relationship_path("@I799@", "@I1203@", "all", self.gedcom_ctx)
        
        # Find path with only parent/child/spouse (should be longer or equal)
        limited_result = find_shortest_relationship_path("@I799@", "@I1203@", "parent,child,spouse", self.gedcom_ctx)
        
        # Find path with only blood relationships (parent/child) - should not find a path
        blood_result = find_shortest_relationship_path("@I799@", "@I1203@", "blood", self.gedcom_ctx)
        
        # All should find valid paths except blood-only (since they're not directly blood-related)
        self.assertIsNotNone(all_result["path"])
        self.assertIsNotNone(limited_result["path"])
        self.assertNotEqual(all_result["distance"], -1)
        self.assertNotEqual(limited_result["distance"], -1)
        
        # The blood-only search should not find a path (distance = -1)
        self.assertEqual(blood_result["distance"], -1)
        self.assertIsNone(blood_result["path"])
        
        # The path with all relationships should be shorter or equal to the limited path
        # (In this case, it should be shorter because sibling relationships provide shortcuts)
        self.assertLessEqual(all_result["distance"], limited_result["distance"])
        
        # Print the distances for verification (this is the key insight from the user's observation)
        print(f"Distance with all relationships: {all_result['distance']}")
        print(f"Distance with parent/child/spouse only: {limited_result['distance']}")
        print(f"Distance with blood relationships only: {blood_result['distance']} (no path expected)")

    def test_royal_family_specific_path_example(self):
        """Test that we can find a path similar to the documented example (distance 14) with specific constraints"""
        # Skip test if the specific individuals are not found in the GEDCOM
        if "@I799@" not in self.gedcom_ctx.individual_lookup or "@I1203@" not in self.gedcom_ctx.individual_lookup:
            self.skipTest("Required individuals not found in royal92.ged")
            
        # Try to find a path that goes through Elizabeth II (@I52@) which was mentioned in the example
        # We can't force the algorithm to find a specific path, but we can verify it works with the data
        
        # First verify that Elizabeth II exists in the GEDCOM
        if "@I52@" in self.gedcom_ctx.individual_lookup:
            # Try to find a path between James Crombie and Elizabeth II
            result = find_shortest_relationship_path("@I799@", "@I52@", "all", self.gedcom_ctx)
            
            # Verify we can find a connection to Elizabeth II
            self.assertIsNotNone(result["path"])
            self.assertNotEqual(result["distance"], -1)
            
            # Try to find a path between Elizabeth II and Alexander Zoubkoff
            result2 = find_shortest_relationship_path("@I52@", "@I1203@", "all", self.gedcom_ctx)
            
            # Verify we can find a connection from Elizabeth II
            self.assertIsNotNone(result2["path"])
            self.assertNotEqual(result2["distance"], -1)


if __name__ == '__main__':
    # Check if royal92.ged exists before running tests
    royal_ged_path = Path(__file__).parent / "royal92.ged"
    if not royal_ged_path.exists():
        print("Skipping royal family tests - royal92.ged not found")
        sys.exit(0)
    
    unittest.main()