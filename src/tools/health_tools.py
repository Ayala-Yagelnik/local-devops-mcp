"""
Health monitoring and auto-recovery tools.

Container health checks, monitoring, and automatic restart capabilities.
"""

import sys
from pathlib import Path

# Add src directory to path for imports
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

from src.health import health_monitor
from mcp.server.fastmcp import FastMCP


def register_health_tools(mcp: FastMCP):
    """Register all health-related MCP tools."""
    
    @mcp.tool()
    def add_health_check(container_id: str, endpoint: str, interval: int = 30):
        """
        Adds health check monitoring to a container with automatic status tracking.
        
        Args:
            container_id (str): Container ID to monitor. Can be:
                - Full ID: "abc123def456789..."
                - Short ID: "abc123def456"
                - Container name: "my-web-server"
            endpoint (str): HTTP endpoint to check for health status.
                          Must be a valid URL including protocol.
                          Examples: "http://localhost:8080/health", "https://api.example.com/status"
            interval (int, optional): Health check interval in seconds.
                                    Must be positive integer. Defaults to 30.
                                    Minimum recommended: 10 seconds.
        
        Returns:
            dict: Health check addition result with structure:
                {
                    "container_id": str,    # Container being monitored
                    "endpoint": str,        # Health check endpoint
                    "interval": int,        # Check interval in seconds
                    "status": "health_check_added"  # Addition status
                }
        
        Raises:
            ValueError: If endpoint URL is invalid or interval is not positive
            RuntimeError: If Docker daemon is not accessible
        """
        return health_monitor.add_health_check(container_id, endpoint, interval)

    @mcp.tool()
    def get_service_health(container_id: str):
        """
        Gets current health status of a monitored service.
        
        Args:
            container_id (str): Container ID to check health for. Can be:
                - Full ID: "abc123def456789..."
                - Short ID: "abc123def456"
                - Container name: "my-web-server"
        
        Returns:
            dict: Health status information with structure:
                {
                    "container_id": str,      # Container being monitored
                    "endpoint": str,          # Health check endpoint
                    "interval": int,           # Check interval in seconds
                    "last_check": float,       # Timestamp of last health check (Unix epoch)
                    "status": str,             # "healthy", "unhealthy", or "unknown"
                    "created_at": float        # When health check was added (Unix epoch)
                }
                
            If no health check exists for container:
            {"error": "No health check for container {container_id}"}
        
        Raises:
            RuntimeError: If Docker daemon is not accessible
            docker.errors.NotFound: If container doesn't exist
            ValueError: If health check endpoint is invalid
        """
        return health_monitor.get_service_health(container_id)

    @mcp.tool()
    def auto_restart_on_failure(container_id: str):
        """
        Enables automatic container restart on health check failure.
        
        This starts a background monitoring thread that continuously checks
        the container's health and restarts it when the health check fails.
        
        Args:
            container_id (str): Container ID to enable auto-restart for. Can be:
                - Full ID: "abc123def456789..."
                - Short ID: "abc123def456"
                - Container name: "my-web-server"
                
            Note: Health check must be added first with add_health_check().
        
        Returns:
            dict: Auto-restart status with structure:
                {
                    "container_id": str,      # Container being monitored
                    "auto_restart": str,       # "enabled"
                    "status": "monitoring_started"  # Monitoring thread status
                }
        
        Raises:
            ValueError: If no health check exists for the container
            RuntimeError: If Docker daemon is not accessible or thread creation fails
            docker.errors.NotFound: If container doesn't exist
        """
        return health_monitor.enable_auto_restart(container_id)
