# GEDCOM MCP Server

Genealogy for AI Agents, by AI Agents

A MCP server for creating, editing and querying genealogical data from GEDCOM files.
Works great with qwen-cli and gemini-cli

Mostly written by various AI Agents, while some parenting was sometimes quite necessary...

It's more an experiment than some finish product and the list of tools is probably way to high but it's covering a lot of various tasks.
Test files will be re-added after they are sorted...

It's able to search the genealogy about complex queries
Also useful for automatically filling the GEDCOM file from internet info (for example,
build a full family GEDCOM from a person wikipedia page..) and creating some nice
biography for any GEDCOM individual, being able to complete the document with geographic
or historal context by searching the web

Some sample complex prompts:
   Load gedcom "myfamily.ged"
   Make a complete, detailled biography of <name of some people from the GEDCOM> and his fammily. Use as much as you can from this genealogy, including any notes from him or his relatives. 
   You can try to find some info on Internet to complete the document, add some historical or geographic context, etc. Be as complete as possible to tell us a nice story, easy to read by everyone

    or

  Create a new GEDCOM file - save it to "napo.ged"                                                                                                                                              
  Fetch the content of Napoleon I's Wikipedia page                                                                                                                                           
    1. Extract genealogical information about him and people mentioned on his page                                                                                                             
    2. Follow links to other people's Wikipedia pages to gather more information                                                                                                              
    3. Create a comprehensive genealogical record  with as much details as possible. Including birth/death dates and place, family relationships (parents, spouses, children...), occupation, etc, and including a note with the person wikipedia page address and important info about his life                                                                                                                    
    4. Repeat the same process with all people added by previous steps                                                                                                                       
   Continuously save the GEDCOM file as new people are added                                                                                                                                 

    or

   Load gedcom "myfamily.ged"
   What's shortest path from John Doe to Bob Smith ?
   And who are their common ancestors ?
   

## Features

- Load and parse GEDCOM files
- Add/edit people, families, events, and places
- Query people, families, events, and places
- Find relationships between individuals
- Generate family trees and timelines
- Search across all genealogical data
- Get detailed person and family information
- Analyze genealogical data with statistics and duplicates detection

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

## Project Structure

- `src/gedcom_mcp/`: Main source code
  - `fastmcp_server.py`: Main server application
  - `gedcom_*.py`: Modules for handling GEDCOM data
- `tests/`: Unit tests
- `to_be_sorted/`: Files that need further organization
- `requirements.txt`: Project dependencies
- `pyproject.toml`: Build configuration

## Contributing

1. Fork the repository
2. Create a new branch for your feature or bug fix
3. Make your changes and commit them with descriptive messages
4. Push your changes to your fork
5. Create a pull request to the main repository

## License

This project is licensed under the MIT License.
