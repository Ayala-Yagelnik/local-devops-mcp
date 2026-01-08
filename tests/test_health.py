# tests/test_health.py
import pytest
import time
from unittest.mock import Mock, patch
from src.health import HealthMonitor

class TestHealthMonitor:
    def setup_method(self):
        """Setup test fixture."""
        self.health_monitor = HealthMonitor()
    
    def test_add_health_check(self):
        """Test adding health check to container."""
        result = self.health_monitor.add_health_check(
            "abc123def456",
            "http://localhost:8080/health",
            interval=30
        )
        
        assert result["container_id"] == "abc123def456"
        assert result["endpoint"] == "http://localhost:8080/health"
        assert result["interval"] == 30
        assert result["status"] == "health_check_added"
        
        # Verify health check is stored
        assert "abc123def456" in self.health_monitor._health_checks
        health_info = self.health_monitor._health_checks["abc123def456"]
        assert health_info["endpoint"] == "http://localhost:8080/health"
        assert health_info["interval"] == 30
    
    def test_get_service_health_success(self):
        """Test getting health status for monitored container."""
        # First add health check
        self.health_monitor.add_health_check(
            "abc123def456",
            "http://localhost:8080/health",
            interval=30
        )
        
        with patch.object(self.health_monitor, '_check_http_endpoint') as mock_check:
            mock_check.return_value = True
            
            result = self.health_monitor.get_service_health("abc123def456")
            
            assert result["container_id"] == "abc123def456"
            assert result["endpoint"] == "http://localhost:8080/health"
            assert result["status"] == "healthy"
            assert result["interval"] == 30
            assert "last_check" in result
    
    def test_get_service_health_not_monitored(self):
        """Test getting health status for unmonitored container."""
        result = self.health_monitor.get_service_health("nonexistent")
        
        assert "error" in result
        assert "No health check for container nonexistent" in result["error"]
    
    def test_enable_auto_restart(self):
        """Test enabling auto-restart for container."""
        # First add health check
        self.health_monitor.add_health_check(
            "abc123def456",
            "http://localhost:8080/health",
            interval=30
        )
        
        with patch('threading.Thread') as mock_thread:
            mock_thread_instance = Mock()
            mock_thread.return_value = mock_thread_instance
            
            result = self.health_monitor.enable_auto_restart("abc123def456")
            
            assert result["container_id"] == "abc123def456"
            assert result["auto_restart"] == "enabled"
            assert result["status"] == "monitoring_started"
            
            # Verify thread was started
            mock_thread.assert_called_once()
            mock_thread_instance.start.assert_called_once()
            
            # Verify monitoring thread is stored
            assert "abc123def456" in self.health_monitor._monitoring_threads
    
    def test_enable_auto_restart_no_health_check(self):
        """Test enabling auto-restart without health check."""
        result = self.health_monitor.enable_auto_restart("nonexistent")
        
        assert "error" in result
        assert "No health check for container nonexistent" in result["error"]
    
    def test_disable_auto_restart(self):
        """Test disabling auto-restart for container."""
        # First enable auto-restart
        self.health_monitor.add_health_check(
            "abc123def456",
            "http://localhost:8080/health",
            interval=30
        )
        
        with patch('threading.Thread') as mock_thread:
            mock_thread_instance = Mock()
            mock_thread.return_value = mock_thread_instance
            self.health_monitor.enable_auto_restart("abc123def456")
            
            # Now disable
            result = self.health_monitor.disable_auto_restart("abc123def456")
            
            assert result["container_id"] == "abc123def456"
            assert result["auto_restart"] == "disabled"
            assert result["status"] == "monitoring_stopped"
            
            # Verify monitoring thread is removed
            assert "abc123def456" not in self.health_monitor._monitoring_threads
    
    def test_remove_health_check(self):
        """Test removing health check for container."""
        # First add health check and enable auto-restart
        self.health_monitor.add_health_check(
            "abc123def456",
            "http://localhost:8080/health",
            interval=30
        )
        
        with patch('threading.Thread') as mock_thread:
            mock_thread_instance = Mock()
            mock_thread.return_value = mock_thread_instance
            self.health_monitor.enable_auto_restart("abc123def456")
            
            # Remove health check
            result = self.health_monitor.remove_health_check("abc123def456")
            
            assert result["container_id"] == "abc123def456"
            assert result["status"] == "health_check_removed"
            
            # Verify health check and monitoring are removed
            assert "abc123def456" not in self.health_monitor._health_checks
            assert "abc123def456" not in self.health_monitor._monitoring_threads
    
    def test_remove_health_check_not_monitored(self):
        """Test removing health check for unmonitored container."""
        result = self.health_monitor.remove_health_check("nonexistent")
        
        assert "error" in result
        assert "No health check for container nonexistent" in result["error"]
    
    def test_list_health_checks(self):
        """Test listing all health checks."""
        # Add multiple health checks
        self.health_monitor.add_health_check(
            "container1",
            "http://localhost:8080/health",
            interval=30
        )
        self.health_monitor.add_health_check(
            "container2",
            "http://localhost:8081/health",
            interval=60
        )
        
        # Enable auto-restart for one
        with patch('threading.Thread') as mock_thread:
            mock_thread_instance = Mock()
            mock_thread.return_value = mock_thread_instance
            self.health_monitor.enable_auto_restart("container1")
        
        result = self.health_monitor.list_health_checks()
        
        assert "health_checks" in result
        health_checks = result["health_checks"]
        assert len(health_checks) == 2
        
        # Check first container (with auto-restart)
        container1_check = next(c for c in health_checks if c["container_id"] == "container1")
        assert container1_check["endpoint"] == "http://localhost:8080/health"
        assert container1_check["interval"] == 30
        assert container1_check["auto_restart"] is True
        
        # Check second container (without auto-restart)
        container2_check = next(c for c in health_checks if c["container_id"] == "container2")
        assert container2_check["endpoint"] == "http://localhost:8081/health"
        assert container2_check["interval"] == 60
        assert container2_check["auto_restart"] is False
    
    def test_check_http_endpoint_success(self):
        """Test successful HTTP endpoint check."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_response = Mock()
            mock_response.status = 200
            mock_urlopen.return_value.__enter__.return_value = mock_response
            
            result = self.health_monitor._check_http_endpoint("http://localhost:8080/health")
            
            assert result is True
    
    def test_check_http_endpoint_failure(self):
        """Test HTTP endpoint check failure."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            import urllib.error
            mock_urlopen.side_effect = urllib.error.HTTPError("url", 500, "Internal Server Error", {}, None)
            
            result = self.health_monitor._check_http_endpoint("http://localhost:8080/health")
            
            assert result is False
    
    def test_check_http_endpoint_network_error(self):
        """Test HTTP endpoint check with network error."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            import urllib.error
            mock_urlopen.side_effect = urllib.error.URLError("Network unreachable")
            
            result = self.health_monitor._check_http_endpoint("http://localhost:8080/health")
            
            assert result is False
    
    @patch('time.sleep')
    def test_monitor_and_restart_healthy(self, mock_sleep):
        """Test monitoring loop when container is healthy."""
        # Setup health check
        self.health_monitor.add_health_check(
            "abc123def456",
            "http://localhost:8080/health",
            interval=1  # Short interval for test
        )
        
        with patch.object(self.health_monitor, '_check_http_endpoint') as mock_check:
            # Container stays healthy
            mock_check.return_value = True
            
            # Simulate monitoring loop (run once then exit)
            with patch.object(self.health_monitor, '_monitoring_threads', {"abc123def456": Mock()}):
                # Run one iteration
                self.health_monitor._monitor_and_restart("abc123def456")
                
                # Should not restart container
                mock_check.assert_called_once_with("http://localhost:8080/health")
                mock_sleep.assert_called_once_with(1)
    
    @patch('time.sleep')
    def test_monitor_and_restart_unhealthy(self, mock_sleep):
        """Test monitoring loop when container is unhealthy."""
        # Setup health check
        self.health_monitor.add_health_check(
            "abc123def456",
            "http://localhost:8080/health",
            interval=1  # Short interval for test
        )
        
        with patch.object(self.health_monitor, '_check_http_endpoint') as mock_check:
            with patch('src.health.get_docker_client') as mock_get_client:
                # Container is unhealthy
                mock_check.return_value = False
                
                mock_client = Mock()
                mock_container = Mock()
                mock_client.containers.get.return_value = mock_container
                mock_get_client.return_value = mock_client
                
                # Simulate monitoring loop (run once then exit)
                with patch.object(self.health_monitor, '_monitoring_threads', {"abc123def456": Mock()}):
                    self.health_monitor._monitor_and_restart("abc123def456")
                    
                    # Should restart container
                    mock_container.restart.assert_called_once()
                    mock_sleep.assert_called_once_with(1)
