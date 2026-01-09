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

from .docker_client import get_docker_client_sync, get_container_by_name


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
        # Support multiple dependencies by storing them as a list
        if service_name not in self._dependencies:
            self._dependencies[service_name] = {
                "depends_on": [],
                "wait_conditions": [],
                "created_at": time.time()
            }
        
        # Add dependency if not already present
        if depends_on not in self._dependencies[service_name]["depends_on"]:
            self._dependencies[service_name]["depends_on"].append(depends_on)
            self._dependencies[service_name]["wait_conditions"].append(wait_condition)
        
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
        from docker_client import get_docker_client_sync
        client = get_docker_client_sync()
        container = get_container_by_name(client, service_name)
        
        return {
            "service": service_name,
            "depends_on": dep_info["depends_on"],
            "wait_conditions": dep_info["wait_conditions"],
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
    
    def sort_services_by_dependencies_multi(self, services: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sort services based on their dependencies (supports multiple dependencies).
        
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
                # Handle both single dependency (string) and multiple dependencies (list)
                if deps:
                    if isinstance(deps, str):
                        deps_list = [deps]
                    else:
                        deps_list = deps
                    
                    # Check if all dependencies are deployed
                    if all(dep in deployed for dep in deps_list):
                        # Move service from remaining to sorted list
                        sorted_services.append(remaining.pop(i))
                        deployed.add(service["name"])
                        break
                else:
                    # No dependencies - can be deployed
                    sorted_services.append(remaining.pop(i))
                    deployed.add(service["name"])
                    break
            else:
                # No service can be deployed - indicates circular dependency or missing dependency
                remaining_names = [s['name'] for s in remaining]
                raise RuntimeError(
                    f"Circular dependency or missing dependency in: {remaining_names}"
                )
        
        return sorted_services
    
    def deploy_group(self, definitions: list) -> dict:
        """
        Deploys multiple services respecting dependencies with smart orchestration.
        
        Args:
            definitions (list): List of service definitions with dependencies
            
        Returns:
            dict: Deployment result with deployed services mapping
        """
        from .docker_client import get_docker_client_sync, pull_image_if_needed
        
        client = get_docker_client_sync()
        deployed_containers = {}
        
        # Create a copy of definitions for dependency resolution
        definitions_copy = []
        for service_def in definitions:
            service_copy = service_def.copy()
            # Convert wait_conditions to wait_condition for the first dependency
            if "wait_conditions" in service_copy:
                service_copy["wait_condition"] = service_copy["wait_conditions"][0]
            definitions_copy.append(service_copy)
        
        # Sort services based on dependencies (supports multiple dependencies)
        sorted_definitions = self.sort_services_by_dependencies_multi(definitions_copy)
        
        # Deploy services in dependency order
        for service_def in sorted_definitions:
            name = service_def["name"]
            image = service_def["image"]
            ports = service_def.get("ports", {})
            env_vars = service_def.get("env_vars", {})
            
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
            
            # Track deployed container
            deployed_containers[name] = container.short_id
            
            # Get the original service definition to check for wait conditions
            original_service = next(s for s in definitions if s["name"] == name)
            
            # Wait for dependencies if defined
            if "wait_conditions" in original_service:
                # Handle multiple wait conditions
                for wait_condition in original_service["wait_conditions"]:
                    wait_success = self.wait_for_condition(wait_condition, timeout=60)
                    if not wait_success:
                        container.stop()
                        container.remove()
                        raise RuntimeError(f"Dependency not met for {name}: {wait_condition}")
            elif "wait_condition" in original_service:
                wait_condition = original_service["wait_condition"]
                wait_success = self.wait_for_condition(wait_condition, timeout=60)
                if not wait_success:
                    container.stop()
                    container.remove()
                    raise RuntimeError(f"Dependency not met for {name}: {wait_condition}")
        
        return {
            "deployed_services": deployed_containers,
            "status": "all_services_running"
        }
    
    async def _check_tcp_port_async(self, host: str, port: int) -> bool:
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
        import urllib.request
        import urllib.error
        
        try:
            # Run HTTP request in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            
            def check_endpoint():
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
                from docker_client import get_docker_client_sync
                client = get_docker_client_sync()
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
            from docker_client import get_docker_client_sync
            client = get_docker_client_sync()
            container = client.containers.get(container_id)
            logs = container.logs(tail=50).decode("utf-8", errors="replace")
            return bool(re.search(pattern, logs, re.IGNORECASE))
        except (DockerException, OSError, re.error) as e:
            import logging
            logging.getLogger(__name__).warning(f"Log pattern check failed for {container_id}: {e}")
            return False

    def deploy_group(self, definitions: list) -> dict:
        """
        Deploys multiple services respecting dependencies with smart orchestration.
        
        Args:
            definitions (list): List of service definitions with dependencies
            
        Returns:
            dict: Deployment result with deployed services mapping
        """
        from .docker_client import get_docker_client_sync, pull_image_if_needed
        
        client = get_docker_client_sync()
        deployed_containers = {}
        
        # Sort services based on dependencies (supports multiple dependencies)
        sorted_definitions = self.sort_services_by_dependencies_multi(definitions)
        
        # Deploy services in dependency order
        for service_def in sorted_definitions:
            name = service_def["name"]
            image = service_def["image"]
            ports = service_def.get("ports", {})
            env_vars = service_def.get("env_vars", {})
            
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
            
            # Track deployed container
            deployed_containers[name] = container.short_id
            
            # Wait for dependencies if defined
            if "wait_condition" in service_def:
                wait_condition = service_def["wait_condition"]
                wait_success = self.wait_for_condition(wait_condition, timeout=60)
                if not wait_success:
                    container.stop()
                    container.remove()
                    raise RuntimeError(f"Dependency not met for {name}: {wait_condition}")
            elif "wait_conditions" in service_def:
                # Handle multiple wait conditions
                for wait_condition in service_def["wait_conditions"]:
                    wait_success = self.wait_for_condition(wait_condition, timeout=60)
                    if not wait_success:
                        container.stop()
                        container.remove()
                        raise RuntimeError(f"Dependency not met for {name}: {wait_condition}")
        
        return {
            "deployed_services": deployed_containers,
            "status": "all_services_running"
        }


# Global dependency manager instance
dependency_manager = DependencyManager()
