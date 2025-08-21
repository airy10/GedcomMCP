# GEDCOM MCP Project Overview

This project, "GedcomMCP," is an AI-driven server designed for creating, editing, and querying genealogical data from GEDCOM files. It aims to provide a robust platform for AI agents to interact with and manage genealogical information, enabling complex queries, data enrichment from external sources like Wikipedia, and the generation of detailed biographies and family trees. It's an experimental project focusing on leveraging AI for genealogical tasks.

## Key Features:
- Load and parse GEDCOM files.
- Add/edit people, families, events, and places.
- Query people, families, events, and places.
- Find relationships between individuals.
- Generate family trees and timelines.
- Search across all genealogical data.
- Get detailed person and family information.
- Analyze genealogical data with statistics and duplicates detection.

## Technologies:
The project is primarily written in Python, utilizing `pytest` for testing. It functions as an MCP (Multi-Agent Communication Protocol) server.

## Building and Running

### Installation:
1.  **Clone the repository:**
    ```bash
    git clone https://github.com/airy10/GedcomMCP.git
    cd GedcomMCP
    ```
2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

### Usage:
To start the server:

-   **With default HTTP transport:**
    ```bash
    python src/gedcom_mcp/fastmcp_server.py
    ```
-   **With stdio transport:**
    ```bash
    python src/gedcom_mcp/fastmcp_server.py --transport stdio
    ```
-   **Specify host/port for HTTP transport:**
    ```bash
    python src/gedcom_mcp/fastmcp_server.py --host 0.0.0.0 --port 8080
    ```

## Development Conventions

### Project Structure:
-   `src/gedcom_mcp/`: Contains the main source code, including `fastmcp_server.py` (main server application) and various `gedcom_*.py` modules for handling GEDCOM data.
-   `tests/`: Houses unit tests for the project.
-   `prompts/`: Contains prompt templates for various AI tasks.
-   `requirements.txt`: Lists project dependencies.
-   `pyproject.toml`: Build configuration.

### Testing:
-   **Run all tests:**
    ```bash
    python -m pytest tests/
    ```
-   **Run tests with verbose output:**
    ```bash
    python -m pytest tests/ -v
    ```
-   **Run a specific test file:**
    ```bash
    python -m pytest tests/test_gedcom_data_access.py
    ```
-   **Run a specific test:**
    ```bash
    python -m pytest tests/test_gedcom_data_access.py::TestGedcomDataAccess::test_load_gedcom_file
    ```

### Contributing:
Contributions are welcome. The standard process involves forking the repository, creating a new branch, making changes, committing with descriptive messages, pushing to your fork, and finally creating a pull request.

### License:
This project is licensed under the MIT License.
