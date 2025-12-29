import sys
from pathlib import Path

# Add parent directory to path to allow imports when running directly
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from mcp_server.server import mcp
from mcp_server.tools.weather import register_weather_tools
from mcp_server.tools.stackoverflow import register_stackoverflow_tool, register_normalize_error_tool


def main() -> None:
    """Entry point for running the MCP server."""
    # Register all tools on the shared MCP instance
    register_weather_tools(mcp)
    register_stackoverflow_tool(mcp)
    register_normalize_error_tool(mcp)

    # Run the server over stdio (as before)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()


