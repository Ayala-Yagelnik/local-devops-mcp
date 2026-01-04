# API Documentation

This document provides detailed API documentation for all available MCP tools.

## Core Docker Operations

### list_running_services()
Lists all currently active Docker containers.

**Returns:**
```json
[
  {
    "id": "abc123",
    "image": ["nginx:latest"],
    "status": "running",
    "ports": {
      "80/tcp": [
        {"HostIp": "0.0.0.0", "HostPort": "8080"}
      ]
    }
  }
]
```

### deploy_service(image, ports, env_vars)
Pulls (if missing) and runs a Docker container.

**Parameters:**
- `image` (str): Docker image name
- `ports` (dict, optional): Port mapping (container: host)
- `env_vars` (dict, optional): Environment variables

**Returns:**
```json
{
  "container_id": "abc123",
  "status": "running"
}
```

### get_service_logs(container_id, tail)
Retrieves logs from a Docker container.

**Parameters:**
- `container_id` (str): Container ID
- `tail` (int, optional): Number of lines to retrieve (default: 50)

**Returns:** String containing container logs

### stop_service(container_id)
Stops and removes a Docker container.

**Parameters:**
- `container_id` (str): Container ID

**Returns:** Success message string

## Dependency Management

### define_dependency(service_name, depends_on, wait_condition)
Defines a dependency with smart waiting condition.

**Parameters:**
- `service_name` (str): Name of the service that depends on another
- `depends_on` (str): Name of the service to wait for
- `wait_condition` (dict): Wait condition configuration

**Wait Condition Types:**
- **TCP**: `{"type": "tcp", "host": "db", "port": 5432}`
- **HTTP**: `{"type": "http", "url": "http://api:8080/health"}`
- **Log**: `{"type": "log", "pattern": "ready to accept connections"}`

**Returns:**
```json
{
  "service": "api",
  "depends_on": "database",
  "condition_type": "tcp",
  "status": "defined"
}
```

### deploy_group(definitions)
Deploys multiple services respecting dependencies.

**Parameters:**
- `definitions` (list): List of service definitions

**Service Definition Format:**
```json
{
  "name": "api",
  "image": "my-api:latest",
  "ports": {"8080": 8080},
  "env_vars": {"ENV": "production"},
  "depends_on": "database",
  "wait_condition": {
    "type": "tcp",
    "host": "database",
    "port": 5432
  }
}
```

**Returns:**
```json
{
  "deployed_services": {
    "database": "abc123",
    "api": "def456"
  },
  "status": "all_services_running"
}
```

### get_dependency_status(service_name)
Shows dependency status and wait times.

**Parameters:**
- `service_name` (str): Service name to check

**Returns:**
```json
{
  "service": "api",
  "depends_on": "database",
  "condition": {"type": "tcp", "host": "database", "port": 5432},
  "container_running": true,
  "created_at": 1640995200
}
```

## Template Management

### create_template(name, image, ports, env_vars, health_check)
Creates a reusable service template.

**Parameters:**
- `name` (str): Template name
- `image` (str): Docker image name
- `ports` (dict): Port mapping
- `env_vars` (dict, optional): Environment variables
- `health_check` (dict, optional): Health check configuration

**Returns:**
```json
{
  "template_name": "web-server",
  "image": "nginx:latest",
  "ports": {"80": 8080},
  "status": "template_created"
}
```

### run_from_template(template_name, overrides)
Runs a service from a template with optional overrides.

**Parameters:**
- `template_name` (str): Name of template to use
- `overrides` (dict, optional): Override parameters

**Override Format:**
```json
{
  "image": "nginx:1.21",
  "ports": {"80": 9090},
  "env_vars": {"ENV": "staging"}
}
```

**Returns:** Same as `deploy_service()`

### list_templates()
Lists all available templates.

**Returns:**
```json
{
  "templates": [
    {
      "name": "web-server",
      "image": "nginx:latest",
      "ports": {"80": 8080},
      "created_at": 1640995200
    }
  ]
}
```

## Health Monitoring

### add_health_check(container_id, endpoint, interval)
Adds health check monitoring to a container.

**Parameters:**
- `container_id` (str): Container ID to monitor
- `endpoint` (str): HTTP endpoint to check
- `interval` (int, optional): Check interval in seconds (default: 30)

**Returns:**
```json
{
  "container_id": "abc123",
  "endpoint": "http://localhost:8080/health",
  "interval": 30,
  "status": "health_check_added"
}
```

### get_service_health(container_id)
Gets health status of a service.

**Parameters:**
- `container_id` (str): Container ID to check

**Returns:**
```json
{
  "endpoint": "http://localhost:8080/health",
  "interval": 30,
  "last_check": 1640995200,
  "status": "healthy",
  "created_at": 1640995000
}
```

### auto_restart_on_failure(container_id)
Enables auto-restart on health check failure.

**Parameters:**
- `container_id` (str): Container ID to monitor

**Returns:**
```json
{
  "container_id": "abc123",
  "auto_restart": "enabled",
  "status": "monitoring_started"
}
```

## Environment Snapshots

### snapshot_env(env_name)
Creates a snapshot of current environment state.

**Parameters:**
- `env_name` (str): Name for the snapshot

**Returns:**
```json
{
  "env_name": "development",
  "containers_count": 3,
  "status": "snapshot_created"
}
```

### restore_env(snapshot_name)
Restores environment from snapshot.

**Parameters:**
- `snapshot_name` (str): Name of snapshot to restore

**Returns:**
```json
{
  "env_name": "development",
  "restored_containers": [
    {
      "original_id": "abc123",
      "new_id": "def456",
      "name": "web-server"
    }
  ],
  "failed_containers": [],
  "status": "env_restored"
}
```

### list_snapshots()
Lists all available snapshots.

**Returns:**
```json
{
  "snapshots": [
    {
      "name": "development",
      "containers_count": 3,
      "created_at": 1640995200
    }
  ]
}
```

## File Watching & Auto-Deploy

### watch_and_redeploy(project_path, patterns)
Watches for file changes and auto-redeploys services.

**Parameters:**
- `project_path` (str): Path to the project directory
- `patterns` (list, optional): File patterns to watch

**Default Patterns:** `['.py', '.js', '.Dockerfile', 'docker-compose.yml']`

**Returns:**
```json
{
  "project_path": "/path/to/project",
  "patterns": [".py", ".js"],
  "status": "watching_started"
}
```

### stop_watching(project_path)
Stops file watching for a project.

**Parameters:**
- `project_path` (str): Project path to stop watching

**Returns:**
```json
{
  "project_path": "/path/to/project",
  "status": "watching_stopped"
}
```

### smart_rebuild(service_name)
Rebuilds only what changed with dependency awareness.

**Parameters:**
- `service_name` (str): Service name to rebuild

**Returns:** Same as `deploy_service()`

## Error Handling

Most tools return error information in the following format:

```json
{
  "error": "Descriptive error message"
}
```

Common error scenarios:
- Container not found
- Port already allocated
- Image not found
- Dependency not met
- Template not found
- Snapshot not found

## Rate Limiting

Some operations may have built-in delays:
- Health checks: Respect configured intervals
- File watching: Debounced to prevent excessive rebuilds
- Dependency waiting: Configurable timeout (default: 60 seconds)
