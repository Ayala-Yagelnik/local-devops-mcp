# tests/conftest.py
import pytest
import asyncio
from unittest.mock import Mock

@pytest.fixture
def mock_docker_client():
    """Mock Docker client fixture."""
    client = Mock()
    client.ping.return_value = True
    return client

@pytest.fixture
def mock_container():
    """Mock Docker container fixture."""
    container = Mock()
    container.id = "abc123def456789"
    container.short_id = "abc123def456"
    container.name = "test-container"
    container.status = "running"
    container.image.tags = ["test:latest"]
    container.attrs = {
        "NetworkSettings": {
            "Ports": {
                "80/tcp": [{"HostPort": "8080"}]
            }
        }
    }
    return container

@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_health_check_data():
    """Mock health check data fixture."""
    return {
        "endpoint": "http://localhost:8080/health",
        "interval": 30,
        "last_check": None,
        "status": "unknown",
        "created_at": 1705123456.789
    }

@pytest.fixture
def mock_dependency_data():
    """Mock dependency data fixture."""
    return {
        "depends_on": "database",
        "wait_condition": {
            "type": "tcp",
            "host": "database",
            "port": 5432
        },
        "created_at": 1705123456.789
    }
