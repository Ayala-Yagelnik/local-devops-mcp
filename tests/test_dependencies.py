# tests/test_dependencies.py
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from src.dependencies import DependencyManager
from src.docker_client import get_docker_client

class TestDependencyManager:
    def setup_method(self):
        """Setup test fixture."""
        self.dependency_manager = DependencyManager()
    
    def test_define_dependency(self):
        """Test dependency definition."""
        result = self.dependency_manager.define_dependency(
            "web-app",
            "database",
            {"type": "tcp", "host": "database", "port": 5432}
        )
        
        assert result["service"] == "web-app"
        assert result["depends_on"] == "database"
        assert result["condition_type"] == "tcp"
        assert result["status"] == "defined"
    
    def test_get_dependency_status_success(self):
        """Test getting dependency status for defined dependency."""
        # First define a dependency
        self.dependency_manager.define_dependency(
            "web-app",
            "database", 
            {"type": "tcp", "host": "database", "port": 5432}
        )
        
        with patch('src.dependencies.get_container_by_name') as mock_get_container:
            mock_container = Mock()
            mock_get_container.return_value = mock_container
            
            result = self.dependency_manager.get_dependency_status("web-app")
            
            assert result["service"] == "web-app"
            assert result["depends_on"] == "database"
            assert result["container_running"] is True
    
    def test_get_dependency_status_not_defined(self):
        """Test getting dependency status for undefined dependency."""
        result = self.dependency_manager.get_dependency_status("nonexistent")
        
        assert "error" in result
        assert "No dependencies defined for nonexistent" in result["error"]
    
    def test_sort_services_by_dependencies(self):
        """Test sorting services by dependencies."""
        services = [
            {"name": "web-app", "depends_on": "database", "image": "web:latest"},
            {"name": "database", "image": "postgres:15"},
            {"name": "api", "depends_on": "database", "image": "api:latest"}
        ]
        
        sorted_services = self.dependency_manager.sort_services_by_dependencies(services)
        
        # Database should come first (no dependencies)
        assert sorted_services[0]["name"] == "database"
        # Web-app and API should come after database
        assert sorted_services[1]["name"] in ["web-app", "api"]
        assert sorted_services[2]["name"] in ["web-app", "api"]
    
    def test_sort_services_circular_dependency(self):
        """Test circular dependency detection."""
        services = [
            {"name": "service-a", "depends_on": "service-b", "image": "a:latest"},
            {"name": "service-b", "depends_on": "service-a", "image": "b:latest"}
        ]
        
        with pytest.raises(RuntimeError, match="Circular dependency"):
            self.dependency_manager.sort_services_by_dependencies(services)
    
    @pytest.mark.asyncio
    async def test_wait_for_condition_tcp_success(self):
        """Test successful TCP condition waiting."""
        with patch.object(self.dependency_manager, '_check_tcp_port_async') as mock_check:
            mock_check.return_value = True
            
            result = await self.dependency_manager.wait_for_condition_async(
                {"type": "tcp", "host": "localhost", "port": 8080},
                timeout=5
            )
            
            assert result is True
            mock_check.assert_called_with("localhost", 8080)
    
    @pytest.mark.asyncio
    async def test_wait_for_condition_http_success(self):
        """Test successful HTTP condition waiting."""
        with patch.object(self.dependency_manager, '_check_http_endpoint_async') as mock_check:
            mock_check.return_value = True
            
            result = await self.dependency_manager.wait_for_condition_async(
                {"type": "http", "url": "http://localhost:8080/health"},
                timeout=5
            )
            
            assert result is True
            mock_check.assert_called_with("http://localhost:8080/health")
    
    @pytest.mark.asyncio
    async def test_wait_for_condition_log_success(self):
        """Test successful log pattern condition waiting."""
        with patch.object(self.dependency_manager, '_check_log_pattern_async') as mock_check:
            mock_check.return_value = True
            
            result = await self.dependency_manager.wait_for_condition_async(
                {"type": "log", "pattern": "ready", "container_id": "abc123"},
                timeout=5
            )
            
            assert result is True
            mock_check.assert_called_with("abc123", "ready")
    
    @pytest.mark.asyncio
    async def test_wait_for_condition_timeout(self):
        """Test condition waiting timeout."""
        with patch.object(self.dependency_manager, '_check_tcp_port_async') as mock_check:
            mock_check.return_value = False
            
            result = await self.dependency_manager.wait_for_condition_async(
                {"type": "tcp", "host": "localhost", "port": 8080},
                timeout=1  # Short timeout for test
            )
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_check_tcp_port_async_success(self):
        """Test async TCP port check success."""
        with patch('socket.socket') as mock_socket:
            mock_sock = Mock()
            mock_sock.connect_ex.return_value = 0  # Success
            mock_socket.return_value = mock_sock
            
            result = await self.dependency_manager._check_tcp_port_async("localhost", 8080)
            
            assert result is True
            mock_sock.connect_ex.assert_called_with(("localhost", 8080))
            mock_sock.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_check_tcp_port_async_failure(self):
        """Test async TCP port check failure."""
        with patch('socket.socket') as mock_socket:
            mock_sock = Mock()
            mock_sock.connect_ex.return_value = 1  # Connection refused
            mock_socket.return_value = mock_sock
            
            result = await self.dependency_manager._check_tcp_port_async("localhost", 8080)
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_check_http_endpoint_async_success(self):
        """Test async HTTP endpoint check success."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_response = Mock()
            mock_response.status = 200
            mock_urlopen.return_value.__enter__.return_value = mock_response
            
            result = await self.dependency_manager._check_http_endpoint_async("http://localhost:8080/health")
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_check_http_endpoint_async_failure(self):
        """Test async HTTP endpoint check failure."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            import urllib.error
            mock_urlopen.side_effect = urllib.error.HTTPError("url", 500, "Internal Server Error", {}, None)
            
            result = await self.dependency_manager._check_http_endpoint_async("http://localhost:8080/health")
            
            assert result is False
    
    def test_check_tcp_port_sync(self):
        """Test synchronous TCP port check."""
        with patch('socket.socket') as mock_socket:
            mock_sock = Mock()
            mock_sock.connect_ex.return_value = 0
            mock_socket.return_value = mock_sock
            
            result = self.dependency_manager._check_tcp_port("localhost", 8080)
            
            assert result is True
    
    def test_check_http_endpoint_sync(self):
        """Test synchronous HTTP endpoint check."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_response = Mock()
            mock_response.status = 200
            mock_urlopen.return_value.__enter__.return_value = mock_response
            
            result = self.dependency_manager._check_http_endpoint("http://localhost:8080/health")
            
            assert result is True
    
    def test_check_log_pattern_sync(self):
        """Test synchronous log pattern check."""
        with patch('src.dependencies.get_docker_client') as mock_get_client:
            mock_client = Mock()
            mock_container = Mock()
            mock_container.logs.return_value = b"Server is ready to accept connections"
            mock_client.containers.get.return_value = mock_container
            mock_get_client.return_value = mock_client
            
            result = self.dependency_manager._check_log_pattern("abc123", "ready")
            
            assert result is True
