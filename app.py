import os
import json
import shutil
import subprocess
import platform
import gzip
import re
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from pathlib import Path
import yaml
from utils.project_manager import ProjectManager
from utils.ssl_generator import SSLGenerator
from utils.hosts_manager import HostsManager

app = Flask(__name__)
app.secret_key = 'wordpress-local-dev-secret-key'

# Initialize managers
project_manager = ProjectManager()
ssl_generator = SSLGenerator()
hosts_manager = HostsManager()

# Cache for WordPress versions (cache for 1 hour)
wordpress_versions_cache = {
    'data': None,
    'timestamp': 0,
    'cache_duration': 3600  # 1 hour in seconds
}

def is_gzipped_file(file_path):
    """Check if a file is gzipped by reading its magic bytes"""
    try:
        with open(file_path, 'rb') as f:
            magic = f.read(2)
            return magic == b'\x1f\x8b'
    except Exception:
        return False

def validate_and_repair_database(file_path):
    """Validate a database file and repair if needed"""
    file_path = Path(file_path)
    
    # Check if file is gzipped
    is_gzipped = (
        file_path.suffix.lower() == '.gz' or 
        file_path.name.lower().endswith('.sql.gz') or
        is_gzipped_file(file_path)
    )
    
    print(f"📋 Validating database file: {file_path.name}")
    print(f"   📦 File type: {'Gzipped SQL' if is_gzipped else 'Plain SQL'}")
    print(f"   📏 File size: {file_path.stat().st_size:,} bytes")
    
    try:
        # Test if file can be read cleanly
        if is_gzipped:
            try:
                with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                    content = f.read()
                print("   ✅ File validation: Perfect UTF-8 encoding")
                return str(file_path), None  # No repair needed
            except UnicodeDecodeError as e:
                print(f"   ⚠️  UTF-8 decode error found: {str(e)[:100]}...")
                return repair_database_file(file_path, is_gzipped)
        else:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                print("   ✅ File validation: Perfect UTF-8 encoding")
                return str(file_path), None  # No repair needed
            except UnicodeDecodeError as e:
                print(f"   ⚠️  UTF-8 decode error found: {str(e)[:100]}...")
                return repair_database_file(file_path, is_gzipped)
                
    except Exception as e:
        print(f"   ❌ Validation error: {str(e)}")
        return str(file_path), f"Validation failed: {str(e)}"

def repair_database_file(file_path, is_gzipped):
    """Repair a database file with encoding issues"""
    file_path = Path(file_path)
    
    # Create repaired filename
    if file_path.name.endswith('.sql.gz'):
        repaired_name = file_path.name.replace('.sql.gz', '_repaired.sql.gz')
    elif file_path.name.endswith('.sql'):
        repaired_name = file_path.name.replace('.sql', '_repaired.sql')
    else:
        repaired_name = f"{file_path.stem}_repaired{file_path.suffix}"
    
    repaired_path = file_path.parent / repaired_name
    
    print(f"   🔧 Repairing file: {repaired_name}")
    
    try:
        # Read with error handling
        print("   📖 Reading file with error replacement...")
        if is_gzipped:
            with gzip.open(file_path, 'rt', encoding='utf-8', errors='replace') as input_file:
                content = input_file.read()
        else:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as input_file:
                content = input_file.read()
        
        # Clean the content
        print("   🧹 Cleaning content...")
        original_length = len(content)
        
        # Remove replacement characters (�)
        cleaned_content = content.replace('�', '')
        
        # Remove control characters that shouldn't be in SQL
        cleaned_content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', cleaned_content)
        
        final_length = len(cleaned_content)
        removed_chars = original_length - final_length
        
        print(f"   ✂️  Removed {removed_chars:,} problematic characters")
        
        # Write cleaned version
        print("   💾 Writing cleaned file...")
        if is_gzipped:
            with gzip.open(repaired_path, 'wt', encoding='utf-8') as output_file:
                output_file.write(cleaned_content)
        else:
            with open(repaired_path, 'w', encoding='utf-8') as output_file:
                output_file.write(cleaned_content)
        
        print(f"   ✅ Repaired file created: {repaired_name}")
        print(f"   📊 Original: {file_path.stat().st_size:,} bytes")
        print(f"   📊 Repaired: {repaired_path.stat().st_size:,} bytes")
        print(f"   📊 Cleaned: {removed_chars:,} characters")
        
        return str(repaired_path), f"File repaired: removed {removed_chars:,} corrupted characters"
        
    except Exception as e:
        print(f"   ❌ Repair failed: {str(e)}")
        return str(file_path), f"Repair failed: {str(e)}"

