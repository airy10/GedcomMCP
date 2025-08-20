# Contributing to GEDCOM MCP Server

We welcome contributions to the GEDCOM MCP Server project! This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/your-username/GedcomMCP.git
   cd GedcomMCP
   ```
3. Create a new branch for your feature or bug fix:
   ```bash
   git checkout -b feature/your-feature-name
   ```
   or
   ```bash
   git checkout -b bugfix/your-bug-fix
   ```

## Development Setup

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
   ```
2. Install the development dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Code Style

- Follow PEP 8 style guide for Python code
- Use meaningful variable and function names
- Write docstrings for all public classes, methods, and functions
- Keep functions and methods small and focused
- Write unit tests for new functionality

## Testing

- Run the existing test suite to ensure nothing is broken:
  ```bash
  python -m pytest tests/
  ```
- Add new tests for any functionality you implement
- Ensure all tests pass before submitting a pull request

## Pull Request Process

1. Ensure your code follows the project's coding standards
2. Update the README.md with details of changes to the interface, if applicable
3. Increase the version numbers in any examples files and the README.md to the new version that this Pull Request would represent
4. Submit a pull request to the main repository with a clear title and description

## Reporting Issues

- Use the GitHub issue tracker to report bugs or suggest features
- Describe the issue in detail
- Include steps to reproduce the issue if it's a bug
- Specify the version of the software you're using

Thank you for your contributions!