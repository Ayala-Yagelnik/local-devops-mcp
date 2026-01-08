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
    
    Example:
        >>> list_running_services()
        [
            {
                "id": "abc123def456",
                "image": ["nginx:latest"],
                "status": "running",
                "ports": {"80/tcp": [{"HostPort": "8080"}]}
            }
        ]
    
    Raises:
        RuntimeError: If Docker daemon is not accessible
        DockerException: If container listing fails
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
    
    Examples:
        # Simple nginx deployment
        deploy_service("nginx:latest", {"80": "8080"})
        
        # Database with environment variables
        deploy_service(
            image="postgres:15",
            ports={"5432": "5432"},
            env_vars={
                "POSTGRES_DB": "myapp",
                "POSTGRES_USER": "user",
                "POSTGRES_PASSWORD": "secure123"
            }
        )
        
        # Local application
        deploy_service("./my-app", {"8000": "8000"})
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
    
    Example:
        >>> get_service_logs("abc123def456", 100)
        "2024-01-15 10:30:01 [INFO] Starting nginx server..."
        
        >>> get_service_logs("my-web-server", 10)
        "Last 10 lines of logs..."
    
    Raises:
        RuntimeError: If Docker daemon is not accessible
        docker.errors.NotFound: If container doesn't exist
        ValueError: If tail parameter is invalid
    """
    client = get_docker_client()
    container = client.containers.get(container_id)

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
    
    Example:
        >>> stop_service("abc123def456")
        "Container abc123def456 stopped and removed successfully."
        
        >>> stop_service("my-web-server")
        "Container my-web-server stopped and removed successfully."
    
    Raises:
        RuntimeError: If Docker daemon is not accessible
        docker.errors.NotFound: If container doesn't exist
        docker.errors.APIError: If stop/remove operation fails
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
    Defines a dependency with smart waiting condition for service orchestration.
    
    Args:
        service_name (str): Name of the service that depends on another service.
                           Must be unique across all defined services.
        depends_on (str): Name of the service to wait for before starting service_name.
                         Must match the name of a service that will be deployed.
        wait_condition (dict): Dictionary defining the waiting condition with type-specific parameters:
            
            TCP Port Check:
            ```json
            {
                "type": "tcp",
                "host": "database",  # Service name or IP address
                "port": 5432         # Port number to check
            }
            ```
            
            HTTP Endpoint Check:
            ```json
            {
                "type": "http",
                "url": "http://api:8080/health"  # Full URL to check
            }
            ```
            
            Log Pattern Check:
            ```json
            {
                "type": "log",
                "pattern": "ready to accept connections",  # Regex pattern to match
                "container_id": "abc123"  # Container ID to check logs (optional)
            }
            ```
    
    Returns:
        dict: Dependency definition result with structure:
            {
                "service": str,        # Service name that depends
                "depends_on": str,      # Service being waited for
                "condition_type": str,  # Type of wait condition (tcp/http/log)
                "status": str           # Always "defined" on success
            }
    
    Example:
        >>> define_dependency(
        ...     "web-app",
        ...     "database",
        ...     {"type": "tcp", "host": "database", "port": 5432}
        ... )
        {
            "service": "web-app",
            "depends_on": "database",
            "condition_type": "tcp",
            "status": "defined"
        }
    
    Raises:
        ValueError: If wait_condition format is invalid
        KeyError: If required condition parameters are missing
    """
    return dependency_manager.define_dependency(service_name, depends_on, wait_condition)


