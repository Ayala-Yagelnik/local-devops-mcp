"""Tests for watcher module."""

import pytest
import tempfile
import time
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from src.watcher import FileWatcher


class TestFileWatcher:
    """Test cases for FileWatcher class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.watcher = FileWatcher()

    def teardown_method(self):
        """Clean up after tests."""
        # Stop all watchers
        for project_path in list(self.watcher._watchers.keys()):
            try:
                self.watcher.stop_watching(project_path)
            except:
                pass

    @patch('src.watcher.watchdog.observers.Observer')
    @patch('src.watcher.watchdog.events.FileSystemEventHandler')
    def test_watch_and_redeploy_success(self, mock_handler, mock_observer):
        """Test successful file watching setup."""
        mock_obs = Mock()
        mock_observer.return_value = mock_obs

        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.watcher.watch_and_redeploy(temp_dir, ['.py', '.js'])

            assert result["project_path"] == temp_dir
            assert result["patterns"] == ['.py', '.js']
            assert result["status"] == "watching_started"
            assert temp_dir in self.watcher._watchers
            mock_obs.start.assert_called_once()

    def test_watch_and_redeploy_default_patterns(self):
        """Test file watching with default patterns."""
        with patch('src.watcher.watchdog.observers.Observer') as mock_observer:
            mock_obs = Mock()
            mock_observer.return_value = mock_obs

            with tempfile.TemporaryDirectory() as temp_dir:
                self.watcher.watch_and_redeploy(temp_dir)

                # Should use default patterns
                call_args = mock_observer.return_value.schedule.call_args
                handler = call_args[0][0]
                assert handler.patterns == ['.py', '.js', '.Dockerfile', 'docker-compose.yml']

    def test_stop_watching_success(self):
        """Test successful stopping of file watcher."""
        with patch('src.watcher.watchdog.observers.Observer') as mock_observer:
            mock_obs = Mock()
            mock_observer.return_value = mock_obs

            with tempfile.TemporaryDirectory() as temp_dir:
                # Start watching first
                self.watcher.watch_and_redeploy(temp_dir)
                
                # Stop watching
                result = self.watcher.stop_watching(temp_dir)

                assert result["project_path"] == temp_dir
                assert result["status"] == "watching_stopped"
                assert temp_dir not in self.watcher._watchers
                mock_obs.stop.assert_called_once()
                mock_obs.join.assert_called_once_with(timeout=5)

    def test_stop_watching_nonexistent(self):
        """Test stopping non-existent watcher."""
        result = self.watcher.stop_watching("/nonexistent/path")
        
        assert "error" in result
        assert "No watcher found" in result["error"]

    def test_list_watchers_empty(self):
        """Test listing watchers when none are active."""
        result = self.watcher.list_watchers()
        assert result["watchers"] == []

    def test_list_watchers_with_active(self):
        """Test listing active watchers."""
        with patch('src.watcher.watchdog.observers.Observer') as mock_observer:
            mock_obs = Mock()
            mock_obs.return_value = mock_obs

            with tempfile.TemporaryDirectory() as temp_dir1, \
                 tempfile.TemporaryDirectory() as temp_dir2:
                
                # Start two watchers
                self.watcher.watch_and_redeploy(temp_dir1, ['.py'])
                self.watcher.watch_and_redeploy(temp_dir2, ['.js'])

                result = self.watcher.list_watchers()

                assert len(result["watchers"]) == 2
                assert result["watchers"][0]["project_path"] == temp_dir1
                assert result["watchers"][0]["patterns"] == ['.py']
                assert result["watchers"][1]["project_path"] == temp_dir2
                assert result["watchers"][1]["patterns"] == ['.js']

    @patch('src.watcher.get_docker_client')
    @patch('src.watcher.get_container_by_name')
    def test_smart_rebuild_success(self, mock_get_container, mock_get_client):
        """Test successful smart rebuild."""
        # Mock container
        mock_container = Mock()
        mock_container.image.tags = ["my-app:latest"]
        mock_container.attrs = {
            "NetworkSettings": {"Ports": {"8000/tcp": [{"HostPort": "8000"}]}},
            "Config": {"Env": ["DEBUG=true"]}
        }
        mock_get_container.return_value = mock_container

        # Mock Docker client
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        with patch.object(self.watcher, '_build_image_if_needed') as mock_build, \
             patch.object(self.watcher, '_deploy_service') as mock_deploy:
            
            mock_deploy.return_value = {"container_id": "new123", "status": "running"}

            result = self.watcher.smart_rebuild("my-app")

            assert result["container_id"] == "new123"
            assert result["status"] == "running"
            mock_container.stop.assert_called_once()
            mock_container.remove.assert_called_once()

    @patch('src.watcher.get_container_by_name')
    def test_smart_rebuild_container_not_found(self, mock_get_container):
        """Test smart rebuild when container not found."""
        mock_get_container.return_value = None

        result = self.watcher.smart_rebuild("nonexistent")

        assert "error" in result
        assert "Container nonexistent not found" in result["error"]

    def test_polling_watcher_fallback(self):
        """Test polling watcher fallback when watchdog not available."""
        with patch('src.watcher.watchdog.observers.Observer', side_effect=ImportError):
            with tempfile.TemporaryDirectory() as temp_dir:
                result = self.watcher.watch_and_redeploy(temp_dir, ['.py'])

                assert result["status"] == "watching_started"
                assert temp_dir in self.watcher._watchers

    def test_polling_watcher_file_change_detection(self):
        """Test that polling watcher detects file changes."""
        with patch('src.watcher.watchdog.observers.Observer', side_effect=ImportError):
            with tempfile.TemporaryDirectory() as temp_dir:
                callback = Mock()
                
                # Start polling watcher
                watcher = self.watcher._start_polling_watcher(temp_dir, ['.py'], callback)
                
                # Create a test file
                test_file = Path(temp_dir) / "test.py"
                test_file.write_text("initial content")
                
                # Wait a bit then modify file
                time.sleep(0.1)
                test_file.write_text("modified content")
                
                # Trigger change detection
                watcher._check_changes()
                
                # Stop watcher
                watcher.stop()
                watcher.join()

    @patch('src.watcher.get_docker_client')
    def test_build_image_if_needed_success(self, mock_get_client):
        """Test successful Docker image build."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a Dockerfile
            dockerfile = Path(temp_dir) / "Dockerfile"
            dockerfile.write_text("FROM nginx:latest")

            result = self.watcher._build_image_if_needed(temp_dir, "test-image")

            assert result is True
            mock_client.images.build.assert_called_once_with(
                path=temp_dir, tag="test-image", rm=True
            )

    def test_build_image_if_needed_no_dockerfile(self):
        """Test build when no Dockerfile exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.watcher._build_image_if_needed(temp_dir, "test-image")
            assert result is False

    @patch('src.watcher.get_docker_client')
    def test_build_image_if_needed_build_error(self, mock_get_client):
        """Test build when Docker build fails."""
        mock_client = Mock()
        mock_client.images.build.side_effect = Exception("Build failed")
        mock_get_client.return_value = mock_client

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a Dockerfile
            dockerfile = Path(temp_dir) / "Dockerfile"
            dockerfile.write_text("FROM invalid:latest")

            result = self.watcher._build_image_if_needed(temp_dir, "test-image")

            assert result is False

    def test_parse_ports(self):
        """Test port parsing from Docker format."""
        ports_dict = {
            "80/tcp": [{"HostPort": "8080"}],
            "443/tcp": [{"HostPort": "8443"}]
        }

        result = self.watcher._parse_ports(ports_dict)

        assert result == {"80/tcp": "8080", "443/tcp": "8443"}

    def test_parse_env_vars(self):
        """Test environment variable parsing."""
        env_list = ["DEBUG=true", "PORT=80", "DATABASE_URL=postgres://localhost/db"]

        result = self.watcher._parse_env_vars(env_list)

        expected = {
            "DEBUG": "true",
            "PORT": "80", 
            "DATABASE_URL": "postgres://localhost/db"
        }
        assert result == expected
