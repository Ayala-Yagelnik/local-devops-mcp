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
from src.tools.container_tools import (
    register_container_tools,
    list_running_services,
    deploy_service,
    get_service_logs,
    stop_service
)
from src.tools.health_tools import (
    register_health_tools,
    add_health_check,
    get_service_health,
    auto_restart_on_failure
)
from src.tools.orchestration_tools import (
    register_orchestration_tools,
    define_dependency,
    get_dependency_status,
    create_template,
    run_from_template,
    list_templates,
    deploy_group
)
from src.tools.state_tools import (
    register_state_tools,
    snapshot_env,
    restore_env,
    list_snapshots,
    watch_and_redeploy,
    stop_watching,
    smart_rebuild
)

# Import managers for test support
from src.health import health_monitor
from src.dependencies import dependency_manager
from src.templates import template_manager
from src.snapshots import snapshot_manager
from src.watcher import file_watcher

# Import docker client for tests
from src.docker_client import get_docker_client_sync, pull_image_if_needed

# Export these for test imports
__all__ = [
    'list_running_services',
    'deploy_service',
    'get_service_logs',
    'stop_service',
    'add_health_check',
    'get_service_health',
    'auto_restart_on_failure',
    'define_dependency',
    'get_dependency_status',
    'create_template',
    'run_from_template',
    'list_templates',
    'deploy_group',
    'snapshot_env',
    'restore_env',
    'list_snapshots',
    'watch_and_redeploy',
    'stop_watching',
    'smart_rebuild',
    'health_monitor',
    'dependency_manager',
    'template_manager',
    'snapshot_manager',
    'file_watcher',
    'get_docker_client_sync',
    'pull_image_if_needed',
]


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
