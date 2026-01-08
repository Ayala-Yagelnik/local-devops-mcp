"""Tests for snapshots module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.snapshots import SnapshotManager


class TestSnapshotManager:
    """Test cases for SnapshotManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.snapshot_manager = SnapshotManager()

    @patch('src.snapshots.Path.exists')
    @patch('src.snapshots.Path.mkdir')
    def test_init_creates_directory(self, mock_mkdir, mock_exists):
        """Test that initialization creates snapshots directory."""
        mock_exists.return_value = False
        
        manager = SnapshotManager()
        
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_snapshot_env_success(self):
        """Test successful environment snapshot creation."""
        mock_containers = [
            Mock(
                id="abc123",
                name="test-container-1",
                image=Mock(tags=["nginx:latest"]),
                attrs={
                    "NetworkSettings": {
                        "Ports": {"80/tcp": [{"HostPort": "8080"}]}
                    },
                    "Config": {
                        "Env": ["DEBUG=true", "PORT=80"]
                    }
                }
            ),
            Mock(
                id="def456", 
                name="test-container-2",
                image=Mock(tags=["postgres:15"]),
                attrs={
                    "NetworkSettings": {"Ports": {}},
                    "Config": {"Env": ["POSTGRES_DB=test"]}
                }
            )
        ]

        with patch('src.snapshots.get_docker_client_sync') as mock_get_client:
            mock_client = Mock()
            mock_client.containers.list.return_value = mock_containers
            mock_get_client.return_value = mock_client

            result = self.snapshot_manager.snapshot_env("test-snapshot")

            assert result["snapshot_name"] == "test-snapshot"
            assert result["container_count"] == 2
            assert result["status"] == "created"
            assert len(result["containers"]) == 2

    def test_snapshot_env_duplicate_name(self):
        """Test error when snapshot name already exists."""
        # Add existing snapshot
        self.snapshot_manager._snapshots["existing"] = {}

        with pytest.raises(ValueError, match="Snapshot 'existing' already exists"):
            self.snapshot_manager.snapshot_env("existing")

    def test_restore_env_success(self):
        """Test successful environment restoration."""
        # Mock snapshot data
        self.snapshot_manager._snapshots["test-snapshot"] = {
            "containers": [
                {
                    "name": "web-server",
                    "image": "nginx:latest", 
                    "ports": {"80/tcp": [{"HostPort": "8080"}]},
                    "env_vars": {"DEBUG": "true"},
                    "volumes": [],
                    "labels": {},
                    "restart_policy": {},
                    "network_mode": "bridge",
                    "id": "original123"
                }
            ]
        }

        with patch('src.snapshots.get_docker_client_sync') as mock_get_client:
            mock_client = Mock()
            mock_container = Mock()
            mock_container.short_id = "new123"
            mock_client.containers.run.return_value = mock_container
            mock_get_client.return_value = mock_client

            result = self.snapshot_manager.restore_env("test-snapshot")

            assert result["snapshot_name"] == "test-snapshot"
            assert result["container_count"] == 1
            assert result["status"] == "restored"
            assert len(result["restored_containers"]) == 1
            assert result["restored_containers"][0]["name"] == "web-server"

    def test_restore_env_nonexistent(self):
        """Test error when restoring non-existent snapshot."""
        with pytest.raises(ValueError, match="Snapshot 'nonexistent' not found"):
            self.snapshot_manager.restore_env("nonexistent")

    def test_list_snapshots_empty(self):
        """Test listing snapshots when none exist."""
        result = self.snapshot_manager.list_snapshots()
        assert result == []

    def test_list_snapshots_with_data(self):
        """Test listing snapshots with existing data."""
        # Add test snapshots
        self.snapshot_manager._snapshots["snapshot1"] = {
            "created_at": 1234567890.0,
            "containers": ["container1", "container2"]
        }
        self.snapshot_manager._snapshots["snapshot2"] = {
            "created_at": 1234567891.0,
            "containers": ["container3"]
        }

        result = self.snapshot_manager.list_snapshots()

        assert len(result) == 2
        assert result[0]["name"] == "snapshot1"
        assert result[0]["container_count"] == 2
        assert result[1]["name"] == "snapshot2"
        assert result[1]["container_count"] == 1

    def test_delete_snapshot_success(self):
        """Test successful snapshot deletion."""
        # Add test snapshot
        self.snapshot_manager._snapshots["test-snapshot"] = {}

        result = self.snapshot_manager.delete_snapshot("test-snapshot")

        assert result["snapshot_name"] == "test-snapshot"
        assert result["status"] == "deleted"
        assert "test-snapshot" not in self.snapshot_manager._snapshots

    def test_delete_snapshot_nonexistent(self):
        """Test error when deleting non-existent snapshot."""
        with pytest.raises(ValueError, match="Snapshot 'nonexistent' not found"):
            self.snapshot_manager.delete_snapshot("nonexistent")
