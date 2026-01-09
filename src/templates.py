"""
Service template management.

This module provides reusable service templates that can be deployed
with optional overrides for consistent configuration management.
"""

import time
from typing import Dict, Any, List, Optional

from docker_client import get_docker_client_sync, pull_image_if_needed_sync
from health import detect_health_check_type


class TemplateManager:
    """Manages reusable service templates."""
    
    def __init__(self):
        self._templates: Dict[str, Dict[str, Any]] = {}
    
    def create_template(
        self,
        name: str,
        image: str,
        ports: Dict[str, str],
        env_vars: Optional[Dict[str, str]] = None,
        health_check: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a reusable service template.
        
        Args:
            name: Template name
            image: Docker image name
            ports: Port mapping (container: host)
            env_vars: Environment variables (optional)
            health_check: Health check configuration (optional)
            
        Returns:
            Dict with template creation result
            
        Raises:
            ValueError: If template name already exists or required fields missing
        """
        if not name or not image or not ports:
            if not name:
                raise ValueError("Missing required field: name")
            if not image:
                raise ValueError("Missing required field: image")
            if not ports:
                raise ValueError("Missing required field: ports")
        
        if name in self._templates:
            raise ValueError(f"Template '{name}' already exists")
        
        # Auto-detect health check if not provided
        if health_check is None:
            # Get the first container port for health check detection
            container_port = list(ports.keys())[0]
            health_endpoint = detect_health_check_type(image, int(container_port))
            health_check = {
                "endpoint": health_endpoint,
                "interval": 30
            }
        
        self._templates[name] = {
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
            "env_vars": env_vars or {},
            "health_check": health_check,
            "status": "created"
        }
    
    def run_from_template(
        self,
        template_name: str,
        overrides: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run a service from a template with optional overrides.
        
        Args:
            template_name: Name of template to use
            overrides: Optional overrides for template parameters
            
        Returns:
            Dict with deployment result
            
        Raises:
            ValueError: If template doesn't exist
        """
        if template_name not in self._templates:
            raise ValueError(f"Template '{template_name}' not found")
        
        template = self._templates[template_name]
        overrides = overrides or {}
        
        # Merge template with overrides
        image = overrides.get("image", template["image"])
        ports = {**template["ports"], **overrides.get("ports", {})}
        env_vars = {**template["env_vars"], **overrides.get("env_vars", {})}
        
        # Deploy the service
        result = self._deploy_service(image, ports, env_vars)
        result["template_name"] = template_name
        result["applied_overrides"] = overrides
        return result
    
    def list_templates(self) -> List[Dict[str, Any]]:
        """
        List all available templates.
        
        Returns:
            List of templates
        """
        return [
            {
                "name": name,
                "image": template.get("image", ""),
                "ports": template.get("ports", {}),
                "env_vars": template.get("env_vars", {}),
                "health_check": template.get("health_check"),
                "created_at": template.get("created_at")
            }
            for name, template in self._templates.items()
        ]
    
    def get_template(self, name: str) -> Dict[str, Any]:
        """
        Get template details by name.
        
        Args:
            name: Template name
            
        Returns:
            Template dict if found
            
        Raises:
            ValueError: If template doesn't exist
        """
        if name not in self._templates:
            raise ValueError(f"Template '{name}' not found")
        return self._templates[name]
    
    def delete_template(self, name: str) -> Dict[str, Any]:
        """
        Delete a template.
        
        Args:
            name: Template name to delete
            
        Returns:
            Dict with deletion result
            
        Raises:
            ValueError: If template doesn't exist
        """
        if name not in self._templates:
            raise ValueError(f"Template '{name}' not found")
        
        del self._templates[name]
        return {"template_name": name, "status": "deleted"}
    
    def update_template(
        self,
        name: str,
        image: Optional[str] = None,
        ports: Optional[Dict[str, str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        health_check: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Update an existing template.
        
        Args:
            name: Template name to update
            image: New image (optional)
            ports: New ports (optional)
            env_vars: New env vars (optional, merged with existing)
            health_check: New health check config (optional)
            
        Returns:
            Dict with update result
            
        Raises:
            ValueError: If template doesn't exist
        """
        if name not in self._templates:
            raise ValueError(f"Template '{name}' not found")
        
        template = self._templates[name]
        
        # Update fields
        if image is not None:
            template["image"] = image
        if ports is not None:
            template["ports"] = ports
        if env_vars is not None:
            template["env_vars"] = {**template["env_vars"], **env_vars}
        if health_check is not None:
            template["health_check"] = health_check
        
        return {"template_name": name, "status": "updated"}
    
    def create_smart_template(
        self,
        name: str,
        image: str,
        ports: Dict[str, str],
        env_vars: Optional[Dict[str, str]] = None,
        auto_health_check: bool = True
    ) -> Dict[str, Any]:
        """
        Create a template with automatic health check detection.
        
        Args:
            name: Template name
            image: Docker image name
            ports: Port mapping (container: host)
            env_vars: Environment variables (optional)
            auto_health_check: Whether to auto-detect health check (default: True)
            
        Returns:
            Dict with template creation result
        """
        health_check = None
        if auto_health_check:
            container_port = list(ports.keys())[0]
            health_endpoint = detect_health_check_type(image, int(container_port))
            health_check = {
                "endpoint": health_endpoint,
                "interval": 30
            }
        
        return self.create_template(name, image, ports, env_vars, health_check)
    
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
        client = get_docker_client_sync()
        
        # Pull image if needed
        pull_image_if_needed_sync(client, image)
        
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


# Global template manager instance
template_manager = TemplateManager()
