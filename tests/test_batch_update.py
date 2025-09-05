import os
import sys
import unittest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.gedcom_mcp.gedcom_context import GedcomContext
from src.gedcom_mcp.gedcom_data_management import batch_update_person_attributes

class TestBatchUpdatePersonAttributesInternal(unittest.TestCase):

    def setUp(self):
        self.gedcom_ctx = GedcomContext()
        
    def test_batch_update_no_gedcom_loaded(self):
        """Test batch update when no GEDCOM file is loaded"""
        self.gedcom_ctx.gedcom_parser = None
        result = batch_update_person_attributes(self.gedcom_ctx, [])
        self.assertIsInstance(result, dict)
        self.assertIn("error", result)
        self.assertEqual(result["error"], "No GEDCOM file loaded. Please load a GEDCOM file first.")
    
    def test_batch_update_empty_list(self):
        """Test batch update with empty list"""
        self.gedcom_ctx.gedcom_parser = MagicMock()
        result = batch_update_person_attributes(self.gedcom_ctx, [])
        self.assertIsInstance(result, dict)
        self.assertEqual(result["total_updates"], 0)
        self.assertEqual(result["successful"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["errors"], [])
    
    def test_batch_update_invalid_update_type(self):
        """Test batch update with invalid update type"""
        self.gedcom_ctx.gedcom_parser = MagicMock()
        updates = ["not a dict"]
        result = batch_update_person_attributes(self.gedcom_ctx, updates)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["total_updates"], 1)
        self.assertEqual(result["successful"], 0)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["error"], "Update must be a dictionary")
    
    def test_batch_update_missing_fields(self):
        """Test batch update with missing required fields"""
        self.gedcom_ctx.gedcom_parser = MagicMock()
        updates = [{}]
        result = batch_update_person_attributes(self.gedcom_ctx, updates)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["total_updates"], 1)
        self.assertEqual(result["successful"], 0)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("Missing required fields", result["errors"][0]["error"])
    
    @patch('src.gedcom_mcp.gedcom_data_management._update_person_attribute_internal')
    def test_batch_update_success(self, mock_update_attr):
        """Test successful batch update"""
        self.gedcom_ctx.gedcom_parser = MagicMock()
        mock_update_attr.return_value = "Successfully updated attribute"
        
        updates = [
            {
                "person_id": "@I1@",
                "attribute_tag": "OCCU",
                "new_value": "Engineer"
            },
            {
                "person_id": "@I2@",
                "attribute_tag": "RELI",
                "new_value": "Christian"
            }
        ]
        
        result = batch_update_person_attributes(self.gedcom_ctx, updates)
        
        self.assertIsInstance(result, dict)
        self.assertEqual(result["total_updates"], 2)
        self.assertEqual(result["successful"], 2)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(len(result["errors"]), 0)
        self.assertEqual(mock_update_attr.call_count, 2)
    
    @patch('src.gedcom_mcp.gedcom_data_management._update_person_attribute_internal')
    def test_batch_update_partial_failure(self, mock_update_attr):
        """Test batch update with partial failure"""
        self.gedcom_ctx.gedcom_parser = MagicMock()
        mock_update_attr.side_effect = [
            "Successfully updated attribute",
            "Error: Person not found"
        ]
        
        updates = [
            {
                "person_id": "@I1@",
                "attribute_tag": "OCCU",
                "new_value": "Engineer"
            },
            {
                "person_id": "@I2@",
                "attribute_tag": "RELI",
                "new_value": "Christian"
            }
        ]
        
        result = batch_update_person_attributes(self.gedcom_ctx, updates)
        
        self.assertIsInstance(result, dict)
        self.assertEqual(result["total_updates"], 2)
        self.assertEqual(result["successful"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(mock_update_attr.call_count, 2)

if __name__ == '__main__':
    unittest.main()