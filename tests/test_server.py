# tests/test_server.py
import pytest
from unittest.mock import Mock, patch
import json

# Import the server module to test its functions
import sys
import os
from pathlib import Path

# Add src directory to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from server import (
    list_running_services,
    deploy_service,
    get_service_logs,
    stop_service,
    define_dependency,
    get_dependency_status,
    create_template,
    run_from_template,
    list_templates,
    add_health_check,
    get_service_health,
    auto_restart_on_failure,
    snapshot_env,
    restore_env,
    list_snapshots,
    watch_and_redeploy,
    stop_watching,
    smart_rebuild
)

class TestServerTools:
    """Test MCP server tool functions."""
    
    @patch('server.get_docker_client')
    def test_list_running_services(self, mock_get_client):
        """Test listing running services."""
        mock_client = Mock()
        mock_container = Mock()
        mock_container.short_id = "abc123def456"
        mock_container.image.tags = ["nginx:latest"]
        mock_container.status = "running"
        mock_container.attrs = {
            "NetworkSettings": {
                "Ports": {
                    "80/tcp": [{"HostPort": "8080"}]
                }
            }
        }
        mock_client.containers.list.return_value = [mock_container]
        mock_get_client.return_value = mock_client
        
        result = list_running_services()
        
        assert len(result) == 1
        assert result[0]["id"] == "abc123def456"
        assert result[0]["image"] == ["nginx:latest"]
        assert result[0]["status"] == "running"
        assert "80/tcp" in result[0]["ports"]
    
    @patch('server.get_docker_client')
    @patch('server.pull_image_if_needed')
    def test_deploy_service(self, mock_pull, mock_get_client):
        """Test deploying a service."""
        mock_client = Mock()
        mock_container = Mock()
        mock_container.short_id = "abc123def456"
        mock_client.containers.run.return_value = mock_container
        mock_get_client.return_value = mock_client
        
        result = deploy_service(
            image="nginx:latest",
            ports={"80": "8080"},
            env_vars={"NGINX_PORT": "80"}
        )
        
        assert result["container_id"] == "abc123def456"
        assert result["status"] == "running"
        mock_pull.assert_called_once_with(mock_client, "nginx:latest")
        mock_client.containers.run.assert_called_once_with(
            image="nginx:latest",
            detach=True,
            ports={"80": "8080"},
            environment={"NGINX_PORT": "80"}
        )
    
    @patch('server.get_docker_client')
    def test_get_service_logs(self, mock_get_client):
        """Test getting service logs."""
        mock_client = Mock()
        mock_container = Mock()
        mock_container.logs.return_value = b"Server started successfully"
        mock_client.containers.get.return_value = mock_container
        mock_get_client.return_value = mock_client
        
        result = get_service_logs("abc123def456", tail=50)
        
        assert result == "Server started successfully"
        mock_client.containers.get.assert_called_once_with("abc123def456")
        mock_container.logs.assert_called_once_with(tail=50)
    
    @patch('server.get_docker_client')
    def test_stop_service(self, mock_get_client):
        """Test stopping a service."""
        mock_client = Mock()
        mock_container = Mock()
        mock_client.containers.get.return_value = mock_container
        mock_get_client.return_value = mock_client
        
        result = stop_service("abc123def456")
        
        assert "stopped and removed successfully" in result
        mock_container.stop.assert_called_once()
        mock_container.remove.assert_called_once()
    
    @patch('server.dependency_manager')
    def test_define_dependency(self, mock_dep_manager):
        """Test defining a dependency."""
        mock_dep_manager.define_dependency.return_value = {
            "service": "web-app",
            "depends_on": "database",
            "condition_type": "tcp",
            "status": "defined"
        }
        
        result = define_dependency(
            "web-app",
            "database",
            {"type": "tcp", "host": "database", "port": 5432}
        )
        
        assert result["service"] == "web-app"
        assert result["depends_on"] == "database"
        assert result["condition_type"] == "tcp"
        assert result["status"] == "defined"
        mock_dep_manager.define_dependency.assert_called_once()
    
    @patch('server.dependency_manager')
    def test_get_dependency_status(self, mock_dep_manager):
        """Test getting dependency status."""
        mock_dep_manager.get_dependency_status.return_value = {
            "service": "web-app",
            "depends_on": "database",
            "condition": {"type": "tcp", "host": "database", "port": 5432},
            "container_running": True,
            "created_at": 1705123456.789
        }
        
        result = get_dependency_status("web-app")
        
        assert result["service"] == "web-app"
        assert result["depends_on"] == "database"
        assert result["container_running"] is True
        mock_dep_manager.get_dependency_status.assert_called_once_with("web-app")
    
    @patch('server.template_manager')
    def test_create_template(self, mock_template_manager):
        """Test creating a template."""
        mock_template_manager.create_template.return_value = {
            "template_name": "web-server",
            "image": "nginx:latest",
            "ports": {"80": "8080"},
            "env_vars": {"NGINX_PORT": "80"},
            "health_check": {"endpoint": "http://localhost:8080/health", "interval": 30},
            "status": "created"
        }
        
        result = create_template(
            name="web-server",
            image="nginx:latest",
            ports={"80": "8080"},
            env_vars={"NGINX_PORT": "80"},
            health_check={"endpoint": "http://localhost:8080/health", "interval": 30}
        )
        
        assert result["template_name"] == "web-server"
        assert result["status"] == "created"
        mock_template_manager.create_template.assert_called_once()
    
    @patch('server.template_manager')
    def test_run_from_template(self, mock_template_manager):
        """Test running service from template."""
        mock_template_manager.run_from_template.return_value = {
            "container_id": "abc123def456",
            "template_name": "web-server",
            "applied_overrides": {"ports": {"80": "9090"}},
            "status": "running"
        }
        
        result = run_from_template("web-server", {"ports": {"80": "9090"}})
        
        assert result["container_id"] == "abc123def456"
        assert result["template_name"] == "web-server"
        assert result["status"] == "running"
        mock_template_manager.run_from_template.assert_called_once()
    
    @patch('server.template_manager')
    def test_list_templates(self, mock_template_manager):
        """Test listing templates."""
        mock_template_manager.list_templates.return_value = [
            {
                "name": "web-server",
                "image": "nginx:latest",
                "ports": {"80": "8080"},
                "env_vars": {"NGINX_PORT": "80"},
                "health_check": {"endpoint": "http://localhost:8080/health", "interval": 30},
                "created_at": 1705123456.789
            }
        ]
        
        result = list_templates()
        
        assert len(result) == 1
        assert result[0]["name"] == "web-server"
        assert result[0]["image"] == "nginx:latest"
        mock_template_manager.list_templates.assert_called_once()
    
    @patch('server.health_monitor')
    def test_add_health_check(self, mock_health_monitor):
        """Test adding health check."""
        mock_health_monitor.add_health_check.return_value = {
            "container_id": "abc123def456",
            "endpoint": "http://localhost:8080/health",
            "interval": 30,
            "status": "health_check_added"
        }
        
        result = add_health_check("abc123def456", "http://localhost:8080/health", 30)
        
        assert result["container_id"] == "abc123def456"
        assert result["status"] == "health_check_added"
        mock_health_monitor.add_health_check.assert_called_once()
    
    @patch('server.health_monitor')
    def test_get_service_health(self, mock_health_monitor):
        """Test getting service health."""
        mock_health_monitor.get_service_health.return_value = {
            "container_id": "abc123def456",
            "endpoint": "http://localhost:8080/health",
            "interval": 30,
            "last_check": 1705123456.789,
            "status": "healthy",
            "created_at": 1705123400.123
        }
        
        result = get_service_health("abc123def456")
        
        assert result["container_id"] == "abc123def456"
        assert result["status"] == "healthy"
        mock_health_monitor.get_service_health.assert_called_once()
    
    @patch('server.health_monitor')
    def test_auto_restart_on_failure(self, mock_health_monitor):
        """Test enabling auto-restart on failure."""
        mock_health_monitor.enable_auto_restart.return_value = {
            "container_id": "abc123def456",
            "auto_restart": "enabled",
            "status": "monitoring_started"
        }
        
        result = auto_restart_on_failure("abc123def456")
        
        assert result["container_id"] == "abc123def456"
        assert result["auto_restart"] == "enabled"
        mock_health_monitor.enable_auto_restart.assert_called_once()
    
    @patch('server.snapshot_manager')
    def test_snapshot_env(self, mock_snapshot_manager):
        """Test creating environment snapshot."""
        mock_snapshot_manager.snapshot_env.return_value = {
            "snapshot_name": "test-snapshot",
            "container_count": 2,
            "containers": [
                {
                    "id": "abc123def456",
                    "name": "postgres",
                    "image": "postgres:15",
                    "ports": {"5432/tcp": [{"HostPort": "5432"}]},
                    "env_vars": {"POSTGRES_DB": "myapp"}
                }
            ],
            "created_at": 1705123456.789,
            "status": "created"
        }
        
        result = snapshot_env("test-snapshot")
        
        assert result["snapshot_name"] == "test-snapshot"
        assert result["status"] == "created"
        mock_snapshot_manager.snapshot_env.assert_called_once()
    
    @patch('server.snapshot_manager')
    def test_restore_env(self, mock_snapshot_manager):
        """Test restoring environment from snapshot."""
        mock_snapshot_manager.restore_env.return_value = {
            "snapshot_name": "test-snapshot",
            "restored_containers": {
                "postgres": "xyz789abc012",
                "redis": "def456ghi789"
            },
            "container_count": 2,
            "status": "restored"
        }
        
        result = restore_env("test-snapshot")
        
        assert result["snapshot_name"] == "test-snapshot"
        assert result["status"] == "restored"
        mock_snapshot_manager.restore_env.assert_called_once()
    
    @patch('server.snapshot_manager')
    def test_list_snapshots(self, mock_snapshot_manager):
        """Test listing snapshots."""
        mock_snapshot_manager.list_snapshots.return_value = [
            {
                "name": "dev-env-v1",
                "container_count": 3,
                "created_at": 1705123456.789,
                "size_bytes": 2048,
                "containers": ["postgres", "redis", "api"]
            }
        ]
        
        result = list_snapshots()
        
        assert len(result) == 1
        assert result[0]["name"] == "dev-env-v1"
        mock_snapshot_manager.list_snapshots.assert_called_once()
    
    @patch('server.file_watcher')
    def test_watch_and_redeploy(self, mock_file_watcher):
        """Test watching and redeploying on file changes."""
        mock_file_watcher.watch_and_redeploy.return_value = {
            "project_path": "/home/user/my-app",
            "patterns": ['.py', '.js', '.html'],
            "watcher_id": "watcher_abc123",
            "status": "watching_started"
        }
        
        result = watch_and_redeploy("/home/user/my-app", ['.py', '.js', '.html'])
        
        assert result["project_path"] == "/home/user/my-app"
        assert result["status"] == "watching_started"
        mock_file_watcher.watch_and_redeploy.assert_called_once()
    
    @patch('server.file_watcher')
    def test_stop_watching(self, mock_file_watcher):
        """Test stopping file watching."""
        mock_file_watcher.stop_watching.return_value = {
            "project_path": "/home/user/my-app",
            "watcher_id": "watcher_abc123",
            "status": "watching_stopped"
        }
        
        result = stop_watching("/home/user/my-app")
        
        assert result["project_path"] == "/home/user/my-app"
        assert result["status"] == "watching_stopped"
        mock_file_watcher.stop_watching.assert_called_once()
    
    @patch('server.file_watcher')
    def test_smart_rebuild(self, mock_file_watcher):
        """Test smart rebuild of service."""
        mock_file_watcher.smart_rebuild.return_value = {
            "service_name": "web-app",
            "rebuilt_components": ["web-app", "api-client"],
            "skipped_components": ["database", "redis"],
            "new_container_id": "xyz789abc012",
            "build_time_seconds": 15.3,
            "status": "rebuilt"
        }
        
        result = smart_rebuild("web-app")
        
        assert result["service_name"] == "web-app"
        assert result["status"] == "rebuilt"
        mock_file_watcher.smart_rebuild.assert_called_once()
