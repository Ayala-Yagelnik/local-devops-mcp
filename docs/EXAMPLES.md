# Usage Examples

This document provides practical examples of using the Local DevOps MCP server.

## Basic Docker Operations

### Deploy a Simple Web Server

```python
# Deploy nginx on port 8080
deploy_service(
    image="nginx:latest",
    ports={"80": 8080}
)

# Deploy with environment variables
deploy_service(
    image="postgres:15",
    ports={"5432": 5432},
    env_vars={
        "POSTGRES_DB": "myapp",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "password"
    }
)
```

### Monitor and Manage Containers

```python
# List all running containers
containers = list_running_services()

# Get logs from a specific container
logs = get_service_logs(container_id="abc123", tail=100)

# Stop a container
stop_service(container_id="abc123")
```

## Advanced Dependency Management

### Web Application Stack with Database

```python
# Define dependencies
define_dependency(
    service_name="webapp",
    depends_on="database",
    wait_condition={
        "type": "tcp",
        "host": "database",
        "port": 5432
    }
)

define_dependency(
    service_name="api",
    depends_on="database",
    wait_condition={
        "type": "log",
        "pattern": "database system is ready to accept connections"
    }
)

# Deploy entire stack
deploy_group([
    {
        "name": "database",
        "image": "postgres:15",
        "ports": {"5432": 5432},
        "env_vars": {
            "POSTGRES_DB": "myapp",
            "POSTGRES_USER": "user",
            "POSTGRES_PASSWORD": "password"
        }
    },
    {
        "name": "redis",
        "image": "redis:7",
        "ports": {"6379": 6379}
    },
    {
        "name": "api",
        "image": "my-api:latest",
        "ports": {"8080": 8080},
        "env_vars": {
            "DATABASE_URL": "postgresql://user:password@database:5432/myapp",
            "REDIS_URL": "redis://redis:6379"
        },
        "depends_on": "database",
        "wait_condition": {
            "type": "tcp",
            "host": "database",
            "port": 5432
        }
    },
    {
        "name": "webapp",
        "image": "my-frontend:latest",
        "ports": {"3000": 3000},
        "env_vars": {
            "API_URL": "http://api:8080"
        },
        "depends_on": "api",
        "wait_condition": {
            "type": "http",
            "url": "http://api:8080/health"
        }
    }
])
```

### Microservices Architecture

```python
# Deploy microservices with complex dependencies
deploy_group([
    {
        "name": "user-service",
        "image": "user-service:latest",
        "ports": {"8001": 8001},
        "depends_on": "postgres",
        "wait_condition": {"type": "tcp", "host": "postgres", "port": 5432}
    },
    {
        "name": "order-service",
        "image": "order-service:latest",
        "ports": {"8002": 8002},
        "depends_on": "postgres",
        "wait_condition": {"type": "tcp", "host": "postgres", "port": 5432}
    },
    {
        "name": "notification-service",
        "image": "notification-service:latest",
        "ports": {"8003": 8003},
        "depends_on": "redis",
        "wait_condition": {"type": "tcp", "host": "redis", "port": 6379}
    },
    {
        "name": "api-gateway",
        "image": "api-gateway:latest",
        "ports": {"8000": 8000},
        "env_vars": {
            "USER_SERVICE_URL": "http://user-service:8001",
            "ORDER_SERVICE_URL": "http://order-service:8002",
            "NOTIFICATION_SERVICE_URL": "http://notification-service:8003"
        },
        "depends_on": "user-service",
        "wait_condition": {"type": "http", "url": "http://user-service:8001/health"}
    }
])
```

## Template Management

### Create Reusable Templates

```python
# Create a web server template
create_template(
    name="web-server",
    image="nginx:latest",
    ports={"80": 8080},
    env_vars={"ENV": "production"},
    health_check={
        "endpoint": "http://localhost:8080",
        "interval": 30
    }
)

# Create a database template
create_template(
    name="postgres-db",
    image="postgres:15",
    ports={"5432": 5432},
    env_vars={
        "POSTGRES_DB": "myapp",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "password"
    }
)
```

### Deploy from Templates

```python
# Deploy from template with overrides
run_from_template(
    template_name="web-server",
    overrides={
        "ports": {"80": 9090},
        "env_vars": {"ENV": "staging"}
    }
)

# Deploy multiple instances from same template
run_from_template(
    template_name="postgres-db",
    overrides={
        "env_vars": {
            "POSTGRES_DB": "test_db",
            "POSTGRES_USER": "test_user"
        }
    }
)
```

## Health Monitoring

### Set Up Health Checks

```python
# Add health check to a container
add_health_check(
    container_id="abc123",
    endpoint="http://localhost:8080/health",
    interval=30
)

# Enable auto-restart on failure
auto_restart_on_failure(container_id="abc123")

# Check health status
health = get_service_health(container_id="abc123")
print(f"Service status: {health['status']}")
```

### Monitor Multiple Services

