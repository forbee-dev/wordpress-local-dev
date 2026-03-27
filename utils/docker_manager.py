import subprocess
import json
from pathlib import Path

from .docker_compose_detect import compose_command


class DockerManager:
    """Handles Docker container operations and docker-compose configuration"""
    
    def __init__(self):
        pass
    
    def get_project_status(self, project_path):
        """Get the status of Docker containers for a project"""
        if not project_path.exists():
            return {'status': 'not_found'}
        
        try:
            result = subprocess.run(
                compose_command('ps', '--format', 'json'),
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                containers = []
                for line in result.stdout.strip().split('\n'):
                    if line:
                        containers.append(json.loads(line))

                running_containers = [c for c in containers if c.get('State') == 'running']
                total_containers = len(containers)

                if total_containers == 0:
                    return {'status': 'stopped', 'containers': []}
                elif len(running_containers) == total_containers:
                    return {'status': 'running', 'containers': containers}
                else:
                    return {'status': 'partial', 'containers': containers}
            else:
                return {'status': 'stopped', 'containers': []}

        except subprocess.TimeoutExpired:
            return {'status': 'error', 'error': 'Status check timed out'}
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
    
    def start_project(self, project_path):
        """Start Docker containers for a project"""
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        
        try:
            result = subprocess.run(
                compose_command('up', '-d'),
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                # Verify containers actually started
                status = self.get_project_status(project_path)
                if status.get('status') == 'running':
                    return {'success': True, 'message': 'Project started successfully'}
                elif status.get('status') == 'partial':
                    # Some containers failed to start
                    error_msg = 'Some containers failed to start. '
                    # Try to get more details from logs
                    logs = self.get_project_logs(project_path, tail_lines=20)
                    if logs:
                        error_msg += f'Recent logs: {logs[-500:]}'  # Last 500 chars
                    return {'success': False, 'error': error_msg}
                else:
                    # Containers didn't start, get error details
                    error_msg = 'Containers failed to start. '
                    if result.stderr:
                        error_msg += result.stderr
                    elif result.stdout:
                        error_msg += result.stdout
                    # Also check logs
                    logs = self.get_project_logs(project_path, tail_lines=20)
                    if logs:
                        error_msg += f'\nRecent logs: {logs[-500:]}'
                    return {'success': False, 'error': error_msg}
            else:
                # docker-compose command failed
                error_output = result.stderr if result.stderr else result.stdout
                return {'success': False, 'error': error_output}

        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Operation timed out. Check Docker status.'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def stop_project(self, project_path):
        """Stop Docker containers for a project"""
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        
        try:
            result = subprocess.run(
                compose_command('down'),
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                return {'success': True, 'message': 'Project stopped successfully'}
            else:
                return {'success': False, 'error': result.stderr}

        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Operation timed out. Check Docker status.'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def restart_project(self, project_path):
        """Restart Docker containers for a project"""
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        
        try:
            # Stop first
            stop_result = subprocess.run(
                compose_command('down'),
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120
            )

            if stop_result.returncode != 0:
                return {'success': False, 'error': f'Failed to stop containers: {stop_result.stderr}'}

            # Then start
            start_result = subprocess.run(
                compose_command('up', '-d'),
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120
            )

            if start_result.returncode == 0:
                return {'success': True, 'message': 'Project restarted successfully'}
            else:
                return {'success': False, 'error': f'Failed to start containers: {start_result.stderr}'}

        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Operation timed out. Check Docker status.'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def restart_container(self, project_path, container_name):
        """Restart a specific container in a project"""
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        
        try:
            result = subprocess.run(
                compose_command('restart', container_name),
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                return {'success': True, 'message': f'Container {container_name} restarted successfully'}
            else:
                return {'success': False, 'error': f'Failed to restart container: {result.stderr}'}

        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Operation timed out. Check Docker status.'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_project_logs(self, project_path, tail_lines=100):
        """Get logs for Docker containers"""
        if not project_path.exists():
            return "Project not found"
        
        try:
            result = subprocess.run(
                compose_command('logs', f'--tail={tail_lines}'),
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.stdout
        except subprocess.TimeoutExpired:
            return "Error: log fetch timed out"
        except Exception as e:
            return f"Error getting logs: {str(e)}"
    
    def create_docker_compose(self, project_path, project_name, wordpress_version, domain, enable_ssl, enable_redis, ports=None):
        """Create docker-compose.yml for the project"""
        
        # Create custom PHP configuration for file uploads
        self._create_php_config(project_path)
        
        # Normalize WordPress version for FPM image
        # Handle versions that already include -fpm, or are "latest", or are just version numbers
        if wordpress_version.endswith('-fpm'):
            # Version already includes -fpm, use as-is
            wp_image_tag = wordpress_version
        elif wordpress_version == 'latest':
            # Latest should use fpm tag (which is latest FPM)
            wp_image_tag = 'fpm'
        elif wordpress_version.startswith('php'):
            # PHP version like php8.3, add -fpm
            wp_image_tag = f"{wordpress_version}-fpm"
        else:
            # Version number like 6.4, add -fpm
            wp_image_tag = f"{wordpress_version}-fpm"
        
        # Build nginx volumes list
        nginx_volumes = [
            "./nginx.conf:/etc/nginx/conf.d/default.conf",
            "./wp-content:/var/www/html/wp-content",
            "wordpress_data:/var/www/html"
        ]
        if enable_ssl:
            nginx_volumes.append("./ssl:/etc/nginx/ssl")
        nginx_volumes_str = "\n".join([f"      - {vol}" for vol in nginx_volumes])
        
        # Build nginx depends_on list
        nginx_depends = ["wordpress"]
        if enable_redis:
            nginx_depends.append("redis")
        nginx_depends_str = "\n".join([f"      - {dep}" for dep in nginx_depends])
        
        # Redis service
        redis_service = """
  redis:
    image: redis:7-alpine
    container_name: ${PROJECT_NAME}_redis
    restart: unless-stopped
    ports:
      - "${REDIS_PORT}:6379"
    volumes:
      - redis_data:/data
    networks:
      - wordpress_network""" if enable_redis else ""
        
        # Build volumes list
        volumes_list = ["wordpress_data:", "mysql_data:"]
        if enable_redis:
            volumes_list.append("redis_data:")
        volumes_str = "\n".join([f"  {vol}" for vol in volumes_list])
        
        compose_content = f"""services:
  wordpress:
    image: wordpress:{wp_image_tag}
    container_name: ${{PROJECT_NAME}}_wordpress
    restart: unless-stopped
    environment:
      WORDPRESS_DB_HOST: mysql
      WORDPRESS_DB_USER: ${{DB_USER}}
      WORDPRESS_DB_PASSWORD: ${{DB_PASSWORD}}
      WORDPRESS_DB_NAME: ${{DB_NAME}}
      WORDPRESS_DEBUG: 1
      WORDPRESS_DEBUG_LOG: 1
      WORDPRESS_DEBUG_DISPLAY: 0
      WP_DEBUG_DISPLAY: 0
      WP_DEBUG_LOG: 1
    volumes:
      - ./wp-content:/var/www/html/wp-content
      - ./php-uploads.ini:/usr/local/etc/php/conf.d/uploads.ini
      - ./php-fpm-pool.conf:/usr/local/etc/php-fpm.d/www.conf
      - wordpress_data:/var/www/html
    networks:
      - wordpress_network
    depends_on:
      - mysql

  wpcli:
    image: wordpress:cli-php8.3
    container_name: ${{PROJECT_NAME}}_wpcli
    environment:
      WORDPRESS_DB_HOST: mysql
      WORDPRESS_DB_USER: ${{DB_USER}}
      WORDPRESS_DB_PASSWORD: ${{DB_PASSWORD}}
      WORDPRESS_DB_NAME: ${{DB_NAME}}
    volumes:
      - ./wp-content:/var/www/html/wp-content
      - wordpress_data:/var/www/html
    networks:
      - wordpress_network
    depends_on:
      - wordpress
      - mysql
    profiles:
      - cli
    working_dir: /var/www/html
    user: "33:33"
    entrypoint: wp
    command: --info

  mysql:
    image: mysql:8.0
    container_name: ${{PROJECT_NAME}}_mysql
    restart: unless-stopped
    environment:
      MYSQL_DATABASE: ${{DB_NAME}}
      MYSQL_USER: ${{DB_USER}}
      MYSQL_PASSWORD: ${{DB_PASSWORD}}
      MYSQL_ROOT_PASSWORD: ${{DB_ROOT_PASSWORD}}
    volumes:
      - mysql_data:/var/lib/mysql
      - ./data:/docker-entrypoint-initdb.d
    ports:
      - "${{MYSQL_PORT}}:3306"
    networks:
      - wordpress_network

  phpmyadmin:
    image: phpmyadmin:latest
    container_name: ${{PROJECT_NAME}}_phpmyadmin
    restart: unless-stopped
    environment:
      PMA_HOST: mysql
      PMA_USER: ${{DB_USER}}
      PMA_PASSWORD: ${{DB_PASSWORD}}
      UPLOAD_LIMIT: 100M
    volumes:
      - ./php-uploads.ini:/usr/local/etc/php/conf.d/uploads.ini
    ports:
      - "${{PHPMYADMIN_PORT}}:80"
    networks:
      - wordpress_network
    depends_on:
      - mysql

  nginx:
    image: nginx:alpine
    container_name: ${{PROJECT_NAME}}_nginx
    restart: unless-stopped
    ports:
      - "${{HTTP_PORT}}:80"
      - "${{HTTPS_PORT}}:443"
    volumes:
{nginx_volumes_str}
    networks:
      - wordpress_network
    depends_on:
{nginx_depends_str}{redis_service}

volumes:
{volumes_str}

networks:
  wordpress_network:
    driver: bridge
"""
        
        with open(project_path / "docker-compose.yml", 'w') as f:
            f.write(compose_content)
        
        # Create .env file
        http_port = ports['HTTP_PORT'] if ports else 80
        https_port = ports['HTTPS_PORT'] if ports else 443
        mysql_port = ports['MYSQL_PORT'] if ports else 3306
        phpmyadmin_port = ports['PHPMYADMIN_PORT'] if ports else 8080
        redis_port = ports['REDIS_PORT'] if ports else 6379

        env_content = f"""PROJECT_NAME={project_name}
DB_NAME=local_{project_name}
DB_USER=wordpress
DB_PASSWORD=wordpress_password
DB_ROOT_PASSWORD=root_password
HTTP_PORT={http_port}
HTTPS_PORT={https_port}
MYSQL_PORT={mysql_port}
PHPMYADMIN_PORT={phpmyadmin_port}
REDIS_PORT={redis_port}
DOMAIN={domain.split('/')[0]}
"""
        
        with open(project_path / ".env", 'w') as f:
            f.write(env_content)
    
    def _create_php_config(self, project_path):
        """Create custom PHP configuration for file uploads and PHP-FPM pool settings"""
        php_config = """; PHP Upload Configuration
; Increase file upload limits for WordPress development

; Maximum file size for uploads
upload_max_filesize = 100M

; Maximum size of POST data
post_max_size = 100M

; Maximum number of files that can be uploaded
max_file_uploads = 20

; Maximum execution time for scripts (in seconds)
max_execution_time = 300

; Maximum amount of memory a script may consume
memory_limit = 256M

; Maximum input variables
max_input_vars = 3000

; Maximum time to parse input data
max_input_time = 300
"""
        
        with open(project_path / "php-uploads.ini", 'w') as f:
            f.write(php_config)
        
        # Create PHP-FPM pool configuration
        php_fpm_pool_config = """; PHP-FPM Pool Configuration
; Override default pool settings to increase max_children for better performance

[www]
; User and group for PHP-FPM processes (required)
user = www-data
group = www-data

; Maximum number of child processes
pm.max_children = 20

; Number of child processes created on startup
pm.start_servers = 5

; Minimum number of idle server processes
pm.min_spare_servers = 3

; Maximum number of idle server processes
pm.max_spare_servers = 8

; Maximum number of requests each child process should execute before respawning
pm.max_requests = 500

; Process manager style (static, dynamic, or ondemand)
pm = dynamic
"""
        
        with open(project_path / "php-fpm-pool.conf", 'w') as f:
            f.write(php_fpm_pool_config)
    
    def get_container_id(self, project_path, service_name):
        """Get the container ID for a docker-compose service. Returns None if not found."""
        try:
            result = subprocess.run(
                compose_command('ps', '-q', service_name),
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0 or not result.stdout:
                return None
            return result.stdout.strip().split('\n')[0]
        except Exception:
            return None

    def copy_file_to_container(self, container_id, host_path, container_path):
        """Copy a file from host to container. host_path and container_path must be absolute."""
        try:
            result = subprocess.run(
                ['docker', 'cp', str(Path(host_path).resolve()), f'{container_id}:{container_path}'],
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                'success': result.returncode == 0,
                'error': result.stderr if result.returncode != 0 else None
            }
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Operation timed out. Check Docker status.'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def exec_command_in_container(self, project_path, container_name, command):
        """Execute a command in a specific container"""
        try:
            cmd = compose_command('exec', '-T', container_name) + command
            result = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120
            )
            return {
                'success': result.returncode == 0,
                'output': result.stdout,
                'error': result.stderr,
                'returncode': result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': 'Operation timed out. Check Docker status.',
                'returncode': -1
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'returncode': -1
            }
    
    def run_wp_cli_command(self, project_path, command):
        """Run a WP CLI command using the wpcli container"""
        try:
            import shlex
            
            # Check if WP CLI service exists in docker-compose
            docker_compose_path = project_path / "docker-compose.yml"
            if not docker_compose_path.exists():
                return {'success': False, 'error': 'docker-compose.yml not found'}
            
            with open(docker_compose_path, 'r') as f:
                compose_content = f.read()
            
            if "wpcli:" not in compose_content:
                return {'success': False, 'error': 'WP CLI service not configured. Please add WP CLI to this project first.'}
            
            # Run the WP CLI command - use shlex.split to properly handle quoted arguments
            cmd = compose_command('--profile', 'cli', 'run', '--rm', 'wpcli')
            cmd.extend(shlex.split(command))

            result = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120
            )

            return {
                'success': result.returncode == 0,
                'output': result.stdout,
                'error': result.stderr,
                'command': command,
                'returncode': result.returncode
            }

        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Operation timed out. Check Docker status.', 'command': command}
        except Exception as e:
            return {'success': False, 'error': str(e), 'command': command}
    
    def has_wpcli_service(self, project_path):
        """Check if project has WP CLI service configured"""
        docker_compose_path = project_path / "docker-compose.yml"
        if not docker_compose_path.exists():
            return False
        
        try:
            with open(docker_compose_path, 'r') as f:
                compose_content = f.read()
            return "wpcli:" in compose_content
        except Exception as e:
            print(f"Warning: could not read docker-compose.yml: {e}")
            return False
