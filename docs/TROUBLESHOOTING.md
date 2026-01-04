# Troubleshooting Guide

This document covers common issues and their solutions when using the Local DevOps MCP server.

## Docker Desktop Issues

### "docker command not found" Error

**Problem:** The MCP server can't find the Docker command.

**Solutions:**
1. **Ensure Docker Desktop is running**
   - Start Docker Desktop from the Start menu
   - Wait for the Docker Engine to be ready (green status)

2. **Restart your IDE**
   - Close and reopen your IDE (Windsurf, VS Code, etc.)
   - This ensures the IDE picks up the updated PATH

3. **Manual PATH check**
   ```bash
   # Check if Docker is in PATH
   where docker
   
   # If not found, add it manually
   $env:Path += ";C:\Program Files\Docker\Docker\resources\bin"
   ```

4. **Reinstall Docker Desktop**
   - Uninstall Docker Desktop
   - Reinstall with "Add to PATH" option enabled

### "docker-credential-desktop not available" Error

**Problem:** Docker credential helper is not accessible to the MCP server.

**Solutions:**
1. **Automatic handling** - The MCP server automatically creates a temporary DOCKER_CONFIG
2. **Manual fix** - Add Docker binaries to system PATH:
   ```bash
   $env:Path += ";C:\Program Files\Docker\Docker\resources\bin"
   ```

## Container Issues

### "Port already allocated" Error

**Problem:** Trying to use a port that's already in use.

**Solutions:**
1. **Check occupied ports**
   ```python
   # List running containers to see port usage
   list_running_services()
   ```

2. **Use different port**
   ```python
   # Use port 8081 instead of 8080
   deploy_service(
       image="nginx:latest",
       ports={"80": 8081}
   )
   ```

3. **Stop conflicting container**
   ```python
   # Find and stop the container using the port
   stop_service(container_id="conflicting_container_id")
   ```

### Container Fails to Start

**Problem:** Container starts but immediately stops.

**Solutions:**
1. **Check container logs**
   ```python
   logs = get_service_logs(container_id="abc123", tail=100)
   print(logs)
   ```

2. **Verify image exists**
   ```bash
   # Check if image exists locally
   docker images
   
   # Pull image manually if needed
   docker pull image_name
   ```

3. **Check environment variables**
   - Ensure all required environment variables are provided
   - Verify variable names and values are correct

## Dependency Issues

### "Dependency not met" Error

**Problem:** Service dependency condition not satisfied within timeout.

**Solutions:**
1. **Check dependency status**
   ```python
   status = get_dependency_status(service_name="api")
   print(status)
   ```

2. **Verify wait condition**
   ```python
   # For TCP dependencies, check if port is accessible
   # For HTTP dependencies, test the endpoint manually
   # For log dependencies, check if pattern exists in logs
   ```

3. **Increase timeout**
   - The default timeout is 60 seconds
   - Some services take longer to start (databases, etc.)

4. **Check service logs**
   ```python
   logs = get_service_logs(container_id="dependency_container_id")
   print(logs)
   ```

### Circular Dependency Error

**Problem:** Services have circular dependencies.

**Solutions:**
1. **Review dependency graph**
   - Draw the dependency relationships
   - Identify the circular reference

2. **Redesign architecture**
   - Remove unnecessary dependencies
   - Introduce intermediate services
   - Use message queues for async communication

3. **Split into separate deployment groups**
   ```python
   # Deploy core services first
   deploy_group([core_services])
   
   # Deploy dependent services after
   deploy_group([dependent_services])
   ```

## File Watching Issues

### File Changes Not Detected

**Problem:** File watcher doesn't detect changes.

**Solutions:**
1. **Check watcher status**
   ```python
   # This will show active watchers
   # (Note: This tool might need to be implemented)
   ```

2. **Verify file patterns**
   ```python
   # Ensure patterns match your files
   watch_and_redeploy(
       project_path="./my-app",
       patterns=[".py", ".js", ".Dockerfile", "requirements.txt"]
   )
   ```

3. **Check file permissions**
   - Ensure the MCP server has read access to project files
   - Check that files aren't locked by other processes

4. **Restart watcher**
   ```python
   stop_watching(project_path="./my-app")
   watch_and_redeploy(project_path="./my-app")
   ```

### Excessive Rebuilds

**Problem:** Files trigger too many rebuilds.

**Solutions:**
1. **Refine file patterns**
   ```python
   # Be more specific about which files to watch
   patterns=[".py", "requirements.txt"]  # Exclude temporary files
   ```

2. **Exclude temporary directories**
   - Add patterns to exclude `__pycache__`, `node_modules`, etc.
   - Use more specific path patterns

3. **Use manual rebuild when needed**
   ```python
   # Disable auto-rebuild and use manual rebuild
   smart_rebuild(service_name="my-service")
   ```

