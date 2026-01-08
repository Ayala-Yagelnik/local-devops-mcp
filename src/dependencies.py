"""
Dependency management and smart waiting logic.

This module provides intelligent dependency resolution with multiple
waiting strategies: TCP port checks, HTTP endpoint validation, and log pattern matching.
"""

import re
import socket
import time
import asyncio
from typing import Dict, Any, List, Optional

import docker
from docker.errors import DockerException

from .docker_client import get_docker_client, get_container_by_name


class DependencyManager:
    """Manages service dependencies with smart waiting capabilities."""
    
    def __init__(self):
        self._dependencies: Dict[str, Dict[str, Any]] = {}
    
    def define_dependency(self, service_name: str, depends_on: str, wait_condition: Dict[str, Any]) -> Dict[str, Any]:
        """
        Define a dependency with smart waiting condition.
        
        Args:
            service_name: Name of the service that depends on another
            depends_on: Name of the service to wait for
            wait_condition: Dictionary with type and details
                           Examples:
                           {"type": "tcp", "host": "db", "port": 5432}
                           {"type": "http", "url": "http://api:8080/health"}
                           {"type": "log", "pattern": "ready to accept connections"}
        
        Returns:
            Dict with dependency definition result
        """
        self._dependencies[service_name] = {
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
    
    def get_dependency_status(self, service_name: str) -> Dict[str, Any]:
        """
        Get dependency status and wait information.
        
        Args:
            service_name: Service name to check
            
        Returns:
            Dict with dependency status information
        """
        if service_name not in self._dependencies:
            return {"error": f"No dependencies defined for {service_name}"}
        
        dep_info = self._dependencies[service_name]
        client = get_docker_client()
        container = get_container_by_name(client, service_name)
        
        return {
            "service": service_name,
            "depends_on": dep_info["depends_on"],
            "condition": dep_info["wait_condition"],
            "container_running": container is not None,
            "created_at": dep_info["created_at"]
        }
    
    async def wait_for_condition_async(self, condition: Dict[str, Any], timeout: int = 60) -> bool:
        """
        Async version of wait for a condition to be met (TCP, HTTP, or log pattern).
        
        Args:
            condition: Condition dictionary with type and parameters
            timeout: Maximum time to wait in seconds
            
        Returns:
            bool: True if condition was met, False otherwise
        """
        start_time = time.time()
        
        # Retry loop with exponential backoff for robust dependency checking
        while time.time() - start_time < timeout:
            cond_type = condition.get("type")
            
            if cond_type == "tcp":
                # Check if TCP port is accessible (network connectivity)
                host = condition.get("host")
                port = condition.get("port")
                if await self._check_tcp_port_async(host, port):
                    return True
                    
            elif cond_type == "http":
                # Check if HTTP endpoint responds with success status
                url = condition.get("url")
                if await self._check_http_endpoint_async(url):
                    return True
                    
            elif cond_type == "log":
                # Check for specific log pattern in container output
                pattern = condition.get("pattern")
                container_id = condition.get("container_id")
                if await self._check_log_pattern_async(container_id, pattern):
                    return True
                    
            await asyncio.sleep(2)
        
        return False
    
    def wait_for_condition(self, condition: Dict[str, Any], timeout: int = 60) -> bool:
        """
        Wait for a condition to be met (TCP, HTTP, or log pattern).
        
        Args:
            condition: Condition dictionary with type and parameters
            timeout: Maximum time to wait in seconds
            
        Returns:
            bool: True if condition was met, False otherwise
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            cond_type = condition.get("type")
            
            if cond_type == "tcp":
                host = condition.get("host")
                port = condition.get("port")
                if self._check_tcp_port(host, port):
                    return True
                    
            elif cond_type == "http":
                url = condition.get("url")
                if self._check_http_endpoint(url):
                    return True
                    
            elif cond_type == "log":
                pattern = condition.get("pattern")
                container_id = condition.get("container_id")
                if self._check_log_pattern(container_id, pattern):
                    return True
                    
            time.sleep(2)
        
        return False
    
    def sort_services_by_dependencies(self, services: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sort services based on their dependencies.
        
        Args:
            services: List of service definitions
            
        Returns:
            List of services sorted in dependency order
            
        Raises:
            RuntimeError: If circular dependency or missing dependency detected
        """
        sorted_services = []
        remaining = services.copy()
        deployed = set()
        
        # Continue until all services are sorted or dependency cycle is detected
        while remaining:
            # Find services that can be deployed (no unmet dependencies)
            for i, service in enumerate(remaining):
                deps = service.get("depends_on")
                # Service can be deployed if it has no dependencies or dependency is already deployed
                if not deps or deps in deployed:
                    # Move service from remaining to sorted list
                    sorted_services.append(remaining.pop(i))
                    deployed.add(service["name"])
                    break
            else:
                # No service can be deployed - indicates circular dependency or missing dependency
                # This is a critical error in the dependency graph
                remaining_names = [s['name'] for s in remaining]
                raise RuntimeError(
                    f"Circular dependency or missing dependency in: {remaining_names}"
                )
        
        return sorted_services
    
    async def _check_tcp_port_async(self, host: str, port: int) -> bool:
        """Async version of check if TCP port is open."""
        try:
            # Run socket connection in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            
            def check_connection():
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                result = sock.connect_ex((host, port))
                sock.close()
                return result == 0
            
            return await loop.run_in_executor(None, check_connection)
        except (OSError, socket.error) as e:
            import logging
            logging.getLogger(__name__).warning(f"TCP port check failed for {host}:{port}: {e}")
            return False
    
    def _check_tcp_port(self, host: str, port: int) -> bool:
        """Check if TCP port is open."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except (OSError, socket.error) as e:
            import logging
            logging.getLogger(__name__).warning(f"TCP port check failed for {host}:{port}: {e}")
            return False
    
    async def _check_http_endpoint_async(self, url: str) -> bool:
        """Async version of check if HTTP endpoint responds."""
        try:
            # Run HTTP request in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            
            def check_endpoint():
                import urllib.request
                import urllib.error
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=5) as response:
                    return response.status < 400
            
            return await loop.run_in_executor(None, check_endpoint)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            import logging
            logging.getLogger(__name__).warning(f"HTTP endpoint check failed for {url}: {e}")
            return False
    
    def _check_http_endpoint(self, url: str) -> bool:
        """Check if HTTP endpoint responds."""
        try:
            import urllib.request
            import urllib.error
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status < 400
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            import logging
            logging.getLogger(__name__).warning(f"HTTP endpoint check failed for {url}: {e}")
            return False
    
    async def _check_log_pattern_async(self, container_id: str, pattern: str) -> bool:
        """Async version of check if log pattern appears in container logs."""
        try:
            # Run Docker operations in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            
            async def check_logs():
                client = await get_docker_client()
                container = await loop.run_in_executor(None, client.containers.get, container_id)
                logs = await loop.run_in_executor(None, lambda: container.logs(tail=50).decode("utf-8", errors="replace"))
                return bool(re.search(pattern, logs, re.IGNORECASE))
            
            return await check_logs()
        except (DockerException, OSError, re.error) as e:
            import logging
            logging.getLogger(__name__).warning(f"Log pattern check failed for {container_id}: {e}")
            return False
    
    def _check_log_pattern(self, container_id: str, pattern: str) -> bool:
        """Check if log pattern appears in container logs."""
        try:
            client = get_docker_client()
            container = client.containers.get(container_id)
            logs = container.logs(tail=50).decode("utf-8", errors="replace")
            return bool(re.search(pattern, logs, re.IGNORECASE))
        except (DockerException, OSError, re.error) as e:
            import logging
            logging.getLogger(__name__).warning(f"Log pattern check failed for {container_id}: {e}")
            return False


# Global dependency manager instance
dependency_manager = DependencyManager()
