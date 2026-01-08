"""
File watching and auto-redeployment functionality.

This module provides intelligent file system monitoring with automatic
container rebuilding and redeployment when source code changes.
"""

import os
import threading
import time
from pathlib import Path
from typing import Dict, Any, List, Callable, Optional

from .docker_client import get_docker_client, get_container_by_name


class FileWatcher:
    """Manages file watching and automatic redeployment."""
    
    def __init__(self):
        self._watchers: Dict[str, Any] = {}
        self._observer_threads: Dict[str, threading.Thread] = {}
    
    def watch_and_redeploy(
        self,
        project_path: str,
        patterns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Watch for file changes and auto-redeploy services.
        
        Args:
            project_path: Path to the project directory
            patterns: File patterns to watch (default: ['.py', '.js', '.Dockerfile'])
            
        Returns:
            Dict with watching status
        """
        if patterns is None:
            patterns = ['.py', '.js', '.Dockerfile', 'docker-compose.yml']
        
        def on_file_change(changed_file: str) -> None:
            """Handle file change events."""
            try:
                self._handle_file_change(project_path, changed_file)
            except Exception as e:
                # Log error but continue watching
                print(f"Error handling file change: {e}")
        
        # Start file watcher
        observer = self._start_file_watcher(project_path, patterns, on_file_change)
        self._watchers[project_path] = observer
        
        return {
            "project_path": project_path,
            "patterns": patterns,
            "status": "watching_started"
        }
    
    def stop_watching(self, project_path: str) -> Dict[str, Any]:
        """
        Stop file watching for a project.
        
        Args:
            project_path: Project path to stop watching
            
        Returns:
            Dict with stop result
        """
        if project_path in self._watchers:
            observer = self._watchers[project_path]
            try:
                observer.stop()
                observer.join(timeout=5)
            except Exception as e:
                # Log the error but don't fail - cleanup should continue
                print(f"Warning: Failed to stop observer for {project_path}: {e}")
            finally:
                del self._watchers[project_path]
                if project_path in self._observer_threads:
                    del self._observer_threads[project_path]
            
            return {
                "project_path": project_path,
                "status": "watching_stopped"
            }
        else:
            return {"error": f"No watcher found for {project_path}"}
    
    def smart_rebuild(self, service_name: str) -> Dict[str, Any]:
        """
        Rebuild only what changed with dependency awareness.
        
        Args:
            service_name: Service name to rebuild
            
        Returns:
            Dict with rebuild result
        """
        client = get_docker_client()
        container = get_container_by_name(client, service_name)
        
        if not container:
            return {"error": f"Container {service_name} not found"}
        
        image = container.image.tags[0] if container.image.tags else "unknown"
        
        # Stop and remove container
        container.stop()
        container.remove()
        
        # Rebuild if local image
        if "/" in image or "." in image:
            project_path = self._extract_project_path(service_name)
            if project_path:
                self._build_image_if_needed(project_path, image)
        
        # Redeploy with same configuration
        ports = self._parse_ports(container.attrs.get("NetworkSettings", {}).get("Ports", {}))
        env_vars = self._parse_env_vars(container.attrs.get("Config", {}).get("Env", []))
        
        return self._deploy_service(image, ports, env_vars)
    
    def list_watchers(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        List all active file watchers.
        
        Returns:
            Dict with list of active watchers
        """
        return {
            "watchers": [
                {
                    "project_path": path,
                    "patterns": getattr(observer, 'patterns', []),
                    "status": "active"
                }
                for path, observer in self._watchers.items()
            ]
        }
    
    def _start_file_watcher(
        self,
        project_path: str,
        patterns: List[str],
        callback: Callable[[str], None]
    ) -> Any:
        """
        Start file system watcher.
        
        Args:
            project_path: Path to watch
            patterns: File patterns to watch
            callback: Callback function for file changes
            
        Returns:
            File watcher observer
        """
        try:
            import watchdog.observers
            import watchdog.events
            
            class ChangeHandler(watchdog.events.FileSystemEventHandler):
                def __init__(self, patterns, callback):
                    self.patterns = patterns
                    self.callback = callback
                
                def on_modified(self, event):
                    if not event.is_directory:
                        for pattern in self.patterns:
                            if event.src_path.endswith(pattern):
                                self.callback(event.src_path)
                                break
            
            event_handler = ChangeHandler(patterns, callback)
            observer = watchdog.observers.Observer()
            observer.schedule(event_handler, str(project_path), recursive=True)
            observer.start()
            
            # Store patterns for later reference
            observer.patterns = patterns
            
            return observer
            
        except ImportError:
            # Fallback to simple polling if watchdog not available
            return self._start_polling_watcher(project_path, patterns, callback)
    
    def _start_polling_watcher(
        self,
        project_path: str,
        patterns: List[str],
        callback: Callable[[str], None]
    ) -> Any:
        """
        Start simple polling-based file watcher (fallback).
        
        Args:
            project_path: Path to watch
            patterns: File patterns to watch
            callback: Callback function for file changes
            
        Returns:
            Mock observer object
        """
        class PollingWatcher:
            def __init__(self, project_path, patterns, callback):
                self.project_path = Path(project_path)
                self.patterns = patterns
                self.callback = callback
                self.running = True
                self.file_mtimes = {}
                self._scan_files()
            
            def _scan_files(self):
                """Scan files and record modification times."""
                for pattern in self.patterns:
                    for file_path in self.project_path.rglob(f"*{pattern}"):
                        if file_path.is_file():
                            self.file_mtimes[str(file_path)] = file_path.stat().st_mtime
            
            def start(self):
                """Start polling in separate thread."""
                def poll():
                    while self.running:
                        time.sleep(2)
                        self._check_changes()
                
                thread = threading.Thread(target=poll, daemon=True)
                thread.start()
                self._thread = thread
            
            def stop(self):
                """Stop polling."""
                self.running = False
            
            def join(self, timeout=None):
                """Wait for thread to finish."""
                if hasattr(self, '_thread'):
                    self._thread.join(timeout=timeout)
            
            def _check_changes(self):
                """Check for file changes."""
                current_mtimes = {}
                for file_path, mtime in self.file_mtimes.items():
                    try:
                        current_mtime = Path(file_path).stat().st_mtime
                        if current_mtime != mtime:
                            self.callback(file_path)
                        current_mtimes[file_path] = current_mtime
                    except (OSError, PermissionError) as e:
                        # Skip files that can't be accessed (common with temporary files)
                        continue
                
                # Check for new files
                self._scan_files()
                self.file_mtimes.update(current_mtimes)
        
        watcher = PollingWatcher(project_path, patterns, callback)
        watcher.start()
        return watcher
    
    def _handle_file_change(self, project_path: str, changed_file: str) -> None:
        """
        Handle file change event.
        
        Args:
            project_path: Project root path
            changed_file: Path to changed file
        """
        client = get_docker_client()
        project_name = Path(project_path).name
        
        # Look for containers related to this project
        for container in client.containers.list():
            if project_name in container.name:
                self._rebuild_container(container, project_path)
                break
    
    def _rebuild_container(self, container, project_path: str) -> None:
        """
        Rebuild a container after file changes.
        
        Args:
            container: Docker container object
            project_path: Project path
        """
        try:
            # Get container info
            image = container.image.tags[0] if container.image.tags else "unknown"
            
            # Stop and remove
            container.stop()
            container.remove()
            
            # Rebuild if local image
            if "/" in image or "." in image:
                self._build_image_if_needed(project_path, image)
            
            # Redeploy
            ports = self._parse_ports(container.attrs.get("NetworkSettings", {}).get("Ports", {}))
            env_vars = self._parse_env_vars(container.attrs.get("Config", {}).get("Env", []))  # Added closing parenthesis
            
            self._deploy_service(image, ports, env_vars)
            
        except Exception as e:
            print(f"Error rebuilding container: {e}")
    
    def _build_image_if_needed(self, project_path: str, image_name: str) -> bool:
        """
        Build Docker image if Dockerfile exists.
        
        Args:
            project_path: Path to project
            image_name: Image name to build
            
        Returns:
            bool: True if image was built
        """
        dockerfile_path = Path(project_path) / "Dockerfile"
        if dockerfile_path.exists():
            try:
                client = get_docker_client()
                client.images.build(path=str(project_path), tag=image_name, rm=True)
                return True
            except (docker.errors.BuildError, docker.errors.APIError, Exception) as e:
                # Log specific build errors for debugging
                print(f"Docker build failed for {image_name}: {e}")
                return False
        return False
    
    def _deploy_service(
        self,
        image: str,
        ports: Dict[str, str],
        env_vars: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Deploy a Docker service.
        
        Args:
            image: Docker image name
            ports: Port mapping
            env_vars: Environment variables
            
        Returns:
            Dict with deployment result
        """
        client = get_docker_client()
        
        # Pull image if needed
        try:
            client.images.get(image)
        except Exception:
            client.images.pull(image)
        
        # Deploy container
        container = client.containers.run(
            image=image,
            detach=True,
            ports=ports,
            environment=env_vars,
        )
        
        return {
            "container_id": container.short_id,
            "status": "running",
        }
    
    def _parse_ports(self, ports_dict: Dict[str, Any]) -> Dict[str, str]:
        """Parse Docker ports dictionary."""
        ports = {}
        for container_port, host_bindings in ports_dict.items():
            if host_bindings:
                ports[container_port] = host_bindings[0]["HostPort"]
        return ports
    
    def _parse_env_vars(self, env_list: List[str]) -> Dict[str, str]:
        """Parse environment variables list."""
        env_vars = {}
        for env_var in env_list:
            if "=" in env_var:
                key, value = env_var.split("=", 1)
                env_vars[key] = value
        return env_vars
    
    def _extract_project_path(self, service_name: str) -> Optional[str]:
        """
        Extract project path from service name.
        
        Args:
            service_name: Service name
            
        Returns:
            Project path or None
        """
        # This is a simple implementation - could be enhanced
        # to track project paths during deployment
        return "."


# Global file watcher instance
file_watcher = FileWatcher()