@app.route('/')
def index():
    """Main interface for creating WordPress projects"""
    projects = project_manager.list_projects()
    return render_template('index.html', projects=projects)

@app.route('/api/wordpress-versions')
def get_wordpress_versions():
    """Get available WordPress Docker image versions from Docker Hub"""
    import time
    
    # Check cache first
    current_time = time.time()
    if (wordpress_versions_cache['data'] and 
        current_time - wordpress_versions_cache['timestamp'] < wordpress_versions_cache['cache_duration']):
        return jsonify(wordpress_versions_cache['data'])
    
    try:
        import requests
        
        print("Fetching WordPress versions from Docker Hub...")
        
        # Fetch WordPress image tags from Docker Hub API
        url = "https://hub.docker.com/v2/repositories/library/wordpress/tags/?page_size=100"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            print(f"Docker Hub API returned status {response.status_code}")
            # Use cached data if available, otherwise fallback
            if wordpress_versions_cache['data']:
                return jsonify(wordpress_versions_cache['data'])
            return jsonify(get_fallback_versions())
        
        data = response.json()
        versions = []
        processed_tags = set()
        
        # Process the tags and create meaningful descriptions
        for tag_info in data.get('results', []):
            tag = tag_info.get('name', '')
            if not tag or tag in processed_tags:
                continue
                
            processed_tags.add(tag)
            
            # Parse tag to create description
            description = parse_wordpress_tag(tag)
            if description:
                versions.append({
                    'version': tag,
                    'description': description
                })
        
        # Sort versions by priority (latest first, then numeric versions)
        versions.sort(key=lambda x: get_version_priority(x['version']))
        
        # Limit to most relevant versions
        final_versions = versions[:20]
        
        # Update cache
        wordpress_versions_cache['data'] = final_versions
        wordpress_versions_cache['timestamp'] = current_time
        
        print(f"Successfully fetched {len(final_versions)} WordPress versions from Docker Hub")
        return jsonify(final_versions)
        
    except Exception as e:
        print(f"Error fetching WordPress versions from Docker Hub: {str(e)}")
        # Use cached data if available, otherwise fallback
        if wordpress_versions_cache['data']:
            print("Using cached WordPress versions due to API error")
            return jsonify(wordpress_versions_cache['data'])
        
        print("Using fallback WordPress versions")
        fallback_versions = get_fallback_versions()
        
        # Cache fallback versions too
        wordpress_versions_cache['data'] = fallback_versions
        wordpress_versions_cache['timestamp'] = current_time
        
        return jsonify(fallback_versions)

def parse_wordpress_tag(tag):
    """Parse WordPress Docker tag and create meaningful description"""
    tag_lower = tag.lower()
    
    # Skip certain tags
    skip_tags = ['beta', 'rc', 'alpha', 'cli', 'fpm-alpine', 'apache', 'cli-php']
    if any(skip in tag_lower for skip in skip_tags):
        return None
    
    # Handle special cases
    if tag == 'latest':
        return 'Latest stable WordPress (Recommended)'
    
    # PHP version tags
    if tag.startswith('php'):
        php_version = tag.replace('php', '')
        return f'Latest WordPress with PHP {php_version}'
    
    # Version number tags
    import re
    
    # Match version patterns like 6.4, 6.4.1, 6.4-php8.1, etc.
    version_match = re.match(r'^(\d+\.\d+(?:\.\d+)?)(?:-php(\d+\.\d+))?(?:-(.+))?$', tag)
    if version_match:
        wp_version = version_match.group(1)
        php_version = version_match.group(2)
        variant = version_match.group(3)
        
        description = f'WordPress {wp_version}'
        
        if php_version:
            description += f' (PHP {php_version})'
        elif not variant:
            # Default PHP version for main WordPress versions
            if wp_version.startswith('6.4') or wp_version.startswith('6.5') or wp_version.startswith('6.6'):
                description += ' (PHP 8.1)'
            elif wp_version.startswith('6.2') or wp_version.startswith('6.3'):
                description += ' (PHP 8.0)'
            elif wp_version.startswith('6.0') or wp_version.startswith('6.1'):
                description += ' (PHP 8.0)'
            else:
                description += ' (Default PHP)'
        
        if variant and variant not in ['apache', 'fpm']:
            description += f' - {variant.title()}'
            
        return description
    
    return None

