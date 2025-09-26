import subprocess
import json
from pathlib import Path


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
                ['docker-compose', 'ps', '--format', 'json'],
                cwd=project_path,
                capture_output=True,
                text=True
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
                
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
    
    def start_project(self, project_path):
        """Start Docker containers for a project"""
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        
        try:
            result = subprocess.run(
                ['docker-compose', 'up', '-d'],
                cwd=project_path,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                return {'success': True, 'message': 'Project started successfully'}
            else:
                return {'success': False, 'error': result.stderr}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def stop_project(self, project_path):
        """Stop Docker containers for a project"""
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        
        try:
            result = subprocess.run(
                ['docker-compose', 'down'],
                cwd=project_path,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                return {'success': True, 'message': 'Project stopped successfully'}
            else:
                return {'success': False, 'error': result.stderr}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def restart_project(self, project_path):
        """Restart Docker containers for a project"""
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        
        try:
            # Stop first
            stop_result = subprocess.run(
                ['docker-compose', 'down'],
                cwd=project_path,
                capture_output=True,
                text=True
            )
            
            if stop_result.returncode != 0:
                return {'success': False, 'error': f'Failed to stop containers: {stop_result.stderr}'}
            
            # Then start
            start_result = subprocess.run(
                ['docker-compose', 'up', '-d'],
                cwd=project_path,
                capture_output=True,
                text=True
            )
            
            if start_result.returncode == 0:
                return {'success': True, 'message': 'Project restarted successfully'}
            else:
                return {'success': False, 'error': f'Failed to start containers: {start_result.stderr}'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_project_logs(self, project_path, tail_lines=100):
        """Get logs for Docker containers"""
        if not project_path.exists():
            return "Project not found"
        
        try:
            result = subprocess.run(
                ['docker-compose', 'logs', f'--tail={tail_lines}'],
                cwd=project_path,
                capture_output=True,
                text=True
            )
            return result.stdout
        except Exception as e:
            return f"Error getting logs: {str(e)}"
    
    def create_docker_compose(self, project_path, project_name, wordpress_version, domain, enable_ssl, enable_redis):
        """Create docker-compose.yml for the project"""
        
        # Create custom PHP configuration for file uploads
        self._create_php_config(project_path)
        
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
        
        compose_content = f"""version: '3.8'

services:
  wordpress:
    image: wordpress:{wordpress_version}-fpm
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
        env_content = f"""PROJECT_NAME={project_name}
DB_NAME=local_{project_name}
DB_USER=wordpress
DB_PASSWORD=wordpress_password
DB_ROOT_PASSWORD=root_password
HTTP_PORT=80
HTTPS_PORT=443
MYSQL_PORT=3306
PHPMYADMIN_PORT=8080
REDIS_PORT=6379
DOMAIN={domain.split('/')[0]}
"""
        
        with open(project_path / ".env", 'w') as f:
            f.write(env_content)
    
    def _create_php_config(self, project_path):
        """Create custom PHP configuration for file uploads"""
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
    
    def exec_command_in_container(self, project_path, container_name, command):
        """Execute a command in a specific container"""
        try:
            cmd = ['docker-compose', 'exec', '-T', container_name] + command
            result = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True
            )
            return {
                'success': result.returncode == 0,
                'output': result.stdout,
                'error': result.stderr,
                'returncode': result.returncode
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
            # Check if WP CLI service exists in docker-compose
            docker_compose_path = project_path / "docker-compose.yml"
            if not docker_compose_path.exists():
                return {'success': False, 'error': 'docker-compose.yml not found'}
            
            with open(docker_compose_path, 'r') as f:
                compose_content = f.read()
            
            if "wpcli:" not in compose_content:
                return {'success': False, 'error': 'WP CLI service not configured. Please add WP CLI to this project first.'}
            
            # Run the WP CLI command
            full_command = f"docker-compose --profile cli run --rm wpcli {command}"
            
            result = subprocess.run(
                full_command.split(),
                cwd=project_path,
                capture_output=True,
                text=True
            )
            
            return {
                'success': result.returncode == 0,
                'output': result.stdout,
                'error': result.stderr,
                'command': command,
                'returncode': result.returncode
            }
                
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
        except:
            return False
