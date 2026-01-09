"""
Container management tools.

Basic Docker container operations: deploy, stop, list, logs.
"""

import sys
from pathlib import Path

# Add src directory to path for imports
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

from src.docker_client import get_docker_client_sync, pull_image_if_needed, get_container_by_name
from mcp.server.fastmcp import FastMCP


def register_container_tools(mcp: FastMCP):
    """Register all container-related MCP tools."""
    
    @mcp.tool()
    def list_running_services():
        """
        Lists all currently active Docker containers with detailed information.
        
        Returns:
            list: Array of container objects with structure:
                [
                    {
                        "id": str,           # Short container ID (first 12 chars)
                        "image": list,       # List of image tags (e.g., ["nginx:latest"])
                        "status": str,       # Container status (e.g., "running", "exited")
                        "ports": dict        # Port mappings {"container_port/host_port": {"HostPort": "host_port"}}
                    }
                ]
        
        Raises:
            RuntimeError: If Docker daemon is not accessible
            DockerException: If container listing fails
        """
        client = get_docker_client_sync()
        containers = client.containers.list(all=True)
        
        result = []
        for container in containers:
            container_info = {
                "id": container.short_id,
                "image": [img_tag for img_tag in container.image.tags],
                "status": container.status,
                "ports": container.ports
            }
            result.append(container_info)
        
        return result

    @mcp.tool()
    def deploy_service(
        image: str,
        ports: dict = None,
        env_vars: dict = None
    ):
        """
        Pulls (if missing) and runs a Docker container with specified configuration.
        
        Args:
            image (str): Docker image name to deploy. Can be:
                - Public image: "nginx:latest", "postgres:15"
                - Local image: "./my-app", "my-custom:1.0"
            ports (dict, optional): Port mapping in format {"container_port": "host_port"}.
                Example: {"80": "8080", "443": "8443"}
                Defaults to {} (no port mapping).
            env_vars (dict, optional): Environment variables as key-value pairs.
                Example: {"DATABASE_URL": "postgres://user:pass@db:5432/mydb"}
                Defaults to {} (no environment variables).
        
        Returns:
            dict: Container deployment information with structure:
                {
                    "container_id": str,  # Short container ID (first 12 chars)
                    "status": str,         # "running" or "error"
                    "message": str,        # Success/error message
                    "image": str,          # Actual image used
                    "ports": dict          # Applied port mapping
                }
        
        Raises:
            RuntimeError: If Docker is not running or image pull fails
            ValueError: If port mapping is invalid
        """
        client = get_docker_client_sync()
        
        # Pull image if needed
        if image.startswith("./"):
            # Build local image
            image_path = image[2:]  # Remove "./"
            try:
                image, build_logs = client.images.build(path=image_path, tag=f"{image_path}:latest")
                image = f"{image_path}:latest"
            except Exception as e:
                return {
                    "container_id": None,
                    "status": "error",
                    "message": f"Failed to build image: {str(e)}",
                    "image": image,
                    "ports": {}
                }
        else:
            # Pull remote image
            pull_image_if_needed(client, image)
        
        # Prepare container configuration
        container_config = {
            "image": image,
            "detach": True,
            "remove": False
        }
        
        if ports:
            port_bindings = {}
            for container_port, host_port in ports.items():
                port_bindings[f"{container_port}/tcp"] = {"HostPort": str(host_port)}
            container_config["ports"] = port_bindings
        
        if env_vars:
            container_config["environment"] = env_vars
        
        try:
            container = client.containers.run(**container_config)
            return {
                "container_id": container.short_id,
                "status": "running",
                "message": f"Container {container.short_id} started successfully",
                "image": image,
                "ports": ports or {}
            }
        except Exception as e:
            return {
                "container_id": None,
                "status": "error",
                "message": f"Failed to start container: {str(e)}",
                "image": image,
                "ports": ports or {}
            }

    @mcp.tool()
    def get_service_logs(container_id: str, tail: int = 50):
        """
        Retrieves logs from a Docker container with configurable line limit.
        
        Args:
            container_id (str): Container ID or name. Can be:
                - Full ID: "abc123def456789..."
                - Short ID: "abc123def456"
                - Container name: "my-web-server"
            tail (int, optional): Number of lines to retrieve from end of logs.
                Defaults to 50. Use -1 for all logs.
        
        Returns:
            str: Container log output as UTF-8 string. Invalid UTF-8 characters
                 are replaced with replacement character.
        
        Raises:
            RuntimeError: If Docker daemon is not accessible
            docker.errors.NotFound: If container doesn't exist
            ValueError: If tail parameter is invalid
        """
        client = get_docker_client_sync()
        container = client.containers.get(container_id)
        
        if tail == -1:
            return container.logs().decode("utf-8", errors="replace")
        else:
            return container.logs(tail=tail).decode("utf-8", errors="replace")

    @mcp.tool()
    def stop_service(container_id: str):
        """
        Stops and removes a Docker container gracefully.
        
        Args:
            container_id (str): Container ID or name to stop. Can be:
                - Full ID: "abc123def456789..."
                - Short ID: "abc123def456"
                - Container name: "my-web-server"
        
        Returns:
            str: Success message confirming container stop and removal.
                 Format: "Container {container_id} stopped and removed successfully."
        
        Raises:
            RuntimeError: If Docker daemon is not accessible
            docker.errors.NotFound: If container doesn't exist
            docker.errors.APIError: If stop/remove operation fails
        """
        client = get_docker_client_sync()
        container = client.containers.get(container_id)
        
        container.stop()
        container.remove()
        
        return f"Container {container_id} stopped and removed successfully."
