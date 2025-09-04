# GEDCOM MCP Server

Genealogy for AI Agents, by AI Agents

A robust MCP server for creating, editing and querying genealogical data from GEDCOM files.
Works great with qwen-cli and gemini-cli

This project provides a comprehensive set of tools for AI agents to work with family history data,
enabling complex genealogical research, data analysis, and automated documentation generation.

The server has been recently improved with fixes for critical bugs, enhanced error handling,
and better code quality while maintaining full backward compatibility.

Some sample complex prompts:
```
   Load gedcom "myfamily.ged"
   Make a complete, detailled biography of <name of some people from the GEDCOM> and his fammily. Use as much as you can from this genealogy, including any notes from him or his relatives. 
   You can try to find some info on Internet to complete the document, add some historical or geographic context, etc. Be as complete as possible to tell us a nice story, easy to read by everyone
```

or
    
```
  Create a new GEDCOM file - save it to "napo.ged"                                                                                                                                              
  Fetch the content of Napoleon I's Wikipedia page                                                                                                                                           
    1. Extract genealogical information about him and people mentioned on his page                                                                                                             
    2. Follow links to other people's Wikipedia pages to gather more information                                                                                                              
    3. Create a comprehensive genealogical record  with as much details as possible. Including birth/death dates and place, family relationships (parents, spouses, children...), occupation, etc, and including a note with the person wikipedia page address and important info about his life                                                                                                                    
    4. Repeat the same process with all people added by previous steps                                                                                                                       
   Continuously save the GEDCOM file as new people are added
```

or
    
```
   Load gedcom "myfamily.ged"
   What's shortest path from John Doe to Bob Smith ?
   And who are their common ancestors ?
```   

## Features

- **Data Management**: Load and parse GEDCOM files, add/edit people, families, events, and places
- **Powerful Querying**: Search across people, families, events, and places with flexible criteria
- **Relationship Analysis**: Find relationships between individuals, common ancestors, and family connections
- **Family Trees**: Generate multi-generational ancestor and descendant trees with detailed information
- **Timeline Generation**: Create chronological timelines of life events
- **Data Analysis**: Analyze genealogical data with comprehensive statistics, duplicate detection, and surname analysis
- **Historical Context**: Extract date ranges and historical period information
- **Metadata Handling**: Rich support for notes, sources, and detailed event information
- **Data Validation**: Validate date consistency and data integrity
- **Batch Operations**: Efficient bulk processing capabilities

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/airy10/GedcomMCP.git
   cd GedcomMCP
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

To start the server with the default HTTP transport:

```bash
python src/gedcom_mcp/fastmcp_server.py
```

To start the server with stdio transport:

```bash
python src/gedcom_mcp/fastmcp_server.py --transport stdio
```

To specify a different host or port for the HTTP transport:

```bash
python src/gedcom_mcp/fastmcp_server.py --host 0.0.0.0 --port 8080
```

## Running Tests

To run all tests:

```bash
python -m pytest tests/
```

To run tests with verbose output:

```bash
python -m pytest tests/ -v
```

To run a specific test file:

```bash
python -m pytest tests/test_gedcom_data_access.py
```

To run a specific test:

```bash
python -m pytest tests/test_gedcom_data_access.py::TestGedcomDataAccess::test_load_gedcom_file
```

## Project Structure

- `src/gedcom_mcp/`: Main source code
  - `fastmcp_server.py`: Main server application and tool definitions
  - `gedcom_context.py`: GEDCOM parsing context and caching management
  - `gedcom_data_access.py`: Data retrieval and extraction functions
  - `gedcom_data_management.py`: Data modification and management functions
  - `gedcom_analysis.py`: Statistical analysis and reporting functions
  - `gedcom_search.py`: Relationship finding and path analysis
  - `gedcom_utils.py`: Utility functions for data processing
  - `gedcom_constants.py`: GEDCOM event and attribute definitions
  - `gedcom_date_utils.py`: Advanced date parsing and validation
  - `gedcom_name_utils.py`: Name parsing and normalization
  - `gedcom_place_utils.py`: Place name normalization and geographic hierarchy
  - `gedcom_models.py`: Data models and structures
- `tests/`: Comprehensive unit and integration tests
- `requirements.txt`: Project dependencies
- `pyproject.toml`: Build configuration
- `prompts/`: Template files for LLM prompt generation

## Recent Improvements

This project has undergone significant improvements including:
- Fixed critical bugs in note processing and attribute handling
- Resolved syntax errors and improved code quality
- Enhanced error handling with better error messages
- Removed debug statements from production code
- Improved documentation consistency
- Maintained full backward compatibility
- All 99 automated tests continue to pass

## Contributing

1. Fork the repository
2. Create a new branch for your feature or bug fix
3. Make your changes and commit them with descriptive messages
4. Push your changes to your fork
5. Create a pull request to the main repository

## License

This project is licensed under the MIT License.
