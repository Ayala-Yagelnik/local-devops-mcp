"""
Service template management.

This module provides reusable service templates that can be deployed
with optional overrides for consistent configuration management.
"""

import time
from typing import Dict, Any, List, Optional

from .docker_client import get_docker_client, pull_image_if_needed


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
        """
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
            "status": "template_created"
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
        """
        if template_name not in self._templates:
            return {"error": f"Template {template_name} not found"}
        
        template = self._templates[template_name]
        overrides = overrides or {}
        
        # Merge template with overrides
        image = overrides.get("image", template["image"])
        ports = {**template["ports"], **overrides.get("ports", {})}
        env_vars = {**template["env_vars"], **overrides.get("env_vars", {})}
        
        # Deploy the service
        return self._deploy_service(image, ports, env_vars)
    
    def list_templates(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        List all available templates.
        
        Returns:
            Dict with list of templates
        """
        return {
            "templates": [
                {
                    "name": name,
                    "image": template["image"],
                    "ports": template["ports"],
                    "created_at": template["created_at"]
                }
                for name, template in self._templates.items()
            ]
        }
    
    def get_template(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get template details by name.
        
        Args:
            name: Template name
            
        Returns:
            Template dict if found, None otherwise
        """
        return self._templates.get(name)
    
    def delete_template(self, name: str) -> Dict[str, Any]:
        """
        Delete a template.
        
        Args:
            name: Template name to delete
            
        Returns:
            Dict with deletion result
        """
        if name in self._templates:
            del self._templates[name]
            return {"template_name": name, "status": "deleted"}
        else:
            return {"error": f"Template {name} not found"}
    
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
        pull_image_if_needed(client, image)
        
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
