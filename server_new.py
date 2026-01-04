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

# Import all modules
from src.docker_client import get_docker_client, pull_image_if_needed, get_container_by_name
from src.dependencies import dependency_manager
from src.templates import template_manager
from src.health import health_monitor
from src.snapshots import snapshot_manager
from src.watcher import file_watcher


# ------------------------------------------------------------------------------
# MCP App
# ------------------------------------------------------------------------------
mcp = FastMCP("local-devops-orchestrator")


# ------------------------------------------------------------------------------
# Core Tools
# ------------------------------------------------------------------------------
@mcp.tool()
def list_running_services():
    """
    Lists all currently active Docker containers.
    """
    client = get_docker_client()
    containers = client.containers.list()

    result = []
    for c in containers:
        result.append({
            "id": c.short_id,
            "image": c.image.tags,
            "status": c.status,
            "ports": c.attrs.get("NetworkSettings", {}).get("Ports", {})
        })

    return result


@mcp.tool()
def deploy_service(
    image: str,
    ports: dict = None,
    env_vars: dict = None,
):
    """
    Pulls (if missing) and runs a Docker container.
    """
    client = get_docker_client()

    # Pull image if needed
    pull_image_if_needed(client, image)

    # Deploy container
    container = client.containers.run(
        image=image,
        detach=True,
        ports=ports or {},
        environment=env_vars or {},
    )

    return {
        "container_id": container.short_id,
        "status": "running",
    }


@mcp.tool()
def get_service_logs(container_id: str, tail: int = 50):
    """
    Retrieves logs from a Docker container.
    """
    client = get_docker_client()
    container = client.containers.get(container_id)

    return container.logs(tail=tail).decode("utf-8", errors="replace")


@mcp.tool()
def stop_service(container_id: str):
    """
    Stops and removes a Docker container.
    """
    client = get_docker_client()
    container = client.containers.get(container_id)

    container.stop()
    container.remove()

    return f"Container {container_id} stopped and removed successfully."


# ------------------------------------------------------------------------------
# Advanced Tools - Dependencies & Smart Waiting
# ------------------------------------------------------------------------------
@mcp.tool()
def define_dependency(service_name: str, depends_on: str, wait_condition: dict):
    """
    Defines a dependency with smart waiting condition.
    
    Args:
        service_name: Name of the service that depends on another
        depends_on: Name of the service to wait for
        wait_condition: Dictionary with type and details
                       Examples:
                       {"type": "tcp", "host": "db", "port": 5432}
                       {"type": "http", "url": "http://api:8080/health"}
                       {"type": "log", "pattern": "ready to accept connections"}
    """
    return dependency_manager.define_dependency(service_name, depends_on, wait_condition)


@mcp.tool()
def deploy_group(definitions: list):
    """
    Deploys multiple services respecting dependencies.
    
    Args:
        definitions: List of service definitions with dependencies
        Example:
        [
            {"name": "postgres", "image": "postgres:15", "ports": {"5432": 5432}},
            {"name": "api", "image": "my-api", "ports": {"8080": 8080},
             "depends_on": "postgres", "wait_condition": {"type": "tcp", "host": "postgres", "port": 5432}}
        ]
    """
    client = get_docker_client()
    deployed_containers = {}
    
    # Sort services based on dependencies
    sorted_definitions = dependency_manager.sort_services_by_dependencies(definitions)
    
    for service_def in sorted_definitions:
        name = service_def["name"]
        image = service_def["image"]
        ports = service_def.get("ports", {})
        env_vars = service_def.get("env_vars", {})
        
        # Build image if it's a local path
        if "/" in image or "." in image:
            from src.watcher import FileWatcher
            watcher = FileWatcher()
            watcher._build_image_if_needed(image, f"{name}:latest")
            image = f"{name}:latest"
        
        # Pull image if needed
        pull_image_if_needed(client, image)
        
        # Deploy container
        container = client.containers.run(
            image=image,
            name=name,
            detach=True,
            ports=ports,
            environment=env_vars,
        )
        
        deployed_containers[name] = container.short_id
        
        # Wait for dependencies if defined
        if "wait_condition" in service_def:
            wait_condition = service_def["wait_condition"]
            if wait_condition.get("type") == "tcp":
                wait_condition["host"] = service_def.get("depends_on")
            elif wait_condition.get("type") == "log":
                wait_condition["container_id"] = deployed_containers.get(service_def.get("depends_on"))
            
            wait_success = dependency_manager.wait_for_condition(wait_condition, timeout=60)
            if not wait_success:
                # Stop the container if dependency not met
                container.stop()
                container.remove()
                raise RuntimeError(f"Dependency not met for {name}: {wait_condition}")
    
    return {
        "deployed_services": deployed_containers,
        "status": "all_services_running"
    }


