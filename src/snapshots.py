"""
Environment snapshot and restore functionality.

This module provides the ability to capture complete container environments
and restore them later, enabling reproducible development and testing setups.
"""

import time
from pathlib import Path
from typing import Dict, Any, List

from docker.errors import ImageNotFound

from docker_client import get_docker_client_sync, pull_image_if_needed_sync


class SnapshotManager:
    """Manages environment snapshots and restoration."""
    
    def __init__(self):
        self._snapshots: Dict[str, Dict[str, Any]] = {}
        # Create snapshots directory if it doesn't exist
        snapshots_dir = Path.home() / ".devops-mcp" / "snapshots"
        if not snapshots_dir.exists():
            snapshots_dir.mkdir(parents=True, exist_ok=True)
    
    def snapshot_env(self, env_name: str) -> Dict[str, Any]:
        """
        Create a snapshot of current environment state.
        
        Args:
            env_name: Name for the snapshot
            
        Returns:
            Dict with snapshot creation result
            
        Raises:
            ValueError: If snapshot name already exists
        """
        if env_name in self._snapshots:
            raise ValueError(f"Snapshot '{env_name}' already exists")
        client = get_docker_client_sync()
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
                "env": container.attrs.get("Config", {}).get("Env", []),
                "labels": container.attrs.get("Config", {}).get("Labels", {}),
                "restart_policy": container.attrs.get("HostConfig", {}).get("RestartPolicy", {}),
                "network_mode": container.attrs.get("HostConfig", {}).get("NetworkMode", "default"),
                "volumes": container.attrs.get("Mounts", [])
            })
        
        self._snapshots[env_name] = snapshot
        
        return {
            "snapshot_name": env_name,
            "container_count": len(snapshot["containers"]),
            "containers": snapshot["containers"],
            "created_at": snapshot["created_at"],
            "status": "created"
        }
    
    def restore_env(self, snapshot_name: str) -> Dict[str, Any]:
        """
        Restore environment from snapshot.
        
        Args:
            snapshot_name: Name of snapshot to restore
            
        Returns:
            Dict with restoration result
            
        Raises:
            ValueError: If snapshot doesn't exist
        """
        if snapshot_name not in self._snapshots:
            raise ValueError(f"Snapshot '{snapshot_name}' not found")
        
        snapshot = self._snapshots[snapshot_name]
        client = get_docker_client_sync()
        restored_containers = []
        failed_containers = []
        
        for container_info in snapshot["containers"]:
            try:
                # Pull image if needed
                image = container_info["image"]
                if image != "unknown":
                    pull_image_if_needed_sync(client, image)
                
                # Parse ports
                ports = {}
                port_bindings = {}
                for container_port, host_bindings in container_info["ports"].items():
                    if host_bindings:
                        host_port = host_bindings[0]["HostPort"]
                        ports[container_port] = host_port
                        port_bindings[container_port] = {"HostPort": host_port}
                
                # Parse environment variables
                env_vars = {}
                env_list = container_info.get("env_vars", container_info.get("env", []))
                if isinstance(env_list, dict):
                    env_vars = env_list
                else:
                    for env_var in env_list:
                        if "=" in env_var:
                            key, value = env_var.split("=", 1)
                            env_vars[key] = value
                
                # Parse volumes
                volumes = {}
                volume_bindings = {}
                for mount in container_info.get("volumes", []):
                    if mount.get("Type") == "bind":
                        source = mount.get("Source")
                        destination = mount.get("Destination")
                        if source and destination:
                            volumes[destination] = {"bind": source, "mode": "rw"}
                
                # Run container with original configuration
                try:
                    container = client.containers.run(
                        image=image,
                        name=container_info["name"],
                        detach=True,
                        ports=port_bindings,
                        environment=env_vars,
                        labels=container_info.get("labels", {}),
                        restart_policy=container_info["restart_policy"],
                        network_mode=container_info["network_mode"],
                        volumes=volumes,
                    )
                    
                    restored_containers.append({
                        "original_id": container_info["id"],
                        "new_id": container.short_id,
                        "name": container_info["name"]
                    })
                except Exception as e:
                    print(f"Error restoring container {container_info['name']}: {e}")
                    continue
                
            except Exception as e:
                failed_containers.append({
                    "name": container_info["name"],
                    "image": container_info["image"],
                    "error": str(e)
                })
        
        return {
            "snapshot_name": snapshot_name,
            "restored_containers": restored_containers,
            "failed_containers": failed_containers,
            "container_count": len(restored_containers),
            "status": "restored"
        }
    
    def list_snapshots(self) -> List[Dict[str, Any]]:
        """
        List all available snapshots.
        
        Returns:
            List of snapshots
        """
        return [
            {
                "name": name,
                "container_count": len(snapshot["containers"]),
                "created_at": snapshot["created_at"],
                "containers": [
                    c["name"] if isinstance(c, dict) else c 
                    for c in snapshot["containers"]
                ]
            }
            for name, snapshot in self._snapshots.items()
        ]
    
    def get_snapshot(self, name: str) -> Dict[str, Any]:
        """
        Get snapshot details by name.
        
        Args:
            name: Snapshot name
            
        Returns:
            Snapshot details or error
        """
        if name not in self._snapshots:
            return {"error": f"Snapshot {name} not found"}
        
        snapshot = self._snapshots[name]
        return {
            "name": snapshot["env_name"],
            "created_at": snapshot["created_at"],
            "containers": snapshot["containers"]
        }
    
    def delete_snapshot(self, name: str) -> Dict[str, Any]:
        """
        Delete a snapshot.
        
        Args:
            name: Snapshot name to delete
            
        Returns:
            Dict with deletion result
            
        Raises:
            ValueError: If snapshot doesn't exist
        """
        if name not in self._snapshots:
            raise ValueError(f"Snapshot '{name}' not found")
        
        del self._snapshots[name]
        return {"snapshot_name": name, "status": "deleted"}
    
    def compare_snapshots(self, name1: str, name2: str) -> Dict[str, Any]:
        """
        Compare two snapshots to show differences.
        
        Args:
            name1: First snapshot name
            name2: Second snapshot name
            
        Returns:
            Dict with comparison results
        """
        if name1 not in self._snapshots:
            return {"error": f"Snapshot {name1} not found"}
        if name2 not in self._snapshots:
            return {"error": f"Snapshot {name2} not found"}
        
        snapshot1 = self._snapshots[name1]
        snapshot2 = self._snapshots[name2]
        
        containers1 = {c["name"]: c for c in snapshot1["containers"]}
        containers2 = {c["name"]: c for c in snapshot2["containers"]}
        
        added = set(containers2.keys()) - set(containers1.keys())
        removed = set(containers1.keys()) - set(containers2.keys())
        common = set(containers1.keys()) & set(containers2.keys())
        
        changed = []
        for name in common:
            c1 = containers1[name]
            c2 = containers2[name]
            if c1["image"] != c2["image"] or c1["ports"] != c2["ports"]:
                changed.append({
                    "name": name,
                    "old_image": c1["image"],
                    "new_image": c2["image"],
                    "old_ports": c1["ports"],
                    "new_ports": c2["ports"]
                })
        
        return {
            "snapshot1": name1,
            "snapshot2": name2,
            "added_containers": list(added),
            "removed_containers": list(removed),
            "changed_containers": changed
        }


# Global snapshot manager instance
snapshot_manager = SnapshotManager()
