import os
import json
import shutil
import subprocess
import platform
import re
import time
from pathlib import Path

from .ssl_generator import SSLGenerator
from .hosts_manager import HostsManager
from .database_manager import DatabaseManager
from .docker_manager import DockerManager
from .repository_manager import RepositoryManager
from .config_manager import ConfigManager
from .wordpress_manager import WordPressManager


class ProjectManager:
    """Main project management orchestrator using specialized managers"""
    
    def __init__(self):
        self.projects_dir = Path("wordpress-projects")
        self.projects_dir.mkdir(exist_ok=True)
        
        # Initialize managers
        self.ssl_generator = SSLGenerator()
        self.hosts_manager = HostsManager()
        self.database_manager = DatabaseManager()
        self.docker_manager = DockerManager()
        self.repository_manager = RepositoryManager()
        self.config_manager = ConfigManager()
        self.wordpress_manager = WordPressManager(self.docker_manager)
    
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
                print(f"🔐 Generating SSL certificates for {domain.split('/')[0]}...")
                # Ensure mkcert CA is installed for trusted certificates
                if self.ssl_generator.mkcert_available and not self.ssl_generator._check_mkcert_ca_installed():
                    print("🔐 Setting up mkcert local CA for trusted SSL certificates...")
                    self.ssl_generator._install_mkcert_ca()
                self.ssl_generator.generate_ssl_cert(project_name, domain.split('/')[0])
            
            # Clone repository if provided
            repo_structure = None
            if repo_url:
                repo_structure = self.repository_manager.clone_repository(repo_url, project_path)
            
            # Create docker-compose.yml and related files
            self.docker_manager.create_docker_compose(project_path, project_name, wordpress_version, 
                                                     domain, enable_ssl, enable_redis)
            
            # Create configuration files
            self.config_manager.create_makefile(project_path, project_name, domain, db_file_path)
            self.config_manager.create_nginx_config(project_path, project_name, domain, enable_ssl, subfolder)
            
            # Create project config
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
                self._copy_database_file(db_file_path, project_path, config)
            
            # Save project config
            self.config_manager.create_project_config(project_path, config)
            
            # Start Docker containers
            print(f"🚀 Starting Docker containers...")
            start_result = self._start_containers_with_setup(project_path, project_name, db_file_path)
            
            if not start_result['success']:
                print(f"   ⚠️  Warning: {start_result['error']}")
            
            return {'success': True, 'project': config}
            
        except Exception as e:
            print(f"❌ Error creating project {project_name}: {str(e)}")
            # Clean up if project creation failed
            self._cleanup_failed_project(project_path)
            return {'success': False, 'error': str(e)}
    
    def list_projects(self):
        """List all WordPress projects"""
        projects = []
        for project_dir in self.projects_dir.iterdir():
            if project_dir.is_dir():
                config = self.config_manager.read_project_config(project_dir)
                if config:
                    try:
                        status = self.docker_manager.get_project_status(project_dir)
                        config['status'] = status
                        projects.append(config)
                    except:
                        pass
        return projects
    
    def get_project_status(self, project_name):
        """Get the status of a WordPress project"""
        project_path = self.projects_dir / project_name
        return self.docker_manager.get_project_status(project_path)
    
    def start_project(self, project_name):
        """Start a WordPress project"""
        project_path = self.projects_dir / project_name
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        
        try:
            # Check and ensure SSL certificates are up to date
            self._ensure_ssl_certificates(project_name)
            
            # Start containers
            result = self.docker_manager.start_project(project_path)
            
            if result['success']:
                # Give containers a moment to fully start
                time.sleep(5)
                
                # Fix wp-config.php to properly read debug environment variables
                print(f"   🔧 Configuring WordPress debug settings...")
                self.wordpress_manager.fix_wp_config_debug(project_path)
                
                return {'success': True, 'message': 'Project started successfully'}
            else:
                return result
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def stop_project(self, project_name):
        """Stop a WordPress project"""
        project_path = self.projects_dir / project_name
        return self.docker_manager.stop_project(project_path)
    
    def restart_project(self, project_name):
        """Restart a WordPress project"""
        project_path = self.projects_dir / project_name
        return self.docker_manager.restart_project(project_path)
    
    def delete_project(self, project_name):
        """Delete a WordPress project"""
        project_path = self.projects_dir / project_name
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        
        try:
            # Stop containers first
            self.docker_manager.stop_project(project_path)
            
            # Read config to get domain for hosts file cleanup
            config = self.config_manager.read_project_config(project_path)
            if config:
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
        return self.docker_manager.get_project_logs(project_path)
    
    def get_wordpress_debug_logs(self, project_name, lines=50):
        """Get WordPress debug logs for a project"""
        project_path = self.projects_dir / project_name
        return self.wordpress_manager.get_debug_logs(project_path, lines)
    
    def clear_wordpress_debug_logs(self, project_name):
        """Clear WordPress debug logs for a project"""
        project_path = self.projects_dir / project_name
        return self.wordpress_manager.clear_debug_logs(project_path)
    
    def import_database(self, project_name, db_file_path, backup_before_import=True):
        """Import database file for a project"""
        project_path = self.projects_dir / project_name
        
        # Check if containers are running
        status = self.docker_manager.get_project_status(project_path)
        if status.get('status') != 'running':
            return {'success': False, 'error': 'Project must be running to import database. Please start the project first.', 'logs': []}
        
        return self.database_manager.import_database(project_path, project_name, db_file_path, backup_before_import)
    
    def run_wp_cli_command(self, project_name, command):
        """Run a WP CLI command on a project"""
        project_path = self.projects_dir / project_name
        return self.wordpress_manager.run_wp_cli_command(project_path, command)
    
    def add_wpcli_to_project(self, project_name):
        """Add WP CLI service to existing project"""
        project_path = self.projects_dir / project_name
        config = self.config_manager.read_project_config(project_path)
        if not config:
            return {'success': False, 'error': 'Project config not found'}
        
        return self.wordpress_manager.add_wpcli_to_project(
            project_path, self.config_manager, self.docker_manager, config
        )
    
    def add_wpcli_to_all_projects(self):
        """Add WP CLI service to all existing projects"""
        projects = self.list_projects()
        results = []
        
        print(f"🚀 Adding WP CLI to all existing projects...")
        
        for project in projects:
            project_name = project['name']
            print(f"\n📦 Processing project: {project_name}")
            result = self.add_wpcli_to_project(project_name)
            results.append({
                'project': project_name,
                'success': result['success'],
                'message': result.get('message', result.get('error', ''))
            })
        
        # Summary
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]
        
        print(f"\n📊 Summary:")
        print(f"   ✅ Successful: {len(successful)}/{len(results)}")
        if failed:
            print(f"   ❌ Failed: {len(failed)}")
            for fail in failed:
                print(f"      • {fail['project']}: {fail['message']}")
        
        return {
            'success': len(failed) == 0,
            'total': len(results),
            'successful': len(successful),
            'failed': len(failed),
            'results': results
        }
    
    def update_wordpress_version(self, project_name, new_version):
        """Update WordPress version for an existing project"""
        project_path = self.projects_dir / project_name
        return self.wordpress_manager.update_wordpress_version(
            project_path, self.config_manager, self.docker_manager, new_version
        )
    
    def update_domain(self, project_name, new_domain, enable_ssl=None):
        """Update domain for an existing project"""
        project_path = self.projects_dir / project_name
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        
        try:
            # Read current config
            config = self.config_manager.read_project_config(project_path)
            if not config:
                return {'success': False, 'error': 'Project config not found'}
            
            old_domain = config.get('domain', 'unknown')
            print(f"🔄 Updating domain from {old_domain} to {new_domain}")
            
            # Update config
            updates = {'domain': new_domain}
            if enable_ssl is not None:
                updates['enable_ssl'] = enable_ssl
            
            # Update hosts file
            print(f"   🔄 Updating hosts file...")
            self.hosts_manager.remove_host(old_domain.split('/')[0])
            self.hosts_manager.add_host(new_domain.split('/')[0])
            
            # Generate new SSL certificate if SSL is enabled
            if config.get('enable_ssl', True):
                print(f"   🔐 Generating new SSL certificate for {new_domain.split('/')[0]}...")
                self.ssl_generator.generate_ssl_cert(project_name, new_domain.split('/')[0])
            
            # Stop containers
            print(f"   🛑 Stopping containers...")
            self.docker_manager.stop_project(project_path)
            
            # Update configuration
            self.config_manager.update_project_config(project_path, updates)
            config.update(updates)
            
            # Rebuild configuration files
            print(f"   🔄 Updating configuration files...")
            self.docker_manager.create_docker_compose(
                project_path, config['name'], config.get('wordpress_version', 'latest'),
                new_domain, config.get('enable_ssl', True), config.get('enable_redis', True)
            )
            
            self.config_manager.create_nginx_config(
                project_path, config['name'], new_domain,
                config.get('enable_ssl', True), config.get('subfolder', '')
            )
            
            # Start containers
            print(f"   🚀 Starting containers with new domain...")
            start_result = self.docker_manager.start_project(project_path)
            
            if start_result['success']:
                print(f"   ✅ Domain updated successfully")
                return {'success': True, 'message': f'Domain updated from {old_domain} to {new_domain}'}
            else:
                return {'success': False, 'error': f'Failed to start containers: {start_result["error"]}'}
                
        except Exception as e:
            print(f"   ❌ Error updating domain: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def update_repository(self, project_name, new_repo_url):
        """Update repository URL and re-clone content for an existing project"""
        project_path = self.projects_dir / project_name
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        
        try:
            config = self.config_manager.read_project_config(project_path)
            if not config:
                return {'success': False, 'error': 'Project config not found'}
            
            old_repo = config.get('repo_url', 'none')
            print(f"🔄 Updating repository from {old_repo} to {new_repo_url}")
            
            # Stop containers to avoid conflicts
            print(f"   🛑 Stopping containers...")
            self.docker_manager.stop_project(project_path)
            
            # Update repository
            repo_structure = self.repository_manager.update_repository(project_path, new_repo_url)
            
            # Update config
            updates = {'repo_url': new_repo_url}
            if repo_structure:
                updates['repository_structure'] = {
                    'type': repo_structure['type'],
                    'has_wp_content': repo_structure['has_wp_content'],
                    'has_composer': repo_structure['has_composer'],
                    'has_package_json': repo_structure['has_package_json'],
                    'is_theme': repo_structure['is_theme'],
                    'is_plugin': repo_structure['is_plugin'],
                    'wp_content_path': str(repo_structure['wp_content_path']) if repo_structure['wp_content_path'] else None
                }
            else:
                updates['repository_structure'] = None
            
            self.config_manager.update_project_config(project_path, updates)
            
            # Start containers
            print(f"   🚀 Starting containers with new repository...")
            start_result = self.docker_manager.start_project(project_path)
            
            if start_result['success']:
                print(f"   ✅ Repository updated successfully")
                return {'success': True, 'message': f'Repository updated from {old_repo} to {new_repo_url}'}
            else:
                return {'success': False, 'error': f'Failed to start containers: {start_result["error"]}'}
                
        except Exception as e:
            print(f"   ❌ Error updating repository: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _copy_database_file(self, db_file_path, project_path, config):
        """Copy database file to project data folder"""
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
    
    def _start_containers_with_setup(self, project_path, project_name, db_file_path):
        """Start containers and perform initial setup"""
        try:
            start_result = subprocess.run(
                ['docker-compose', 'up', '-d'],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if start_result.returncode == 0:
                print(f"   ✅ Docker containers started successfully")
                
                # Give containers a moment to fully start
                time.sleep(5)
                
                # Fix wp-config.php to properly read debug environment variables
                print(f"   🔧 Configuring WordPress debug settings...")
                self.wordpress_manager.fix_wp_config_debug(project_path)
                
                # If database file was provided, import it after containers are running
                if db_file_path and Path(project_path / "data" / Path(db_file_path).name).exists():
                    print(f"   📋 Importing database...")
                    
                    db_import_result = self.database_manager.import_database(
                        project_path, project_name,
                        str(project_path / "data" / Path(db_file_path).name),
                        backup_before_import=False
                    )
                    
                    if db_import_result['success']:
                        print(f"   ✅ Database imported successfully")
                    else:
                        print(f"   ⚠️  Warning: Database import failed: {db_import_result['error']}")
                
                return {'success': True}
            else:
                return {'success': False, 'error': f'Failed to start containers: {start_result.stderr}'}
                
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Container startup timed out'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _cleanup_failed_project(self, project_path):
        """Clean up if project creation failed"""
        try:
            if project_path.exists():
                shutil.rmtree(project_path)
                print(f"   🧹 Cleaned up failed project directory")
        except:
            pass
    
    def _ensure_ssl_certificates(self, project_name):
        """Ensure SSL certificates are present and up to date for a project"""
        try:
            project_path = self.projects_dir / project_name
            config = self.config_manager.read_project_config(project_path)
            
            if not config:
                print(f"   ⚠️  No config found for {project_name}, skipping SSL check")
                return
            
            # Check if SSL is enabled
            if not config.get('enable_ssl', True):
                print(f"   ℹ️  SSL disabled for {project_name}, skipping SSL check")
                return
            
            domain = config.get('domain', '').split('/')[0]
            if not domain:
                print(f"   ⚠️  No domain found for {project_name}, skipping SSL check")
                return
            
            ssl_dir = project_path / "ssl"
            cert_file = ssl_dir / "cert.pem"
            key_file = ssl_dir / "key.pem"
            
            # Check if SSL certificates exist and are valid
            ssl_needs_update = False
            
            if not cert_file.exists() or not key_file.exists():
                print(f"   🔐 SSL certificates missing for {project_name}, generating...")
                ssl_needs_update = True
            else:
                # Check if certificates are expired or need regeneration
                try:
                    cert_age = time.time() - cert_file.stat().st_mtime
                    if cert_age > 30 * 24 * 3600:  # 30 days
                        print(f"   🔐 SSL certificates are old for {project_name}, regenerating...")
                        ssl_needs_update = True
                except:
                    ssl_needs_update = True
            
            # Regenerate SSL certificates if needed
            if ssl_needs_update:
                print(f"   🔐 Ensuring SSL certificates for {domain}...")
                # Ensure mkcert CA is installed for trusted certificates
                if self.ssl_generator.mkcert_available and not self.ssl_generator._check_mkcert_ca_installed():
                    print("   🔐 Setting up mkcert local CA for trusted SSL certificates...")
                    self.ssl_generator._install_mkcert_ca()
                success = self.ssl_generator.generate_ssl_cert(project_name, domain)
                if success:
                    print(f"   ✅ SSL certificates updated for {domain}")
                else:
                    print(f"   ⚠️  Warning: Failed to generate SSL certificates for {domain}")
            else:
                print(f"   ✅ SSL certificates are up to date for {domain}")
                
        except Exception as e:
            print(f"   ⚠️  Warning: Error checking SSL certificates for {project_name}: {str(e)}")
    
    # Legacy method for backward compatibility - removed as it's now handled automatically
    # def fix_php_upload_limits(self, project_name):
    #     """PHP upload limits are now handled automatically in all projects"""
    #     return {'success': True, 'message': 'PHP upload limits are automatically configured (100MB)'}