@mcp.tool()
def deploy_group(definitions: list):
    """
    Deploys multiple services respecting dependencies with smart orchestration.
    
    Args:
        definitions (list): List of service definitions with dependencies. Each service
                          definition is a dictionary with the following structure:
            
            Basic Service Definition:
            ```json
            {
                "name": "service-name",
                "image": "image:tag",
                "ports": {"container_port": "host_port"},  # Optional
                "env_vars": {"KEY": "value"}              # Optional
            }
            ```
            
            Service with Dependency:
            ```json
            {
                "name": "web-app",
                "image": "my-app:latest",
                "ports": {"8000": "8080"},
                "depends_on": "database",
                "wait_condition": {
                    "type": "tcp",
                    "host": "database",
                    "port": 5432
                }
            }
            ```
            
            Local Image Build:
            ```json
            {
                "name": "my-app",
                "image": "./path/to/app",  # Local path - will be built as "my-app:latest"
                "ports": {"8000": "8000"}
            }
            ```
    
    Returns:
        dict: Deployment result with structure:
            {
                "deployed_services": {
                    "service_name": "container_id"  # Mapping of service names to container IDs
                },
                "status": "all_services_running"     # Success status
            }
    
    Example:
        >>> deploy_group([
        ...     {
        ...         "name": "postgres",
        ...         "image": "postgres:15",
        ...         "ports": {"5432": "5432"},
        ...         "env_vars": {
        ...             "POSTGRES_DB": "myapp",
        ...             "POSTGRES_PASSWORD": "secret"
        ...         }
        ...     },
        ...     {
        ...         "name": "api",
        ...         "image": "my-api:latest",
        ...         "ports": {"8080": "8080"},
        ...         "depends_on": "postgres",
        ...         "wait_condition": {"type": "tcp", "host": "postgres", "port": 5432}
        ...     }
        ... ])
        {
            "deployed_services": {
                "postgres": "abc123def456",
                "api": "def789ghi012"
            },
            "status": "all_services_running"
        }
    
    Raises:
        RuntimeError: If dependency not met within timeout or circular dependency detected
        ValueError: If service definition is invalid
        docker.errors.ImageNotFound: If image cannot be pulled or built
    """
    client = get_docker_client()
    deployed_containers = {}
    
    # Sort services based on dependencies
    sorted_definitions = dependency_manager.sort_services_by_dependencies(definitions)
    
    # Deploy services in dependency order
    for service_def in sorted_definitions:
        name = service_def["name"]
        image = service_def["image"]
        ports = service_def.get("ports", {})
        env_vars = service_def.get("env_vars", {})
        
        # Build image if it's a local path (indicated by / or . in path)
        if "/" in image or "." in image:
            from src.watcher import FileWatcher
            watcher = FileWatcher()
            # Build image with service name as tag
            watcher._build_image_if_needed(image, f"{name}:latest")
            image = f"{name}:latest"
        
        # Pull image if needed (handles both local and remote images)
        pull_image_if_needed(client, image)
        
        # Deploy container with all configurations
        container = client.containers.run(
            image=image,
            name=name,
            detach=True,
            ports=ports,
            environment=env_vars,
        )
        
        # Track deployed container for dependency resolution
        deployed_containers[name] = container.short_id
        
        # Wait for dependencies if defined for this service
        if "wait_condition" in service_def:
            wait_condition = service_def["wait_condition"]
            # Configure wait condition with actual container/service references
            if wait_condition.get("type") == "tcp":
                # Use dependency service name as host for TCP checks
                wait_condition["host"] = service_def.get("depends_on")
            elif wait_condition.get("type") == "log":
                # Use deployed container ID for log pattern checks
                wait_condition["container_id"] = deployed_containers.get(service_def.get("depends_on"))
            
            # Wait for dependency to be ready with timeout
            wait_success = dependency_manager.wait_for_condition(wait_condition, timeout=60)
            if not wait_success:
                # Clean up: stop and remove container if dependency not met
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
    Shows dependency status and wait times for a specific service.
    
    Args:
        service_name (str): Name of the service to check dependency status for.
                           Must match a service name previously defined with define_dependency().
    
    Returns:
        dict: Dependency status information with structure:
            {
                "service": str,           # Service name
                "depends_on": str,        # Service it depends on
                "condition": dict,         # Wait condition details
                "container_running": bool, # Whether service container is currently running
                "created_at": float       # Timestamp when dependency was defined (Unix epoch)
            }
            
            If service has no dependencies defined:
            {"error": "No dependencies defined for {service_name}"}
    
    Example:
        >>> get_dependency_status("web-app")
        {
            "service": "web-app",
            "depends_on": "database",
            "condition": {
                "type": "tcp",
                "host": "database",
                "port": 5432
            },
            "container_running": True,
            "created_at": 1705123456.789
        }
    
    Raises:
        RuntimeError: If Docker daemon is not accessible
        docker.errors.APIError: If container status check fails
    """
    return dependency_manager.get_dependency_status(service_name)


# ------------------------------------------------------------------------------
# Advanced Tools - Templates
# ------------------------------------------------------------------------------
@mcp.tool()
def create_template(name: str, image: str, ports: dict, env_vars: dict = None, health_check: dict = None):
    """
    Creates a reusable service template for consistent deployments.
    
    Args:
        name (str): Unique template name. Used as identifier when running from template.
                   Must be unique across all templates.
        image (str): Docker image to use in template. Can be:
            - Public image: "nginx:latest", "postgres:15"
            - Local image: "./my-app", "my-custom:1.0"
        ports (dict): Port mapping in format {"container_port": "host_port"}.
                     Required field. Example: {"80": "8080", "443": "8443"}
        env_vars (dict, optional): Environment variables as key-value pairs.
                                  Example: {"DATABASE_URL": "postgres://user:pass@db:5432/mydb"}
                                  Defaults to {} if not provided.
        health_check (dict, optional): Health check configuration for auto-monitoring.
                                      Example:
                                      ```json
                                      {
                                          "endpoint": "http://localhost:8080/health",
                                          "interval": 30
                                      }
                                      ```
    
    Returns:
        dict: Template creation result with structure:
            {
                "template_name": str,    # Template name
                "image": str,           # Image used
                "ports": dict,          # Port mapping
                "env_vars": dict,       # Environment variables
                "health_check": dict,   # Health check config
                "status": "created"     # Creation status
            }
    
    Example:
        >>> create_template(
        ...     "web-server",
        ...     "nginx:latest",
        ...     {"80": "8080"},
        ...     {"NGINX_PORT": "80"},
        ...     {"endpoint": "http://localhost:8080/health", "interval": 30}
        ... )
        {
            "template_name": "web-server",
            "image": "nginx:latest",
            "ports": {"80": "8080"},
            "env_vars": {"NGINX_PORT": "80"},
            "health_check": {"endpoint": "http://localhost:8080/health", "interval": 30},
            "status": "created"
        }
    
    Raises:
        ValueError: If template name already exists or required fields missing
        RuntimeError: If template storage fails
    """
    return template_manager.create_template(name, image, ports, env_vars, health_check)


@mcp.tool()
def run_from_template(template_name: str, overrides: dict = None):
    """
    Runs a service from a template with optional parameter overrides.
    
    Args:
        template_name (str): Name of existing template to deploy.
                             Must match a template created with create_template().
        overrides (dict, optional): Parameter overrides to customize deployment.
                                  Any field from the template can be overridden:
                                  ```json
                                  {
                                      "ports": {"80": "9090"},           # Override ports
                                      "env_vars": {"DEBUG": "true"},     # Merge/override env vars
                                      "health_check": {"interval": 10}   # Override health check
                                  }
                                  ```
                                  Defaults to {} (no overrides).
    
    Returns:
        dict: Deployment result with structure:
            {
                "container_id": str,     # Short container ID (first 12 chars)
                "template_name": str,     # Template used
                "applied_overrides": dict, # Overrides that were applied
                "status": "running"       # Container status
            }
    
    Example:
        >>> run_from_template("web-server", {"ports": {"80": "9090"}})
        {
            "container_id": "abc123def456",
            "template_name": "web-server",
            "applied_overrides": {"ports": {"80": "9090"}},
            "status": "running"
        }
        
        >>> run_from_template("database")
        {
            "container_id": "def789ghi012",
            "template_name": "database",
            "applied_overrides": {},
            "status": "running"
        }
    
    Raises:
        ValueError: If template doesn't exist
        RuntimeError: If deployment fails
        docker.errors.ImageNotFound: If template image cannot be pulled
    """
    return template_manager.run_from_template(template_name, overrides)


@mcp.tool()
def list_templates():
    """
    Lists all available service templates with their configurations.
    
    Returns:
        list: Array of template objects with structure:
            [
                {
                    "name": str,           # Template name
                    "image": str,          # Docker image
                    "ports": dict,         # Port mapping
                    "env_vars": dict,      # Environment variables
                    "health_check": dict,  # Health check config
                    "created_at": float    # Creation timestamp (Unix epoch)
                }
            ]
    
    Example:
        >>> list_templates()
        [
            {
                "name": "web-server",
                "image": "nginx:latest",
                "ports": {"80": "8080"},
                "env_vars": {"NGINX_PORT": "80"},
                "health_check": {"endpoint": "http://localhost:8080/health", "interval": 30},
                "created_at": 1705123456.789
            },
            {
                "name": "database",
                "image": "postgres:15",
                "ports": {"5432": "5432"},
                "env_vars": {"POSTGRES_DB": "myapp"},
                "health_check": None,
                "created_at": 1705123490.123
            }
        ]
    
    Raises:
        RuntimeError: If template storage access fails
    """
    return template_manager.list_templates()


# ------------------------------------------------------------------------------
# Advanced Tools - Health Monitoring
# ------------------------------------------------------------------------------
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
    
    Example:
        >>> add_health_check("abc123def456", "http://localhost:8080/health", 15)
        {
            "container_id": "abc123def456",
            "endpoint": "http://localhost:8080/health",
            "interval": 15,
            "status": "health_check_added"
        }
        
        >>> add_health_check("my-web-server", "https://api.example.com/status")
        {
            "container_id": "my-web-server",
            "endpoint": "https://api.example.com/status",
            "interval": 30,
            "status": "health_check_added"
        }
    
    Raises:
        ValueError: If endpoint URL is invalid or interval is not positive
        RuntimeError: If Docker daemon is not accessible
        docker.errors.NotFound: If container doesn't exist
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
    
    Example:
        >>> get_service_health("abc123def456")
        {
            "container_id": "abc123def456",
            "endpoint": "http://localhost:8080/health",
            "interval": 30,
            "last_check": 1705123456.789,
            "status": "healthy",
            "created_at": 1705123400.123
        }
    
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
    
    Example:
        >>> auto_restart_on_failure("abc123def456")
        {
            "container_id": "abc123def456",
            "auto_restart": "enabled",
            "status": "monitoring_started"
        }
    
    Raises:
        ValueError: If no health check exists for the container
        RuntimeError: If Docker daemon is not accessible or thread creation fails
        docker.errors.NotFound: If container doesn't exist
    """
    return health_monitor.enable_auto_restart(container_id)


