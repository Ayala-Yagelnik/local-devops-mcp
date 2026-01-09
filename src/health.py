"""
Health monitoring and auto-restart functionality.

This module provides comprehensive health monitoring for Docker containers
with automatic restart capabilities and status tracking.
"""

import threading
import time
from typing import Dict, Any, List

from docker.errors import DockerException
from docker_client import get_docker_client, get_docker_client_sync


class HealthMonitor:
    """Manages health checks and auto-restart for containers."""
    
    def __init__(self):
        self._health_checks: Dict[str, Dict[str, Any]] = {}
        self._monitoring_threads: Dict[str, threading.Thread] = {}
    
    def add_health_check(
        self,
        container_id: str,
        endpoint: str,
        interval: int = 30
    ) -> Dict[str, Any]:
        """
        Add health check monitoring to a container.
        
        Args:
            container_id: Container ID to monitor
            endpoint: HTTP endpoint to check
            interval: Check interval in seconds
            
        Returns:
            Dict with health check addition result
        """
        self._health_checks[container_id] = {
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
    
    def get_service_health(self, container_id: str) -> Dict[str, Any]:
        """
        Get health status of a service.
        
        Args:
            container_id: Container ID to check
            
        Returns:
            Dict with health status information
        """
        if container_id not in self._health_checks:
            return {"error": f"No health check for container {container_id}"}
        
        health_info = self._health_checks[container_id]
        
        # Perform health check
        endpoint = health_info["endpoint"]
        if endpoint.startswith("tcp://"):
            is_healthy = self._check_tcp_endpoint(endpoint)
        elif endpoint.startswith("http://") or endpoint.startswith("https://"):
            is_healthy = self._check_http_endpoint(endpoint)
        else:
            # Default to TCP for unknown protocols
            is_healthy = self._check_tcp_endpoint(f"tcp://{endpoint}")
        
        health_info["last_check"] = time.time()
        health_info["status"] = "healthy" if is_healthy else "unhealthy"
        
        # Ensure container_id is included in the response
        health_info["container_id"] = container_id
        
        return health_info
    
    def enable_auto_restart(self, container_id: str) -> Dict[str, Any]:
        """
        Enable auto-restart on health check failure.
        
        Args:
            container_id: Container ID to monitor
            
        Returns:
            Dict with auto-restart status
        """
        if container_id not in self._health_checks:
            return {"error": f"No health check for container {container_id}"}
        
        # Stop existing monitoring if any
        if container_id in self._monitoring_threads:
            self._monitoring_threads[container_id].stop()
        
        # Start new monitoring thread
        thread = threading.Thread(
            target=self._monitor_and_restart,
            args=(container_id,),
            daemon=True
        )
        thread.start()
        self._monitoring_threads[container_id] = thread
        
        return {
            "container_id": container_id,
            "auto_restart": "enabled",
            "status": "monitoring_started"
        }
    
    def disable_auto_restart(self, container_id: str) -> Dict[str, Any]:
        """
        Disable auto-restart for a container.
        
        Args:
            container_id: Container ID to stop monitoring
            
        Returns:
            Dict with disable result
        """
        if container_id in self._monitoring_threads:
            # Note: We can't actually stop threads in Python, but we can
            # remove the reference so it won't restart on next check
            del self._monitoring_threads[container_id]
        
        return {
            "container_id": container_id,
            "auto_restart": "disabled",
            "status": "monitoring_stopped"
        }
    
    def remove_health_check(self, container_id: str) -> Dict[str, Any]:
        """
        Remove health check for a container.
        
        Args:
            container_id: Container ID to remove monitoring from
            
        Returns:
            Dict with removal result
        """
        # Disable auto-restart first
        self.disable_auto_restart(container_id)
        
        # Remove health check
        if container_id in self._health_checks:
            del self._health_checks[container_id]
            return {
                "container_id": container_id,
                "status": "health_check_removed"
            }
        else:
            return {"error": f"No health check for container {container_id}"}
    
    def list_health_checks(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        List all active health checks.
        
        Returns:
            Dict with list of health checks
        """
        return {
            "health_checks": [
                {
                    "container_id": container_id,
                    "endpoint": info["endpoint"],
                    "interval": info["interval"],
                    "status": info["status"],
                    "auto_restart": container_id in self._monitoring_threads
                }
                for container_id, info in self._health_checks.items()
            ]
        }
    
    def _monitor_and_restart(self, container_id: str) -> None:
        """
        Monitor container health and restart on failure.
        
        This runs in a separate thread and continuously monitors
        the container health, restarting it when needed.
        """
        while container_id in self._health_checks and container_id in self._monitoring_threads:
            health_info = self._health_checks[container_id]
            endpoint = health_info["endpoint"]
            
            # Check endpoint based on protocol
            if endpoint.startswith("tcp://"):
                is_healthy = self._check_tcp_endpoint(endpoint)
            elif endpoint.startswith("http://") or endpoint.startswith("https://"):
                is_healthy = self._check_http_endpoint(endpoint)
            else:
                # Default to TCP for unknown protocols
                is_healthy = self._check_tcp_endpoint(f"tcp://{endpoint}")
            
            # Update health status
            health_info["status"] = "healthy" if is_healthy else "unhealthy"
            health_info["last_check"] = time.time()
            
            if not is_healthy:
                try:
                    from src.docker_client import get_docker_client_sync
                    client = get_docker_client_sync()
                    container = client.containers.get(container_id)
                    container.restart()
                    time.sleep(health_info["interval"])
                except (DockerException, OSError) as e:
                    # Container might have been removed, stop monitoring
                    import logging
                    logging.getLogger(__name__).warning(f"Failed to restart container {container_id}: {e}")
                    break
            else:
                time.sleep(health_info["interval"])
    
    def _check_http_endpoint(self, url: str) -> bool:
        """
        Check if HTTP endpoint responds.
        
        Args:
            url: HTTP endpoint URL
            
        Returns:
            bool: True if endpoint is healthy
        """
        try:
            import urllib.request
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status < 400
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            import logging
            logging.getLogger(__name__).warning(f"HTTP endpoint check failed for {url}: {e}")
            return False
    
    def _check_tcp_endpoint(self, endpoint: str) -> bool:
        """
        Check if TCP endpoint is reachable.
        
        Args:
            endpoint: TCP endpoint in format "tcp://host:port"
            
        Returns:
            bool: True if endpoint is reachable
        """
        try:
            # Parse tcp://host:port format
            if endpoint.startswith("tcp://"):
                endpoint = endpoint[6:]  # Remove "tcp://"
            
            host, port = endpoint.split(":")
            port = int(port)
            
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()
            
            return result == 0
        except (ValueError, OSError) as e:
            import logging
            logging.getLogger(__name__).warning(f"TCP endpoint check failed for {endpoint}: {e}")
            return False


def detect_health_check_type(image_name: str, port: int) -> str:
    """
    Detect appropriate health check type based on image and port.
    
    Args:
        image_name: Docker image name (e.g., "postgres:15", "nginx:latest")
        port: Container port number
        
    Returns:
        str: Health check endpoint URL
    """
    image_lower = image_name.lower()
    
    # Database services - use TCP
    if any(db in image_lower for db in ['postgres', 'mysql', 'mongodb', 'mariadb']):
        return f"tcp://localhost:{port}"
    
    # Cache services - use TCP  
    if any(cache in image_lower for cache in ['redis', 'memcached']):
        return f"tcp://localhost:{port}"
    
    # Message queues - use TCP
    if any(queue in image_lower for queue in ['rabbitmq', 'kafka', 'nats']):
        return f"tcp://localhost:{port}"
    
    # Web servers - try HTTP first, fallback to TCP
    if any(web in image_lower for web in ['nginx', 'apache', 'httpd', 'caddy']):
        return f"http://localhost:{port}"
    
    # Application servers - try HTTP with health endpoint
    if any(app in image_lower for app in ['api', 'app', 'server', 'service']):
        return f"http://localhost:{port}/health"
    
    # Frontend frameworks - use HTTP
    if any(frontend in image_lower for frontend in ['react', 'vue', 'angular', 'next']):
        return f"http://localhost:{port}"
    
    # Default to TCP for unknown services
    return f"tcp://localhost:{port}"


# Global health monitor instance
health_monitor = HealthMonitor()
