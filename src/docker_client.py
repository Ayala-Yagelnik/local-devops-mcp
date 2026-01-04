"""
Docker client utilities and credential handling.

This module provides robust Docker client initialization with automatic
PATH management and credential helper fallback for Windows environments.
"""

import json
import os
import tempfile
from typing import Optional

import docker
from docker.errors import DockerException, ImageNotFound


def get_docker_client() -> docker.DockerClient:
    """
    Get a configured Docker client with automatic PATH and credential handling.
    
    This function handles common Windows/Docker Desktop issues:
    - Adds Docker binaries to PATH if not present
    - Creates temporary DOCKER_CONFIG if credential helper is missing
    
    Returns:
        docker.DockerClient: Configured Docker client
        
    Raises:
        RuntimeError: If Docker is not running or not accessible
    """
    # Add Docker binaries to PATH on Windows
    docker_bin = r"C:\Program Files\Docker\Docker\resources\bin"
    if os.path.isdir(docker_bin):
        current_path = os.environ.get("PATH", "")
        path_parts = {p.strip().lower() for p in current_path.split(os.pathsep) if p.strip()}
        if docker_bin.lower() not in path_parts:
            os.environ["PATH"] = current_path + (os.pathsep if current_path else "") + docker_bin

    # Handle credential helper issues
    _setup_docker_config()

    # Create and test Docker client
    try:
        client = docker.from_env()
        client.ping()
        return client
    except DockerException as e:
        raise RuntimeError(
            "Docker is not running or not accessible. "
            "Please start Docker Desktop."
        ) from e


def _setup_docker_config() -> None:
    """
    Setup Docker configuration to handle credential helper issues.
    
    Creates a temporary DOCKER_CONFIG with empty config.json if the
    default config references a credential helper that's not available.
    """
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
                    # Create temporary config without credential store
                    tmp_dir = tempfile.mkdtemp(prefix="mcp_docker_config_")
                    with open(
                        os.path.join(tmp_dir, "config.json"),
                        "w",
                        encoding="utf-8",
                    ) as f:
                        json.dump({}, f)
                    os.environ["DOCKER_CONFIG"] = tmp_dir
    except Exception:
        # If anything fails, continue with default config
        pass


def pull_image_if_needed(client: docker.DockerClient, image: str) -> bool:
    """
    Pull Docker image if it doesn't exist locally.
    
    Args:
        client: Docker client instance
        image: Image name to pull
        
    Returns:
        bool: True if image was pulled, False if it already existed
    """
    try:
        client.images.get(image)
        return False
    except ImageNotFound:
        client.images.pull(image)
        return True


def get_container_by_name(client: docker.DockerClient, name: str) -> Optional[docker.models.containers.Container]:
    """
    Get container by name (partial match).
    
    Args:
        client: Docker client instance
        name: Container name to search for
        
    Returns:
        Container object if found, None otherwise
    """
    try:
        for container in client.containers.list():
            if name in container.name:
                return container
        return None
    except:
        return None
