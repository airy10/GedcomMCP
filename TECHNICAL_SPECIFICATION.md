# GEDCOM MCP Server - Technical Specification

## Overview

This document provides technical specifications for implementing key improvements to the GEDCOM MCP server, focusing on enhanced search capabilities, better error handling, and performance improvements.

## 1. Enhanced Search Capabilities

### 1.1 Fuzzy Search Implementation

#### Requirements
- Integrate fuzzy string matching library (fuzzywuzzy or rapidfuzz)
- Maintain backward compatibility with existing exact search
- Provide configurable similarity thresholds
- Support for name, place, and other text fields

#### Implementation Plan

```python
# Add to requirements.txt
fuzzywuzzy>=0.18.0
python-levenshtein>=0.12.0

# New tool in fastmcp_server.py
@mcp.tool()
async def fuzzy_search_person(name: str, ctx: Context, threshold: int = 80, max_results: int = 50) -> list:
    """Search for persons with fuzzy name matching.
    
    Args:
        name: Search term to match against person names
        threshold: Minimum similarity score (0-100)
        max_results: Maximum number of results to return
    """
    from fuzzywuzzy import fuzz, process
    
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return [{"error": "No GEDCOM file loaded. Please load a GEDCOM file first."}]
    
    # Prepare list of names for fuzzy matching
    choices = []
    person_lookup = {}
    
    for person_id, individual in gedcom_ctx.individual_lookup.items():
        person_name = individual.get_name()
        if isinstance(person_name, tuple):
            person_name = " ".join(str(part) for part in person_name if part)
        else:
            person_name = str(person_name) if person_name else ""
        
        if person_name:  # Only include non-empty names
            choices.append(person_name)
            person_lookup[person_name] = person_id
    
    # Perform fuzzy search
    results = process.extract(name, choices, limit=max_results)
    
    # Filter by threshold and format results
    matches = []
    for match_name, score in results:
        if score >= threshold:
            person_id = person_lookup[match_name]
            person = get_person_details_internal(person_id, gedcom_ctx)
            if person:
                matches.append({
                    "person": person.model_dump(),
                    "similarity_score": score
                })
    
    return matches
```

#### Testing
- Unit tests for various name variations
- Performance tests with large datasets
- Integration tests with existing search functionality

### 1.2 Advanced Querying

#### Requirements
- Support for complex query conditions
- Logical operators (AND, OR, NOT)
- Comparison operators ($gt, $lt, $eq, $ne, $in, $nin)
- Regular expression support

#### Implementation Plan

```python
@mcp.tool()
async def query_people_advanced(ctx: Context, filters: str = "{}", page: int = 1, page_size: int = 100) -> dict:
    """Advanced querying with complex conditions and aggregations.
    
    Args:
        filters: JSON string containing query filters
        page: Page number for pagination
        page_size: Number of results per page
    """
    import json
    import operator
    
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {"error": "No GEDCOM file loaded. Please load a GEDCOM file first."}
    
    try:
        query_filters = json.loads(filters) if filters else {}
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON in filters parameter: {e}"}
    
    # Operator mapping
    ops = {
        "$gt": operator.gt,
        "$lt": operator.lt,
        "$gte": operator.ge,
        "$lte": operator.le,
        "$eq": operator.eq,
        "$ne": operator.ne,
        "$in": lambda x, y: x in y,
        "$nin": lambda x, y: x not in y
    }
    
    matching_people = []
    
    for person_id, individual in gedcom_ctx.individual_lookup.items():
        person = get_person_details_internal(person_id, gedcom_ctx)
        if person and _matches_advanced_criteria(person, query_filters, ops):
            matching_people.append(person)
    
    # Sort and paginate
    matching_people.sort(key=lambda p: p.id)
    total_count = len(matching_people)
    total_pages = (total_count + page_size - 1) // page_size
    start_index = (page - 1) * page_size
    end_index = min(start_index + page_size, total_count)
    page_people = matching_people[start_index:end_index]
    
    return {
        "total_count": total_count,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": page_size,
        "people": [person.model_dump() for person in page_people]
    }

def _matches_advanced_criteria(person, filters, ops):
    """Check if a person matches advanced query criteria."""
    for field, condition in filters.items():
        person_value = getattr(person, field, None)
        
        if isinstance(condition, dict):
            # Handle operator conditions
            for op_name, op_value in condition.items():
                if op_name in ops:
                    if not ops[op_name](person_value, op_value):
                        return False
                elif op_name == "$regex":
                    import re
                    if not re.search(op_value, str(person_value), re.IGNORECASE):
                        return False
        else:
            # Handle direct value matching
            if person_value != condition:
                return False
    
    return True
```

