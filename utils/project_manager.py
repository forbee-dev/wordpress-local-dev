import os
import json
import shutil
import subprocess
import platform
import re
import gzip
import io
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import yaml
from .ssl_generator import SSLGenerator
from .hosts_manager import HostsManager

class DatabaseLogger:
    """Simple logger to collect messages during database operations"""
    def __init__(self):
        self.logs = []
    
    def log(self, message):
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append({
            'timestamp': timestamp,
            'message': message
        })
        # Also print to console
        print(message)
    
    def get_logs(self):
        return self.logs

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
                print(f"🔐 Generating SSL certificates for {domain.split('/')[0]}...")
                # Ensure mkcert CA is installed for trusted certificates
                if self.ssl_generator.mkcert_available and not self.ssl_generator._check_mkcert_ca_installed():
                    print("🔐 Setting up mkcert local CA for trusted SSL certificates...")
                    self.ssl_generator._install_mkcert_ca()
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
                    
                    # Give containers a moment to fully start
                    import time
                    time.sleep(5)
                    
                    # Fix wp-config.php to properly read debug environment variables
                    print(f"   🔧 Configuring WordPress debug settings...")
                    self._fix_wp_config_debug(project_name)
                    
                    # If database file was provided, import it after containers are running
                    if db_file_path and Path(project_path / "data" / Path(db_file_path).name).exists():
                        print(f"   📋 Importing database...")
                        
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
            # Check and ensure SSL certificates are up to date
            self._ensure_ssl_certificates(project_name)
            
            result = subprocess.run(
                ['docker-compose', 'up', '-d'],
                cwd=project_path,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # Give containers a moment to fully start
                import time
                time.sleep(5)
                
                # Fix wp-config.php to properly read debug environment variables
                print(f"   🔧 Configuring WordPress debug settings...")
                self._fix_wp_config_debug(project_name)
                
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
    
    def _is_gzipped_file(self, file_path):
        """Check if a file is gzipped by reading its magic bytes"""
        try:
            with open(file_path, 'rb') as f:
                # Read first 2 bytes to check for gzip magic number (0x1f, 0x8b)
                magic = f.read(2)
                return magic == b'\x1f\x8b'
        except Exception:
            return False
    
    def _read_database_file(self, file_path, logger=None):
        """Read database file content, handling both regular and gzipped files"""
        try:
            file_path_obj = Path(file_path)
            if logger:
                logger.log(f"📖 Reading database file: {file_path_obj.name}")
            
            # Check if file is gzipped by extension or magic bytes
            is_gzipped = (
                file_path_obj.suffix.lower() == '.gz' or 
                file_path_obj.name.lower().endswith('.sql.gz') or
                self._is_gzipped_file(file_path)
            )
            
            if logger:
                logger.log(f"   📦 File type detected: {'Gzipped' if is_gzipped else 'Plain text'}")
            
            if is_gzipped:
                if logger:
                    logger.log(f"   📦 Detected gzipped database file, decompressing...")
                try:
                    # Try UTF-8 first
                    with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                        return f.read()
                except UnicodeDecodeError:
                    if logger:
                        logger.log(f"   ⚠️  UTF-8 decode failed, trying with error handling...")
                    # Fallback: read with error handling to skip invalid bytes
                    with gzip.open(file_path, 'rt', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                        if logger:
                            logger.log(f"   ✅ File read with {content.count('�')} replacement characters")
                        return content
            else:
                if logger:
                    logger.log(f"   📄 Reading plain text database file...")
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        return f.read()
                except UnicodeDecodeError:
                    if logger:
                        logger.log(f"   ⚠️  UTF-8 decode failed, trying with error handling...")
                    # Fallback: read with error handling to skip invalid bytes
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                        if logger:
                            logger.log(f"   ✅ File read with {content.count('�')} replacement characters")
                        return content
                    
        except Exception as e:
            # One more fallback: try reading as binary and decode with latin1 (which maps all bytes)
            try:
                if logger:
                    logger.log(f"   🔄 Trying binary mode with latin1 encoding as final fallback...")
                if is_gzipped:
                    with gzip.open(file_path, 'rb') as f:
                        content_bytes = f.read()
                else:
                    with open(file_path, 'rb') as f:
                        content_bytes = f.read()
                
                # Try to decode as UTF-8 with replacement characters
                try:
                    content = content_bytes.decode('utf-8', errors='replace')
                    if logger:
                        logger.log(f"   ✅ Binary fallback successful with UTF-8 replacement")
                    return content
                except:
                    # Final fallback: latin1 (maps all bytes 1:1)
                    content = content_bytes.decode('latin1')
                    if logger:
                        logger.log(f"   ✅ Binary fallback successful with latin1 encoding")
                    return content
                    
            except Exception as final_e:
                raise Exception(f"Failed to read database file with all fallback methods. Last error: {str(final_e)}")

    def import_database(self, project_name, db_file_path, backup_before_import=True):
        """Import database file with fallback strategy: try original first, then repaired version"""
        project_path = self.projects_dir / project_name
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found', 'logs': []}
        
        # Create logger to collect messages
        logger = DatabaseLogger()
        
        try:
            logger.log("🔄 Starting database import process...")
            
            # Check if containers are running
            status = self.get_project_status(project_name)
            if status.get('status') != 'running':
                return {'success': False, 'error': 'Project must be running to import database. Please start the project first.', 'logs': logger.get_logs()}
            
            # Validate database file exists
            if not Path(db_file_path).exists():
                return {'success': False, 'error': f'Database file not found: {db_file_path}', 'logs': logger.get_logs()}
            
            # Read environment variables
            env_file = project_path / '.env'
            env_vars = {}
            if env_file.exists():
                try:
                    with open(env_file, 'r') as f:
                        for line in f:
                            if '=' in line and not line.startswith('#'):
                                key, value = line.strip().split('=', 1)
                                env_vars[key] = value
                except Exception as e:
                    logger.log(f"Warning: Could not read .env file: {e}")
            
            db_name = env_vars.get('DB_NAME', f'local_{project_name}')
            db_user = env_vars.get('DB_USER', 'wordpress')
            db_password = env_vars.get('DB_PASSWORD', 'wordpress_password')
            
            # Backup current database if requested
            if backup_before_import:
                try:
                    backup_filename = f"backup_before_import_{project_name}_{subprocess.run(['date', '+%Y%m%d_%H%M%S'], capture_output=True, text=True).stdout.strip()}.sql"
                    backup_path = project_path / 'data' / backup_filename
                    
                    logger.log(f"🔄 Creating database backup...")
                    # Export current database with error handling for corrupted data
                    backup_result = subprocess.run([
                        'docker-compose', 'exec', '-T', 'mysql',
                        'mysqldump', f'-u{db_user}', f'-p{db_password}', 
                        '--single-transaction', '--routines', '--triggers', 
                        '--default-character-set=utf8mb4', db_name
                    ], cwd=project_path, capture_output=True, text=True)
                    
                    if backup_result.returncode == 0:
                        with open(backup_path, 'w', encoding='utf-8', errors='replace') as f:
                            f.write(backup_result.stdout)
                        logger.log(f"✅ Database backed up to: {backup_path}")
                    else:
                        logger.log(f"⚠️  Backup failed: {backup_result.stderr}")
                        # Try alternative backup method for corrupted databases
                        logger.log(f"🔄 Attempting alternative backup method...")
                        backup_result = subprocess.run([
                            'docker-compose', 'exec', '-T', 'mysql',
                            'mysqldump', f'-u{db_user}', f'-p{db_password}', 
                            '--skip-extended-insert', '--skip-lock-tables', db_name
                        ], cwd=project_path, capture_output=True, text=True)
                        
                        if backup_result.returncode == 0:
                            with open(backup_path, 'w', encoding='utf-8', errors='replace') as f:
                                f.write(backup_result.stdout)
                            logger.log(f"✅ Alternative backup successful: {backup_path}")
                        else:
                            logger.log(f"❌ Both backup methods failed, skipping backup")
                            
                except Exception as e:
                    logger.log(f"❌ Backup failed but continuing with import: {e}")
            
            # Clear database before import to avoid duplicate key errors
            logger.log(f"🗑️  Clearing database to avoid conflicts...")
            try:
                # Drop and recreate database
                clear_result = subprocess.run([
                    'docker-compose', 'exec', '-T', 'mysql',
                    'mysql', f'-u{db_user}', f'-p{db_password}', 
                    '-e', f'DROP DATABASE IF EXISTS {db_name}; CREATE DATABASE {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;'
                ], cwd=project_path, capture_output=True, text=True)
                
                if clear_result.returncode == 0:
                    logger.log(f"✅ Database cleared and recreated successfully")
                else:
                    logger.log(f"⚠️  Database clear failed: {clear_result.stderr}")
                    
            except Exception as e:
                logger.log(f"⚠️  Failed to clear database: {e}")
            
            # Implement fallback strategy: try original first, then repaired
            # Let the fallback function handle all database-related errors
            logger.log(f"🔄 About to start fallback import for: {Path(db_file_path).name}")
            result = self._import_database_with_fallback(project_path, db_file_path, db_name, db_user, db_password, logger)
            
            # Add captured logs to result
            result['logs'] = logger.get_logs()
            return result
            
        except Exception as e:
            logger.log(f"❌ Unexpected error during import: {str(e)}")
            return {'success': False, 'error': str(e), 'logs': logger.get_logs()}
    
    def _import_database_with_fallback(self, project_path, db_file_path, db_name, db_user, db_password, logger):
        """Try importing database with fallback strategy"""
        db_file_path = Path(db_file_path)
        
        logger.log(f"🔄 Starting fallback import for: {db_file_path.name}")
        
        # Determine file type and find potential fallback files
        files_to_try = []
        
        # Strategy: Always try original first, then repaired
        if '_repaired' in db_file_path.name:
            # If provided file is repaired, try it first, then look for original
            files_to_try.append(db_file_path)
            original_name = db_file_path.name.replace('_repaired', '')
            original_path = db_file_path.parent / original_name
            if original_path.exists():
                files_to_try.append(original_path)
        else:
            # If provided file is original, try it first, then look for repaired
            files_to_try.append(db_file_path)
            
            # Look for repaired version
            if db_file_path.name.endswith('.sql.gz'):
                repaired_name = db_file_path.name.replace('.sql.gz', '_repaired.sql.gz')
            elif db_file_path.name.endswith('.sql'):
                repaired_name = db_file_path.name.replace('.sql', '_repaired.sql')
            else:
                repaired_name = f"{db_file_path.stem}_repaired{db_file_path.suffix}"
            
            repaired_path = db_file_path.parent / repaired_name
            if repaired_path.exists():
                files_to_try.append(repaired_path)
        
        # Try each file in order
        last_error = None
        original_failed = False
        
        for i, file_to_try in enumerate(files_to_try):
            file_type = "repaired" if "_repaired" in file_to_try.name else "original"
            attempt_msg = f"Attempt {i+1}/{len(files_to_try)}"
            
            logger.log(f"📋 {attempt_msg}: Trying {file_type} file: {file_to_try.name}")
            
            try:
                # Read database content (handles both plain and gzipped files)
                db_content = self._read_database_file(file_to_try, logger)
                
                # Import database
                import_result = subprocess.run([
                    'docker-compose', 'exec', '-T', 'mysql',
                    'mysql', f'-u{db_user}', f'-p{db_password}', db_name
                ], input=db_content, cwd=project_path, capture_output=True, text=True)
                
                if import_result.returncode == 0:
                    logger.log(f"   ✅ Database imported successfully using {file_type} file: {file_to_try.name}")
                    return {'success': True, 'message': f'Database imported successfully using {file_type} file: {file_to_try.name}'}
                else:
                    error_msg = f'Database import failed with {file_type} file: {import_result.stderr}'
                    logger.log(f"   ❌ {error_msg}")
                    last_error = error_msg
                    
                    # Mark if original file failed (for repair creation)
                    if file_type == "original":
                        original_failed = True
                    
                    continue  # Try next file
                    
            except Exception as e:
                error_msg = f'Error reading {file_type} file {file_to_try.name}: {str(e)}'
                logger.log(f"   ❌ {error_msg}")
                last_error = error_msg
                
                # Mark if original file failed (for repair creation)
                if file_type == "original":
                    original_failed = True
                
                continue  # Try next file
        
        # If original failed and no repaired file was found, try to create one
        if original_failed and len(files_to_try) == 1:
            logger.log(f"🔧 Original file failed, attempting to create and try repaired version...")
            
            try:
                # Import the repair functions from app.py
                import gzip
                import re
                
                # Create repaired filename
                if db_file_path.name.endswith('.sql.gz'):
                    repaired_name = db_file_path.name.replace('.sql.gz', '_repaired.sql.gz')
                elif db_file_path.name.endswith('.sql'):
                    repaired_name = db_file_path.name.replace('.sql', '_repaired.sql')
                else:
                    repaired_name = f"{db_file_path.stem}_repaired{db_file_path.suffix}"
                
                repaired_path = db_file_path.parent / repaired_name
                
                # Check if file is gzipped
                is_gzipped = (
                    db_file_path.suffix.lower() == '.gz' or 
                    db_file_path.name.lower().endswith('.sql.gz') or
                    self._is_gzipped_file(db_file_path)
                )
                
                logger.log(f"   🔧 Creating repaired file: {repaired_name}")
                
                # Read with error handling
                if is_gzipped:
                    with gzip.open(db_file_path, 'rt', encoding='utf-8', errors='replace') as input_file:
                        content = input_file.read()
                else:
                    with open(db_file_path, 'r', encoding='utf-8', errors='replace') as input_file:
                        content = input_file.read()
                
                # Clean the content
                original_length = len(content)
                cleaned_content = content.replace('�', '')
                cleaned_content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', cleaned_content)
                final_length = len(cleaned_content)
                removed_chars = original_length - final_length
                
                logger.log(f"   ✂️  Removed {removed_chars:,} problematic characters")
                
                # Write cleaned version
                if is_gzipped:
                    with gzip.open(repaired_path, 'wt', encoding='utf-8') as output_file:
                        output_file.write(cleaned_content)
                else:
                    with open(repaired_path, 'w', encoding='utf-8') as output_file:
                        output_file.write(cleaned_content)
                
                logger.log(f"   ✅ Repaired file created, attempting import...")
                
                # Try importing the repaired file
                import_result = subprocess.run([
                    'docker-compose', 'exec', '-T', 'mysql',
                    'mysql', f'-u{db_user}', f'-p{db_password}', db_name
                ], input=cleaned_content, cwd=project_path, capture_output=True, text=True)
                
                if import_result.returncode == 0:
                    logger.log(f"   ✅ Database imported successfully using repaired file: {repaired_name}")
                    return {'success': True, 'message': f'Database imported successfully using repaired file: {repaired_name} (removed {removed_chars:,} corrupted characters)'}
                else:
                    error_msg = f'Database import failed even with repaired file: {import_result.stderr}'
                    logger.log(f"   ❌ {error_msg}")
                    last_error = error_msg
                    
            except Exception as e:
                error_msg = f'Failed to create repaired file: {str(e)}'
                logger.log(f"   ❌ {error_msg}")
                last_error = error_msg
        
        # If all attempts failed
        attempt_count = len(files_to_try) + (1 if original_failed and len(files_to_try) == 1 else 0)
        if attempt_count > 1:
            return {'success': False, 'error': f'All {attempt_count} import attempts failed. Last error: {last_error}'}
        else:
            return {'success': False, 'error': last_error or 'Database import failed'}
    
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
    
    def _fix_wp_config_debug(self, project_name):
        """Fix wp-config.php to properly read debug environment variables"""
        try:
            # Create a temporary PHP script file
            fix_script_path = self.projects_dir / project_name / "fix_debug.php"
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
            wp_content_script_path = self.projects_dir / project_name / "wp-content" / "fix_debug.php"
            shutil.copy2(fix_script_path, wp_content_script_path)
            
            # Run the fix script in the WordPress container
            result = subprocess.run(
                ['docker-compose', 'exec', '-T', 'wordpress', 'php', '/var/www/html/wp-content/fix_debug.php'],
                cwd=self.projects_dir / project_name,
                capture_output=True,
                text=True
            )
            
            # Clean up the temporary files
            if fix_script_path.exists():
                fix_script_path.unlink()
            if wp_content_script_path.exists():
                wp_content_script_path.unlink()
            
            if result.returncode == 0:
                print(f"   ✅ WordPress debug configuration updated")
            else:
                print(f"   ⚠️  Warning: Could not update wp-config.php debug settings: {result.stderr}")
                
        except Exception as e:
            print(f"   ⚠️  Warning: Error updating wp-config.php: {str(e)}")

    def add_wpcli_to_project(self, project_name):
        """Add WP CLI service to existing project"""
        try:
            project_path = self.projects_dir / project_name
            if not project_path.exists():
                return {'success': False, 'error': 'Project not found'}
            
            docker_compose_path = project_path / "docker-compose.yml"
            if docker_compose_path.exists():
                # Check if WP CLI is already present
                with open(docker_compose_path, 'r') as f:
                    compose_content = f.read()
                
                if "wpcli:" in compose_content:
                    print(f"   ✅ WP CLI already configured for {project_name}")
                    return {'success': True, 'message': 'WP CLI is already configured for this project'}
                
                # Read project config to get settings
                config_path = project_path / "config.json"
                if config_path.exists():
                    with open(config_path, 'r') as f:
                        config = json.load(f)
                    
                    print(f"   🔄 Updating docker-compose.yml to include WP CLI...")
                    # Regenerate docker-compose with WP CLI
                    self._create_docker_compose(
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
                    return {'success': False, 'error': 'Project config.json not found'}
            else:
                return {'success': False, 'error': 'docker-compose.yml not found'}
                
        except Exception as e:
            print(f"   ❌ Error adding WP CLI: {str(e)}")
            return {'success': False, 'error': str(e)}

    def add_wpcli_to_all_projects(self):
        """Add WP CLI service to all existing projects"""
        projects = self.list_projects()['projects']
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

    def run_wp_cli_command(self, project_name, command):
        """Run a WP CLI command on a project"""
        try:
            project_path = self.projects_dir / project_name
            if not project_path.exists():
                return {'success': False, 'error': 'Project not found'}
            
            docker_compose_path = project_path / "docker-compose.yml"
            if not docker_compose_path.exists():
                return {'success': False, 'error': 'docker-compose.yml not found'}
            
            # Check if WP CLI service exists
            with open(docker_compose_path, 'r') as f:
                compose_content = f.read()
            
            if "wpcli:" not in compose_content:
                return {'success': False, 'error': 'WP CLI service not configured. Please add WP CLI to this project first.'}
            
            # Run the WP CLI command
            full_command = f"docker-compose --profile cli run --rm wpcli {command}"
            print(f"🔧 Running WP CLI command: {command}")
            print(f"   Command: {full_command}")
            
            result = subprocess.run(
                full_command.split(),
                cwd=project_path,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print(f"   ✅ Command executed successfully")
                return {
                    'success': True, 
                    'output': result.stdout,
                    'command': command
                }
            else:
                print(f"   ❌ Command failed: {result.stderr}")
                return {
                    'success': False, 
                    'error': result.stderr,
                    'command': command
                }
                
        except Exception as e:
            print(f"   ❌ Error running WP CLI command: {str(e)}")
            return {'success': False, 'error': str(e)}

    def fix_php_upload_limits(self, project_name):
        """Fix PHP upload limits for an existing project"""
        try:
            project_path = self.projects_dir / project_name
            if not project_path.exists():
                return {'success': False, 'error': 'Project not found'}

            print(f"🔧 Fixing PHP upload limits for project: {project_name}")
            
            # Create or update PHP configuration
            self._create_php_config(project_path)
            print(f"   ✅ Created PHP upload configuration")
            
            # Check if docker-compose.yml needs updating
            docker_compose_path = project_path / "docker-compose.yml"
            if docker_compose_path.exists():
                with open(docker_compose_path, 'r') as f:
                    compose_content = f.read()
                
                # Check if PHP config is already mounted
                if './php-uploads.ini:/usr/local/etc/php/conf.d/uploads.ini' not in compose_content:
                    # Need to update docker-compose.yml
                    print(f"   🔄 Updating docker-compose.yml...")
                    
                    # Get project config to rebuild docker-compose with current settings
                    config_path = project_path / "config.json"
                    if config_path.exists():
                        with open(config_path, 'r') as f:
                            config = json.load(f)
                        
                        # Rebuild docker-compose.yml with new PHP config
                        self._create_docker_compose(
                            project_path, 
                            config['name'], 
                            config.get('wordpress_version', 'latest'),
                            config['domain'], 
                            config.get('enable_ssl', True), 
                            config.get('enable_redis', True)
                        )
                        print(f"   ✅ Updated docker-compose.yml with PHP configuration")
                        
                        # Restart containers to apply changes
                        print(f"   🔄 Restarting containers to apply changes...")
                        restart_result = subprocess.run(
                            ['docker-compose', 'down'],
                            cwd=project_path,
                            capture_output=True,
                            text=True
                        )
                        
                        restart_result = subprocess.run(
                            ['docker-compose', 'up', '-d'],
                            cwd=project_path,
                            capture_output=True,
                            text=True
                        )
                        
                        if restart_result.returncode == 0:
                            print(f"   ✅ Containers restarted successfully")
                            print(f"   📏 New upload limits: 100MB")
                            return {'success': True, 'message': 'PHP upload limits updated successfully. You can now upload files up to 100MB.'}
                        else:
                            print(f"   ⚠️  Warning: Container restart failed: {restart_result.stderr}")
                            return {'success': False, 'error': f'Container restart failed: {restart_result.stderr}'}
                    else:
                        return {'success': False, 'error': 'Project config.json not found'}
                else:
                    print(f"   ✅ PHP upload configuration already present")
                    return {'success': True, 'message': 'PHP upload limits are already configured'}
            else:
                return {'success': False, 'error': 'docker-compose.yml not found'}
                
        except Exception as e:
            print(f"   ❌ Error fixing PHP upload limits: {str(e)}")
            return {'success': False, 'error': str(e)}

    def update_wordpress_version(self, project_name, new_version):
        """Update WordPress version for an existing project"""
        try:
            project_path = self.projects_dir / project_name
            if not project_path.exists():
                return {'success': False, 'error': 'Project not found'}
            
            # Read current config
            config_path = project_path / "config.json"
            if not config_path.exists():
                return {'success': False, 'error': 'Project config not found'}
            
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            old_version = config.get('wordpress_version', 'unknown')
            print(f"🔄 Updating WordPress version from {old_version} to {new_version}")
            
            # Update config
            config['wordpress_version'] = new_version
            
            # Stop containers first
            print(f"   🛑 Stopping containers...")
            subprocess.run(['docker-compose', 'down'], cwd=project_path, capture_output=True)
            
            # Rebuild docker-compose.yml with new version
            print(f"   🔄 Updating docker-compose.yml...")
            self._create_docker_compose(
                project_path,
                config['name'],
                new_version,
                config['domain'],
                config.get('enable_ssl', True),
                config.get('enable_redis', True)
            )
            
            # Save updated config
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Start containers with new version
            print(f"   🚀 Starting containers with new WordPress version...")
            start_result = subprocess.run(
                ['docker-compose', 'up', '-d'],
                cwd=project_path,
                capture_output=True,
                text=True
            )
            
            if start_result.returncode == 0:
                print(f"   ✅ WordPress version updated successfully")
                return {'success': True, 'message': f'WordPress version updated from {old_version} to {new_version}'}
            else:
                return {'success': False, 'error': f'Failed to start containers: {start_result.stderr}'}
                
        except Exception as e:
            print(f"   ❌ Error updating WordPress version: {str(e)}")
            return {'success': False, 'error': str(e)}

    def update_domain(self, project_name, new_domain, enable_ssl=None):
        """Update domain for an existing project"""
        try:
            project_path = self.projects_dir / project_name
            if not project_path.exists():
                return {'success': False, 'error': 'Project not found'}
            
            # Read current config
            config_path = project_path / "config.json"
            if not config_path.exists():
                return {'success': False, 'error': 'Project config not found'}
            
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            old_domain = config.get('domain', 'unknown')
            print(f"🔄 Updating domain from {old_domain} to {new_domain}")
            
            # Update config
            config['domain'] = new_domain
            if enable_ssl is not None:
                config['enable_ssl'] = enable_ssl
            
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
            subprocess.run(['docker-compose', 'down'], cwd=project_path, capture_output=True)
            
            # Rebuild docker-compose.yml and nginx config
            print(f"   🔄 Updating configuration files...")
            self._create_docker_compose(
                project_path,
                config['name'],
                config.get('wordpress_version', 'latest'),
                new_domain,
                config.get('enable_ssl', True),
                config.get('enable_redis', True)
            )
            
            self._create_nginx_config(
                project_path,
                config['name'],
                new_domain,
                config.get('enable_ssl', True),
                config.get('subfolder', '')
            )
            
            # Save updated config
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Start containers
            print(f"   🚀 Starting containers with new domain...")
            start_result = subprocess.run(
                ['docker-compose', 'up', '-d'],
                cwd=project_path,
                capture_output=True,
                text=True
            )
            
            if start_result.returncode == 0:
                print(f"   ✅ Domain updated successfully")
                return {'success': True, 'message': f'Domain updated from {old_domain} to {new_domain}'}
            else:
                return {'success': False, 'error': f'Failed to start containers: {start_result.stderr}'}
                
        except Exception as e:
            print(f"   ❌ Error updating domain: {str(e)}")
            return {'success': False, 'error': str(e)}

    def update_repository(self, project_name, new_repo_url):
        """Update repository URL and re-clone content for an existing project"""
        try:
            project_path = self.projects_dir / project_name
            if not project_path.exists():
                return {'success': False, 'error': 'Project not found'}
            
            # Read current config
            config_path = project_path / "config.json"
            if not config_path.exists():
                return {'success': False, 'error': 'Project config not found'}
            
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            old_repo = config.get('repo_url', 'none')
            print(f"🔄 Updating repository from {old_repo} to {new_repo_url}")
            
            # Stop containers to avoid conflicts
            print(f"   🛑 Stopping containers...")
            subprocess.run(['docker-compose', 'down'], cwd=project_path, capture_output=True)
            
            # Remove old repository if it exists
            repo_dir = project_path / "repository"
            if repo_dir.exists():
                print(f"   🗑️  Removing old repository...")
                shutil.rmtree(repo_dir)
            
            # Remove old wp-content symlink/copy
            wp_content_path = project_path / "wp-content"
            if wp_content_path.exists():
                if wp_content_path.is_symlink():
                    wp_content_path.unlink()
                else:
                    shutil.rmtree(wp_content_path)
            
            # Create new wp-content directory
            wp_content_path.mkdir()
            
            # Clone new repository if URL provided
            repo_structure = None
            if new_repo_url and new_repo_url.strip():
                print(f"   📥 Cloning new repository...")
                repo_structure = self._clone_repository(new_repo_url, project_path)
            else:
                print(f"   ℹ️  No repository URL provided, keeping default wp-content")
            
            # Update config
            config['repo_url'] = new_repo_url
            if repo_structure:
                config['repository_structure'] = {
                    'type': repo_structure['type'],
                    'has_wp_content': repo_structure['has_wp_content'],
                    'has_composer': repo_structure['has_composer'],
                    'has_package_json': repo_structure['has_package_json'],
                    'is_theme': repo_structure['is_theme'],
                    'is_plugin': repo_structure['is_plugin'],
                    'wp_content_path': str(repo_structure['wp_content_path']) if repo_structure['wp_content_path'] else None
                }
            else:
                config['repository_structure'] = None
            
            # Save updated config
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Start containers
            print(f"   🚀 Starting containers with new repository...")
            start_result = subprocess.run(
                ['docker-compose', 'up', '-d'],
                cwd=project_path,
                capture_output=True,
                text=True
            )
            
            if start_result.returncode == 0:
                print(f"   ✅ Repository updated successfully")
                return {'success': True, 'message': f'Repository updated from {old_repo} to {new_repo_url}'}
            else:
                return {'success': False, 'error': f'Failed to start containers: {start_result.stderr}'}
                
        except Exception as e:
            print(f"   ❌ Error updating repository: {str(e)}")
            return {'success': False, 'error': str(e)}

    def update_project_config(self, project_name, **updates):
        """Update various project configuration settings"""
        try:
            project_path = self.projects_dir / project_name
            if not project_path.exists():
                return {'success': False, 'error': 'Project not found'}
            
            # Read current config
            config_path = project_path / "config.json"
            if not config_path.exists():
                return {'success': False, 'error': 'Project config not found'}
            
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            print(f"🔄 Updating project configuration for {project_name}")
            
            # Track what needs to be updated
            needs_restart = False
            updated_fields = []
            
            # Update allowed fields
            allowed_fields = ['enable_ssl', 'enable_redis', 'subfolder', 'custom_domain']
            for field, value in updates.items():
                if field in allowed_fields and field in config:
                    old_value = config[field]
                    config[field] = value
                    updated_fields.append(f"{field}: {old_value} → {value}")
                    
                    # Some changes require container restart
                    if field in ['enable_ssl', 'enable_redis']:
                        needs_restart = True
            
            # Handle domain update if custom_domain changed
            if 'custom_domain' in updates and updates['custom_domain']:
                new_domain = updates['custom_domain']
                if config.get('subfolder'):
                    new_domain = f"{new_domain}/{config['subfolder']}"
                config['domain'] = new_domain
                updated_fields.append(f"domain: {config.get('domain', 'unknown')} → {new_domain}")
                needs_restart = True
            
            # Save updated config
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            if needs_restart:
                print(f"   🔄 Configuration changes require container restart...")
                
                # Check if SSL certificates need updating
                if 'enable_ssl' in updates or 'custom_domain' in updates:
                    domain = config['domain'].split('/')[0]
                    print(f"   🔐 Updating SSL certificates for {domain}...")
                    self.ssl_generator.generate_ssl_cert(project_name, domain)
                
                # Stop containers
                subprocess.run(['docker-compose', 'down'], cwd=project_path, capture_output=True)
                
                # Rebuild docker-compose.yml with new settings
                self._create_docker_compose(
                    project_path,
                    config['name'],
                    config.get('wordpress_version', 'latest'),
                    config['domain'],
                    config.get('enable_ssl', True),
                    config.get('enable_redis', True)
                )
                
                # Update nginx config if needed
                self._create_nginx_config(
                    project_path,
                    config['name'],
                    config['domain'],
                    config.get('enable_ssl', True),
                    config.get('subfolder', '')
                )
                
                # Start containers
                start_result = subprocess.run(
                    ['docker-compose', 'up', '-d'],
                    cwd=project_path,
                    capture_output=True,
                    text=True
                )
                
                if start_result.returncode != 0:
                    return {'success': False, 'error': f'Failed to restart containers: {start_result.stderr}'}
            
            print(f"   ✅ Configuration updated successfully")
            return {
                'success': True, 
                'message': f'Project configuration updated',
                'updated_fields': updated_fields
            }
                
        except Exception as e:
            print(f"   ❌ Error updating project configuration: {str(e)}")
            return {'success': False, 'error': str(e)}

    def _ensure_ssl_certificates(self, project_name):
        """Ensure SSL certificates are present and up to date for a project"""
        try:
            project_path = self.projects_dir / project_name
            config_path = project_path / "config.json"
            
            if not config_path.exists():
                print(f"   ⚠️  No config found for {project_name}, skipping SSL check")
                return
            
            # Read project config
            with open(config_path, 'r') as f:
                config = json.load(f)
            
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
                    # Simple check: if files are older than 30 days, regenerate
                    import time
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