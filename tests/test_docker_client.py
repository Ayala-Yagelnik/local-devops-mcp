# tests/test_docker_client.py
import pytest
import asyncio
from unittest.mock import Mock, patch
from src.docker_client import get_docker_client, get_docker_client_sync, pull_image_if_needed, pull_image_if_needed_sync, get_container_by_name, get_container_by_name_sync
from docker.errors import DockerException, ImageNotFound

class TestDockerClient:
    def test_get_docker_client_success(self):
        """Test successful Docker client creation."""
        with patch('docker.from_env') as mock_docker:
            mock_client = Mock()
            mock_client.ping.return_value = True
            mock_docker.return_value = mock_client
            
            client = get_docker_client_sync()
            assert client is not None
            mock_client.ping.assert_called_once()
    
    def test_get_docker_client_failure(self):
        """Test Docker client creation failure."""
        with patch('docker.from_env') as mock_docker:
            mock_docker.side_effect = DockerException("Connection failed")
            
            with pytest.raises(RuntimeError, match="Docker is not running"):
                get_docker_client_sync()
    
    @pytest.mark.asyncio
    async def test_get_docker_client_async_success(self):
        """Test successful async Docker client creation."""
        with patch('docker.from_env') as mock_docker:
            mock_client = Mock()
            mock_client.ping.return_value = True
            mock_docker.return_value = mock_client
            
            client = await get_docker_client()
            assert client is not None
            mock_client.ping.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_docker_client_async_failure(self):
        """Test async Docker client creation failure."""
        with patch('docker.from_env') as mock_docker:
            mock_docker.side_effect = DockerException("Connection failed")
            
            with pytest.raises(RuntimeError, match="Docker is not running"):
                await get_docker_client()
    
    def test_pull_image_if_needed_sync_exists(self):
        """Test pulling image when it already exists."""
        mock_client = Mock()
        mock_client.images.get.return_value = Mock()
        
        result = pull_image_if_needed_sync(mock_client, "nginx:latest")
        
        assert result is False
        mock_client.images.get.assert_called_once_with("nginx:latest")
        mock_client.images.pull.assert_not_called()
    
    def test_pull_image_if_needed_sync_not_exists(self):
        """Test pulling image when it doesn't exist."""
        mock_client = Mock()
        mock_client.images.get.side_effect = ImageNotFound("Image not found")
        mock_client.images.pull.return_value = Mock()
        
        result = pull_image_if_needed_sync(mock_client, "nginx:latest")
        
        assert result is True
        mock_client.images.get.assert_called_once_with("nginx:latest")
        mock_client.images.pull.assert_called_once_with("nginx:latest")
    
    @pytest.mark.asyncio
    async def test_pull_image_if_needed_async_exists(self):
        """Test async pulling image when it already exists."""
        mock_client = Mock()
        mock_client.images.get.return_value = Mock()
        
        result = await pull_image_if_needed(mock_client, "nginx:latest")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_pull_image_if_needed_async_not_exists(self):
        """Test async pulling image when it doesn't exist."""
        mock_client = Mock()
        mock_client.images.get.side_effect = ImageNotFound("Image not found")
        mock_client.images.pull.return_value = Mock()
        
        result = await pull_image_if_needed(mock_client, "nginx:latest")
        
        assert result is True
    
    def test_get_container_by_name_sync_found(self):
        """Test finding container by name when it exists."""
        mock_client = Mock()
        mock_container = Mock()
        mock_container.name = "test-web-server"
        mock_client.containers.list.return_value = [mock_container]
        
        result = get_container_by_name_sync(mock_client, "web")
        
        assert result is mock_container
        mock_client.containers.list.assert_called_once()
    
    def test_get_container_by_name_sync_not_found(self):
        """Test finding container by name when it doesn't exist."""
        mock_client = Mock()
        mock_container = Mock()
        mock_container.name = "other-container"
        mock_client.containers.list.return_value = [mock_container]
        
        result = get_container_by_name_sync(mock_client, "web")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_container_by_name_async_found(self):
        """Test async finding container by name when it exists."""
        mock_client = Mock()
        mock_container = Mock()
        mock_container.name = "test-web-server"
        mock_client.containers.list.return_value = [mock_container]
        
        result = await get_container_by_name(mock_client, "web")
        
        assert result is mock_container
    
    @pytest.mark.asyncio
    async def test_get_container_by_name_async_not_found(self):
        """Test async finding container by name when it doesn't exist."""
        mock_client = Mock()
        mock_container = Mock()
        mock_container.name = "other-container"
        mock_client.containers.list.return_value = [mock_container]
        
        result = await get_container_by_name(mock_client, "web")
        
        assert result is None
    
    def test_get_container_by_name_sync_exception(self):
        """Test container lookup with Docker exception."""
        mock_client = Mock()
        mock_client.containers.list.side_effect = DockerException("Connection failed")
        
        result = get_container_by_name_sync(mock_client, "web")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_container_by_name_async_exception(self):
        """Test async container lookup with Docker exception."""
        mock_client = Mock()
        mock_client.containers.list.side_effect = DockerException("Connection failed")
        
        result = await get_container_by_name(mock_client, "web")
        
        assert result is None