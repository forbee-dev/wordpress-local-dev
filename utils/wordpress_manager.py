import subprocess
import shutil
from pathlib import Path


class WordPressManager:
    """Handles WordPress-specific operations"""
    
    def __init__(self, docker_manager):
        self.docker_manager = docker_manager
    
    def get_debug_logs(self, project_path, lines=50):
        """Get WordPress debug logs for a project"""
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        
        try:
            # Check if containers are running
            status = self.docker_manager.get_project_status(project_path)
            if status.get('status') != 'running':
                return {'success': False, 'error': 'Project must be running to view debug logs'}
            
            # Get debug logs from WordPress container
            result = self.docker_manager.exec_command_in_container(
                project_path, 'wordpress', ['tail', f'-{lines}', '/var/www/html/wp-content/debug.log']
            )
            
            if result['success']:
                return {'success': True, 'logs': result['output']}
            else:
                # If debug.log doesn't exist yet, return empty logs
                if "No such file or directory" in result['error']:
                    return {'success': True, 'logs': 'No debug logs found yet. Debug logging is enabled but no errors have been logged.'}
                else:
                    return {'success': False, 'error': f'Error reading debug logs: {result["error"]}'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def clear_debug_logs(self, project_path):
        """Clear WordPress debug logs for a project"""
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        
        try:
            # Check if containers are running
            status = self.docker_manager.get_project_status(project_path)
            if status.get('status') != 'running':
                return {'success': False, 'error': 'Project must be running to clear debug logs'}
            
            # Clear debug logs in WordPress container
            result = self.docker_manager.exec_command_in_container(
                project_path, 'wordpress', ['sh', '-c', 'echo "" > /var/www/html/wp-content/debug.log']
            )
            
            if result['success']:
                return {'success': True, 'message': 'Debug logs cleared successfully'}
            else:
                return {'success': False, 'error': f'Error clearing debug logs: {result["error"]}'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def fix_wp_config_debug(self, project_path):
        """Fix wp-config.php to properly read debug environment variables"""
        try:
            # Create a temporary PHP script file
            fix_script_path = project_path / "fix_debug.php"
            fix_script_content = '''<?php
$content = file_get_contents('/var/www/html/wp-config.php');

$old = "define( 'WP_DEBUG', !!getenv_docker('WORDPRESS_DEBUG', '') );";
$new = "define( 'WP_DEBUG', !!getenv_docker('WORDPRESS_DEBUG', '') );
define( 'WP_DEBUG_LOG', !!getenv_docker('WORDPRESS_DEBUG_LOG', '') );
define( 'WP_DEBUG_DISPLAY', !!getenv_docker('WORDPRESS_DEBUG_DISPLAY', '') );";

$content = str_replace($old, $new, $content);
file_put_contents('/var/www/html/wp-config.php', $content);
echo "wp-config.php updated successfully\\n";
?>'''
            
            # Write the script to a file
            with open(fix_script_path, 'w') as f:
                f.write(fix_script_content)
            
            # Copy the script to wp-content directory
            wp_content_script_path = project_path / "wp-content" / "fix_debug.php"
            shutil.copy2(fix_script_path, wp_content_script_path)
            
            # Run the fix script in the WordPress container
            result = self.docker_manager.exec_command_in_container(
                project_path, 'wordpress', ['php', '/var/www/html/wp-content/fix_debug.php']
            )
            
            # Clean up the temporary files
            if fix_script_path.exists():
                fix_script_path.unlink()
            if wp_content_script_path.exists():
                wp_content_script_path.unlink()
            
            if result['success']:
                print(f"   ✅ WordPress debug configuration updated")
                return True
            else:
                print(f"   ⚠️  Warning: Could not update wp-config.php debug settings: {result['error']}")
                return False
                
        except Exception as e:
            print(f"   ⚠️  Warning: Error updating wp-config.php: {str(e)}")
            return False
    
    def run_wp_cli_command(self, project_path, command):
        """Run a WP CLI command on a project"""
        try:
            if not project_path.exists():
                return {'success': False, 'error': 'Project not found'}
            
            # Check if WP CLI service exists
            if not self.docker_manager.has_wpcli_service(project_path):
                return {'success': False, 'error': 'WP CLI service not configured. Please add WP CLI to this project first.'}
            
            # Run the WP CLI command
            print(f"🔧 Running WP CLI command: {command}")
            result = self.docker_manager.run_wp_cli_command(project_path, command)
            
            if result['success']:
                print(f"   ✅ Command executed successfully")
            else:
                print(f"   ❌ Command failed: {result['error']}")
            
            return result
                
        except Exception as e:
            print(f"   ❌ Error running WP CLI command: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def add_wpcli_to_project(self, project_path, config_manager, docker_manager, config):
        """Add WP CLI service to existing project"""
        try:
            if not project_path.exists():
                return {'success': False, 'error': 'Project not found'}
            
            docker_compose_path = project_path / "docker-compose.yml"
            if docker_compose_path.exists():
                # Check if WP CLI is already present
                with open(docker_compose_path, 'r') as f:
                    compose_content = f.read()
                
                if "wpcli:" in compose_content:
                    print(f"   ✅ WP CLI already configured")
                    return {'success': True, 'message': 'WP CLI is already configured for this project'}
                
                print(f"   🔄 Updating docker-compose.yml to include WP CLI...")
                # Regenerate docker-compose with WP CLI
                docker_manager.create_docker_compose(
                    project_path, 
                    config['name'], 
                    config.get('wordpress_version', 'php8.3'),
                    config['domain'], 
                    config.get('enable_ssl', True), 
                    config.get('enable_redis', True)
                )
                print(f"   ✅ Updated docker-compose.yml with WP CLI service")
                
                return {'success': True, 'message': 'WP CLI service added successfully. Use "docker-compose --profile cli run --rm wpcli <command>" to run WP CLI commands.'}
            else:
                return {'success': False, 'error': 'docker-compose.yml not found'}
                
        except Exception as e:
            print(f"   ❌ Error adding WP CLI: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def update_wordpress_version(self, project_path, config_manager, docker_manager, new_version):
        """Update WordPress version for an existing project"""
        try:
            if not project_path.exists():
                return {'success': False, 'error': 'Project not found'}
            
            # Read current config
            config = config_manager.read_project_config(project_path)
            if not config:
                return {'success': False, 'error': 'Project config not found'}
            
            old_version = config.get('wordpress_version', 'unknown')
            print(f"🔄 Updating WordPress version from {old_version} to {new_version}")
            
            # Update config
            config['wordpress_version'] = new_version
            
            # Stop containers first
            print(f"   🛑 Stopping containers...")
            docker_manager.stop_project(project_path)
            
            # Rebuild docker-compose.yml with new version
            print(f"   🔄 Updating docker-compose.yml...")
            docker_manager.create_docker_compose(
                project_path,
                config['name'],
                new_version,
                config['domain'],
                config.get('enable_ssl', True),
                config.get('enable_redis', True)
            )
            
            # Save updated config
            config_manager.update_project_config(project_path, {'wordpress_version': new_version})
            
            # Start containers with new version
            print(f"   🚀 Starting containers with new WordPress version...")
            start_result = docker_manager.start_project(project_path)
            
            if start_result['success']:
                print(f"   ✅ WordPress version updated successfully")
                return {'success': True, 'message': f'WordPress version updated from {old_version} to {new_version}'}
            else:
                return {'success': False, 'error': f'Failed to start containers: {start_result["error"]}'}
                
        except Exception as e:
            print(f"   ❌ Error updating WordPress version: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def install_wordpress(self, project_path, site_title, admin_user, admin_password, admin_email):
        """Install WordPress using WP CLI"""
        try:
            # Check if WP CLI is available
            if not self.docker_manager.has_wpcli_service(project_path):
                return {'success': False, 'error': 'WP CLI service not configured'}
            
            # Get project domain from config
            config_manager = None  # This would need to be injected
            config = config_manager.read_project_config(project_path) if config_manager else None
            site_url = f"https://{config.get('domain', 'localhost')}" if config else "https://localhost"
            
            # Install WordPress
            install_command = f"core install --url='{site_url}' --title='{site_title}' --admin_user='{admin_user}' --admin_password='{admin_password}' --admin_email='{admin_email}'"
            
            result = self.run_wp_cli_command(project_path, install_command)
            
            if result['success']:
                return {
                    'success': True,
                    'message': f'WordPress installed successfully. Admin user: {admin_user}',
                    'site_url': site_url,
                    'admin_url': f"{site_url}/wp-admin"
                }
            else:
                return result
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def create_user(self, project_path, username, email, role='subscriber', password=None):
        """Create a WordPress user using WP CLI"""
        try:
            if not self.docker_manager.has_wpcli_service(project_path):
                return {'success': False, 'error': 'WP CLI service not configured'}
            
            # Generate password if not provided
            if not password:
                import secrets
                import string
                password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
            
            # Create user
            create_command = f"user create {username} {email} --role={role} --user_pass='{password}'"
            
            result = self.run_wp_cli_command(project_path, create_command)
            
            if result['success']:
                return {
                    'success': True,
                    'message': f'User {username} created successfully',
                    'username': username,
                    'password': password,
                    'email': email,
                    'role': role
                }
            else:
                return result
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def activate_plugin(self, project_path, plugin_name):
        """Activate a WordPress plugin using WP CLI"""
        try:
            if not self.docker_manager.has_wpcli_service(project_path):
                return {'success': False, 'error': 'WP CLI service not configured'}
            
            result = self.run_wp_cli_command(project_path, f"plugin activate {plugin_name}")
            return result
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def activate_theme(self, project_path, theme_name):
        """Activate a WordPress theme using WP CLI"""
        try:
            if not self.docker_manager.has_wpcli_service(project_path):
                return {'success': False, 'error': 'WP CLI service not configured'}
            
            result = self.run_wp_cli_command(project_path, f"theme activate {theme_name}")
            return result
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def search_replace_url(self, project_path, old_url, new_url):
        """Perform search and replace on WordPress URLs using WP CLI"""
        try:
            if not self.docker_manager.has_wpcli_service(project_path):
                return {'success': False, 'error': 'WP CLI service not configured'}
            
            result = self.run_wp_cli_command(project_path, f"search-replace '{old_url}' '{new_url}' --dry-run")
            
            if result['success']:
                # If dry run succeeded, do the actual replacement
                result = self.run_wp_cli_command(project_path, f"search-replace '{old_url}' '{new_url}'")
                if result['success']:
                    return {
                        'success': True,
                        'message': f'Successfully replaced {old_url} with {new_url}',
                        'output': result['output']
                    }
            
            return result
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