```python
# Deploy services with health monitoring
services = deploy_group([
    {
        "name": "api",
        "image": "my-api:latest",
        "ports": {"8080": 8080}
    },
    {
        "name": "worker",
        "image": "my-worker:latest",
        "ports": {"8081": 8081}
    }
])

# Add health checks to all services
for service_name, container_id in services["deployed_services"].items():
    add_health_check(
        container_id=container_id,
        endpoint=f"http://localhost:{8080 if service_name == 'api' else 8081}/health",
        interval=30
    )
    auto_restart_on_failure(container_id)
```

## Environment Snapshots

### Save and Restore Development Environments

```python
# Create snapshot of current setup
snapshot_env(env_name="development-setup")

# Continue working...
# Make changes, test new features, etc.

# Restore to previous state
restore_env(snapshot_name="development-setup")
```

### Environment Management Workflow

```python
# Save clean state
snapshot_env(env_name="clean-state")

# Deploy experimental setup
deploy_group([
    {"name": "experimental-db", "image": "postgres:15", "ports": {"5432": 5433}},
    {"name": "experimental-api", "image": "my-api:experimental", "ports": {"8080": 8081}}
])

# Test experimental features
# ... run tests, validate behavior ...

# Restore clean state
restore_env(snapshot_name="clean-state")

# List all available snapshots
snapshots = list_snapshots()
print(f"Available snapshots: {[s['name'] for s in snapshots['snapshots']]}")
```

## Auto-Deploy with File Watching

### Development Workflow

```python
# Start watching for changes
watch_and_redeploy(
    project_path="./my-web-app",
    patterns=[".py", ".js", ".Dockerfile", "requirements.txt"]
)

# Now make changes to your code files
# The system will automatically rebuild and redeploy when files change

# Stop watching when done
stop_watching(project_path="./my-web-app")
```

### Multi-Project Setup

```python
# Watch multiple projects
projects = [
    "./frontend",
    "./backend-api",
    "./worker-service"
]

for project in projects:
    watch_and_redeploy(
        project_path=project,
        patterns=[".py", ".js", ".Dockerfile"]
    )
```

### Smart Rebuild

```python
# Rebuild only what changed
smart_rebuild(service_name="api")

# This will:
# 1. Stop the container
# 2. Rebuild the image if Dockerfile changed
# 3. Redeploy with same configuration
# 4. Respect any dependencies
```

## Complete Development Workflow

### Setting Up a New Project

```python
# 1. Create templates for common services
create_template(
    name="web-service",
    image="nginx:latest",
    ports={"80": 8080}
)

create_template(
    name="api-service",
    image="python:3.11-slim",
    ports={"8000": 8000},
    env_vars={"PYTHONUNBUFFERED": "1"}
)

# 2. Deploy initial stack
deploy_group([
    {
        "name": "database",
        "image": "postgres:15",
        "ports": {"5432": 5432}
    },
    {
        "name": "api",
        "image": "./backend",
        "ports": {"8000": 8000},
        "depends_on": "database",
        "wait_condition": {"type": "tcp", "host": "database", "port": 5432}
    },
    {
        "name": "frontend",
        "image": "./frontend",
        "ports": {"3000": 3000},
        "depends_on": "api",
        "wait_condition": {"type": "http", "url": "http://api:8000/health"}
    }
])

# 3. Set up health monitoring
containers = list_running_services()
for container in containers:
    if "api" in container["id"] or "frontend" in container["id"]:
        add_health_check(
            container_id=container["id"],
            endpoint=f"http://localhost:{container['ports'].get('8000/tcp', [{}])[0].get('HostPort', '8000')}/health",
            interval=30
        )

# 4. Enable file watching for development
watch_and_redeploy(project_path="./backend")
watch_and_redeploy(project_path="./frontend")

# 5. Save baseline snapshot
snapshot_env(env_name="initial-setup")
```

### Testing Workflow

```python
# Save current state
snapshot_env(env_name="before-tests")

# Deploy test configuration
deploy_group([
    {"name": "test-db", "image": "postgres:15", "ports": {"5432": 5434}},
    {"name": "test-api", "image": "my-api:test", "ports": {"8000": 8001}}
])

# Run tests (external process)
# ... test execution ...

# Restore original state
restore_env(snapshot_name="before-tests")
```

## Troubleshooting Examples

### Debug Dependency Issues

```python
# Check dependency status
status = get_dependency_status(service_name="api")
print(f"Dependency status: {status}")

# Check if dependency is met
if not status["container_running"]:
    print("Dependency container is not running")
    
# Check wait condition details
condition = status["condition"]
print(f"Wait condition type: {condition['type']}")

# List all containers to see what's running
containers = list_running_services()
print(f"Running containers: {[c['id'] for c in containers]}")
```

### Health Check Debugging

```python
# Check health status
health = get_service_health(container_id="abc123")
print(f"Health status: {health['status']}")

# Check last check time
if health["last_check"]:
    import time
    last_check = time.ctime(health["last_check"])
    print(f"Last health check: {last_check}")

# Test endpoint manually
import requests
try:
    response = requests.get(health["endpoint"], timeout=5)
    print(f"Manual check result: {response.status_code}")
except Exception as e:
    print(f"Manual check failed: {e}")
```

These examples demonstrate common workflows and patterns for using the Local DevOps MCP server effectively.