## Health Check Issues

### Health Check Always Fails

**Problem:** Health check consistently reports unhealthy status.

**Solutions:**
1. **Test endpoint manually**
   ```bash
   # Test the health endpoint directly
   curl http://localhost:8080/health
   ```

2. **Check endpoint configuration**
   - Verify the URL is correct
   - Ensure the endpoint exists in your application
   - Check if the application is actually running

3. **Adjust health check interval**
   ```python
   # Increase interval for slower services
   add_health_check(
       container_id="abc123",
       endpoint="http://localhost:8080/health",
       interval=60  # Increase from default 30
   )
   ```

4. **Check application logs**
   ```python
   logs = get_service_logs(container_id="abc123")
   print(logs)
   ```

## Snapshot Issues

### Snapshot Restore Fails

**Problem:** Can't restore environment from snapshot.

**Solutions:**
1. **Check snapshot contents**
   ```python
   # List snapshots to see what's available
   list_snapshots()
   
   # Get detailed snapshot info
   # (Note: This might need to be implemented)
   ```

2. **Verify image availability**
   - Ensure all images from the snapshot are still available
   - Pull missing images manually if needed

3. **Check port conflicts**
   - Ports from snapshot might conflict with running containers
   - Stop conflicting containers before restoring

4. **Partial restore handling**
   - Some containers might fail to restore
   - Check the `failed_containers` in the restore result

## Performance Issues

### Slow Deployment

**Problem:** Services take too long to deploy.

**Solutions:**
1. **Optimize Docker images**
   - Use smaller base images
   - Multi-stage builds
   - Remove unnecessary dependencies

2. **Reduce dependency wait times**
   - Use more specific wait conditions
   - Optimize application startup time

3. **Parallel deployment**
   - Deploy independent services in parallel
   - Only wait for actual dependencies

### High Resource Usage

**Problem:** Docker Desktop or system becomes slow.

**Solutions:**
1. **Monitor resource usage**
   ```bash
   # Check Docker Desktop resource limits
   # In Docker Desktop settings > Resources
   ```

2. **Clean up unused resources**
   ```bash
   # Remove unused containers
   docker container prune
   
   # Remove unused images
   docker image prune
   
   # Remove unused networks
   docker network prune
   ```

3. **Adjust container limits**
   - Set memory limits for containers
   - Limit CPU usage if needed

## Network Issues

### Container Communication Problems

**Problem:** Containers can't communicate with each other.

**Solutions:**
1. **Check network configuration**
   - Ensure containers are on the same network
   - Verify service names are correct

2. **Test connectivity**
   ```bash
   # Exec into one container and ping another
   docker exec -it container1 ping container2
   ```

3. **Use Docker networking**
   - Create custom networks
   - Use service names for communication

4. **Check firewall settings**
   - Windows Firewall might block container communication
   - Antivirus software might interfere

## Debug Mode

### Enable Verbose Logging

**Problem:** Need more detailed information for debugging.

**Solutions:**
1. **Set debug environment variable**
   ```bash
   export MCP_DEBUG=1
   ```

2. **Check Docker logs**
   ```bash
   # View Docker Desktop logs
   # In Docker Desktop > Troubleshoot > Logs
   ```

3. **Enable Python debugging**
   - Add print statements to the MCP server code
   - Use Python logging module for structured logging

## Common Error Messages

### "Image not found"
- Pull the image manually: `docker pull image_name`
- Check image name spelling
- Verify registry accessibility

### "Container not found"
- Check container ID spelling
- Use `list_running_services()` to find correct ID
- Container might have already stopped

### "Permission denied"
- Run IDE as administrator
- Check Docker Desktop permissions
- Verify file system permissions

### "Connection refused"
- Service might not be ready yet
- Check if port is correct
- Verify service is actually running

## Getting Help

### Collect Debug Information

When reporting issues, collect this information:

1. **System information**
   ```bash
   # Docker version
   docker version
   
   # Docker info
   docker info
   
   # System info
   uname -a
   ```

2. **MCP server logs**
   - Check IDE console output
   - Enable debug mode if needed

3. **Container information**
   ```python
   # List all containers
   list_running_services()
   
   # Get logs from problematic containers
   get_service_logs(container_id="abc123")
   ```

4. **Configuration details**
   - MCP configuration file
   - Docker Desktop settings
   - Network configuration

### Community Support

- Check the project repository for known issues
- Search existing discussions for similar problems
- Create detailed bug reports with steps to reproduce

### Best Practices

1. **Start simple** - Test basic operations before complex workflows
2. **Use snapshots** - Save working states before making changes
3. **Monitor resources** - Keep an eye on system resource usage
4. **Clean up regularly** - Remove unused containers and images
5. **Document configurations** - Keep track of working setups
