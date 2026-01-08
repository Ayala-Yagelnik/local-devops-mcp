"""
Docker client utilities and credential handling.

This module provides robust Docker client initialization with automatic
PATH management and credential helper fallback for Windows environments.
"""

import json
import os
import tempfile
from typing import Optional
import asyncio

import docker
from docker.errors import DockerException, ImageNotFound

# Try to import aiofiles, fallback to standard file operations if not available
try:
    import aiofiles
except ImportError:
    aiofiles = None


async def get_docker_client() -> docker.DockerClient:
    """
    Initialize Docker client with proper error handling and Windows compatibility.
    
    Returns:
        docker.DockerClient: Configured Docker client
        
    Raises:
        RuntimeError: If Docker is not accessible
        DockerConnectionError: If connection fails
        DockerCredentialError: If credential handling fails
    """
    # Add Docker binaries to PATH on Windows
    docker_bin = r"C:\Program Files\Docker\Docker\resources\bin"
    if os.path.isdir(docker_bin):
        current_path = os.environ.get("PATH", "")
        path_parts = {p.strip().lower() for p in current_path.split(os.pathsep) if p.strip()}
        if docker_bin.lower() not in path_parts:
            os.environ["PATH"] = current_path + (os.pathsep if current_path else "") + docker_bin

    # Handle credential helper issues
    await _setup_docker_config_async()

    # Create and test Docker client
    try:
        client = docker.from_env()
        # Run ping in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, client.ping)
        return client
    except DockerException as e:
        raise RuntimeError(
            "Docker is not running or not accessible. "
            "Please start Docker Desktop."
        ) from e


def get_docker_client_sync() -> docker.DockerClient:
    """
    Synchronous version of get_docker_client for backward compatibility.
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


async def _setup_docker_config_async() -> None:
    """
    Async version of Docker configuration setup to handle credential helper issues.
    
    Creates a temporary DOCKER_CONFIG with empty config.json if
    default config references a credential helper that's not available.
    """
    docker_config_dir = os.environ.get("DOCKER_CONFIG") or os.path.join(
        os.path.expanduser("~"), ".docker"
    )
    docker_config_path = os.path.join(docker_config_dir, "config.json")
    
    try:
        if os.path.isfile(docker_config_path):
            if aiofiles:
                async with aiofiles.open(docker_config_path, "r", encoding="utf-8") as f:
                    content = await f.read()
                    cfg = json.loads(content) or {}
            else:
                # Fallback to synchronous file operations
                with open(docker_config_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    cfg = json.loads(content) or {}

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
                    if aiofiles:
                        async with aiofiles.open(
                            os.path.join(tmp_dir, "config.json"),
                            "w",
                            encoding="utf-8",
                        ) as f:
                            await f.write(json.dumps({}))
                    else:
                        # Fallback to synchronous file operations
                        with open(
                            os.path.join(tmp_dir, "config.json"),
                            "w",
                            encoding="utf-8",
                        ) as f:
                            json.dump({}, f)
                    os.environ["DOCKER_CONFIG"] = tmp_dir
    except (OSError, json.JSONDecodeError, PermissionError) as e:
        # If anything fails, continue with default config
        # Log error for debugging purposes
        import logging
        logging.getLogger(__name__).warning(f"Failed to setup Docker config async: {e}")
        pass


def _setup_docker_config() -> None:
    """
    Synchronous version of Docker configuration setup for backward compatibility.
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
    except (OSError, json.JSONDecodeError, PermissionError) as e:
        # If anything fails, continue with default config
        # Log the error for debugging purposes
        import logging
        logging.getLogger(__name__).warning(f"Failed to setup Docker config: {e}")
        pass


async def pull_image_if_needed(client: docker.DockerClient, image: str) -> bool:
    """
    Async version of pull Docker image if it doesn't exist locally.
    
    Args:
        client: Docker client instance
        image: Image name to pull
        
    Returns:
        bool: True if image was pulled, False if it already existed
    """
    try:
        # Run image check in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, client.images.get, image)
        return False
    except ImageNotFound:
        # Run image pull in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, client.images.pull, image)
        return True


def pull_image_if_needed_sync(client: docker.DockerClient, image: str) -> bool:
    """
    Synchronous version of pull_image_if_needed for backward compatibility.
    """
    try:
        client.images.get(image)
        return False
    except ImageNotFound:
        client.images.pull(image)
        return True


async def get_container_by_name(client: docker.DockerClient, name: str) -> Optional[docker.models.containers.Container]:
    """
    Async version of get container by name (partial match).
    
    Args:
        client: Docker client instance
        name: Container name to search for
        
    Returns:
        Container object if found, None otherwise
    """
    try:
        # Run container listing in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        containers = await loop.run_in_executor(None, client.containers.list)
        
        for container in containers:
            if name in container.name:
                return container
        return None
    except (DockerException, OSError) as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to get container by name async: {e}")
        return None


def get_container_by_name_sync(client: docker.DockerClient, name: str) -> Optional[docker.models.containers.Container]:
    """
    Synchronous version of get_container_by_name for backward compatibility.
    """
    try:
        for container in client.containers.list():
            if name in container.name:
                return container
        return None
    except (DockerException, OSError) as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to get container by name: {e}")
        return None
