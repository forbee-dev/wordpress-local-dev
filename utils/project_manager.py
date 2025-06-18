import os
import json
import shutil
import subprocess
import platform
import re
from pathlib import Path
import yaml
from .ssl_generator import SSLGenerator
from .hosts_manager import HostsManager

class ProjectManager:
    def __init__(self):
        self.projects_dir = Path("wordpress-projects")
        self.projects_dir.mkdir(exist_ok=True)
        self.ssl_generator = SSLGenerator()
        self.hosts_manager = HostsManager()
    
    def create_project(self, project_name, wordpress_version, repo_url, db_file_path=None, 
                      subfolder='', custom_domain='', enable_ssl=True, enable_redis=True):
        """Create a new WordPress project"""
        try:
            # Validate project name
            if not re.match(r'^[a-zA-Z0-9\-_]+$', project_name):
                return {'success': False, 'error': 'Project name can only contain letters, numbers, hyphens, and underscores'}
            
            project_path = self.projects_dir / project_name
            if project_path.exists():
                return {'success': False, 'error': 'Project already exists'}
            
            # Create project directory structure
            project_path.mkdir()
            (project_path / "wp-content").mkdir()
            (project_path / "data").mkdir()
            (project_path / "ssl").mkdir()
            
            # Generate domain
            domain = custom_domain if custom_domain else f"local.{project_name}.test"
            if subfolder:
                domain = f"{domain}/{subfolder}"
            
            # Generate SSL certificates if enabled
            if enable_ssl:
                self.ssl_generator.generate_ssl_cert(project_name, domain.split('/')[0])
            
            # Clone repository 
            repo_structure = None
            if repo_url:
                repo_structure = self._clone_repository(repo_url, project_path)
            
            # Create docker-compose.yml
            self._create_docker_compose(project_path, project_name, wordpress_version, 
                                      domain, enable_ssl, enable_redis)
            
            # Create Makefile
            self._create_makefile(project_path, project_name, domain, db_file_path)
            
            # Create nginx configuration
            self._create_nginx_config(project_path, project_name, domain, enable_ssl, subfolder)
            
            # Create project config (convert paths to strings for JSON serialization)
            repo_structure_json = None
            if repo_structure:
                repo_structure_json = {
                    'type': repo_structure['type'],
                    'has_wp_content': repo_structure['has_wp_content'],
                    'has_composer': repo_structure['has_composer'],
                    'has_package_json': repo_structure['has_package_json'],
                    'is_theme': repo_structure['is_theme'],
                    'is_plugin': repo_structure['is_plugin'],
                    'wp_content_path': str(repo_structure['wp_content_path']) if repo_structure['wp_content_path'] else None
                }
            
            config = {
                'name': project_name,
                'wordpress_version': wordpress_version,
                'repo_url': repo_url,
                'domain': domain,
                'subfolder': subfolder,
                'enable_ssl': enable_ssl,
                'enable_redis': enable_redis,
                'created_at': str(Path().resolve()),
                'db_file': db_file_path,
                'repository_structure': repo_structure_json
            }
            
            # Add to hosts file
            self.hosts_manager.add_host(domain.split('/')[0])
            
            # Copy database file to project data folder if provided
            if db_file_path and Path(db_file_path).exists():
                try:
                    project_data_dir = project_path / "data"
                    project_data_dir.mkdir(exist_ok=True)
                    
                    db_filename = Path(db_file_path).name
                    project_db_path = project_data_dir / db_filename
                    
                    # Copy database file to project data folder
                    shutil.copy2(db_file_path, project_db_path)
                    print(f"   📋 Database file copied to: data/{db_filename}")
                    
                    # Update config with project-relative path
                    config['db_file'] = f"data/{db_filename}"
                    
                except Exception as e:
                    print(f"   ⚠️  Warning: Could not copy database file: {str(e)}")
            
            # Save updated config
            with open(project_path / "config.json", 'w') as f:
                json.dump(config, f, indent=2)
            
            # Start Docker containers
            print(f"🚀 Starting Docker containers...")
            try:
                start_result = subprocess.run(
                    ['docker-compose', 'up', '-d'],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    timeout=120  # 2 minute timeout for container startup
                )
                
                if start_result.returncode == 0:
                    print(f"   ✅ Docker containers started successfully")
                    
                    # If database file was provided, import it after containers are running
                    if db_file_path and Path(project_path / "data" / Path(db_file_path).name).exists():
                        print(f"   📋 Importing database...")
                        # Give containers a moment to fully start
                        import time
                        time.sleep(5)
                        
                        # Import database using the project-relative path
                        db_import_result = self.import_database(
                            project_name, 
                            str(project_path / "data" / Path(db_file_path).name),
                            backup_before_import=False
                        )
                        
                        if db_import_result['success']:
                            print(f"   ✅ Database imported successfully")
                        else:
                            print(f"   ⚠️  Warning: Database import failed: {db_import_result['error']}")
                    
                else:
                    print(f"   ⚠️  Warning: Failed to start containers: {start_result.stderr}")
                    
            except subprocess.TimeoutExpired:
                print(f"   ⚠️  Warning: Container startup timed out")
            except Exception as e:
                print(f"   ⚠️  Warning: Error starting containers: {str(e)}")
            
            return {'success': True, 'project': config}
            
        except Exception as e:
            print(f"❌ Error creating project {project_name}: {str(e)}")
            # Clean up if project creation failed
            try:
                if project_path.exists():
                    shutil.rmtree(project_path)
                    print(f"   🧹 Cleaned up failed project directory")
            except:
                pass
            return {'success': False, 'error': str(e)}
    
    def list_projects(self):
        """List all WordPress projects"""
        projects = []
        for project_dir in self.projects_dir.iterdir():
            if project_dir.is_dir():
                config_file = project_dir / "config.json"
                if config_file.exists():
                    try:
                        with open(config_file, 'r') as f:
                            config = json.load(f)
                        status = self.get_project_status(project_dir.name)
                        config['status'] = status
                        projects.append(config)
                    except:
                        pass
        return projects
    
    def get_project_status(self, project_name):
        """Get the status of a WordPress project"""
        project_path = self.projects_dir / project_name
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
    
    def start_project(self, project_name):
        """Start a WordPress project"""
        project_path = self.projects_dir / project_name
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
    
    def stop_project(self, project_name):
        """Stop a WordPress project"""
        project_path = self.projects_dir / project_name
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
    
    def delete_project(self, project_name):
        """Delete a WordPress project"""
        project_path = self.projects_dir / project_name
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        
        try:
            # Stop containers first
            subprocess.run(['docker-compose', 'down', '-v'], cwd=project_path, capture_output=True)
            
            # Read config to get domain
            config_file = project_path / "config.json"
            if config_file.exists():
                with open(config_file, 'r') as f:
                    config = json.load(f)
                domain = config.get('domain', '').split('/')[0]
                if domain:
                    self.hosts_manager.remove_host(domain)
            
            # Remove project directory
            shutil.rmtree(project_path)
            
            return {'success': True, 'message': 'Project deleted successfully'}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_project_logs(self, project_name):
        """Get logs for a WordPress project"""
        project_path = self.projects_dir / project_name
        if not project_path.exists():
            return "Project not found"
        
        try:
            result = subprocess.run(
                ['docker-compose', 'logs', '--tail=100'],
                cwd=project_path,
                capture_output=True,
                text=True
            )
            return result.stdout
        except Exception as e:
            return f"Error getting logs: {str(e)}"
    
    def get_wordpress_debug_logs(self, project_name, lines=50):
        """Get WordPress debug logs for a project"""
        project_path = self.projects_dir / project_name
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        
        try:
            # Check if containers are running
            status = self.get_project_status(project_name)
            if status.get('status') != 'running':
                return {'success': False, 'error': 'Project must be running to view debug logs'}
            
            # Get debug logs from WordPress container
            result = subprocess.run(
                ['docker-compose', 'exec', '-T', 'wordpress', 'tail', f'-{lines}', '/var/www/html/wp-content/debug.log'],
                cwd=project_path,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                return {'success': True, 'logs': result.stdout}
            else:
                # If debug.log doesn't exist yet, return empty logs
                if "No such file or directory" in result.stderr:
                    return {'success': True, 'logs': 'No debug logs found yet. Debug logging is enabled but no errors have been logged.'}
                else:
                    return {'success': False, 'error': f'Error reading debug logs: {result.stderr}'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def clear_wordpress_debug_logs(self, project_name):
        """Clear WordPress debug logs for a project"""
        project_path = self.projects_dir / project_name
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        
        try:
            # Check if containers are running
            status = self.get_project_status(project_name)
            if status.get('status') != 'running':
                return {'success': False, 'error': 'Project must be running to clear debug logs'}
            
            # Clear debug logs in WordPress container
            result = subprocess.run(
                ['docker-compose', 'exec', '-T', 'wordpress', 'sh', '-c', 'echo "" > /var/www/html/wp-content/debug.log'],
                cwd=project_path,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                return {'success': True, 'message': 'Debug logs cleared successfully'}
            else:
                return {'success': False, 'error': f'Error clearing debug logs: {result.stderr}'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def import_database(self, project_name, db_file_path, backup_before_import=True):
        """Import database file into existing project"""
        project_path = self.projects_dir / project_name
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        
        try:
            # Check if containers are running
            status = self.get_project_status(project_name)
            if status.get('status') != 'running':
                return {'success': False, 'error': 'Project must be running to import database. Please start the project first.'}
            
            # Read environment variables
            env_file = project_path / '.env'
            env_vars = {}
            if env_file.exists():
                with open(env_file, 'r') as f:
                    for line in f:
                        if '=' in line and not line.startswith('#'):
                            key, value = line.strip().split('=', 1)
                            env_vars[key] = value
            
            db_name = env_vars.get('DB_NAME', f'local_{project_name}')
            db_user = env_vars.get('DB_USER', 'wordpress')
            db_password = env_vars.get('DB_PASSWORD', 'wordpress_password')
            
            # Backup current database if requested
            if backup_before_import:
                backup_filename = f"backup_before_import_{project_name}_{subprocess.run(['date', '+%Y%m%d_%H%M%S'], capture_output=True, text=True).stdout.strip()}.sql"
                backup_path = project_path / 'data' / backup_filename
                
                # Export current database
                backup_result = subprocess.run([
                    'docker-compose', 'exec', '-T', 'mysql',
                    'mysqldump', f'-u{db_user}', f'-p{db_password}', db_name
                ], cwd=project_path, capture_output=True, text=True)
                
                if backup_result.returncode == 0:
                    with open(backup_path, 'w') as f:
                        f.write(backup_result.stdout)
                    print(f"Database backed up to: {backup_path}")
                else:
                    print(f"Warning: Failed to backup database: {backup_result.stderr}")
            
            # Import new database
            with open(db_file_path, 'r') as f:
                import_result = subprocess.run([
                    'docker-compose', 'exec', '-T', 'mysql',
                    'mysql', f'-u{db_user}', f'-p{db_password}', db_name
                ], input=f.read(), cwd=project_path, capture_output=True, text=True)
            
            if import_result.returncode == 0:
                return {'success': True, 'message': 'Database imported successfully'}
            else:
                return {'success': False, 'error': f'Database import failed: {import_result.stderr}'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _clone_repository(self, repo_url, project_path):
        """Clone entire repository into project directory"""
        try:
            # Skip cloning if no repo URL provided
            if not repo_url or not repo_url.strip():
                print("ℹ️  No repository URL provided, skipping Git clone")
                return None
            
            # Create repository directory inside project
            repo_dir = project_path / "repository"
            
            # Create environment with credential helpers disabled to avoid prompts
            env = os.environ.copy()
            env['GIT_TERMINAL_PROMPT'] = '0'  # Disable interactive prompts
            env['GIT_ASKPASS'] = 'echo'       # Provide empty password for HTTPS
            
            print(f"🔄 Cloning repository: {repo_url}")
            
            # Clone repository directly to repository directory
            result = subprocess.run([
                'git', 'clone', 
                '--quiet',                   # Reduce output
                repo_url, 
                str(repo_dir)
            ], 
            env=env, 
            capture_output=True, 
            text=True, 
            timeout=60  # 60 second timeout
            )
            
            if result.returncode != 0:
                # If clone failed, provide helpful error message
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                
                if "Authentication failed" in error_msg or "fatal: could not read Username" in error_msg:
                    raise Exception(
                        f"Git authentication failed. For private repositories:\n"
                        f"• Use SSH URL (git@github.com:user/repo.git) with configured SSH keys\n"
                        f"• Or use personal access token in HTTPS URL\n"
                        f"• Or make the repository public\n"
                        f"Error: {error_msg}"
                    )
                elif "Repository not found" in error_msg:
                    raise Exception(f"Repository not found or access denied: {repo_url}")
                else:
                    raise Exception(f"Failed to clone repository: {error_msg}")
            
            print(f"✅ Repository cloned to: repository/")
            
            # Analyze repository structure
            repo_structure = self._analyze_repository_structure(repo_dir)
            print(f"   📂 Repository type: {repo_structure['type']}")
            
            # Set up wp-content linking/copying based on repository structure
            wp_content_path = project_path / "wp-content"
            self._setup_wp_content_from_repo(repo_dir, wp_content_path, repo_structure)
                
            return repo_structure
            
        except subprocess.TimeoutExpired:
            # Clean up on timeout
            if repo_dir.exists():
                shutil.rmtree(repo_dir)
            raise Exception("Git clone timed out after 60 seconds. Check repository URL and network connection.")
        except subprocess.CalledProcessError as e:
            # Clean up on error
            if repo_dir.exists():
                shutil.rmtree(repo_dir)
            raise Exception(f"Failed to clone repository: {str(e)}")
        except Exception as e:
            # Clean up on any error
            if repo_dir.exists():
                shutil.rmtree(repo_dir)
            raise e
    
    def _analyze_repository_structure(self, repo_dir):
        """Analyze repository structure to determine type and content"""
        structure = {
            'type': 'unknown',
            'has_wp_content': False,
            'has_composer': False,
            'has_package_json': False,
            'is_theme': False,
            'is_plugin': False,
            'wp_content_path': None
        }
        
        # Check for wp-content directory
        wp_content_path = repo_dir / "wp-content"
        if wp_content_path.exists() and wp_content_path.is_dir():
            structure['has_wp_content'] = True
            structure['wp_content_path'] = wp_content_path
            structure['type'] = 'full-wordpress-project'
        
        # Check for Composer
        if (repo_dir / "composer.json").exists():
            structure['has_composer'] = True
        
        # Check for Node.js/NPM
        if (repo_dir / "package.json").exists():
            structure['has_package_json'] = True
        
        # If no wp-content, check if it's a theme or plugin
        if not structure['has_wp_content']:
            # Check for theme indicators
            if (repo_dir / "style.css").exists() and (repo_dir / "index.php").exists():
                structure['is_theme'] = True
                structure['type'] = 'wordpress-theme'
            
            # Check for plugin indicators
            elif any(repo_dir.glob("*.php")):
                # Look for plugin header in PHP files
                for php_file in repo_dir.glob("*.php"):
                    try:
                        with open(php_file, 'r', encoding='utf-8') as f:
                            content = f.read(1000)  # Read first 1000 chars
                            if "Plugin Name:" in content:
                                structure['is_plugin'] = True
                                structure['type'] = 'wordpress-plugin'
                                break
                    except:
                        continue
            
            # If still unknown but has development files
            if structure['type'] == 'unknown':
                if structure['has_composer'] or structure['has_package_json']:
                    structure['type'] = 'development-project'
                else:
                    structure['type'] = 'generic-repository'
        
        return structure
    
    def _setup_wp_content_from_repo(self, repo_dir, wp_content_path, repo_structure):
        """Set up wp-content based on repository structure"""
        
        if repo_structure['has_wp_content']:
            # Repository has wp-content - create symlink or copy
            repo_wp_content = repo_structure['wp_content_path']
            
            # Remove default wp-content and create symlink to repository wp-content
            if wp_content_path.exists():
                shutil.rmtree(wp_content_path)
            
            try:
                # Try to create symlink (preferred for development)
                # Use relative path for better portability
                relative_path = Path("repository") / "wp-content"
                wp_content_path.symlink_to(relative_path, target_is_directory=True)
                print(f"   🔗 Created symlink: wp-content -> repository/wp-content")
            except OSError as e:
                print(f"   ⚠️  Symlink failed ({str(e)}), copying instead...")
                # Fallback to copying if symlinks not supported
                try:
                    shutil.copytree(str(repo_wp_content), str(wp_content_path))
                    print(f"   📁 Copied wp-content from repository (symlink not supported)")
                except Exception as copy_error:
                    raise Exception(f"Failed to link or copy wp-content: symlink error: {str(e)}, copy error: {str(copy_error)}")
                
        elif repo_structure['is_theme']:
            # Repository is a theme - put it in themes directory
            themes_dir = wp_content_path / "themes"
            themes_dir.mkdir(parents=True, exist_ok=True)
            
            # Use repository name as theme name
            theme_name = repo_dir.name if repo_dir.name != "repository" else "custom-theme"
            theme_path = themes_dir / theme_name
            
            try:
                # Create symlink to theme
                if theme_path.exists():
                    if theme_path.is_symlink():
                        theme_path.unlink()
                    else:
                        shutil.rmtree(theme_path)
                
                # Use relative path for better portability
                relative_repo_path = Path("../../../repository")
                theme_path.symlink_to(relative_repo_path, target_is_directory=True)
                print(f"   🎨 Created theme symlink: wp-content/themes/{theme_name} -> repository/")
            except OSError as e:
                print(f"   ⚠️  Theme symlink failed ({str(e)}), copying instead...")
                # Fallback to copying
                try:
                    if theme_path.exists():
                        shutil.rmtree(theme_path)
                    shutil.copytree(str(repo_dir), str(theme_path))
                    print(f"   🎨 Copied theme to: wp-content/themes/{theme_name}")
                except Exception as copy_error:
                    raise Exception(f"Failed to link or copy theme: symlink error: {str(e)}, copy error: {str(copy_error)}")
                
        elif repo_structure['is_plugin']:
            # Repository is a plugin - put it in plugins directory  
            plugins_dir = wp_content_path / "plugins"
            plugins_dir.mkdir(parents=True, exist_ok=True)
            
            # Use repository name as plugin name
            plugin_name = repo_dir.name if repo_dir.name != "repository" else "custom-plugin"
            plugin_path = plugins_dir / plugin_name
            
            try:
                # Create symlink to plugin
                if plugin_path.exists():
                    if plugin_path.is_symlink():
                        plugin_path.unlink()
                    else:
                        shutil.rmtree(plugin_path)
                
                # Use relative path for better portability
                relative_repo_path = Path("../../../repository")
                plugin_path.symlink_to(relative_repo_path, target_is_directory=True)
                print(f"   🔌 Created plugin symlink: wp-content/plugins/{plugin_name} -> repository/")
            except OSError as e:
                print(f"   ⚠️  Plugin symlink failed ({str(e)}), copying instead...")
                # Fallback to copying
                try:
                    if plugin_path.exists():
                        shutil.rmtree(plugin_path)
                    shutil.copytree(str(repo_dir), str(plugin_path))
                    print(f"   🔌 Copied plugin to: wp-content/plugins/{plugin_name}")
                except Exception as copy_error:
                    raise Exception(f"Failed to link or copy plugin: symlink error: {str(e)}, copy error: {str(copy_error)}")
        
        else:
            # Generic repository - just keep default wp-content
            print(f"   📁 Repository available at: repository/ (no automatic wp-content setup)")
            print(f"   ℹ️  You can manually configure how to use the repository content")
    
    def _create_docker_compose(self, project_path, project_name, wordpress_version, domain, enable_ssl, enable_redis):
        """Create docker-compose.yml for the project"""
        
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
    volumes:
      - ./wp-content:/var/www/html/wp-content
      - wordpress_data:/var/www/html
    networks:
      - wordpress_network
    depends_on:
      - mysql

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
    
    def _create_makefile(self, project_path, project_name, domain, db_file_path):
        """Create Makefile for the project"""
        
        db_import_command = ""
        if db_file_path:
            # Use the project-relative path for the Makefile
            relative_db_path = f"data/{Path(db_file_path).name}"
            db_import_command = f"""
db-import: ## Import database from file
\t@echo "Importing database from {relative_db_path}..."
\t@docker-compose exec -T mysql mysql -u${{DB_USER}} -p${{DB_PASSWORD}} ${{DB_NAME}} < "{relative_db_path}"
\t@echo "Database imported successfully!"
"""
        
        makefile_content = f"""# WordPress Local Development Environment Makefile
# Project: {project_name}
# Domain: {domain}

include .env

.PHONY: help start stop restart build logs shell db-export db-import clean status

help: ## Show this help message
\t@echo "Available commands:"
\t@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {{FS = ":.*?## "}}; {{printf "\\033[36m%-20s\\033[0m %s\\n", $$1, $$2}}'

start: ## Start the WordPress environment
\t@echo "Starting WordPress environment..."
\t@docker-compose up -d
\t@echo "WordPress is running at: https://${{DOMAIN}}"
\t@echo "phpMyAdmin is running at: http://localhost:${{PHPMYADMIN_PORT}}"

stop: ## Stop the WordPress environment
\t@echo "Stopping WordPress environment..."
\t@docker-compose down

restart: ## Restart the WordPress environment
\t@echo "Restarting WordPress environment..."
\t@docker-compose restart

build: ## Build/rebuild the WordPress environment
\t@echo "Building WordPress environment..."
\t@docker-compose down
\t@docker-compose up -d --build

logs: ## Show logs
\t@docker-compose logs -f

debug-logs: ## Show WordPress debug logs (live)
\t@echo "Showing WordPress debug logs..."
\t@docker-compose exec wordpress tail -f /var/www/html/wp-content/debug.log

debug-recent: ## Show recent WordPress debug entries
\t@echo "Recent WordPress debug entries:"
\t@docker-compose exec wordpress tail -50 /var/www/html/wp-content/debug.log

shell: ## Access WordPress container shell
\t@docker-compose exec wordpress bash

db-export: ## Export database to file
\t@echo "Exporting database..."
\t@docker-compose exec mysql mysqldump -u${{DB_USER}} -p${{DB_PASSWORD}} ${{DB_NAME}} > ./data/export_$(shell date +%Y%m%d_%H%M%S).sql
\t@echo "Database exported to ./data/"
{db_import_command}
clean: ## Clean up containers and volumes
\t@echo "Cleaning up..."
\t@docker-compose down -v
\t@docker system prune -f

status: ## Show container status
\t@docker-compose ps
"""
        
        with open(project_path / "Makefile", 'w') as f:
            f.write(makefile_content)
    
    def _create_nginx_config(self, project_path, project_name, domain, enable_ssl, subfolder):
        """Create nginx configuration"""
        
        ssl_config = """
    listen 443 ssl http2;
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;""" if enable_ssl else ""
        
        # Handle subfolder routing
        location_config = "/"
        if subfolder:
            location_config = f"/{subfolder}/"
        
        # Build nginx configuration based on subfolder setup
        if subfolder:
            nginx_content = f"""server {{
    listen 80;{ssl_config}
    server_name {domain.split('/')[0]};
    
    root /var/www/html;
    index index.php index.html index.htm;
    
    client_max_body_size 100M;
    
    # Handle WordPress files in subfolder context
    location ~ ^/{subfolder}/(wp-content|wp-includes|wp-admin)/ {{
        rewrite ^/{subfolder}/(.*)$ /$1 last;
    }}
    
    # Handle WordPress core PHP files in subfolder context
    location ~ ^/{subfolder}/(wp-login\\.php|wp-cron\\.php|wp-mail\\.php|wp-signup\\.php|wp-activate\\.php|wp-trackback\\.php|xmlrpc\\.php)$ {{
        rewrite ^/{subfolder}/(.*)$ /$1 last;
    }}
    
    # Handle root access - redirect to subfolder
    location = / {{
        try_files $uri $uri/ /index.php?$args;
    }}
    
    # Handle /{subfolder} subfolder
    location /{subfolder} {{
        return 301 /{subfolder}/;
    }}
    
    location /{subfolder}/ {{
        try_files $uri $uri/ /index.php?$args;
    }}
    
    # Handle all other requests
    location / {{
        try_files $uri $uri/ /index.php?$args;
    }}
    
    # PHP-FPM processing
    location ~ \\.php$ {{
        try_files $uri =404;
        fastcgi_split_path_info ^(.+\\.php)(/.+)$;
        fastcgi_pass wordpress:9000;
        fastcgi_index index.php;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        include fastcgi_params;
    }}
    
    # Security
    location ~ /\\.ht {{
        deny all;
    }}
    
    # Static files optimization
    location = /favicon.ico {{
        log_not_found off;
        access_log off;
    }}
    
    location = /robots.txt {{
        log_not_found off;
        access_log off;
        allow all;
    }}
    
    location ~* \\.(css|gif|ico|jpeg|jpg|js|png|svg|woff|woff2|ttf|eot)$ {{
        expires 1y;
        add_header Cache-Control "public, immutable";
        log_not_found off;
    }}
}}
"""
        else:
            nginx_content = f"""server {{
    listen 80;{ssl_config}
    server_name {domain.split('/')[0]};
    
    root /var/www/html;
    index index.php index.html index.htm;
    
    client_max_body_size 100M;
    
    location / {{
        try_files $uri $uri/ /index.php?$args;
    }}
    
    # PHP-FPM processing
    location ~ \\.php$ {{
        try_files $uri =404;
        fastcgi_split_path_info ^(.+\\.php)(/.+)$;
        fastcgi_pass wordpress:9000;
        fastcgi_index index.php;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        include fastcgi_params;
    }}
    
    # Security
    location ~ /\\.ht {{
        deny all;
    }}
    
    # Static files optimization
    location = /favicon.ico {{
        log_not_found off;
        access_log off;
    }}
    
    location = /robots.txt {{
        log_not_found off;
        access_log off;
        allow all;
    }}
    
    location ~* \\.(css|gif|ico|jpeg|jpg|js|png|svg|woff|woff2|ttf|eot)$ {{
        expires 1y;
        add_header Cache-Control "public, immutable";
        log_not_found off;
    }}
}}
"""
        
        with open(project_path / "nginx.conf", 'w') as f:
            f.write(nginx_content) 