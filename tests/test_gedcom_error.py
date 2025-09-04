import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.gedcom_mcp.fastmcp_server import GedcomError

class TestGedcomError(unittest.TestCase):

    def test_gedcom_error_creation(self):
        """Test creating a GedcomError with all parameters"""
        error = GedcomError(
            "Test error message",
            error_code="TEST_ERROR",
            recovery_suggestion="Try doing something else"
        )
        
        self.assertEqual(error.message, "Test error message")
        self.assertEqual(error.error_code, "TEST_ERROR")
        self.assertEqual(error.recovery_suggestion, "Try doing something else")
        self.assertEqual(str(error), "Test error message")

    def test_gedcom_error_default_error_code(self):
        """Test creating a GedcomError with default error code"""
        error = GedcomError("Test error message")
        
        self.assertEqual(error.message, "Test error message")
        self.assertEqual(error.error_code, "UNKNOWN_ERROR")
        self.assertIsNone(error.recovery_suggestion)

    def test_gedcom_error_to_dict(self):
        """Test converting GedcomError to dictionary"""
        # Test with all parameters
        error = GedcomError(
            "Test error message",
            error_code="TEST_ERROR",
            recovery_suggestion="Try doing something else"
        )
        
        error_dict = error.to_dict()
        self.assertIsInstance(error_dict, dict)
        self.assertEqual(error_dict["error"], "Test error message")
        self.assertEqual(error_dict["error_code"], "TEST_ERROR")
        self.assertEqual(error_dict["recovery_suggestion"], "Try doing something else")
        
        # Test with default error code
        error2 = GedcomError("Another error")
        error_dict2 = error2.to_dict()
        self.assertEqual(error_dict2["error"], "Another error")
        self.assertEqual(error_dict2["error_code"], "UNKNOWN_ERROR")
        self.assertNotIn("recovery_suggestion", error_dict2)

if __name__ == '__main__':
    unittest.main()