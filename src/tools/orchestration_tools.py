"""
Service orchestration and dependency management tools.

Advanced deployment with dependencies, templates, and smart waiting.
"""

import sys
from pathlib import Path

# Add src directory to path for imports
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

from src.dependencies import dependency_manager
from src.templates import template_manager
from mcp.server.fastmcp import FastMCP


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
    
    Raises:
        ValueError: If wait_condition format is invalid
        KeyError: If required condition parameters are missing
    """
    return dependency_manager.define_dependency(service_name, depends_on, wait_condition)


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
    
    Raises:
        RuntimeError: If dependency not met within timeout or circular dependency detected
        ValueError: If service definition is invalid
        docker.errors.ImageNotFound: If image cannot be pulled or built
    """
    return dependency_manager.deploy_group(definitions)


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
    
    Raises:
        RuntimeError: If Docker daemon is not accessible
        docker.errors.APIError: If container status check fails
    """
    return dependency_manager.get_dependency_status(service_name)


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
    
    Raises:
        ValueError: If template name already exists or required fields missing
        RuntimeError: If template storage fails
    """
    return template_manager.create_template(name, image, ports, env_vars, health_check)


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
    
    Raises:
        ValueError: If template doesn't exist
        RuntimeError: If deployment fails
        docker.errors.ImageNotFound: If template image cannot be pulled
    """
    return template_manager.run_from_template(template_name, overrides)


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
    
    Raises:
        RuntimeError: If template storage access fails
    """
    return template_manager.list_templates()


def register_orchestration_tools(mcp: FastMCP):
    """Register all orchestration-related MCP tools."""
    mcp.tool()(define_dependency)
    mcp.tool()(deploy_group)
    mcp.tool()(get_dependency_status)
    mcp.tool()(create_template)
    mcp.tool()(run_from_template)
    mcp.tool()(list_templates)