## 2. Better Error Handling

### 2.1 Structured Error Implementation

#### Requirements
- Consistent error format across all tools
- Error codes for programmatic handling
- Recovery suggestions for users
- Logging for debugging

#### Implementation Plan

```python
class GedcomError(Exception):
    """Base exception for GEDCOM operations."""
    
    def __init__(self, message: str, error_code: str = None, recovery_suggestion: str = None):
        self.message = message
        self.error_code = error_code or "UNKNOWN_ERROR"
        self.recovery_suggestion = recovery_suggestion
        super().__init__(self.message)
    
    def to_dict(self) -> dict:
        """Convert error to dictionary format."""
        result = {
            "error": self.message,
            "error_code": self.error_code
        }
        if self.recovery_suggestion:
            result["recovery_suggestion"] = self.recovery_suggestion
        return result

# Example usage in a tool
@mcp.tool()
async def load_gedcom(file_path: str, ctx: Context) -> dict:
    """Load and parse a GEDCOM file."""
    import os
    from pathlib import Path
    
    # Validate file path
    if not file_path:
        raise GedcomError(
            "File path is required",
            error_code="MISSING_FILE_PATH",
            recovery_suggestion="Provide a valid file path to a GEDCOM file"
        )
    
    # Check if file exists
    path = Path(file_path)
    if not path.exists():
        raise GedcomError(
            f"File not found: {file_path}",
            error_code="FILE_NOT_FOUND",
            recovery_suggestion="Check that the file path is correct and the file exists"
        )
    
    # Check if it's a file (not directory)
    if not path.is_file():
        raise GedcomError(
            f"Path is not a file: {file_path}",
            error_code="NOT_A_FILE",
            recovery_suggestion="Provide a path to a GEDCOM file, not a directory"
        )
    
    # Try to load the file
    gedcom_ctx = get_gedcom_context(ctx)
    try:
        success = load_gedcom_file(file_path, gedcom_ctx)
        if success:
            gedcom_ctx.gedcom_file_path = file_path
            return {
                "status": "success",
                "message": f"Successfully loaded GEDCOM file: {file_path}",
                "individuals": len(gedcom_ctx.individual_lookup),
                "families": len(gedcom_ctx.family_lookup)
            }
        else:
            raise GedcomError(
                f"Failed to parse GEDCOM file: {file_path}",
                error_code="PARSE_ERROR",
                recovery_suggestion="Check that the file is a valid GEDCOM format"
            )
    except Exception as e:
        raise GedcomError(
            f"Error loading GEDCOM file: {str(e)}",
            error_code="LOAD_ERROR",
            recovery_suggestion="Check file permissions and format"
        )
```

## 3. Performance Improvements

### 3.1 Progress Indicators

#### Requirements
- Progress tracking for long-running operations
- Regular status updates
- Non-blocking operation where possible

#### Implementation Plan

