"""
Local DevOps MCP Server

A powerful Model Context Protocol (MCP) server that provides advanced 
Docker container orchestration capabilities.
"""

import sys
import os
from pathlib import Path

# Add src directory to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from mcp.server.fastmcp import FastMCP

# Import tool modules
from src.tools.container_tools import register_container_tools
from src.tools.health_tools import register_health_tools
from src.tools.orchestration_tools import register_orchestration_tools
from src.tools.state_tools import register_state_tools


# ------------------------------------------------------------------------------
# MCP App
# ------------------------------------------------------------------------------
mcp = FastMCP("local-devops-orchestrator")


# ------------------------------------------------------------------------------
# Register All Tools
# ------------------------------------------------------------------------------
def register_all_tools():
    """Register all MCP tools from different modules."""
    register_container_tools(mcp)
    register_health_tools(mcp)
    register_orchestration_tools(mcp)
    register_state_tools(mcp)


# Register tools on import
register_all_tools()


# ------------------------------------------------------------------------------
# Entry point (stdio)
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    if hasattr(mcp, "run_stdio"):
        mcp.run_stdio()
    else:
        mcp.run(transport="stdio")
