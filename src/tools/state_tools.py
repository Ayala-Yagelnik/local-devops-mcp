"""
State management and persistence tools.

Environment snapshots, restoration, and file watching capabilities.
"""

import sys
from pathlib import Path

# Add src directory to path for imports
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

from src.snapshots import snapshot_manager
from src.watcher import file_watcher
from mcp.server.fastmcp import FastMCP


def register_state_tools(mcp: FastMCP):
    """Register all state management MCP tools."""
    
    # Snapshot Management Tools
    @mcp.tool()
    def snapshot_env(env_name: str):
        """
        Creates a snapshot of current environment state for later restoration.
        
        Captures all running containers, their configurations, and network state
        to enable complete environment restoration later.
        
        Args:
            env_name (str): Unique name for the snapshot. Used as identifier
                           when restoring. Must be unique across all snapshots.
                           Examples: "dev-env-v1", "testing-setup", "production-backup"
        
        Returns:
            dict: Snapshot creation result with structure:
                {
                    "snapshot_name": str,     # Snapshot name
                    "container_count": int,    # Number of containers captured
                    "containers": [           # List of captured container info
                        {
                            "id": str,          # Container ID
                            "name": str,        # Container name
                            "image": str,       # Image used
                            "ports": dict,      # Port mappings
                            "env_vars": dict    # Environment variables
                        }
                    ],
                    "created_at": float,       # Creation timestamp (Unix epoch)
                    "status": "created"        # Creation status
                }
        
        Raises:
            ValueError: If snapshot name already exists or is invalid
            RuntimeError: If Docker daemon is not accessible or snapshot creation fails
            docker.errors.APIError: If container information retrieval fails
        """
        return snapshot_manager.snapshot_env(env_name)

    @mcp.tool()
    def restore_env(snapshot_name: str):
        """
        Restores environment from a previously created snapshot.
        
        Recreates all containers from the snapshot with their original configurations
        including port mappings, environment variables, and network settings.
        
        Args:
            snapshot_name (str): Name of snapshot to restore.
                               Must match a snapshot created with snapshot_env().
        
        Returns:
            dict: Restoration result with structure:
                {
                    "snapshot_name": str,     # Restored snapshot name
                    "restored_containers": {   # Mapping of service names to new container IDs
                        "service_name": "container_id"
                    },
                    "container_count": int,    # Number of containers restored
                    "status": "restored"       # Restoration status
                }
        
        Raises:
            ValueError: If snapshot doesn't exist
            RuntimeError: If restoration fails or Docker daemon is not accessible
            docker.errors.ImageNotFound: If required images are not available
            docker.errors.APIError: If container creation fails
        """
        return snapshot_manager.restore_env(snapshot_name)

    @mcp.tool()
    def list_snapshots():
        """
        Lists all available environment snapshots with their details.
        
        Returns:
            list: Array of snapshot objects with structure:
                [
                    {
                        "name": str,           # Snapshot name
                        "container_count": int, # Number of containers in snapshot
                        "created_at": float,   # Creation timestamp (Unix epoch)
                        "size_bytes": int,      # Approximate snapshot size
                        "containers": [         # List of container names in snapshot
                            "postgres",
                            "redis",
                            "api"
                        ]
                    }
                ]
        
        Raises:
            RuntimeError: If snapshot storage access fails
        """
        return snapshot_manager.list_snapshots()

    # File Watching Tools
    @mcp.tool()
    def watch_and_redeploy(project_path: str, patterns: list = None):
        """
        Watches for file changes and automatically redeploys services on changes.
        
        Starts a background file watcher that monitors the specified directory
        for changes and automatically rebuilds and redeploys services when files
        matching the patterns are modified.
        
        Args:
            project_path (str): Absolute path to the project directory to watch.
                               Must contain a Dockerfile or build configuration.
                               Examples: "/home/user/my-app", "C:\\projects\\web-app"
            patterns (list, optional): File patterns to watch for changes.
                                      Defaults to ['.py', '.js', '.Dockerfile'].
                                      Can include any file extension or pattern.
                                      Examples: ['.py', '.js', '.html', '.css'], ['*.ts', 'package.json']
        
        Returns:
            dict: File watching setup result with structure:
                {
                    "project_path": str,      # Path being watched
                    "patterns": list,         # File patterns being monitored
                    "watcher_id": str,        # Unique watcher identifier
                    "status": "watching_started"  # Setup status
                }
        
        Example:
            >>> watch_and_redeploy("/home/user/my-web-app", ['.py', '.js', '.html'])
            {
                "project_path": "/home/user/my-web-app",
                "patterns": ['.py', '.js', '.html'],
                "watcher_id": "watcher_abc123",
                "status": "watching_started"
            }
        
        Raises:
            ValueError: If project path doesn't exist or has no Dockerfile
            RuntimeError: If file watcher setup fails
            PermissionError: If insufficient permissions to watch directory
        """
        return file_watcher.watch_and_redeploy(project_path, patterns)

    @mcp.tool()
    def stop_watching(project_path: str):
        """
        Stops file watching for a specific project.
        
        Stops the background file watcher for the specified project path
        and cleans up monitoring resources.
        
        Args:
            project_path (str): Path to the project directory to stop watching for.
                               Must match a path previously used with watch_and_redeploy().
                               Examples: 
                               "/home/user/my-web-app", "C:\\projects\\web-app"
        
        Returns:
            dict: Stop watching result with structure:
                {
                    "project_path": str,      # Path that was being watched
                    "watcher_id": str,        # Watcher ID that was stopped
                    "status": "watching_stopped"  # Stop status
                }
                
            If no watcher exists for the path:
            {"error": "No watcher found for path: {project_path}"}
        
        Raises:
            RuntimeError: If stopping the watcher fails
            PermissionError: If insufficient permissions to stop monitoring
        """
        return file_watcher.stop_watching(project_path)

    @mcp.tool()
    def smart_rebuild(service_name: str):
        """
        Rebuilds only what changed with dependency awareness for faster deployments.
        
        Analyzes the service's dependencies and rebuilds only the components
        that have changed, skipping unchanged dependencies to speed up deployment.
        
        Args:
            service_name (str): Name of the service to rebuild.
                               Must match a running service name.
                               The service should have been deployed with deploy_group()
                               or be part of a watched project.
        
        Returns:
            dict: Smart rebuild result with structure:
                {
                    "service_name": str,      # Service that was rebuilt
                    "rebuilt_components": list, # List of components that were rebuilt
                    "skipped_components": list, # List of components that were skipped (unchanged)
                    "new_container_id": str,   # New container ID after rebuild
                    "build_time_seconds": float, # Time taken for rebuild
                    "status": "rebuilt"       # Rebuild status
                }
        
        Example:
            >>> smart_rebuild("web-app")
            {
                "service_name": "web-app",
                "rebuilt_components": ["web-app", "api-client"],
                "skipped_components": ["database", "redis"],
                "new_container_id": "xyz789abc012",
                "build_time_seconds": 15.3,
                "status": "rebuilt"
            }
        
        Raises:
            ValueError: If service doesn't exist or has no dependencies defined
            RuntimeError: If rebuild fails or Docker daemon is not accessible
            docker.errors.BuildError: If Docker build fails
            docker.errors.APIError: If container operations fail
        """
        return file_watcher.smart_rebuild(service_name)