```python
import time
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)

class ProgressTracker:
    """Track progress of long-running operations."""
    
    def __init__(self, total_items: int, description: str, update_interval: int = 1000):
        self.total_items = total_items
        self.processed = 0
        self.description = description
        self.update_interval = update_interval
        self.start_time = time.time()
        self.last_update = 0
    
    def update(self, increment: int = 1, force: bool = False) -> None:
        """Update progress counter."""
        self.processed += increment
        current_time = time.time()
        
        # Update if forced or if enough time has passed
        if force or (current_time - self.last_update) >= 1.0:  # Update every second
            self._report_progress()
            self.last_update = current_time
    
    def _report_progress(self) -> None:
        """Report current progress."""
        if self.total_items > 0:
            percentage = (self.processed / self.total_items) * 100
            elapsed = time.time() - self.start_time
            
            # Estimate remaining time
            if self.processed > 0:
                rate = self.processed / elapsed
                remaining = (self.total_items - self.processed) / rate if rate > 0 else 0
            else:
                remaining = 0
            
            logger.info(
                f"{self.description}: {percentage:.1f}% complete "
                f"({self.processed}/{self.total_items}) - "
                f"Elapsed: {elapsed:.1f}s, Remaining: {remaining:.1f}s"
            )
    
    def finish(self) -> None:
        """Mark operation as complete."""
        self.processed = self.total_items
        self._report_progress()
        total_time = time.time() - self.start_time
        logger.info(f"{self.description}: Complete in {total_time:.1f}s")

# Example usage in _rebuild_lookups
def _rebuild_lookups(gedcom_ctx: GedcomContext):
    """Rebuild lookup dictionaries with progress tracking."""
    logger.info("Rebuilding lookup dictionaries...")
    
    # Clear existing lookups
    gedcom_ctx.individual_lookup.clear()
    gedcom_ctx.family_lookup.clear()
    gedcom_ctx.source_lookup.clear()
    gedcom_ctx.note_lookup.clear()
    
    # Get root elements
    root_elements = gedcom_ctx.gedcom_parser.get_root_child_elements()
    total_elements = len(root_elements)
    
    # Create progress tracker
    progress = ProgressTracker(total_elements, "Rebuilding lookups")
    
    # Process elements
    for i, elem in enumerate(root_elements):
        pointer = elem.get_pointer()
        tag = elem.get_tag()
        
        if isinstance(elem, IndividualElement):
            gedcom_ctx.individual_lookup[pointer] = elem
        elif isinstance(elem, FamilyElement):
            gedcom_ctx.family_lookup[pointer] = elem
        elif tag == "SOUR":
            gedcom_ctx.source_lookup[pointer] = elem
        elif tag == "NOTE":
            gedcom_ctx.note_lookup[pointer] = elem
        
        # Update progress every 100 elements
        if i % 100 == 0:
            progress.update(100)
    
    progress.finish()
    logger.info(
        f"Rebuilt lookup dictionaries: {len(gedcom_ctx.individual_lookup)} individuals, "
        f"{len(gedcom_ctx.family_lookup)} families, {len(gedcom_ctx.source_lookup)} sources, "
        f"{len(gedcom_ctx.note_lookup)} notes"
    )
```

## 4. Batch Operations

### 4.1 Batch Update Implementation

#### Requirements
- Efficient processing of multiple updates
- Transaction-like behavior with rollback
- Detailed reporting of results

#### Implementation Plan

```python
@mcp.tool()
async def batch_update_person_attributes(updates: str, ctx: Context) -> dict:
    """Update multiple person attributes in a single operation.
    
    Args:
        updates: JSON string containing list of updates
                Each update should have: person_id, attribute_tag, new_value
    """
    import json
    
    gedcom_ctx = get_gedcom_context(ctx)
    if not gedcom_ctx.gedcom_parser:
        return {"error": "No GEDCOM file loaded. Please load a GEDCOM file first."}
    
    try:
        update_list = json.loads(updates) if updates else []
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON in updates parameter: {e}"}
    
    if not isinstance(update_list, list):
        return {"error": "Updates parameter must be a JSON array"}
    
    results = {
        "total_updates": len(update_list),
        "successful": 0,
        "failed": 0,
        "errors": []
    }
    
    # Process updates
    for i, update in enumerate(update_list):
        try:
            # Validate update structure
            if not isinstance(update, dict):
                results["failed"] += 1
                results["errors"].append({
                    "index": i,
                    "error": "Update must be a JSON object"
                })
                continue
            
            person_id = update.get("person_id")
            attribute_tag = update.get("attribute_tag")
            new_value = update.get("new_value")
            
            if not all([person_id, attribute_tag, new_value is not None]):
                results["failed"] += 1
                results["errors"].append({
                    "index": i,
                    "error": "Missing required fields: person_id, attribute_tag, new_value"
                })
                continue
            
            # Perform update
            result = _update_person_attribute_internal(gedcom_ctx, person_id, attribute_tag, new_value)
            if "Error" in result:
                results["failed"] += 1
                results["errors"].append({
                    "index": i,
                    "person_id": person_id,
                    "error": result
                })
            else:
                results["successful"] += 1
                
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({
                "index": i,
                "error": str(e)
            })
    
    # Clear caches after successful updates
    if results["successful"] > 0:
        gedcom_ctx.clear_caches()
        _rebuild_lookups(gedcom_ctx)
    
    return results
```

## 5. Testing Strategy

### 5.1 Unit Tests