# ------------------------------------------------------------------------------
# Advanced Tools - Snapshots & State Management
# ------------------------------------------------------------------------------
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
    
    Example:
        >>> snapshot_env("my-dev-setup")
        {
            "snapshot_name": "my-dev-setup",
            "container_count": 3,
            "containers": [
                {
                    "id": "abc123def456",
                    "name": "postgres",
                    "image": "postgres:15",
                    "ports": {"5432/tcp": [{"HostPort": "5432"}]},
                    "env_vars": {"POSTGRES_DB": "myapp"}
                },
                {
                    "id": "def789ghi012",
                    "name": "redis",
                    "image": "redis:7",
                    "ports": {"6379/tcp": [{"HostPort": "6379"}]},
                    "env_vars": {}
                }
            ],
            "created_at": 1705123456.789,
            "status": "created"
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
    
    Example:
        >>> restore_env("my-dev-setup")
        {
            "snapshot_name": "my-dev-setup",
            "restored_containers": {
                "postgres": "xyz789abc012",
                "redis": "def456ghi789",
                "api": "ghi012jkl345"
            },
            "container_count": 3,
            "status": "restored"
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
    
    Example:
        >>> list_snapshots()
        [
            {
                "name": "dev-env-v1",
                "container_count": 3,
                "created_at": 1705123456.789,
                "size_bytes": 2048,
                "containers": ["postgres", "redis", "api"]
            },
            {
                "name": "testing-setup",
                "container_count": 2,
                "created_at": 1705123500.123,
                "size_bytes": 1536,
                "containers": ["database", "web-server"]
            }
        ]
    
    Raises:
        RuntimeError: If snapshot storage access fails
    """
    return snapshot_manager.list_snapshots()


# ------------------------------------------------------------------------------
# Advanced Tools - Auto-Deploy with File Watching
# ------------------------------------------------------------------------------
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
        
        >>> watch_and_redeploy("C:\\projects\\api")
        {
            "project_path": "C:\\projects\\api",
            "patterns": ['.py', '.js', '.Dockerfile'],
            "watcher_id": "watcher_def456",
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
                           Examples: "/home/user/my-app", "C:\\projects\\web-app"
    
    Returns:
        dict: Stop watching result with structure:
            {
                "project_path": str,      # Path that was being watched
                "watcher_id": str,        # Watcher ID that was stopped
                "status": "watching_stopped"  # Stop status
            }
            
            If no watcher exists for the path:
            {"error": "No watcher found for path: {project_path}"}
    
    Example:
        >>> stop_watching("/home/user/my-web-app")
        {
            "project_path": "/home/user/my-web-app",
            "watcher_id": "watcher_abc123",
            "status": "watching_stopped"
        }
    
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


# ------------------------------------------------------------------------------
# Entry point (stdio)
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    if hasattr(mcp, "run_stdio"):
        mcp.run_stdio()
    else:
        mcp.run(transport="stdio")
