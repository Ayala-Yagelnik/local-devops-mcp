"""Tests for templates module."""

import pytest
from unittest.mock import Mock, patch
from src.templates import TemplateManager


class TestTemplateManager:
    """Test cases for TemplateManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.template_manager = TemplateManager()

    def test_create_template_success(self):
        """Test successful template creation."""
        result = self.template_manager.create_template(
            name="web-server",
            image="nginx:latest",
            ports={"80": "8080"},
            env_vars={"NGINX_PORT": "80"},
            health_check={"endpoint": "http://localhost:8080/health", "interval": 30}
        )

        assert result["template_name"] == "web-server"
        assert result["image"] == "nginx:latest"
        assert result["ports"] == {"80": "8080"}
        assert result["env_vars"] == {"NGINX_PORT": "80"}
        assert result["health_check"]["endpoint"] == "http://localhost:8080/health"
        assert result["status"] == "created"
        assert "web-server" in self.template_manager._templates

    def test_create_template_duplicate_name(self):
        """Test error when template name already exists."""
        # Create first template
        self.template_manager.create_template("test", "nginx:latest", {"80": "8080"})

        # Try to create duplicate
        with pytest.raises(ValueError, match="Template 'test' already exists"):
            self.template_manager.create_template("test", "redis:latest", {"6379": "6379"})

    def test_create_template_missing_required_fields(self):
        """Test error when required fields are missing."""
        with pytest.raises(ValueError, match="Missing required field: name"):
            self.template_manager.create_template("", "nginx:latest", {"80": "8080"})

        with pytest.raises(ValueError, match="Missing required field: image"):
            self.template_manager.create_template("test", "", {"80": "8080"})

        with pytest.raises(ValueError, match="Missing required field: ports"):
            self.template_manager.create_template("test", "nginx:latest", {})

    def test_list_templates_empty(self):
        """Test listing templates when none exist."""
        result = self.template_manager.list_templates()
        assert result == []

    def test_list_templates_with_data(self):
        """Test listing templates with existing data."""
        # Add test templates
        self.template_manager._templates["web-server"] = {
            "name": "web-server",
            "image": "nginx:latest",
            "ports": {"80": "8080"},
            "env_vars": {"NGINX_PORT": "80"},
            "created_at": 1234567890.0
        }
        self.template_manager._templates["database"] = {
            "name": "database",
            "image": "postgres:15",
            "ports": {"5432": "5432"},
            "env_vars": {"POSTGRES_DB": "myapp"},
            "created_at": 1234567891.0
        }

        result = self.template_manager.list_templates()

        assert len(result) == 2
        assert result[0]["name"] == "web-server"
        assert result[0]["image"] == "nginx:latest"
        assert result[1]["name"] == "database"
        assert result[1]["image"] == "postgres:15"

    def test_get_template_success(self):
        """Test successful template retrieval."""
        # Add test template
        template_data = {
            "name": "web-server",
            "image": "nginx:latest",
            "ports": {"80": "8080"},
            "env_vars": {"NGINX_PORT": "80"}
        }
        self.template_manager._templates["web-server"] = template_data

        result = self.template_manager.get_template("web-server")

        assert result == template_data

    def test_get_template_nonexistent(self):
        """Test error when getting non-existent template."""
        with pytest.raises(ValueError, match="Template 'nonexistent' not found"):
            self.template_manager.get_template("nonexistent")

    def test_update_template_success(self):
        """Test successful template update."""
        # Create initial template
        self.template_manager.create_template("web-server", "nginx:latest", {"80": "8080"})

        # Update with new data
        result = self.template_manager.update_template(
            "web-server",
            image="nginx:1.21",
            env_vars={"NGINX_PORT": "80", "DEBUG": "true"}
        )

        assert result["template_name"] == "web-server"
        assert result["status"] == "updated"
        
        # Verify updated data
        template = self.template_manager._templates["web-server"]
        assert template["image"] == "nginx:1.21"
        assert template["env_vars"]["DEBUG"] == "true"
        # Original ports should remain
        assert template["ports"] == {"80": "8080"}

    def test_update_template_nonexistent(self):
        """Test error when updating non-existent template."""
        with pytest.raises(ValueError, match="Template 'nonexistent' not found"):
            self.template_manager.update_template("nonexistent", image="nginx:latest")

    def test_delete_template_success(self):
        """Test successful template deletion."""
        # Create template first
        self.template_manager.create_template("test", "nginx:latest", {"80": "8080"})

        result = self.template_manager.delete_template("test")

        assert result["template_name"] == "test"
        assert result["status"] == "deleted"
        assert "test" not in self.template_manager._templates

    def test_delete_template_nonexistent(self):
        """Test error when deleting non-existent template."""
        with pytest.raises(ValueError, match="Template 'nonexistent' not found"):
            self.template_manager.delete_template("nonexistent")

    @patch('src.templates.get_docker_client')
    def test_run_from_template_success(self, mock_get_client):
        """Test successful deployment from template."""
        # Create template
        self.template_manager.create_template(
            "web-server",
            "nginx:latest",
            {"80": "8080"},
            {"NGINX_PORT": "80"}
        )

        # Mock Docker client
        mock_client = Mock()
        mock_container = Mock()
        mock_container.short_id = "abc123"
        mock_client.containers.run.return_value = mock_container
        mock_get_client.return_value = mock_client

        result = self.template_manager.run_from_template("web-server")

        assert result["template_name"] == "web-server"
        assert result["container_id"] == "abc123"
        assert result["status"] == "running"
        assert result["applied_overrides"] == {}

    def test_run_from_template_with_overrides(self):
        """Test deployment from template with parameter overrides."""
        # Create template
        self.template_manager.create_template(
            "web-server",
            "nginx:latest", 
            {"80": "8080"},
            {"NGINX_PORT": "80"}
        )

        with patch('src.templates.get_docker_client') as mock_get_client:
            mock_client = Mock()
            mock_container = Mock()
            mock_container.short_id = "def456"
            mock_client.containers.run.return_value = mock_container
            mock_get_client.return_value = mock_client

            overrides = {
                "ports": {"80": "9090"},
                "env_vars": {"DEBUG": "true"}
            }

            result = self.template_manager.run_from_template("web-server", overrides)

            assert result["applied_overrides"] == overrides
            # Verify Docker was called with overridden parameters
            mock_client.containers.run.assert_called_once()
            call_args = mock_client.containers.run.call_args
            assert call_args[1]["ports"] == {"80": "9090"}
            assert call_args[1]["environment"]["DEBUG"] == "true"

    def test_run_from_template_nonexistent(self):
        """Test error when running non-existent template."""
        with pytest.raises(ValueError, match="Template 'nonexistent' not found"):
            self.template_manager.run_from_template("nonexistent")