def get_version_priority(version):
    """Get sorting priority for WordPress versions"""
    if version == 'latest':
        return 0
    
    # PHP version tags
    if version.startswith('php'):
        php_ver = version.replace('php', '')
        return 10 + float(php_ver) if php_ver.replace('.', '').isdigit() else 100
    
    # WordPress version numbers
    import re
    version_match = re.match(r'^(\d+)\.(\d+)(?:\.(\d+))?', version)
    if version_match:
        major = int(version_match.group(1))
        minor = int(version_match.group(2))
        patch = int(version_match.group(3)) if version_match.group(3) else 0
        return 1000 - (major * 100 + minor * 10 + patch)
    
    return 9999

def get_fallback_versions():
    """Fallback WordPress versions if Docker Hub API fails"""
    return [
        {'version': 'latest', 'description': 'Latest stable WordPress (Recommended)'},
        {'version': '6.4', 'description': 'WordPress 6.4 (PHP 8.1)'},
        {'version': '6.3', 'description': 'WordPress 6.3 (PHP 8.0)'},
        {'version': '6.2', 'description': 'WordPress 6.2 (PHP 8.0)'},
        {'version': '6.1', 'description': 'WordPress 6.1 (PHP 8.0)'},
        {'version': '6.0', 'description': 'WordPress 6.0 (PHP 8.0)'},
        {'version': 'php8.2', 'description': 'Latest WordPress with PHP 8.2'},
        {'version': 'php8.1', 'description': 'Latest WordPress with PHP 8.1'},
        {'version': 'php8.0', 'description': 'Latest WordPress with PHP 8.0'},
        {'version': 'php7.4', 'description': 'Latest WordPress with PHP 7.4'},
    ]

