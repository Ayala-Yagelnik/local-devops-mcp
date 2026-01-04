"""
Health monitoring and auto-restart functionality.

This module provides comprehensive health monitoring for Docker containers
with automatic restart capabilities and status tracking.
"""

import threading
import time
from typing import Dict, Any, List

from .docker_client import get_docker_client


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
        is_healthy = self._check_http_endpoint(health_info["endpoint"])
        health_info["last_check"] = time.time()
        health_info["status"] = "healthy" if is_healthy else "unhealthy"
        
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
            is_healthy = self._check_http_endpoint(health_info["endpoint"])
            
            if not is_healthy:
                try:
                    client = get_docker_client()
                    container = client.containers.get(container_id)
                    container.restart()
                    time.sleep(health_info["interval"])
                except:
                    # Container might have been removed, stop monitoring
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
        except:
            return False


# Global health monitor instance
health_monitor = HealthMonitor()
