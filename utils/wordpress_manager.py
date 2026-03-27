import subprocess
import shutil
import re
from pathlib import Path
from .docker_compose_detect import compose_command
from .port_allocator import PortAllocator


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

    def get_wp_config(self, project_path):
        """Read wp-config.php from the WordPress container. Project must be running."""
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        try:
            status = self.docker_manager.get_project_status(project_path)
            if status.get('status') != 'running':
                return {'success': False, 'error': 'Project must be running to access wp-config.php'}
            result = self.docker_manager.exec_command_in_container(
                project_path, 'wordpress', ['cat', '/var/www/html/wp-config.php']
            )
            if result['success']:
                return {'success': True, 'content': result['output']}
            return {'success': False, 'error': result.get('error') or 'Failed to read wp-config.php'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def regenerate_wp_config(self, project_path):
        """
        Regenerate wp-config.php from environment variables.
        Deletes wp-config.php and restarts the WordPress container so the official
        Docker entrypoint recreates it from wp-config-docker.php (full config with
        DB_*, salts, table prefix, etc. via getenv_docker).
        We do NOT use 'wp config create' — it can produce minimal/incomplete configs
        (e.g. only DB_NAME + debug) when run without explicit --dbname/--dbuser/etc.
        """
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        try:
            status = self.docker_manager.get_project_status(project_path)
            if status.get('status') != 'running':
                return {'success': False, 'error': 'Project must be running to regenerate wp-config.php'}
            
            print(f"   🗑️  Removing existing wp-config.php...")
            delete_result = self.docker_manager.exec_command_in_container(
                project_path, 'wordpress',
                ['sh', '-c', 'rm -f /var/www/html/wp-config.php']
            )
            
            if not delete_result.get('success', False):
                return {'success': False, 'error': 'Failed to remove wp-config.php'}
            
            print(f"   ✅ Removed wp-config.php")
            print(f"   🔄 Restarting WordPress container to regenerate wp-config.php from environment variables...")
            restart_result = self.docker_manager.restart_container(project_path, 'wordpress')
            if not restart_result.get('success', False):
                return {'success': False, 'error': 'Failed to restart WordPress container'}
            
            import time
            time.sleep(8)  # Give WordPress entrypoint time to recreate wp-config from wp-config-docker.php
            return {'success': True, 'message': 'wp-config.php regeneration triggered. WordPress will recreate it from environment variables.'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def update_wp_config(self, project_path, content):
        """Overwrite wp-config.php in the WordPress container. Project must be running."""
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found'}
        try:
            status = self.docker_manager.get_project_status(project_path)
            if status.get('status') != 'running':
                return {'success': False, 'error': 'Project must be running to update wp-config.php'}
            data_dir = project_path / 'data'
            data_dir.mkdir(exist_ok=True)
            tmp_path = data_dir / '.wp-config-edit.tmp'
            tmp_path.write_text(content, encoding='utf-8')
            try:
                container_id = self.docker_manager.get_container_id(project_path, 'wordpress')
                if not container_id:
                    return {'success': False, 'error': 'WordPress container not found'}
                cp = self.docker_manager.copy_file_to_container(
                    container_id, str(tmp_path), '/tmp/wp-config-edit.php'
                )
                if not cp['success']:
                    return {'success': False, 'error': cp.get('error') or 'Failed to copy file into container'}
                mv = self.docker_manager.exec_command_in_container(
                    project_path, 'wordpress',
                    ['sh', '-c', 'mv /tmp/wp-config-edit.php /var/www/html/wp-config.php']
                )
                if not mv['success']:
                    return {'success': False, 'error': mv.get('error') or 'Failed to replace wp-config.php'}
                return {'success': True, 'message': 'wp-config.php updated successfully'}
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def fix_wp_config_debug(self, project_path):
        """Fix wp-config.php to set WordPress debug constants to the correct values"""
        try:
            # Create a temporary PHP script file
            fix_script_path = project_path / "fix_debug.php"
            fix_script_content = '''<?php
$config_path = '/var/www/html/wp-config.php';

// Guard: do not run if wp-config.php does not exist or is too small
// (Docker entrypoint may not have generated it yet)
if (!file_exists($config_path)) {
    echo "wp-config.php does not exist yet, skipping debug config\\n";
    exit(0);
}
$content = file_get_contents($config_path);
if ($content === false || strlen($content) < 100) {
    echo "wp-config.php is empty or incomplete, skipping debug config\\n";
    exit(0);
}

// Remove any existing WP_DEBUG, WP_DEBUG_LOG, or WP_DEBUG_DISPLAY lines
$lines = explode("\\n", $content);
$new_lines = [];

foreach ($lines as $i => $line) {
    $trimmed = trim($line);
    // Skip lines that define WP_DEBUG constants (handle both single and double quotes)
    if (preg_match("/define\\s*\\(\\s*['\\"](WP_DEBUG|WP_DEBUG_LOG|WP_DEBUG_DISPLAY)['\\"]/i", $trimmed)) {
        continue;
    }
    $new_lines[] = $line;
}

$content = implode("\\n", $new_lines);

// Find the position to insert the debug constants
// Look for the comment about debugging mode first
$insert_position = false;
$comment_marker = "For developers: WordPress debugging mode";
$comment_pos = strpos($content, $comment_marker);

if ($comment_pos !== false) {
    // Find the end of the comment block (after the closing */)
    $comment_end = strpos($content, "*/", $comment_pos);
    if ($comment_end !== false) {
        // Find the next newline after the comment
        $insert_position = strpos($content, "\\n", $comment_end);
        if ($insert_position !== false) {
            $insert_position += 1; // Position after the newline
        }
    }
}

// If not found, look for "stop editing" comment
if ($insert_position === false) {
    $stop_editing = strpos($content, "stop editing");
    if ($stop_editing !== false) {
        // Find the newline before "stop editing"
        $insert_position = strrpos(substr($content, 0, $stop_editing), "\\n");
        if ($insert_position !== false) {
            $insert_position += 1; // Position after the newline
        }
    }
}

// Default: insert before the last closing PHP tag or at end of file
if ($insert_position === false) {
    $php_close = strrpos($content, "?>");
    if ($php_close !== false) {
        $insert_position = $php_close;
    } else {
        $insert_position = strlen($content);
    }
}

// Insert the debug constants
$debug_constants = "\\n// Enable WP_DEBUG mode\\n";
$debug_constants .= "define( 'WP_DEBUG', true );\\n";
$debug_constants .= "define( 'WP_DEBUG_LOG', true );\\n";
$debug_constants .= "define( 'WP_DEBUG_DISPLAY', false );\\n";

$content = substr_replace($content, $debug_constants, $insert_position, 0);

// Write the updated content
file_put_contents($config_path, $content);
echo "wp-config.php updated successfully\\n";
?>'''
            
            # Write the script to a file
            with open(fix_script_path, 'w') as f:
                f.write(fix_script_content)
            
            # Copy the script to wp-content directory
            wp_content_script_path = project_path / "wp-content" / "fix_debug.php"
            wp_content_script_path.parent.mkdir(parents=True, exist_ok=True)
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
    
    def _get_table_prefix_from_mysql(self, project_path):
        """
        Discover actual WordPress table prefix via raw MySQL SHOW TABLES.
        Does not use WP-CLI, so it works even when wp-config has wrong $table_prefix.
        Returns (options_table, table_prefix) or (None, None) on failure.
        """
        env_vars = {}
        env_file = project_path / '.env'
        if env_file.exists():
            try:
                with open(env_file, 'r') as f:
                    for line in f:
                        if '=' in line and not line.strip().startswith('#'):
                            k, v = line.strip().split('=', 1)
                            env_vars[k] = v
            except Exception:
                pass
        db_name = env_vars.get('DB_NAME', 'wordpress')
        db_user = env_vars.get('DB_USER', 'wordpress')
        db_password = env_vars.get('DB_PASSWORD', 'wordpress_password')
        try:
            result = subprocess.run(
                compose_command('exec', '-T', 'mysql',
                    'mysql', f'-u{db_user}', f'-p{db_password}', db_name,
                    '-e', 'SHOW TABLES;'),
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0 or not result.stdout.strip():
                return (None, None)
            lines = [ln.strip() for ln in result.stdout.strip().split('\n') if ln.strip()]
            options_table = None
            table_prefix = 'wp_'
            for ln in lines:
                if 'options' in ln.lower() and '_options' in ln and 'table' not in ln.lower():
                    options_table = ln
                    table_prefix = ln.split('_options')[0] + '_'
                    break
            return (options_table, table_prefix) if options_table else (None, None)
        except Exception:
            return (None, None)
    
    def _update_wp_config_table_prefix(self, project_path, new_prefix):
        """Update $table_prefix in wp-config.php to match the database. Returns bool."""
        r = self.get_wp_config(project_path)
        if not r.get('success') or not r.get('content'):
            return False
        content = r['content']
        replacement = f"$table_prefix = '{new_prefix}';"
        # Classic: $table_prefix = 'wp_'; or $table_prefix = "wp_";
        classic = re.search(r"\$table_prefix\s*=\s*['\"][^'\"]*['\"]\s*;", content)
        # Docker getenv: $table_prefix = getenv_docker('WORDPRESS_TABLE_PREFIX', 'wp_');
        getenv_line = re.search(
            r"\$table_prefix\s*=\s*getenv_docker\s*\(\s*['\"]WORDPRESS_TABLE_PREFIX['\"]\s*,\s*['\"][^'\"]*['\"]\s*\)\s*;",
            content
        )
        if classic:
            replaced = re.sub(r"\$table_prefix\s*=\s*['\"][^'\"]*['\"]\s*;", replacement, content, count=1)
        elif getenv_line:
            replaced = re.sub(
                r"\$table_prefix\s*=\s*getenv_docker\s*\(\s*['\"]WORDPRESS_TABLE_PREFIX['\"]\s*,\s*['\"][^'\"]*['\"]\s*\)\s*;",
                replacement,
                content,
                count=1
            )
        else:
            return False
        if replaced == content:
            return False
        up = self.update_wp_config(project_path, replaced)
        return up.get('success', False)
    
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
                
                print(f"   Updating docker-compose.yml to include WP CLI...")
                # Regenerate docker-compose with WP CLI, preserving existing ports
                existing_ports = None
                if config.get('port_index'):
                    projects_dir = project_path.parent
                    allocator = PortAllocator(projects_dir)
                    existing_ports = allocator.get_ports_for_index(config['port_index'])

                docker_manager.create_docker_compose(
                    project_path,
                    config['name'],
                    config.get('wordpress_version', 'php8.3'),
                    config['domain'],
                    config.get('enable_ssl', True),
                    config.get('enable_redis', True),
                    ports=existing_ports
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
            
            # Rebuild docker-compose.yml with new version, preserving existing ports
            print(f"   Updating docker-compose.yml...")
            existing_ports = None
            if config.get('port_index'):
                projects_dir = project_path.parent
                allocator = PortAllocator(projects_dir)
                existing_ports = allocator.get_ports_for_index(config['port_index'])

            docker_manager.create_docker_compose(
                project_path,
                config['name'],
                new_version,
                config['domain'],
                config.get('enable_ssl', True),
                config.get('enable_redis', True),
                ports=existing_ports
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
    
    def fix_database_connection(self, project_path):
        """
        Comprehensive fix for database connection issues.
        Waits for MySQL, verifies wp-config.php, tests connection, and creates database if needed.
        """
        import time
        
        try:
            # Check if containers are running
            status = self.docker_manager.get_project_status(project_path)
            if status.get('status') != 'running':
                return {'success': False, 'error': 'Project must be running to fix database connection'}
            
            print(f"   🔧 Diagnosing database connection issue...")
            
            # Read .env file to get database credentials
            env_file = project_path / '.env'
            env_vars = {}
            if env_file.exists():
                with open(env_file, 'r') as f:
                    for line in f:
                        if '=' in line and not line.startswith('#'):
                            key, value = line.strip().split('=', 1)
                            env_vars[key] = value
            
            db_name = env_vars.get('DB_NAME', 'wordpress')
            db_user = env_vars.get('DB_USER', 'wordpress')
            db_password = env_vars.get('DB_PASSWORD', 'wordpress_password')
            db_root_password = env_vars.get('DB_ROOT_PASSWORD', 'root_password')
            
            print(f"   📋 Database: {db_name}, User: {db_user}")
            
            # Step 1: Wait for MySQL to be ready
            print(f"   ⏳ Waiting for MySQL to be ready...")
            mysql_ready = False
            for attempt in range(30):  # Wait up to 30 seconds
                # Use MYSQL_PWD environment variable to avoid password in command line
                result = self.docker_manager.exec_command_in_container(
                    project_path, 'mysql', 
                    ['sh', '-c', f'MYSQL_PWD={db_root_password} mysqladmin ping -h localhost -u root']
                )
                if result.get('success', False) and 'mysqld is alive' in result.get('output', ''):
                    mysql_ready = True
                    print(f"   ✅ MySQL is ready")
                    break
                time.sleep(1)
            
            if not mysql_ready:
                print(f"   ⚠️  MySQL may not be fully ready, but continuing...")
            
            # Step 2: Ensure database exists (using MYSQL_PWD to avoid password in command)
            print(f"   🔍 Checking if database '{db_name}' exists...")
            check_db_cmd = f"MYSQL_PWD={db_root_password} mysql -uroot -e \"SHOW DATABASES LIKE '{db_name}';\" | grep -q '{db_name}' && echo 'EXISTS' || echo 'NOT_EXISTS'"
            result = self.docker_manager.exec_command_in_container(
                project_path, 'mysql', ['sh', '-c', check_db_cmd]
            )
            
            db_exists = 'EXISTS' in result.get('output', '')
            
            if not db_exists:
                print(f"   📦 Creating database '{db_name}'...")
                create_db_cmd = f"MYSQL_PWD={db_root_password} mysql -uroot -e \"CREATE DATABASE IF NOT EXISTS \\`{db_name}\\`;\""
                result = self.docker_manager.exec_command_in_container(
                    project_path, 'mysql', ['sh', '-c', create_db_cmd]
                )
                if result.get('success', False):
                    print(f"   ✅ Database created")
                else:
                    print(f"   ⚠️  Warning: Could not create database: {result.get('error', 'Unknown error')}")
            
            # Step 3: Ensure user has permissions (MySQL 8.0+ uses CREATE USER then GRANT)
            print(f"   🔐 Ensuring database user has proper permissions...")
            # First, try to create user if it doesn't exist, then grant privileges
            grant_cmd = f"""MYSQL_PWD={db_root_password} mysql -uroot -e "
                CREATE USER IF NOT EXISTS '{db_user}'@'%' IDENTIFIED BY '{db_password}';
                GRANT ALL PRIVILEGES ON \\`{db_name}\\`.* TO '{db_user}'@'%';
                FLUSH PRIVILEGES;
            \""""
            result = self.docker_manager.exec_command_in_container(
                project_path, 'mysql', ['sh', '-c', grant_cmd]
            )
            if result.get('success', False):
                print(f"   ✅ Permissions granted")
            else:
                print(f"   ⚠️  Warning: Could not grant permissions: {result.get('error', 'Unknown error')}")
            
            # Step 4: Test database connection from WordPress container
            print(f"   🧪 Testing database connection from WordPress container...")
            test_script = f"""php -r "
            \\$db_host = 'mysql';
            \\$db_name = '{db_name}';
            \\$db_user = '{db_user}';
            \\$db_password = '{db_password}';
            try {{
                \\$conn = new mysqli(\\$db_host, \\$db_user, \\$db_password, \\$db_name);
                if (\\$conn->connect_error) {{
                    echo 'CONNECTION_FAILED: ' . \\$conn->connect_error;
                    exit(1);
                }} else {{
                    echo 'CONNECTION_SUCCESS';
                    \\$conn->close();
                }}
            }} catch (Exception \\$e) {{
                echo 'CONNECTION_ERROR: ' . \\$e->getMessage();
                exit(1);
            }}
            " """
            
            result = self.docker_manager.exec_command_in_container(
                project_path, 'wordpress', ['sh', '-c', test_script]
            )
            
            if 'CONNECTION_SUCCESS' in result.get('output', ''):
                print(f"   ✅ Database connection test successful")
            else:
                print(f"   ⚠️  Database connection test failed: {result.get('output', result.get('error', 'Unknown error'))}")
            
            # Step 5: Verify and fix wp-config.php
            print(f"   🔍 Verifying wp-config.php...")
            wp_config_result = self.get_wp_config(project_path)
            
            # Check if wp-config.php exists and is readable
            if not wp_config_result.get('success', False):
                print(f"   ⚠️  wp-config.php not found or unreadable")
                print(f"   🔄 Regenerating wp-config.php from environment variables...")
                # Use the regenerate function
                regenerate_result = self.regenerate_wp_config(project_path)
                if regenerate_result.get('success', False):
                    print(f"   ✅ wp-config.php regeneration triggered")
                    # Try to read again after regeneration
                    time.sleep(3)
                    wp_config_result = self.get_wp_config(project_path)
                else:
                    print(f"   ⚠️  Could not regenerate wp-config.php: {regenerate_result.get('error', 'Unknown error')}")
            
            # Now check if we need to fix DB_HOST
            if wp_config_result.get('success', False):
                wp_config = wp_config_result.get('content', '')
                
                # Only fix DB_HOST if it's set to 'localhost' (the main issue)
                # WordPress should have generated it correctly from environment variables, but sometimes it doesn't
                db_host_wrong = False
                if "define( 'DB_HOST', 'localhost'" in wp_config or 'define( "DB_HOST", "localhost"' in wp_config:
                    print(f"   ⚠️  wp-config.php has DB_HOST set to 'localhost' (should be 'mysql')")
                    db_host_wrong = True
                elif "'DB_HOST'" not in wp_config and '"DB_HOST"' not in wp_config:
                    print(f"   ⚠️  wp-config.php DB_HOST not found - may need regeneration")
                    db_host_wrong = True
                
                if db_host_wrong:
                    import re
                    # Only fix DB_HOST - be very careful to preserve everything else
                    # Match: define( 'DB_HOST', 'anything' ); or define( "DB_HOST", "anything" );
                    original_config = wp_config
                    has_db_host_line = bool(re.search(r"define\s*\(\s*['\"]DB_HOST['\"]\s*,\s*['\"]", wp_config))

                    if has_db_host_line:
                        print(f"   🔧 Fixing DB_HOST in wp-config.php (surgical fix - only changing DB_HOST)...")
                        # Fix single quotes
                        wp_config = re.sub(
                            r"(define\s*\(\s*['\"]DB_HOST['\"]\s*,\s*['\"])([^'\"]+)(['\"])",
                            r"\1mysql\3",
                            wp_config
                        )
                        # Fix double quotes
                        wp_config = re.sub(
                            r'(define\s*\(\s*["\']DB_HOST["\']\s*,\s*["\'])([^"\']+)(["\'])',
                            r'\1mysql\3',
                            wp_config
                        )
                        if wp_config != original_config:
                            update_result = self.update_wp_config(project_path, wp_config)
                            if update_result.get('success', False):
                                print(f"   ✅ Fixed DB_HOST in wp-config.php (changed to 'mysql')")
                            else:
                                print(f"   ⚠️  Warning: Could not update wp-config.php: {update_result.get('error', 'Unknown error')}")
                        else:
                            print(f"   ⚠️  Could not find DB_HOST definition to fix")
                    else:
                        # DB_HOST missing entirely (e.g. minimal/broken wp-config) — regenerate full config
                        print(f"   🔄 Regenerating wp-config.php (DB_HOST missing, config incomplete)...")
                        regenerate_result = self.regenerate_wp_config(project_path)
                        if regenerate_result.get('success', False):
                            print(f"   ✅ wp-config.php regenerated with full config from environment variables")
                        else:
                            print(f"   ⚠️  Could not regenerate wp-config.php: {regenerate_result.get('error', 'Unknown error')}")
                else:
                    # Check if DB_HOST is already correct
                    if "define( 'DB_HOST', 'mysql'" in wp_config or 'define( "DB_HOST", "mysql"' in wp_config:
                        print(f"   ✅ wp-config.php DB_HOST is correct ('mysql')")
                    else:
                        print(f"   ℹ️  wp-config.php DB_HOST appears to be set (not 'localhost')")
            else:
                print(f"   ⚠️  Could not read wp-config.php after regeneration attempt")
                print(f"   ℹ️  WordPress should regenerate wp-config.php from environment variables on next container start")
            
            # Step 6: Restart WordPress container to apply changes
            print(f"   🔄 Restarting WordPress container...")
            restart_result = self.docker_manager.restart_container(project_path, 'wordpress')
            if restart_result.get('success', False):
                time.sleep(3)
                print(f"   ✅ WordPress container restarted")
            
            return {
                'success': True, 
                'message': 'Database connection fix completed. Please refresh your browser.'
            }
            
        except Exception as e:
            return {'success': False, 'error': f'Error fixing database connection: {str(e)}'}
    
    def verify_database_connection(self, project_path):
        """Verify WordPress can connect to the database after import"""
        try:
            # Check if containers are running
            status = self.docker_manager.get_project_status(project_path)
            if status.get('status') != 'running':
                return {'success': False, 'error': 'Project must be running to verify database connection'}
            
            # Use WP CLI to check if WordPress can connect to the database
            if self.docker_manager.has_wpcli_service(project_path):
                result = self.run_wp_cli_command(project_path, "core is-installed")
                # If WordPress is installed, the command will succeed
                # If not installed, it will return an error, which is also fine - means database is empty
                return {'success': True, 'message': 'Database connection verified'}
            else:
                # If WP CLI is not available, just restart WordPress container to clear cache
                print(f"   🔄 Restarting WordPress container to recognize imported database...")
                restart_result = self.docker_manager.restart_container(project_path, 'wordpress')
                if restart_result.get('success', False):
                    return {'success': True, 'message': 'WordPress container restarted to recognize imported database'}
                else:
                    return {'success': True, 'message': 'Database imported (WordPress will recognize it on next access)'}
                
        except Exception as e:
            # Even if verification fails, the database was imported successfully
            return {'success': True, 'message': f'Database imported (verification warning: {str(e)})'}
    
    def ensure_wordpress_recognizes_database(self, project_path):
        """Ensure WordPress recognizes the imported database by using comprehensive install detection fix"""
        try:
            # Check if containers are running
            status = self.docker_manager.get_project_status(project_path)
            if status.get('status') != 'running':
                return {'success': False, 'error': 'Project must be running'}
            
            # Use the comprehensive fix_wordpress_install_detection function
            # which checks if WordPress is installed, verifies database connection,
            # clears cache, and performs necessary restarts
            return self.fix_wordpress_install_detection(project_path)
                
        except Exception as e:
            # Even if fix fails, the database was imported successfully
            return {'success': True, 'message': f'Database imported (install detection warning: {str(e)})'}
    
    def fix_wordpress_install_detection(self, project_path):
        """
        Fix WordPress redirecting to install.php when database is already imported.
        Uses WP-CLI to directly check and fix the installation state.
        """
        try:
            import time
            import json
            from pathlib import Path
            
            # Check if containers are running
            status = self.docker_manager.get_project_status(project_path)
            if status.get('status') != 'running':
                return {'success': False, 'error': 'Project must be running to fix install detection'}
            
            print(f"   🔧 Fixing WordPress install detection using WP-CLI...")
            
            # Step 1: Check if WP CLI is available
            if not self.docker_manager.has_wpcli_service(project_path):
                print(f"   ⚠️  WP CLI not available, restarting WordPress container...")
                restart_result = self.docker_manager.restart_container(project_path, 'wordpress')
                if restart_result.get('success', False):
                    time.sleep(3)
                    return {'success': True, 'message': 'WordPress container restarted. Please refresh your browser.'}
                else:
                    return {'success': False, 'error': 'Failed to restart WordPress container'}
            
            # Step 2: Check if WordPress thinks it's installed
            is_installed_result = self.run_wp_cli_command(project_path, "core is-installed")
            
            if is_installed_result.get('success', False):
                print(f"   ✅ WordPress correctly detects installation")
                return {'success': True, 'message': 'WordPress installation is correctly detected'}
            
            # Step 3: Discover actual table prefix via raw MySQL (no WP-CLI)
            # WP-CLI fails when wp-config has $table_prefix='wp_' but DB uses e.g. EWZ30HiS_
            print(f"   🔍 Discovering database tables and table prefix...")
            options_table, table_prefix = self._get_table_prefix_from_mysql(project_path)
            if not options_table:
                return {'success': False, 'error': 'No database tables or options table found. Please verify the database was imported correctly.'}
            print(f"   ✅ Found options table: {options_table} (prefix: {table_prefix})")
            
            # Step 4: If DB uses custom prefix, update wp-config and restart WordPress
            if table_prefix != 'wp_':
                print(f"   🔄 Database uses custom prefix '{table_prefix}'; syncing wp-config.php...")
                if self._update_wp_config_table_prefix(project_path, table_prefix):
                    print(f"   ✅ Updated wp-config.php table prefix to '{table_prefix}'")
                    self.docker_manager.restart_container(project_path, 'wordpress')
                    time.sleep(4)
                else:
                    print(f"   ⚠️  Could not update wp-config table prefix; continuing anyway.")
            
            # Step 5: Check database connection via WP-CLI (now prefix should match)
            print(f"   🔍 Checking database connection...")
            db_check_result = self.run_wp_cli_command(project_path, "option get siteurl")
            
            if not db_check_result.get('success', False):
                print(f"   ⚠️  Database connection issue: {db_check_result.get('error', 'Unknown error')}")
                print(f"   🔄 Restarting database and WordPress containers...")
                self.docker_manager.restart_container(project_path, 'mysql')
                time.sleep(2)
                self.docker_manager.restart_container(project_path, 'wordpress')
                
                print(f"   ⏳ Waiting for MySQL to be ready after restart...")
                env_file = project_path / '.env'
                db_root_password = 'root_password'
                if env_file.exists():
                    with open(env_file, 'r') as f:
                        for line in f:
                            if 'DB_ROOT_PASSWORD' in line and '=' in line:
                                db_root_password = line.split('=', 1)[1].strip()
                                break
                
                mysql_ready = False
                for attempt in range(30):
                    result = self.docker_manager.exec_command_in_container(
                        project_path, 'mysql', 
                        ['sh', '-c', f'MYSQL_PWD={db_root_password} mysqladmin ping -h localhost -u root']
                    )
                    if result.get('success', False) and 'mysqld is alive' in result.get('output', ''):
                        mysql_ready = True
                        print(f"   ✅ MySQL is ready")
                        break
                    time.sleep(1)
                
                if not mysql_ready:
                    print(f"   ⚠️  MySQL may not be fully ready, but continuing...")
                time.sleep(2)
                
                print(f"   🔄 Retrying database connection check...")
                for retry in range(5):
                    db_check_result = self.run_wp_cli_command(project_path, "option get siteurl")
                    if db_check_result.get('success', False):
                        print(f"   ✅ Database connection successful")
                        break
                    if retry < 4:
                        print(f"   ⏳ Retry {retry + 1}/5...")
                        time.sleep(2)
                
                if not db_check_result.get('success', False):
                    return {'success': False, 'error': f'Database connection failed after restart: {db_check_result.get("error", "Unknown error")}'}
            
            # Step 6: Get project domain from config
            config_file = project_path / 'config.json'
            project_domain = None
            if config_file.exists():
                try:
                    with open(config_file, 'r') as f:
                        config = json.load(f)
                        project_domain = config.get('domain', '')
                except:
                    pass
            
            if not project_domain:
                # Try to get from .env or default
                env_file = project_path / '.env'
                if env_file.exists():
                    with open(env_file, 'r') as f:
                        for line in f:
                            if 'DOMAIN' in line and '=' in line:
                                project_domain = line.split('=', 1)[1].strip()
                                break
            
            # Determine protocol
            protocol = 'https' if (config_file.exists() and json.load(open(config_file)).get('enable_ssl', False)) else 'http'
            site_url = f"{protocol}://{project_domain}" if project_domain else None
            
            # Step 7: Get current siteurl and home options
            print(f"   🔍 Checking current siteurl and home options...")
            siteurl_result = self.run_wp_cli_command(project_path, "option get siteurl")
            home_result = self.run_wp_cli_command(project_path, "option get home")
            
            current_siteurl = siteurl_result.get('output', '').strip() if siteurl_result.get('success') else None
            current_home = home_result.get('output', '').strip() if home_result.get('success') else None
            
            # Step 8: Update siteurl and home if needed
            if site_url:
                if current_siteurl != site_url:
                    print(f"   🔄 Updating siteurl from '{current_siteurl}' to '{site_url}'...")
                    update_siteurl = self.run_wp_cli_command(project_path, f"option update siteurl '{site_url}'")
                    if update_siteurl.get('success', False):
                        print(f"   ✅ siteurl updated")
                    else:
                        print(f"   ⚠️  Could not update siteurl: {update_siteurl.get('error', 'Unknown error')}")
                
                if current_home != site_url:
                    print(f"   🔄 Updating home from '{current_home}' to '{site_url}'...")
                    update_home = self.run_wp_cli_command(project_path, f"option update home '{site_url}'")
                    if update_home.get('success', False):
                        print(f"   ✅ home updated")
                    else:
                        print(f"   ⚠️  Could not update home: {update_home.get('error', 'Unknown error')}")
            
            # Step 9: Clear all caches
            print(f"   🔄 Clearing WordPress caches...")
            self.run_wp_cli_command(project_path, "cache flush")
            self.run_wp_cli_command(project_path, "transient delete --all")
            self.run_wp_cli_command(project_path, "rewrite flush")
            
            # Step 10: Restart WordPress container
            print(f"   🔄 Restarting WordPress container...")
            restart_result = self.docker_manager.restart_container(project_path, 'wordpress')
            if restart_result.get('success', False):
                time.sleep(3)
                
                # Step 11: Final verification
                verify_result = self.run_wp_cli_command(project_path, "core is-installed")
                if verify_result.get('success', False):
                    print(f"   ✅ WordPress now correctly detects installation")
                    return {'success': True, 'message': 'WordPress installation detection fixed. Please refresh your browser.'}
                else:
                    # Force check by querying the database directly
                    print(f"   🔍 Forcing installation check by querying database...")
                    # Use double quotes for outer string, single quotes for SQL string value
                    install_check = self.run_wp_cli_command(project_path, f'db query "SELECT option_value FROM {options_table} WHERE option_name=\'siteurl\' LIMIT 1"')
                    
                    if install_check.get('success', False) and install_check.get('output', '').strip():
                        print(f"   ✅ Database contains WordPress data. WordPress should recognize installation after page refresh.")
                        return {'success': True, 'message': 'Database verified. WordPress should detect installation. Please refresh your browser.'}
                    else:
                        return {'success': False, 'error': 'WordPress still not detecting installation. Database may be incomplete.'}
            else:
                return {'success': False, 'error': 'Failed to restart WordPress container'}
                
        except Exception as e:
            print(f"   ❌ Error fixing WordPress install detection: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': f'Error fixing install detection: {str(e)}'}