@app.route('/api/create-project', methods=['POST'])
def create_project():
    """Create a new WordPress project"""
    try:
        # Handle file upload
        db_file_path = None
        validation_message = None
        if 'db_file' in request.files:
            file = request.files['db_file']
            if file and file.filename:
                # Create uploads directory if it doesn't exist
                uploads_dir = Path('uploads')
                uploads_dir.mkdir(exist_ok=True)
                
                # Save the uploaded file
                filename = secure_filename(file.filename)
                temp_db_path = uploads_dir / filename
                file.save(str(temp_db_path))
                
                print(f"🔄 Validating uploaded database file during project creation")
                
                # Validate and repair the database file if needed
                final_db_path, repair_message = validate_and_repair_database(temp_db_path)
                db_file_path = Path(final_db_path)
                
                if repair_message:
                    validation_message = f"Database file repaired: {repair_message}"
                    # Clean up original if repaired version was created
                    if final_db_path != str(temp_db_path):
                        try:
                            os.remove(str(temp_db_path))
                        except:
                            pass
                else:
                    validation_message = "Database file validation passed"
        
        # Get form data
        project_name = request.form.get('project_name')
        wordpress_version = request.form.get('wordpress_version')
        repo_url = request.form.get('repo_url')
        subfolder = request.form.get('subfolder', '')
        custom_domain = request.form.get('custom_domain', '')
        enable_ssl = request.form.get('enable_ssl') == 'on'
        enable_redis = request.form.get('enable_redis') == 'on'
        
        # Validate required fields
        if not project_name or not wordpress_version:
            return jsonify({'error': 'Project name and WordPress version are required'}), 400
        
        # Create the project
        result = project_manager.create_project(
            project_name=project_name,
            wordpress_version=wordpress_version,
            repo_url=repo_url,
            db_file_path=str(db_file_path) if db_file_path else None,
            subfolder=subfolder,
            custom_domain=custom_domain,
            enable_ssl=enable_ssl,
            enable_redis=enable_redis
        )
        
        if result['success']:
            response_data = {
                'message': 'Project created successfully!',
                'project': result['project']
            }
            if validation_message:
                response_data['validation_message'] = validation_message
            return jsonify(response_data)
        else:
            return jsonify({'error': result['error']}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects')
def list_projects():
    """List all WordPress projects"""
    projects = project_manager.list_projects()
    return jsonify(projects)

@app.route('/api/projects/<project_name>/status')
def project_status(project_name):
    """Get project status"""
    status = project_manager.get_project_status(project_name)
    return jsonify(status)

@app.route('/api/projects/<project_name>/start', methods=['POST'])
def start_project(project_name):
    """Start a WordPress project"""
    try:
        result = project_manager.start_project(project_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<project_name>/stop', methods=['POST'])
def stop_project(project_name):
    """Stop a WordPress project"""
    try:
        result = project_manager.stop_project(project_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<project_name>/delete', methods=['DELETE'])
def delete_project(project_name):
    """Delete a WordPress project"""
    try:
        result = project_manager.delete_project(project_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<project_name>/logs')
def project_logs(project_name):
    """Get project logs"""
    try:
        logs = project_manager.get_project_logs(project_name)
        return jsonify({'logs': logs})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<project_name>/debug-logs')
def project_debug_logs(project_name):
    """Get WordPress debug logs"""
    try:
        lines = request.args.get('lines', 50, type=int)
        result = project_manager.get_wordpress_debug_logs(project_name, lines)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<project_name>/debug-logs/clear', methods=['POST'])
def clear_debug_logs(project_name):
    """Clear WordPress debug logs"""
    try:
        result = project_manager.clear_wordpress_debug_logs(project_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<project_name>/upload-db', methods=['POST'])
def upload_database(project_name):
    """Upload and import database file for existing project with automatic validation and repair"""
    try:
        # Check if project exists
        project_path = Path('wordpress-projects') / project_name
        if not project_path.exists():
            return jsonify({'error': 'Project not found'}), 404
        
        # Handle file upload
        if 'db_file' not in request.files:
            return jsonify({'error': 'No database file provided'}), 400
        
        file = request.files['db_file']
        if not file or not file.filename:
            return jsonify({'error': 'No file selected'}), 400
        
        # Get form options
        backup_before_upload = request.form.get('backup_before_upload') == 'on'
        
        # Save the uploaded file to project's data directory
        data_dir = project_path / 'data'
        data_dir.mkdir(exist_ok=True)
        
        filename = secure_filename(file.filename)
        db_file_path = data_dir / filename
        file.save(str(db_file_path))
        
        print(f"🔄 Processing uploaded database file for project: {project_name}")
        
        # Validate and repair the database file if needed
        final_db_path, repair_message = validate_and_repair_database(db_file_path)
        
        # Prepare response message
        messages = []
        if repair_message:
            messages.append(f"🔧 {repair_message}")
            messages.append(f"📁 Using repaired file: {Path(final_db_path).name}")
        else:
            messages.append("✅ File validation passed - no repair needed")
        
        # Import the database (original or repaired version)
        print(f"📋 Importing database from: {Path(final_db_path).name}")
        result = project_manager.import_database(
            project_name=project_name,
            db_file_path=final_db_path,
            backup_before_import=backup_before_upload
        )
        
        if result['success']:
            messages.append("✅ Database imported successfully!")
            
            # Clean up: remove original file if a repaired version was created
            if repair_message and final_db_path != str(db_file_path):
                try:
                    os.remove(str(db_file_path))
                    messages.append(f"🧹 Cleaned up original file")
                except:
                    pass  # Don't fail if cleanup fails
            
            return jsonify({
                'message': ' | '.join(messages),
                'details': {
                    'validation_passed': repair_message is None,
                    'repair_performed': repair_message is not None,
                    'final_file': Path(final_db_path).name,
                    'import_successful': True
                }
            })
        else:
            return jsonify({
                'error': f"Database import failed: {result['error']}",
                'details': {
                    'validation_passed': repair_message is None,
                    'repair_performed': repair_message is not None,
                    'final_file': Path(final_db_path).name,
                    'import_successful': False
                }
            }), 400
            
    except Exception as e:
        print(f"❌ Error in upload_database: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/import-database/<project_name>', methods=['POST'])
def import_database_legacy(project_name):
    """Import database for a project (legacy endpoint with automatic validation and repair)"""
    try:
        if 'db_file' not in request.files:
            return jsonify({'error': 'No database file provided'}), 400
        
        file = request.files['db_file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Create uploads directory if it doesn't exist
        uploads_dir = Path('uploads')
        uploads_dir.mkdir(exist_ok=True)
        
        # Save the uploaded file
        filename = secure_filename(file.filename)
        temp_db_path = uploads_dir / filename
        file.save(str(temp_db_path))
        
        print(f"🔄 Processing uploaded database file for legacy import: {project_name}")
        
        # Validate and repair the database file if needed
        final_db_path, repair_message = validate_and_repair_database(temp_db_path)
        
        # Import the database (original or repaired version)
        result = project_manager.import_database(project_name, final_db_path)
        
        # Clean up uploaded files
        try:
            if final_db_path != str(temp_db_path):
                # Remove both original and repaired files for legacy endpoint
                os.remove(str(temp_db_path))
                os.remove(final_db_path)
            else:
                # Remove original file only
                os.remove(str(temp_db_path))
        except:
            pass
        
        if result['success']:
            response_data = {'message': result['message']}
            if repair_message:
                response_data['validation_message'] = f"File was repaired: {repair_message}"
            return jsonify(response_data)
        else:
            return jsonify({'error': result['error']}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/fix-upload-limits/<project_name>', methods=['POST'])
def fix_upload_limits(project_name):
    """Fix PHP upload limits for a project"""
    try:
        result = project_manager.fix_php_upload_limits(project_name)
        
        if result['success']:
            return jsonify({'message': result['message']})
        else:
            return jsonify({'error': result['error']}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/add-wpcli/<project_name>', methods=['POST'])
def add_wpcli_to_project(project_name):
    """Add WP CLI service to a project"""
    try:
        result = project_manager.add_wpcli_to_project(project_name)
        
        if result['success']:
            return jsonify({'message': result['message']})
        else:
            return jsonify({'error': result['error']}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/add-wpcli-all', methods=['POST'])
def add_wpcli_to_all_projects():
    """Add WP CLI service to all projects"""
    try:
        result = project_manager.add_wpcli_to_all_projects()
        
        if result['success']:
            return jsonify({
                'message': f'WP CLI added to {result["successful"]}/{result["total"]} projects',
                'results': result['results']
            })
        else:
            return jsonify({
                'error': f'Failed to add WP CLI to {result["failed"]} projects',
                'results': result['results']
            }), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/wp-cli/<project_name>', methods=['POST'])
def run_wp_cli_command(project_name):
    """Run a WP CLI command on a project"""
    try:
        data = request.get_json()
        if not data or 'command' not in data:
            return jsonify({'error': 'No command provided'}), 400
        
        command = data['command']
        result = project_manager.run_wp_cli_command(project_name, command)
        
        if result['success']:
            return jsonify({
                'message': 'Command executed successfully',
                'output': result['output'],
                'command': result['command']
            })
        else:
            return jsonify({
                'error': result['error'],
                'command': result['command']
            }), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs('wordpress-projects', exist_ok=True)
    os.makedirs('uploads', exist_ok=True)
    os.makedirs('utils', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    
    print("🚀 Starting WordPress Local Development Environment...")
    print("📂 Projects will be created in: ./wordpress-projects/")
    print("🌐 Open http://localhost:5001 in your browser")
    
    app.run(debug=True, host='0.0.0.0', port=5001) 