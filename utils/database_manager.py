import gzip
import subprocess
import re
from pathlib import Path
from datetime import datetime


class DatabaseLogger:
    """Simple logger to collect messages during database operations"""
    def __init__(self):
        self.logs = []
    
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append({
            'timestamp': timestamp,
            'message': message
        })
        # Also print to console
        print(message)
    
    def get_logs(self):
        return self.logs


class DatabaseManager:
    """Handles all database-related operations"""
    
    def __init__(self):
        pass
    
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

    def import_database(self, project_path, project_name, db_file_path, backup_before_import=True):
        """Import database file with fallback strategy: try original first, then repaired version"""
        if not project_path.exists():
            return {'success': False, 'error': 'Project not found', 'logs': []}
        
        # Create logger to collect messages
        logger = DatabaseLogger()
        
        try:
            logger.log("🔄 Starting database import process...")
            
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
                self._backup_database(project_path, project_name, db_name, db_user, db_password, logger)
            
            # Clear database before import to avoid duplicate key errors
            self._clear_database(project_path, db_name, db_user, db_password, logger)
            
            # Implement fallback strategy: try original first, then repaired
            result = self._import_database_with_fallback(project_path, db_file_path, db_name, db_user, db_password, logger)
            
            # Add captured logs to result
            result['logs'] = logger.get_logs()
            return result
            
        except Exception as e:
            logger.log(f"❌ Unexpected error during import: {str(e)}")
            return {'success': False, 'error': str(e), 'logs': logger.get_logs()}
    
    def _backup_database(self, project_path, project_name, db_name, db_user, db_password, logger):
        """Create a backup of the current database"""
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
    
    def _clear_database(self, project_path, db_name, db_user, db_password, logger):
        """Clear database before import to avoid conflicts"""
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
            return self._create_and_import_repaired_file(project_path, db_file_path, db_name, db_user, db_password, logger)
        
        # If all attempts failed
        attempt_count = len(files_to_try) + (1 if original_failed and len(files_to_try) == 1 else 0)
        if attempt_count > 1:
            return {'success': False, 'error': f'All {attempt_count} import attempts failed. Last error: {last_error}'}
        else:
            return {'success': False, 'error': last_error or 'Database import failed'}
    
    def _create_and_import_repaired_file(self, project_path, db_file_path, db_name, db_user, db_password, logger):
        """Create a repaired version of the database file and try importing it"""
        logger.log(f"🔧 Original file failed, attempting to create and try repaired version...")
        
        try:
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
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            error_msg = f'Failed to create repaired file: {str(e)}'
            logger.log(f"   ❌ {error_msg}")
            return {'success': False, 'error': error_msg}
