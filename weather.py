"""Backward-compatible entry point for the MCP server.

This module is kept so that existing commands like
`uv run weather.py` continue to work unchanged.
"""

from mcp_server.main import main


if __name__ == "__main__":
    main()
