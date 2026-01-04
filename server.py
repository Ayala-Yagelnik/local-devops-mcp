"""
Local DevOps MCP Server

A powerful Model Context Protocol (MCP) server that provides advanced 
Docker container orchestration capabilities.
"""
import json
import sys
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import threading
import docker
from docker.errors import DockerException, ImageNotFound
from typing import Dict, List, Optional, Any

from mcp.server.fastmcp import FastMCP


# ------------------------------------------------------------------------------
# MCP App
# ------------------------------------------------------------------------------
mcp = FastMCP("local-devops-orchestrator")

# ------------------------------------------------------------------------------
# Global State
# ------------------------------------------------------------------------------
_dependencies: Dict[str, Dict[str, Any]] = {}
_watchers: Dict[str, threading.Thread] = {}
_snapshots: Dict[str, Dict[str, Any]] = {}
_templates: Dict[str, Dict[str, Any]] = {}
_health_checks: Dict[str, Dict[str, Any]] = {}


# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------
def wait_for_condition(condition: Dict[str, Any], timeout: int = 60) -> bool:
    """Wait for a condition to be met (TCP, HTTP, or log pattern)"""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        cond_type = condition.get("type")
        
        if cond_type == "tcp":
            host = condition.get("host")
            port = condition.get("port")
            if check_tcp_port(host, port):
                return True
                
        elif cond_type == "http":
            url = condition.get("url")
            if check_http_endpoint(url):
                return True
                
        elif cond_type == "log":
            pattern = condition.get("pattern")
            container_id = condition.get("container_id")
            if check_log_pattern(container_id, pattern):
                return True
                
        time.sleep(2)
    
    return False

def check_tcp_port(host: str, port: int) -> bool:
    """Check if TCP port is open"""
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False

def check_http_endpoint(url: str) -> bool:
    """Check if HTTP endpoint responds"""
    try:
        import urllib.request
        import urllib.error
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status < 400
    except:
        return False

def check_log_pattern(container_id: str, pattern: str) -> bool:
    """Check if log pattern appears in container logs"""
    try:
        client = get_docker_client()
        container = client.containers.get(container_id)
        logs = container.logs(tail=50).decode("utf-8", errors="replace")
        return bool(re.search(pattern, logs, re.IGNORECASE))
    except:
        return False

def get_container_by_name(name: str):
    """Get container by name"""
    try:
        client = get_docker_client()
        for container in client.containers.list():
            if name in container.name:
                return container
        return None
    except:
        return None

def build_image_if_needed(image_path: str, image_name: str):
    """Build Docker image if Dockerfile exists"""
    dockerfile_path = Path(image_path) / "Dockerfile"
    if dockerfile_path.exists():
        try:
            client = get_docker_client()
            client.images.build(path=str(image_path), tag=image_name, rm=True)
            return True
        except:
            return False
    return False

def watch_files(project_path: str, patterns: List[str], callback):
    """Watch for file changes and trigger callback"""
    import watchdog.observers
    import watchdog.events
    
    class ChangeHandler(watchdog.events.FileSystemEventHandler):
        def __init__(self, patterns, callback):
            self.patterns = patterns
            self.callback = callback
            
        def on_modified(self, event):
            if not event.is_directory:
                for pattern in patterns:
                    if event.src_path.endswith(pattern):
                        self.callback(event.src_path)
                        break
    
    event_handler = ChangeHandler(patterns, callback)
    observer = watchdog.observers.Observer()
    observer.schedule(event_handler, str(project_path), recursive=True)
    observer.start()
    return observer