@mcp.tool()
def get_dependency_status(service_name: str):
    """
    Shows dependency status and wait times.
    """
    return dependency_manager.get_dependency_status(service_name)


# ------------------------------------------------------------------------------
# Advanced Tools - Templates
# ------------------------------------------------------------------------------
@mcp.tool()
def create_template(name: str, image: str, ports: dict, env_vars: dict = None, health_check: dict = None):
    """
    Creates a reusable service template.
    """
    return template_manager.create_template(name, image, ports, env_vars, health_check)


@mcp.tool()
def run_from_template(template_name: str, overrides: dict = None):
    """
    Runs a service from a template with optional overrides.
    """
    return template_manager.run_from_template(template_name, overrides)


@mcp.tool()
def list_templates():
    """
    Lists all available templates.
    """
    return template_manager.list_templates()


# ------------------------------------------------------------------------------
# Advanced Tools - Health Monitoring
# ------------------------------------------------------------------------------
@mcp.tool()
def add_health_check(container_id: str, endpoint: str, interval: int = 30):
    """
    Adds health check monitoring to a container.
    """
    return health_monitor.add_health_check(container_id, endpoint, interval)


@mcp.tool()
def get_service_health(container_id: str):
    """
    Gets health status of a service.
    """
    return health_monitor.get_service_health(container_id)


@mcp.tool()
def auto_restart_on_failure(container_id: str):
    """
    Enables auto-restart on health check failure.
    """
    return health_monitor.enable_auto_restart(container_id)


# ------------------------------------------------------------------------------
# Advanced Tools - Snapshots & State Management
# ------------------------------------------------------------------------------
@mcp.tool()
def snapshot_env(env_name: str):
    """
    Creates a snapshot of current environment state.
    """
    return snapshot_manager.snapshot_env(env_name)


@mcp.tool()
def restore_env(snapshot_name: str):
    """
    Restores environment from snapshot.
    """
    return snapshot_manager.restore_env(snapshot_name)


@mcp.tool()
def list_snapshots():
    """
    Lists all available snapshots.
    """
    return snapshot_manager.list_snapshots()


# ------------------------------------------------------------------------------
# Advanced Tools - Auto-Deploy with File Watching
# ------------------------------------------------------------------------------
@mcp.tool()
def watch_and_redeploy(project_path: str, patterns: list = None):
    """
    Watches for file changes and auto-redeploys services.
    
    Args:
        project_path: Path to the project directory
        patterns: File patterns to watch (default: ['.py', '.js', '.Dockerfile'])
    """
    return file_watcher.watch_and_redeploy(project_path, patterns)


@mcp.tool()
def stop_watching(project_path: str):
    """
    Stops file watching for a project.
    """
    return file_watcher.stop_watching(project_path)


@mcp.tool()
def smart_rebuild(service_name: str):
    """
    Rebuilds only what changed with dependency awareness.
    """
    return file_watcher.smart_rebuild(service_name)


# ------------------------------------------------------------------------------
# Entry point (stdio)
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    if hasattr(mcp, "run_stdio"):
        mcp.run_stdio()
    else:
        mcp.run(transport="stdio")
