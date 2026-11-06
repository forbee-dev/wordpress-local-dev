import shutil
import subprocess
import time
import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .validators import (
    is_valid_domain,
    is_valid_project_name,
    is_valid_subfolder,
    is_valid_wordpress_version,
)
from .ssl_generator import SSLGenerator
from .hosts_manager import HostsManager
from .database_manager import DatabaseManager
from .docker_manager import DockerManager
from .repository_manager import RepositoryManager
from .config_manager import ConfigManager
from .wordpress_manager import WordPressManager
from .port_allocator import PortAllocator
from .docker_compose_detect import compose_command
from .proxy_manager import ProxyManager


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
        self.proxy_manager = ProxyManager(Path('.'), self.projects_dir)
    
    def create_project(self, project_name, wordpress_version, repo_url, db_file_path=None, 
                      subfolder='', custom_domain='', enable_ssl=True, enable_redis=True):
        """Create a new WordPress project"""
        try:
            # Validate project name (fullmatch: `$` would allow a trailing newline)
            if not is_valid_project_name(project_name):
                return {'success': False, 'error': 'Project name can only contain letters, numbers, hyphens, and underscores'}
            if not is_valid_wordpress_version(wordpress_version):
                return {'success': False, 'error': 'Invalid WordPress version'}

            # Accept either `custom_domain` or `custom_domain/subfolder`, but not
            # both spellings at once. Normalize before building the domain.
            if custom_domain:
                if not is_valid_domain(custom_domain):
                    return {'success': False, 'error': 'Invalid custom domain'}
                if '/' in custom_domain:
                    custom_domain, embedded_subfolder = custom_domain.split('/', 1)
                    if subfolder and subfolder != embedded_subfolder:
                        return {'success': False, 'error': 'Subfolder specified twice'}
                    subfolder = embedded_subfolder
            if not is_valid_subfolder(subfolder):
                return {'success': False, 'error': 'Invalid subfolder (letters, numbers, ".", "_", "~", "-" and "/" only)'}
            
            project_path = self.projects_dir / project_name
            if project_path.exists():
                return {'success': False, 'error': 'Project already exists'}
            
            # Create project directory structure
            project_path.mkdir()
            (project_path / "wp-content").mkdir()
            data_dir = project_path / "data"
            data_dir.mkdir()
            (project_path / "ssl").mkdir()
            
            # If DB was uploaded to temp dir, move it into project data/ (API never creates project dir)
            if db_file_path and Path(db_file_path).exists():
                src = Path(db_file_path)
                dst = data_dir / src.name
                if dst.resolve() != src.resolve():
                    shutil.move(str(src), str(dst))
                    db_file_path = str(dst)
            
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
            
            # Allocate unique ports
            allocator = PortAllocator(self.projects_dir)
            port_index = allocator.allocate_next_index()
            ports = allocator.get_ports_for_index(port_index)
            print(f"   Allocated ports for project (index {port_index}): HTTP={ports['HTTP_PORT']}, HTTPS={ports['HTTPS_PORT']}")

            # Create docker-compose.yml and related files
            self.docker_manager.create_docker_compose(project_path, project_name, wordpress_version,
                                                     domain, enable_ssl, enable_redis, ports=ports)
            
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
                'created_at': datetime.datetime.now().isoformat(),
                'db_file': db_file_path,
                'repository_structure': repo_structure_json,
                'port_index': port_index,
                'ports': ports
            }
            
            # Add to hosts file
            hosts_result = self.hosts_manager.add_host(domain.split('/')[0])
            if isinstance(hosts_result, dict) and hosts_result.get('manual_action_required'):
                config['hosts_instruction'] = hosts_result.get('instruction')

            # Database file is already saved to project data folder during upload
            if db_file_path and Path(db_file_path).exists():
                # Update config with project-relative path for reference
                db_filename = Path(db_file_path).name
                config['db_file'] = f"data/{db_filename}"
            
            # Save project config
            self.config_manager.create_project_config(project_path, config)
            
            # Start Docker containers
            print(f"🚀 Starting Docker containers...")
            start_result = self._start_containers_with_setup(project_path, project_name, db_file_path)
            
            if not start_result['success']:
                print(f"   ⚠️  Warning: {start_result['error']}")
            else:
                # Connect to shared reverse proxy
                config_data = self.config_manager.read_project_config(project_path)
                if config_data:
                    self.proxy_manager.on_project_start(project_name, config_data)

            return {'success': True, 'project': config}
            
        except Exception as e:
            print(f"❌ Error creating project {project_name}: {str(e)}")
            # Clean up if project creation failed
            self._cleanup_failed_project(project_path)
            return {'success': False, 'error': 'Failed to create project; check the server logs.'}
    
    def list_projects(self):
        """List all WordPress projects.

        Docker status checks are independent, so they run in parallel: with a
        dozen projects the dashboard used to wait for a dozen ``compose ps``
        calls back-to-back.
        """
        project_dirs = [d for d in self.projects_dir.iterdir() if d.is_dir()]

        def load(project_dir):
            config = self.config_manager.read_project_config(project_dir)
            if not config:
                return None
            try:
                config['status'] = self.docker_manager.get_project_status(project_dir)
            except Exception as e:
                print(f"Warning: could not load project {project_dir.name}: {e}")
                config['status'] = {'status': 'error', 'error': 'Unable to read container status'}
            return config

        if not project_dirs:
            return []

        with ThreadPoolExecutor(max_workers=min(8, len(project_dirs))) as pool:
            return [config for config in pool.map(load, project_dirs) if config]
    
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

                # Configure WordPress debug settings in wp-config.php
                print(f"   🔧 Configuring WordPress debug settings...")
                self.wordpress_manager.fix_wp_config_debug(project_path)

                # Connect to shared reverse proxy
                config = self.config_manager.read_project_config(project_path)
                if config:
                    self.proxy_manager.on_project_start(project_name, config)

                return {'success': True, 'message': 'Project started successfully'}
            else:
                return result
                
        except Exception as e:
            print(f"   ❌ Error starting project: {str(e)}")
            return {'success': False, 'error': 'Failed to start project; check the server logs.'}
    
    def stop_project(self, project_name):
        """Stop a WordPress project"""
        project_path = self.projects_dir / project_name
        result = self.docker_manager.stop_project(project_path)
        self.proxy_manager.on_project_stop(project_name)
        return result
    
    def restart_project(self, project_name):
        """Restart a WordPress project (with proxy reconnection)"""
        project_path = self.projects_dir / project_name
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}

        # Disconnect proxy before stopping (network will be destroyed by down)
        self.proxy_manager.on_project_stop(project_name)

        result = self.docker_manager.restart_project(project_path)

        if result.get('success'):
            time.sleep(3)
            # Reconnect proxy to the newly-created network
            config = self.config_manager.read_project_config(project_path)
            if config:
                self.proxy_manager.on_project_start(project_name, config)

        return result
    
    def delete_project(self, project_name):
        """Delete a WordPress project"""
        project_path = self.projects_dir / project_name
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        
        try:
            # Stop containers first
            self.docker_manager.stop_project(project_path)

            # Disconnect from shared reverse proxy
            self.proxy_manager.on_project_delete(project_name)

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
            print(f"   ❌ Error deleting project: {str(e)}")
            return {'success': False, 'error': 'Failed to delete project; check the server logs.'}
    
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
    
    def fix_database_connection(self, project_name):
        """Fix database connection issues for a project"""
        project_path = self.projects_dir / project_name
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        return self.wordpress_manager.fix_database_connection(project_path)
    
    def fix_wordpress_install_detection(self, project_name):
        """Fix WordPress redirecting to install.php when database is already imported"""
        project_path = self.projects_dir / project_name
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        return self.wordpress_manager.fix_wordpress_install_detection(project_path)

    def get_wp_config(self, project_name):
        """Get wp-config.php content from the WordPress container"""
        project_path = self.projects_dir / project_name
        return self.wordpress_manager.get_wp_config(project_path)

    def update_wp_config(self, project_name, content):
        """Update wp-config.php in the WordPress container"""
        project_path = self.projects_dir / project_name
        return self.wordpress_manager.update_wp_config(project_path, content)
    
    def import_database(self, project_name, db_file_path, backup_before_import=True, url_search=None, url_replace=None):
        """Import database file for a project. Optional url_search/url_replace to rewrite URLs in the dump (e.g. production → local)."""
        project_path = self.projects_dir / project_name
        
        # Check if containers are running
        status = self.docker_manager.get_project_status(project_path)
        if status.get('status') != 'running':
            return {'success': False, 'error': 'Project must be running to import database. Please start the project first.', 'logs': []}
        
        # Import the database
        result = self.database_manager.import_database(
            project_path, project_name, db_file_path, backup_before_import,
            url_search=url_search, url_replace=url_replace
        )
        
        # If import was successful, ensure WordPress recognizes the imported database
        if result.get('success'):
            print(f"   🔄 Ensuring WordPress recognizes imported database...")
            wp_result = self.wordpress_manager.ensure_wordpress_recognizes_database(project_path)
            if wp_result.get('success'):
                result['message'] = result.get('message', 'Database imported successfully') + '. ' + wp_result.get('message', '')
        
        return result
    
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
        if not is_valid_wordpress_version(new_version):
            return {'success': False, 'error': 'Invalid WordPress version'}
        project_path = self.projects_dir / project_name
        return self.wordpress_manager.update_wordpress_version(
            project_path, self.config_manager, self.docker_manager, new_version
        )
    
    def sync_wordpress_core(self, project_name, force=False):
        """Sync core files from the image into the docroot for an existing project"""
        project_path = self.projects_dir / project_name
        return self.wordpress_manager.sync_core_files(project_path, force=force)

    def get_core_version_status(self, project_name):
        """Report the image vs. actually-served WordPress core version"""
        project_path = self.projects_dir / project_name
        return self.wordpress_manager.get_core_version_status(project_path)

    def update_domain(self, project_name, new_domain, enable_ssl=None):
        """Update domain for an existing project"""
        project_path = self.projects_dir / project_name
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}

        new_domain = str(new_domain or '').strip()
        if not is_valid_domain(new_domain):
            return {'success': False, 'error': 'Invalid domain'}

        try:
            # Read current config
            config = self.config_manager.read_project_config(project_path)
            if not config:
                return {'success': False, 'error': 'Project config not found'}

            # A domain may carry the subfolder (`host/path`); otherwise keep the
            # project's existing subfolder. Persist whichever applies.
            domain_parts = new_domain.split('/', 1)
            if len(domain_parts) == 2:
                new_host, new_subfolder = domain_parts
            else:
                new_host = domain_parts[0]
                new_subfolder = config.get('subfolder', '') or ''
            if not is_valid_subfolder(new_subfolder):
                return {'success': False, 'error': 'Invalid subfolder'}
            new_domain = f"{new_host}/{new_subfolder}" if new_subfolder else new_host

            old_domain = config.get('domain', 'unknown')
            print(f"🔄 Updating domain from {old_domain} to {new_domain}")
            
            # Update config
            updates = {'domain': new_domain, 'subfolder': new_subfolder}
            if enable_ssl is not None:
                updates['enable_ssl'] = enable_ssl
            
            # Update hosts file
            print(f"   🔄 Updating hosts file...")
            self.hosts_manager.remove_host(old_domain.split('/')[0])
            hosts_result = self.hosts_manager.add_host(new_host)

            # Generate new SSL certificate if SSL is enabled
            if config.get('enable_ssl', True):
                print(f"   🔐 Generating new SSL certificate for {new_host}...")
                self.ssl_generator.generate_ssl_cert(project_name, new_host)
            
            # Stop containers
            print(f"   🛑 Stopping containers...")
            self.docker_manager.stop_project(project_path)
            
            # Update configuration
            self.config_manager.update_project_config(project_path, updates)
            config.update(updates)
            
            # Rebuild configuration files
            print(f"   Updating configuration files...")
            existing_ports = None
            if config.get('port_index'):
                allocator = PortAllocator(self.projects_dir)
                existing_ports = allocator.get_ports_for_index(config['port_index'])

            self.docker_manager.create_docker_compose(
                project_path, config['name'], config.get('wordpress_version') or 'latest',
                new_domain, config.get('enable_ssl', True), config.get('enable_redis', True),
                ports=existing_ports
            )
            
            self.config_manager.create_nginx_config(
                project_path, config['name'], new_domain,
                config.get('enable_ssl', True), new_subfolder
            )
            
            # Start containers
            print(f"   🚀 Starting containers with new domain...")
            start_result = self.docker_manager.start_project(project_path)
            
            if start_result['success']:
                print(f"   ✅ Domain updated successfully")
                response = {'success': True, 'message': f'Domain updated from {old_domain} to {new_domain}'}
                if isinstance(hosts_result, dict) and hosts_result.get('manual_action_required'):
                    response['hosts_instruction'] = hosts_result.get('instruction')
                return response
            else:
                return {'success': False, 'error': f'Failed to start containers: {start_result["error"]}'}

        except Exception as e:
            print(f"   ❌ Error updating domain: {str(e)}")
            return {'success': False, 'error': 'Failed to update domain; check the server logs.'}

    def update_project_config(self, project_name, **updates):
        """Apply dashboard configuration changes (domain, subfolder, SSL, Redis)."""
        project_path = self.projects_dir / project_name
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}

        stopped = False
        try:
            config = self.config_manager.read_project_config(project_path)
            if not config:
                return {'success': False, 'error': 'Project config not found'}

            current_host = config.get('domain', '').split('/', 1)[0]
            requested_domain = str(updates.get('custom_domain') or '').strip()
            subfolder = updates.get('subfolder', config.get('subfolder', '')) or ''

            if requested_domain:
                if not is_valid_domain(requested_domain):
                    return {'success': False, 'error': 'Invalid domain or subfolder'}
                domain_parts = requested_domain.split('/', 1)
                new_host = domain_parts[0]
                if len(domain_parts) == 2:
                    embedded_subfolder = domain_parts[1]
                    if subfolder and subfolder != embedded_subfolder:
                        return {'success': False, 'error': 'Subfolder specified twice'}
                    subfolder = embedded_subfolder
            else:
                new_host = current_host

            if not is_valid_subfolder(subfolder):
                return {'success': False, 'error': 'Invalid domain or subfolder'}

            enable_ssl = bool(updates.get('enable_ssl', config.get('enable_ssl', True)))
            enable_redis = bool(updates.get('enable_redis', config.get('enable_redis', True)))
            new_domain = f"{new_host}/{subfolder}" if subfolder else new_host

            updated_fields = [
                field for field, value in (
                    ('domain', new_domain),
                    ('subfolder', subfolder),
                    ('enable_ssl', enable_ssl),
                    ('enable_redis', enable_redis),
                )
                if config.get(field) != value
            ]

            if not updated_fields:
                return {
                    'success': True,
                    'message': 'No configuration changes',
                    'updated_fields': [],
                }

            if new_host != current_host:
                print(f"   🔄 Changing domain {current_host} → {new_host}")
                self.hosts_manager.remove_host(current_host)
                self.hosts_manager.add_host(new_host)
                if enable_ssl:
                    self.ssl_generator.generate_ssl_cert(project_name, new_host)
            elif enable_ssl and not config.get('enable_ssl', True):
                self.ssl_generator.generate_ssl_cert(project_name, new_host)

            self.config_manager.update_project_config(project_path, {
                'domain': new_domain,
                'subfolder': subfolder,
                'enable_ssl': enable_ssl,
                'enable_redis': enable_redis,
            })
            config.update({
                'domain': new_domain,
                'subfolder': subfolder,
                'enable_ssl': enable_ssl,
                'enable_redis': enable_redis,
            })

            self.docker_manager.stop_project(project_path)
            stopped = True

            ports = None
            if config.get('port_index'):
                ports = PortAllocator(self.projects_dir).get_ports_for_index(config['port_index'])

            self.docker_manager.create_docker_compose(
                project_path, config.get('name', project_name),
                config.get('wordpress_version') or 'latest',
                new_domain, enable_ssl, enable_redis, ports=ports)
            self.config_manager.create_nginx_config(
                project_path, config.get('name', project_name),
                new_domain, enable_ssl, subfolder)

            start_result = self.docker_manager.start_project(project_path)
            stopped = not start_result.get('success')
            if not start_result.get('success'):
                return {
                    'success': False,
                    'error': f'Configuration saved but containers failed to start: {start_result.get("error")}',
                }

            return {
                'success': True,
                'message': 'Project configuration updated',
                'updated_fields': updated_fields,
            }

        except Exception as e:
            print(f"   ❌ Error updating project config: {str(e)}")
            if stopped:
                # Don't leave a previously running project down after a failed
                # rebuild; starting again is safe (and idempotent).
                self.docker_manager.start_project(project_path)
            return {'success': False, 'error': 'Failed to update project configuration; check the server logs.'}

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
            return {'success': False, 'error': 'Failed to update repository; check the server logs.'}
    
    def link_existing_repository(self, project_name):
        """Link an existing manually cloned repository to wp-content"""
        project_path = self.projects_dir / project_name
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        
        try:
            config = self.config_manager.read_project_config(project_path)
            if not config:
                return {'success': False, 'error': 'Project config not found'}
            
            print(f"🔗 Linking existing repository for project: {project_name}")
            
            # Stop containers to avoid conflicts
            print(f"   🛑 Stopping containers...")
            self.docker_manager.stop_project(project_path)
            
            # Link repository
            result = self.repository_manager.link_existing_repository(project_path)
            
            if not result['success']:
                return result
            
            # Update config with repository structure info
            repo_structure = result.get('repository_structure')
            if repo_structure:
                updates = {
                    'repository_structure': {
                        'type': repo_structure['type'],
                        'has_wp_content': repo_structure['has_wp_content'],
                        'has_composer': repo_structure['has_composer'],
                        'has_package_json': repo_structure['has_package_json'],
                        'is_theme': repo_structure['is_theme'],
                        'is_plugin': repo_structure['is_plugin'],
                        'wp_content_path': str(repo_structure['wp_content_path']) if repo_structure['wp_content_path'] else None
                    }
                }
                # Try to get repo URL from git if available
                repo_info = self.repository_manager.get_repository_info(project_path)
                if repo_info.get('has_repository') and repo_info.get('remote_url') != 'Unknown':
                    updates['repo_url'] = repo_info['remote_url']
                
                self.config_manager.update_project_config(project_path, updates)
            
            # Start containers
            print(f"   🚀 Starting containers with linked repository...")
            start_result = self.docker_manager.start_project(project_path)
            
            if start_result['success']:
                print(f"   ✅ Repository linked successfully")
                return {'success': True, 'message': result['message']}
            else:
                return {'success': False, 'error': f'Failed to start containers: {start_result["error"]}'}
                
        except Exception as e:
            print(f"   ❌ Error linking repository: {str(e)}")
            return {'success': False, 'error': 'Failed to link repository; check the server logs.'}
    
    def update_project_with_database(self, project_name, db_file_path, backup_before_import=True):
        """Add an initial database to a project that was created without one"""
        project_path = self.projects_dir / project_name
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found', 'logs': []}
        
        try:
            config = self.config_manager.read_project_config(project_path)
            if not config:
                return {'success': False, 'error': 'Project config not found', 'logs': []}
            
            # Check if project already has a database file in config
            existing_db = config.get('db_file')
            if existing_db and Path(project_path / existing_db).exists():
                # Project already has a database, use regular import
                print(f"📋 Project already has a database, importing as replacement...")
                return self.import_database(project_name, db_file_path, backup_before_import)
            
            # Ensure project is running
            status = self.docker_manager.get_project_status(project_path)
            if status.get('status') != 'running':
                print(f"   🚀 Starting project to import initial database...")
                start_result = self.docker_manager.start_project(project_path)
                if not start_result.get('success'):
                    return {'success': False, 'error': f'Failed to start project: {start_result.get("error")}', 'logs': []}
                # Wait a moment for containers to be ready
                import time
                time.sleep(5)
            
            # Save database file to project data folder if it's not already there
            db_file_path_obj = Path(db_file_path)
            if not db_file_path_obj.is_absolute() or str(db_file_path_obj.parent) != str(project_path / 'data'):
                # Copy file to project data folder
                data_dir = project_path / 'data'
                data_dir.mkdir(exist_ok=True)
                target_path = data_dir / db_file_path_obj.name
                if db_file_path_obj.exists():
                    import shutil
                    shutil.copy2(db_file_path_obj, target_path)
                    db_file_path = str(target_path)
                else:
                    return {'success': False, 'error': f'Database file not found: {db_file_path}', 'logs': []}
            
            # Import the database
            print(f"📋 Importing initial database for project: {project_name}")
            result = self.database_manager.import_database(project_path, project_name, db_file_path, backup_before_import)
            
            # If import was successful, update config and ensure WordPress recognizes it
            if result.get('success'):
                # Update project config to track the database file
                db_filename = Path(db_file_path).name
                self.config_manager.update_project_config(project_path, {
                    'db_file': f"data/{db_filename}"
                })
                
                # Ensure WordPress recognizes the imported database
                print(f"   🔄 Ensuring WordPress recognizes imported database...")
                wp_result = self.wordpress_manager.ensure_wordpress_recognizes_database(project_path)
                if wp_result.get('success'):
                    result['message'] = result.get('message', 'Initial database imported successfully') + '. ' + wp_result.get('message', '')
            
            return result
                
        except Exception as e:
            print(f"   ❌ Error updating project with database: {str(e)}")
            return {
                'success': False,
                'error': 'Failed to update project with database; check the server logs.',
                'logs': [],
            }
    
    
    def _start_containers_with_setup(self, project_path, project_name, db_file_path):
        """Start containers and perform initial setup"""
        try:
            start_result = subprocess.run(
                compose_command('up', '-d'),
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if start_result.returncode == 0:
                print(f"   ✅ Docker containers started successfully")
                
                # Give containers a moment to fully start
                time.sleep(5)
                
                # Configure WordPress debug settings in wp-config.php
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
                        # Fix table prefix and ensure WordPress recognizes the imported database
                        print(f"   🔄 Ensuring WordPress recognizes imported database...")
                        self.wordpress_manager.ensure_wordpress_recognizes_database(project_path)
                    else:
                        print(f"   ⚠️  Warning: Database import failed: {db_import_result['error']}")

                return {'success': True}
            else:
                return {'success': False, 'error': f'Failed to start containers: {start_result.stderr}'}
                
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Container startup timed out'}
        except Exception as e:
            print(f"   ❌ Error starting containers: {str(e)}")
            return {'success': False, 'error': 'Container startup failed; check the server logs.'}
    
    def _cleanup_failed_project(self, project_path):
        """Clean up if project creation failed"""
        try:
            if project_path.exists():
                shutil.rmtree(project_path)
                print(f"   🧹 Cleaned up failed project directory")
        except Exception as e:
            print(f"Warning: cleanup failed: {e}")

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
                except Exception as e:
                    print(f"Warning: SSL cert age check failed: {e}")
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
    
    def fix_php_upload_limits(self, project_name):
        """PHP upload limits are now handled automatically in all projects"""
        project_path = self.projects_dir / project_name
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        return {'success': True, 'message': 'PHP upload limits are automatically configured (100MB)'}

    def migrate_project_ports(self, project_name):
        """Assign unique ports to an existing project that still uses default ports."""
        project_path = self.projects_dir / project_name
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}

        config = self.config_manager.read_project_config(project_path)
        if not config:
            return {'success': False, 'error': 'Project config not found'}

        if config.get('port_index'):
            ports = PortAllocator(self.projects_dir).get_ports_for_index(config['port_index'])
            return {'success': True, 'message': f'Already migrated (index {config["port_index"]})', 'ports': ports}

        allocator = PortAllocator(self.projects_dir)
        port_index = allocator.allocate_next_index()
        ports = allocator.get_ports_for_index(port_index)

        # Update config
        self.config_manager.update_project_config(project_path, {
            'port_index': port_index,
            'ports': ports,
        })

        # Rewrite .env with new ports
        self.docker_manager.create_docker_compose(
            project_path, config['name'],
            config.get('wordpress_version') or 'latest',
            config.get('domain', f'local.{project_name}.test'),
            config.get('enable_ssl', True),
            config.get('enable_redis', True),
            ports=ports,
        )

        # Regenerate nginx config (unchanged, but ensures consistency)
        self.config_manager.create_nginx_config(
            project_path, config['name'],
            config.get('domain', f'local.{project_name}.test'),
            config.get('enable_ssl', True),
            config.get('subfolder', ''),
        )

        return {
            'success': True,
            'message': f'Migrated to port index {port_index}',
            'port_index': port_index,
            'ports': ports,
        }

    def migrate_all_project_ports(self):
        """Migrate all existing projects to unique ports."""
        results = []
        for project_dir in sorted(self.projects_dir.iterdir()):
            if not project_dir.is_dir():
                continue
            config = self.config_manager.read_project_config(project_dir)
            if not config:
                continue
            name = config.get('name', project_dir.name)
            result = self.migrate_project_ports(name)
            results.append({'project': name, **result})
        return results