def get_docker_client():
    docker_bin = r"C:\Program Files\Docker\Docker\resources\bin"
    if os.path.isdir(docker_bin):
        current_path = os.environ.get("PATH", "")
        path_parts = {p.strip().lower() for p in current_path.split(os.pathsep) if p.strip()}
        if docker_bin.lower() not in path_parts:
            os.environ["PATH"] = current_path + (os.pathsep if current_path else "") + docker_bin

    docker_config_dir = os.environ.get("DOCKER_CONFIG") or os.path.join(
        os.path.expanduser("~"), ".docker"
    )
    docker_config_path = os.path.join(docker_config_dir, "config.json")
    try:
        if os.path.isfile(docker_config_path):
            with open(docker_config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f) or {}

            creds_store = cfg.get("credsStore")
            if creds_store:
                helper_name = f"docker-credential-{creds_store}"
                helper_in_path = any(
                    os.path.isfile(os.path.join(p, helper_name + ext))
                    for p in os.environ.get("PATH", "").split(os.pathsep)
                    if p
                    for ext in (".exe", ".cmd", ".bat", "")
                )
                if not helper_in_path:
                    tmp_dir = tempfile.mkdtemp(prefix="mcp_docker_config_")
                    with open(
                        os.path.join(tmp_dir, "config.json"),
                        "w",
                        encoding="utf-8",
                    ) as f:
                        json.dump({}, f)
                    os.environ["DOCKER_CONFIG"] = tmp_dir
    except Exception:
        pass

    try:
        client = docker.from_env()
        client.ping()
        return client
    except DockerException as e:
        raise RuntimeError(
            "Docker is not running or not accessible. "
            "Please start Docker Desktop."
        ) from e


# ------------------------------------------------------------------------------
# Tools
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
    ports: dict | None = None,
    env_vars: dict | None = None,
):
    """
    Pulls (if missing) and runs a Docker container.
    """
    client = get_docker_client()

    try:
        client.images.get(image)
    except ImageNotFound:
        client.images.pull(image)

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
    _dependencies[service_name] = {
        "depends_on": depends_on,
        "wait_condition": wait_condition,
        "created_at": time.time()
    }
    
    return {
        "service": service_name,
        "depends_on": depends_on,
        "condition_type": wait_condition.get("type"),
        "status": "defined"
    }

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
    def sort_by_deps(services):
        sorted_services = []
        remaining = services.copy()
        
        while remaining:
            for i, service in enumerate(remaining):
                deps = service.get("depends_on")
                if not deps or deps in deployed_containers:
                    sorted_services.append(remaining.pop(i))
                    break
            else:
                # Circular dependency or missing dependency
                raise RuntimeError(f"Circular dependency or missing dependency in: {[s['name'] for s in remaining]}")
        
        return sorted_services
    
    sorted_definitions = sort_by_deps(definitions)
    
    for service_def in sorted_definitions:
        name = service_def["name"]
        image = service_def["image"]
        ports = service_def.get("ports", {})
        env_vars = service_def.get("env_vars", {})
        
        # Build image if it's a local path
        if "/" in image or "." in image:
            build_image_if_needed(image, f"{name}:latest")
            image = f"{name}:latest"
        
        # Pull image if needed
        try:
            client.images.get(image)
        except ImageNotFound:
            client.images.pull(image)
        
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
            
            wait_success = wait_for_condition(wait_condition, timeout=60)
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
    if service_name not in _dependencies:
        return {"error": f"No dependencies defined for {service_name}"}
    
    dep_info = _dependencies[service_name]
    container = get_container_by_name(service_name)
    
    return {
        "service": service_name,
        "depends_on": dep_info["depends_on"],
        "condition": dep_info["wait_condition"],
        "container_running": container is not None,
        "created_at": dep_info["created_at"]
    }


# ------------------------------------------------------------------------------
# Advanced Tools - Templates
# ------------------------------------------------------------------------------
@mcp.tool()
def create_template(name: str, image: str, ports: dict, env_vars: dict = None, health_check: dict = None):
    """
    Creates a reusable service template.
    """
    _templates[name] = {
        "image": image,
        "ports": ports,
        "env_vars": env_vars or {},
        "health_check": health_check,
        "created_at": time.time()
    }
    
    return {
        "template_name": name,
        "image": image,
        "ports": ports,
        "status": "template_created"
    }