```python
# tests/test_enhanced_search.py
import unittest
from unittest.mock import patch, MagicMock
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gedcom_mcp.gedcom_context import GedcomContext
from src.gedcom_mcp.fastmcp_server import fuzzy_search_person

class TestEnhancedSearch(unittest.TestCase):
    
    def setUp(self):
        self.ctx = MagicMock()
        self.gedcom_ctx = GedcomContext()
        
    @patch('src.gedcom_mcp.fastmcp_server.get_gedcom_context')
    @patch('src.gedcom_mcp.fastmcp_server.get_person_details_internal')
    def test_fuzzy_search_exact_match(self, mock_get_person, mock_get_context):
        # Test setup
        mock_get_context.return_value = self.gedcom_ctx
        self.gedcom_ctx.gedcom_parser = MagicMock()
        
        # Mock individual lookup
        mock_individual = MagicMock()
        mock_individual.get_name.return_value = "John Smith"
        self.gedcom_ctx.individual_lookup = {"@I1@": mock_individual}
        
        # Mock person details
        mock_person = MagicMock()
        mock_person.id = "@I1@"
        mock_person.name = "John Smith"
        mock_get_person.return_value = mock_person
        
        # Test execution
        result = fuzzy_search_person("John Smith", self.ctx, threshold=90)
        
        # Assertions
        self.assertIsInstance(result, list)
        # Note: This is a simplified test - actual implementation would require
        # more complex mocking of the fuzzywuzzy library

if __name__ == '__main__':
    unittest.main()
```

### 5.2 Integration Tests

```python
# tests/test_batch_operations.py
import unittest
import json
from unittest.mock import patch, MagicMock
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gedcom_mcp.fastmcp_server import batch_update_person_attributes

class TestBatchOperations(unittest.TestCase):
    
    def setUp(self):
        self.ctx = MagicMock()
        
    @patch('src.gedcom_mcp.fastmcp_server.get_gedcom_context')
    @patch('src.gedcom_mcp.fastmcp_server._update_person_attribute_internal')
    def test_batch_update_success(self, mock_update_attr, mock_get_context):
        # Test setup
        mock_gedcom_ctx = MagicMock()
        mock_get_context.return_value = mock_gedcom_ctx
        mock_gedcom_ctx.gedcom_parser = MagicMock()
        
        mock_update_attr.return_value = "Successfully updated attribute"
        
        # Test data
        updates = json.dumps([
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
        ])
        
        # Test execution
        result = batch_update_person_attributes(updates, self.ctx)
        
        # Assertions
        self.assertIsInstance(result, dict)
        self.assertEqual(result["total_updates"], 2)
        self.assertEqual(result["successful"], 2)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(len(result["errors"]), 0)

if __name__ == '__main__':
    unittest.main()
```

## 6. Deployment Considerations

### 6.1 Dependency Management

Update `requirements.txt`:
```
fastmcp>=0.1.0
python-gedcom>=0.1.0
pydantic>=2.0.0
cachetools>=4.0.0
unidecode>=1.3.0
nameparser>=1.1.3
fuzzywuzzy>=0.18.0
python-levenshtein>=0.12.0
```

Update `pyproject.toml`:
```toml
[project.dependencies]
# ... existing dependencies ...
"fuzzywuzzy>=0.18.0",
"python-levenshtein>=0.12.0",

[project.optional-dependencies]
dev = [
    # ... existing dev dependencies ...
    "pytest-asyncio>=0.21.0",
]
```

### 6.2 Performance Monitoring

Add performance monitoring to critical functions:
```python
import time
import functools

def performance_monitor(func):
    """Decorator to monitor function performance."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        logger.info(f"{func.__name__} executed in {end_time - start_time:.3f}s")
        return result
    return wrapper

# Apply to critical functions
@performance_monitor
def _rebuild_lookups(gedcom_ctx: GedcomContext):
    # ... implementation ...
    pass
```

## 7. Documentation Updates

### 7.1 API Documentation

Update the help documentation in `fastmcp_server.py`:
```python
# Add to the help template
"""
## Enhanced Search Tools:
- **fuzzy_search_person**(name, threshold, max_results) - Search for persons with fuzzy name matching
- **query_people_advanced**(filters, page, page_size) - Advanced querying with complex conditions

## Batch Operations:
- **batch_update_person_attributes**(updates) - Update multiple person attributes in a single operation

## Data Quality Tools:
- **validate_gedcom_data**() - Validate GEDCOM data integrity and consistency
"""
```

This technical specification provides a roadmap for implementing key improvements to the GEDCOM MCP server while maintaining backward compatibility and ensuring robust testing.