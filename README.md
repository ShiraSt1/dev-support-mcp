# Nebius - MCP Server for Developer Support

Nebius is a local **Model Context Protocol (MCP)** server written in Python, designed to help developers diagnose and understand programming errors.  
The server exposes multiple MCP tools, including Stack Overflow–based error analysis and a small weather API integration.

All MCP tools were tested both with Claude and the MCP Inspector to ensure
correct tool registration, argument validation, and consistent JSON-RPC responses.

## Project Overview

Nebius assists developers by:
- Cleaning and normalizing raw error messages
- Detecting error types and programming languages
- Searching Stack Overflow for relevant questions
- Returning high-quality answers in a structured format

The project demonstrates how to build reliable, extensible MCP servers that integrate with external APIs.

## Key Features

### MCP Server
- Built with **FastMCP**
- Runs over stdio transport
- Supports structured tool registration and responses

### Stack Overflow Integration
- **Search Tool**: Searches Stack Overflow for questions related to error messages or stack traces
- **Smart Filtering**: Prefers questions with accepted answers and can filter by programming language tags
- **Answer Retrieval**: Automatically fetches and includes the full text of accepted answers (or highest-scored answers when no accepted answer exists)
- **Relevance Sorting**: Returns results sorted by relevance and answer quality

### Error Analysis Workflow
- **Error Normalization**: Cleans raw error messages.
- **Error Signature Extraction**: Identifies the main exception/error type from normalized errors
- **Language Detection**: Automatically detects programming languages from error patterns (Python, JavaScript, Java, C/C++)

### Weather MCP Tools (NOAA / NWS)
A secondary MCP module based on the official **NOAA / National Weather Service API**, included as a reference for external API integration.

Available tools:
- `nws_active_alerts` – Active weather alerts for a US state
- `nws_precise_forecast` – Short-term weather forecast by latitude and longitude


## Project Structure

```
nebius/
├── mcp_server/
│   ├── __init__.py          # Package initialization
│   ├── server.py            # FastMCP server instance creation
│   ├── main.py              # Entry point - registers tools and runs server
│   └── tools/
│       ├── __init__.py      # Tools package initialization
│       ├── stackoverflow.py # Stack Overflow search and error normalization tools
│       └── weather.py       # Weather API tools (NWS integration)
├── pyproject.toml           # Project configuration and dependencies
├── uv.lock                  # Dependency lock file
└── README.md                # This file
```

### Main Files

- **`mcp_server/main.py`**: Entry point that registers all tools (`search_stackoverflow`, `normalize_error`, and weather tools) and starts the MCP server using stdio transport.

- **`mcp_server/server.py`**: Creates and exports a shared `FastMCP` instance named "coding-assistant" that all tools register to.

- **`mcp_server/tools/stackoverflow.py`**: Contains two main tools:
  - `search_stackoverflow`: Searches Stack Overflow API and returns relevant questions with answers
  - `normalize_error`: Normalizes error messages and extracts error signatures and language information

- **`mcp_server/tools/weather.py`**: Contains weather-related tools (secondary features):
  - `nws_active_alerts`: Gets active weather alerts for US states
  - `nws_precise_forecast`: Gets weather forecasts for US locations

## Installation

### Requirements
- Python 3.11+
- uv (recommended) or pip

```bash
uv sync
# or
pip install -e .
```

## Running the Server

```bash
python -m mcp_server.main
# or
uv run -m mcp_server.main
```

The server runs over stdio and is compatible with MCP clients.

### Integration with MCP Clients

To use this server with an MCP client (such as Claude Desktop or other MCP-compatible tools), configure the client to run:
```
python -m mcp_server.main
# or
uv run -m mcp_server.main
```

The client will communicate with the server via stdio, sending tool call requests and receiving structured responses.

## Using the Stack Overflow Tool

### Inputs

- **`full_error`** (required): The full error message or stack trace text to search for
- **`language`** (optional): Programming language tag to filter results (e.g., `"python"`, `"javascript"`, `"java"`). If provided, only questions tagged with this language will be returned.

### Outputs

The tool returns a dictionary with:
- **`error_message`**: The original error message provided
- **`short_explanation`**: A brief explanation of what was searched
- **`results`**: A list of up to 3 results, each containing:
  - `question_title`: The title of the Stack Overflow question
  - `has_accepted_answer`: Boolean indicating if the question has an accepted answer
  - `link`: URL to the question or answer
  - `score`: Question score (upvotes - downvotes)
  - `creation_date`: ISO format date when the question was created
  - `answer_text`: Full HTML content of the answer (accepted answer if available, otherwise highest-scored answer)
  - `answer_is_accepted`: Boolean indicating if the returned answer is the accepted one

### Example Usage

**Input:**
```python
{
    "full_error": "Traceback (most recent call last):\n  File \"script.py\", line 5, in <module>\n    result = 10 / 0\nZeroDivisionError: division by zero",
    "language": "python"
}
```

**Output:**
```json
{
    "error_message": "Traceback (most recent call last):\n  File \"script.py\", line 5, in <module>\n    result = 10 / 0\nZeroDivisionError: division by zero",
    "short_explanation": "A search was performed on Stack Overflow using this error: \"Traceback (most recent call last):\".",
    "results": [
        {
            "question_title": "How to handle ZeroDivisionError in Python?",
            "has_accepted_answer": true,
            "link": "https://stackoverflow.com/a/12345678",
            "score": 45,
            "creation_date": "2023-01-15T10:30:00+00:00",
            "answer_text": "<p>You can handle ZeroDivisionError using try-except blocks...</p>",
            "answer_is_accepted": true
        }
    ]
}
```

## Using the Error Normalization Tool

### Example Usage
**Input:**
```
Traceback (most recent call last):
  File "C:\Users\dev\project\main.py", line 42, in <module>
    process_data(data)
  File "C:\Users\dev\project\utils.py", line 15, in process_data
    result = data[key]
KeyError: 'missing_key'
```

**Output:**
```json
{
    "normalized_error": "KeyError: 'missing_key'",
    "error_signature": "KeyError",
    "detected_language": "python"
}
```

## Technologies Used

- **Python 3.11+**: Core programming language
- **FastMCP**: MCP server framework for tool registration and stdio transport
- **httpx**: Async HTTP client for API requests
- **StackExchange API v2.3**: Stack Overflow search and answer retrieval
- **uv**: Modern Python package manager (optional, but recommended)

## Environment Variables

This project uses environment variables for environment-specific configuration.

Create a `.env` file in the project root with the following variables:

- `CUSTOM_CA_BUNDLE`  
  Path to a custom CA bundle file, required in environments with HTTPS inspection (e.g. corporate proxy, NetSpark).

- `STACKEXCHANGE_API_BASE`  
  Base URL for the Stack Exchange API.  
  Default: `https://api.stackexchange.com/2.3`

- `NWS_API_BASE`
  Base URL for the U.S. National Weather Service (NWS) API used by the weather tools.

- `USER_AGENT`
  User-Agent header used for NWS API requests.