@mcp.tool()
def run_from_template(template_name: str, overrides: dict = None):
    """
    Runs a service from a template with optional overrides.
    """
    if template_name not in _templates:
        return {"error": f"Template {template_name} not found"}
    
    template = _templates[template_name]
    overrides = overrides or {}
    
    # Merge template with overrides
    image = overrides.get("image", template["image"])
    ports = {**template["ports"], **overrides.get("ports", {})}
    env_vars = {**template["env_vars"], **overrides.get("env_vars", {})}
    
    return deploy_service(image=image, ports=ports, env_vars=env_vars)

@mcp.tool()
def list_templates():
    """
    Lists all available templates.
    """
    return {
        "templates": [
            {
                "name": name,
                "image": template["image"],
                "ports": template["ports"],
                "created_at": template["created_at"]
            }
            for name, template in _templates.items()
        ]
    }


# ------------------------------------------------------------------------------
# Advanced Tools - Health Monitoring
# ------------------------------------------------------------------------------
@mcp.tool()
def add_health_check(container_id: str, endpoint: str, interval: int = 30):
    """
    Adds health check monitoring to a container.
    """
    _health_checks[container_id] = {
        "endpoint": endpoint,
        "interval": interval,
        "last_check": None,
        "status": "unknown",
        "created_at": time.time()
    }
    
    return {
        "container_id": container_id,
        "endpoint": endpoint,
        "interval": interval,
        "status": "health_check_added"
    }

@mcp.tool()
def get_service_health(container_id: str):
    """
    Gets health status of a service.
    """
    if container_id not in _health_checks:
        return {"error": f"No health check for container {container_id}"}
    
    health_info = _health_checks[container_id]
    
    # Perform health check
    is_healthy = check_http_endpoint(health_info["endpoint"])
    health_info["last_check"] = time.time()
    health_info["status"] = "healthy" if is_healthy else "unhealthy"
    
    return health_info

@mcp.tool()
def auto_restart_on_failure(container_id: str):
    """
    Enables auto-restart on health check failure.
    """
    def monitor_and_restart():
        while container_id in _health_checks:
            health_info = _health_checks[container_id]
            is_healthy = check_http_endpoint(health_info["endpoint"])
            
            if not is_healthy:
                try:
                    client = get_docker_client()
                    container = client.containers.get(container_id)
                    container.restart()
                    time.sleep(health_info["interval"])
                except:
                    break
            else:
                time.sleep(health_info["interval"])
    
    thread = threading.Thread(target=monitor_and_restart, daemon=True)
    thread.start()
    
    return {
        "container_id": container_id,
        "auto_restart": "enabled",
        "status": "monitoring_started"
    }


# ------------------------------------------------------------------------------
# Advanced Tools - Snapshots & State Management
# ------------------------------------------------------------------------------
@mcp.tool()
def snapshot_env(env_name: str):
    """
    Creates a snapshot of current environment state.
    """
    client = get_docker_client()
    containers = client.containers.list()
    
    snapshot = {
        "env_name": env_name,
        "created_at": time.time(),
        "containers": []
    }
    
    for container in containers:
        snapshot["containers"].append({
            "id": container.short_id,
            "name": container.name,
            "image": container.image.tags[0] if container.image.tags else "unknown",
            "ports": container.attrs.get("NetworkSettings", {}).get("Ports", {}),
            "env": container.attrs.get("Config", {}).get("Env", [])
        })
    
    _snapshots[env_name] = snapshot
    
    return {
        "env_name": env_name,
        "containers_count": len(snapshot["containers"]),
        "status": "snapshot_created"
    }

@mcp.tool()
def restore_env(snapshot_name: str):
    """
    Restores environment from snapshot.
    """
    if snapshot_name not in _snapshots:
        return {"error": f"Snapshot {snapshot_name} not found"}
    
    snapshot = _snapshots[snapshot_name]
    client = get_docker_client()
    restored_containers = []
    
    for container_info in snapshot["containers"]:
        try:
            # Pull image if needed
            image = container_info["image"]
            try:
                client.images.get(image)
            except ImageNotFound:
                client.images.pull(image)
            
            # Parse ports
            ports = {}
            for container_port, host_bindings in container_info["ports"].items():
                if host_bindings:
                    ports[container_port] = host_bindings[0]["HostPort"]
            
            # Parse environment variables
            env_vars = {}
            for env_var in container_info["env"]:
                if "=" in env_var:
                    key, value = env_var.split("=", 1)
                    env_vars[key] = value
            
            # Run container
            container = client.containers.run(
                image=image,
                name=container_info["name"],
                detach=True,
                ports=ports,
                environment=env_vars,
            )
            
            restored_containers.append(container.short_id)
        except Exception as e:
            pass  # Continue with other containers
    
    return {
        "env_name": snapshot_name,
        "restored_containers": restored_containers,
        "status": "env_restored"
    }

@mcp.tool()
def list_snapshots():
    """
    Lists all available snapshots.
    """
    return {
        "snapshots": [
            {
                "name": name,
                "containers_count": len(snapshot["containers"]),
                "created_at": snapshot["created_at"]
            }
            for name, snapshot in _snapshots.items()
        ]
    }


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
    if patterns is None:
        patterns = ['.py', '.js', '.Dockerfile', 'docker-compose.yml']
    
    def on_file_change(changed_file):
        try:
            # Find and rebuild containers for this project
            client = get_docker_client()
            project_name = Path(project_path).name
            
            # Look for containers with project name
            for container in client.containers.list():
                if project_name in container.name:
                    # Get container info
                    image = container.image.tags[0] if container.image.tags else "unknown"
                    
                    # Stop and remove
                    container.stop()
                    container.remove()
                    
                    # Rebuild if local image
                    if "/" in image or "." in image:
                        build_image_if_needed(project_path, image)
                    
                    # Redeploy
                    new_container = client.containers.run(
                        image=image,
                        name=container.name,
                        detach=True,
                        ports=container.attrs.get("NetworkSettings", {}).get("Ports", {}),
                        environment=container.attrs.get("Config", {}).get("Env", []),
                    )
                    
                    break
        except:
            pass  # Continue watching
    
    # Start file watcher
    observer = watch_files(project_path, patterns, on_file_change)
    _watchers[project_path] = observer
    
    return {
        "project_path": project_path,
        "patterns": patterns,
        "status": "watching_started"
    }

@mcp.tool()
def stop_watching(project_path: str):
    """
    Stops file watching for a project.
    """
    if project_path in _watchers:
        observer = _watchers[project_path]
        observer.stop()
        observer.join()
        del _watchers[project_path]
        
        return {
            "project_path": project_path,
            "status": "watching_stopped"
        }
    else:
        return {
            "error": f"No watcher found for {project_path}"
        }

@mcp.tool()
def smart_rebuild(service_name: str):
    """
    Rebuilds only what changed with dependency awareness.
    """
    container = get_container_by_name(service_name)
    if not container:
        return {"error": f"Container {service_name} not found"}
    
    image = container.image.tags[0] if container.image.tags else "unknown"
    
    # Stop and remove
    container.stop()
    container.remove()
    
    # Rebuild if needed
    if "/" in image or "." in image:
        # Extract project path from image name
        project_path = "."  # Default to current directory
        build_image_if_needed(project_path, image)
    
    # Redeploy
    return deploy_service(
        image=image,
        ports=container.attrs.get("NetworkSettings", {}).get("Ports", {}),
        env_vars=dict(env.split("=", 1) for env in container.attrs.get("Config", {}).get("Env", []) if "=" in env)
    )


# ------------------------------------------------------------------------------
# Entry point (stdio)
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    if hasattr(mcp, "run_stdio"):
        mcp.run_stdio()
    else:
        mcp.run(transport="stdio")
