import os
import json
import re
import secrets
import shutil
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from utils.project_manager import ProjectManager
from utils.ssl_generator import SSLGenerator
from utils.hosts_manager import HostsManager
from utils.validators import is_valid_project_name, is_valid_wordpress_version

# All project, ssl and data paths are relative to the repo. Anchor the process
# here so `python /path/to/app.py` works from any directory.
BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)

app = Flask(__name__)


def _load_secret_key():
    """Use FLASK_SECRET_KEY, or a key persisted in the repo (not in git)."""
    env_key = os.environ.get('FLASK_SECRET_KEY')
    if env_key:
        return env_key

    key_file = BASE_DIR / '.flask_secret'
    try:
        try:
            key = key_file.read_text().strip()
            if key:
                return key
        except OSError:
            pass

        key = secrets.token_hex(32)
        try:
            # O_EXCL makes creation atomic: two first starts cannot both win
            # and overwrite each other with different keys.
            fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            existing = key_file.read_text().strip()
            return existing or key

        try:
            with os.fdopen(fd, 'w') as handle:
                handle.write(key)
        except BaseException:
            try:
                key_file.unlink()
            except OSError:
                pass
            raise
        return key
    except OSError:
        # Read-only checkout: fall back to a per-process key.
        return secrets.token_hex(32)


app.secret_key = _load_secret_key()

# Only answer requests addressed to this machine. Binding to 127.0.0.1 stops
# other devices, and this stops DNS-rebinding pages from reaching the app.
app.config['TRUSTED_HOSTS'] = ['localhost', '127.0.0.1', '[::1]']


# Cap request bodies so a single upload cannot fill the disk. DB dumps are the
# large case, so the default is generous and can be overridden. A malformed
# value must not crash the app at import time.
def _max_upload_mb():
    try:
        value = int(os.environ.get('MAX_UPLOAD_MB', '2048'))
    except (TypeError, ValueError):
        return 2048
    return value if value > 0 else 2048


MAX_UPLOAD_MB = _max_upload_mb()
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_MB * 1024 * 1024


def safe_upload_filename(filename):
    """Return a safe basename while preserving non-ASCII names.

    Werkzeug's secure_filename strips non-ASCII entirely: "数据库.sql" becomes
    "sql", which can collide with another upload. Keep the user's name but
    remove path components, control characters and reserved characters.
    """
    name = str(filename).replace('\\', '/').rsplit('/', 1)[-1]
    name = ''.join(
        ch for ch in name
        if ch.isprintable() and ch not in '/\\:*?"<>|`$;'
    ).strip()
    if not name or set(name) == {'.'}:
        return ''

    # Keep the extension intact even when the basename is very long: generated
    # Makefiles and importers still rely on the suffix.
    stem, dot, extension = name.rpartition('.')
    if dot and stem:
        extension = extension[:50]
        stem = stem[:max(1, 200 - len(extension) - 1)]
        return f"{stem}.{extension}"
    return name[:200]


def internal_error(exc, context=None):
    """Log the detail and return a generic body (no local paths to the client)."""
    # Streaming/upload errors raised while reading the request are HTTP
    # exceptions, not bugs; surface them as JSON instead of a 500.
    if isinstance(exc, HTTPException):
        if exc.code == 413:
            return jsonify({'error': f'Upload too large (limit {MAX_UPLOAD_MB} MB)'}), 413
        return jsonify({'error': exc.description}), exc.code or 500

    context = context or request.endpoint or 'request'
    app.logger.exception('Unhandled error during %s: %s', context, exc)
    return jsonify({'error': f'Internal server error while handling {context}'}), 500

@app.before_request
def validate_project_name():
    """Reject project names that are not a single safe path segment.

    Without this, a request such as ``DELETE /api/projects/../delete`` reaches
    the delete view with ``project_name='..'`` and removes the whole repo.
    """
    project_name = (request.view_args or {}).get('project_name')
    if project_name is not None and not is_valid_project_name(project_name):
        return jsonify({'error': 'Invalid project name'}), 400

LOCAL_HOSTNAMES = {'localhost', '127.0.0.1', '::1'}

@app.before_request
def reject_cross_origin_writes():
    """Block state-changing requests coming from another website.

    Browsers send Origin on cross-site POSTs, so a page on the internet cannot
    drive this local app (CSRF) even though it can reach 127.0.0.1.
    """
    if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return None

    origin = request.headers.get('Origin')
    if not origin:
        # Non-browser clients (curl, scripts) don't send Origin.
        return None

    if urlparse(origin).hostname not in LOCAL_HOSTNAMES:
        return jsonify({'error': 'Cross-origin request rejected'}), 403

# Docker Compose, port allocation and hosts edits are not reentrant. Serialize
# mutations so two clicks (or two tabs) cannot allocate the same ports or run
# compose operations over each other. Waiting is bounded: a stuck operation
# answers 503 instead of queueing every later write forever.
_MUTATION_LOCK = threading.Lock()
_MUTATION_LOCK_TIMEOUT = 30

@app.before_request
def serialize_mutations():
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        if not _MUTATION_LOCK.acquire(timeout=_MUTATION_LOCK_TIMEOUT):
            return jsonify({'error': 'Another operation is in progress; try again shortly.'}), 503
        g.mutation_lock_held = True

@app.teardown_request
def release_mutation_lock(exc):
    if g.pop('mutation_lock_held', False):
        _MUTATION_LOCK.release()

@app.errorhandler(413)
def upload_too_large(exc):
    return jsonify({'error': f'Upload too large (limit {MAX_UPLOAD_MB} MB)'}), 413

# Initialize managers
project_manager = ProjectManager()
ssl_generator = SSLGenerator()
hosts_manager = HostsManager()

# Detect Docker Compose version at startup
try:
    from utils.docker_compose_detect import get_compose_command, get_compose_version
    _compose_cmd = get_compose_command()
    print(f"🐳 Docker Compose detected: {' '.join(_compose_cmd)} ({get_compose_version()})")
except RuntimeError as e:
    print(f"⚠️  WARNING: {e}")
    print("   Some features will not work without Docker Compose.")
except Exception as e:
    print(f"⚠️  WARNING: Could not detect Docker Compose: {e}")

# Cache for WordPress versions (cache for 1 hour)
wordpress_versions_cache = {
    'data': None,
    'timestamp': 0,
    'cache_duration': 3600  # 1 hour in seconds
}
_VERSIONS_LOCK = threading.Lock()
_VERSIONS_FETCH_LOCK = threading.Lock()


def _read_versions_cache(require_fresh=False):
    with _VERSIONS_LOCK:
        data = wordpress_versions_cache['data']
        age = time.time() - wordpress_versions_cache['timestamp']
        duration = wordpress_versions_cache['cache_duration']
    if require_fresh and not (data and age < duration):
        return None
    return data


def _write_versions_cache(data, timestamp):
    with _VERSIONS_LOCK:
        wordpress_versions_cache['data'] = data
        wordpress_versions_cache['timestamp'] = timestamp


@app.route('/')
def index():
    """Main interface for creating WordPress projects"""
    projects = project_manager.list_projects()
    return render_template('index.html', projects=projects)

@app.route('/api/wordpress-versions')
def get_wordpress_versions():
    """Get available WordPress Docker image versions from Docker Hub"""
    # Check cache first
    current_time = time.time()
    cached = _read_versions_cache(require_fresh=True)
    if cached:
        return jsonify(cached)

    # One request fetches; concurrent callers wait and reuse its result instead
    # of all hitting Docker Hub at once (cache stampede).
    if not _VERSIONS_FETCH_LOCK.acquire(timeout=20):
        cached = _read_versions_cache()
        return jsonify(cached or get_fallback_versions())

    try:
        cached = _read_versions_cache(require_fresh=True)
        if cached:
            return jsonify(cached)

        import requests

        print("Fetching WordPress versions from Docker Hub...")

        # Fetch WordPress image tags from Docker Hub API
        # Paginate through results — Docker Hub returns newest tags first and
        # beta/RC tags now outnumber stable tags on the first page.
        versions = []
        processed_tags = set()
        url = "https://hub.docker.com/v2/repositories/library/wordpress/tags/?page_size=100"
        max_pages = 5  # Up to 500 tags to ensure we find enough stable versions

        for _page in range(max_pages):
            response = requests.get(
                url,
                timeout=10,
                headers={'User-Agent': 'wordpress-local-dev/1.0'},
            )

            if response.status_code != 200:
                print(f"Docker Hub API returned status {response.status_code}")
                break

            data = response.json()

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

            # Stop paginating once we have enough stable versions
            if len(versions) >= 30:
                break

            url = data.get('next')
            if not url:
                break

        if not versions:
            print("No stable versions found after pagination")
            cached = _read_versions_cache()
            if cached:
                return jsonify(cached)
            return jsonify(get_fallback_versions())

        # Sort versions by priority (latest first, then numeric versions)
        versions.sort(key=lambda x: get_version_priority(x['version']))

        # Limit to most relevant versions
        final_versions = versions[:20]

        # Update cache
        _write_versions_cache(final_versions, current_time)

        print(f"Successfully fetched {len(final_versions)} WordPress versions from Docker Hub")
        return jsonify(final_versions)

    except Exception as e:
        print(f"Error fetching WordPress versions from Docker Hub: {str(e)}")
        # Use cached data if available, otherwise fallback
        cached = _read_versions_cache()
        if cached:
            print("Using cached WordPress versions due to API error")
            return jsonify(cached)

        print("Using fallback WordPress versions")
        fallback_versions = get_fallback_versions()

        # Cache fallback versions too
        _write_versions_cache(fallback_versions, current_time)

        return jsonify(fallback_versions)

    finally:
        _VERSIONS_FETCH_LOCK.release()


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
        {'version': '6.8', 'description': 'WordPress 6.8 (Default PHP)'},
        {'version': '6.7', 'description': 'WordPress 6.7 (Default PHP)'},
        {'version': '6.6', 'description': 'WordPress 6.6 (Default PHP)'},
        {'version': '6.5', 'description': 'WordPress 6.5 (Default PHP)'},
        {'version': '6.4', 'description': 'WordPress 6.4 (PHP 8.1)'},
        {'version': '6.3', 'description': 'WordPress 6.3 (PHP 8.0)'},
        {'version': 'php8.4', 'description': 'Latest WordPress with PHP 8.4'},
        {'version': 'php8.3', 'description': 'Latest WordPress with PHP 8.3'},
        {'version': 'php8.2', 'description': 'Latest WordPress with PHP 8.2'},
        {'version': 'php8.1', 'description': 'Latest WordPress with PHP 8.1'},
    ]

@app.route('/api/create-project', methods=['POST'])
def create_project():
    """Create a new WordPress project"""
    tmpdir = None
    try:
        # Get form data first to get project name
        project_name = request.form.get('project_name')
        if not project_name:
            return jsonify({'error': 'Project name is required'}), 400

        # Handle file upload - save to temp dir (never create project folder before create_project)
        db_file_path = None
        if 'db_file' in request.files:
            file = request.files['db_file']
            if file and file.filename:
                filename = safe_upload_filename(file.filename)
                if not filename:
                    return jsonify({'error': 'Invalid database file name'}), 400
                tmpdir = tempfile.mkdtemp(prefix='wp-create-db-')
                upload_path = Path(tmpdir) / filename
                file.save(str(upload_path))
                db_file_path = upload_path

        # Get remaining form data
        wordpress_version = request.form.get('wordpress_version')
        repo_url = request.form.get('repo_url')
        subfolder = request.form.get('subfolder', '')
        custom_domain = request.form.get('custom_domain', '')
        enable_ssl = request.form.get('enable_ssl') == 'on'
        enable_redis = request.form.get('enable_redis') == 'on'

        # Validate required fields
        if not project_name or not wordpress_version:
            return jsonify({'error': 'Project name and WordPress version are required'}), 400
        if not is_valid_wordpress_version(wordpress_version):
            return jsonify({'error': 'Invalid WordPress version'}), 400

        # Create the project (moves DB from temp to project data/ if provided)
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
            return jsonify({
                'message': 'Project created successfully!',
                'project': result['project']
            })
        else:
            return jsonify({'error': result['error']}), 400

    except Exception as e:
        return internal_error(e)
    finally:
        if tmpdir and Path(tmpdir).exists():
            try:
                shutil.rmtree(tmpdir)
            except Exception:
                pass

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
        return internal_error(e)

@app.route('/api/projects/<project_name>/stop', methods=['POST'])
def stop_project(project_name):
    """Stop a WordPress project"""
    try:
        result = project_manager.stop_project(project_name)
        return jsonify(result)
    except Exception as e:
        return internal_error(e)

@app.route('/api/projects/<project_name>/delete', methods=['DELETE'])
def delete_project(project_name):
    """Delete a WordPress project"""
    try:
        result = project_manager.delete_project(project_name)
        return jsonify(result)
    except Exception as e:
        return internal_error(e)

@app.route('/api/projects/<project_name>/logs')
def project_logs(project_name):
    """Get project logs"""
    try:
        logs = project_manager.get_project_logs(project_name)
        return jsonify({'logs': logs})
    except Exception as e:
        return internal_error(e)

@app.route('/api/projects/<project_name>/debug-logs')
def project_debug_logs(project_name):
    """Get WordPress debug logs"""
    try:
        lines = max(1, min(request.args.get('lines', 50, type=int), 2000))
        result = project_manager.get_wordpress_debug_logs(project_name, lines)
        return jsonify(result)
    except Exception as e:
        return internal_error(e)

@app.route('/api/projects/<project_name>/debug-logs/clear', methods=['POST'])
def clear_debug_logs(project_name):
    """Clear WordPress debug logs"""
    try:
        result = project_manager.clear_wordpress_debug_logs(project_name)
        return jsonify(result)
    except Exception as e:
        return internal_error(e)

@app.route('/api/projects/<project_name>/fix-database-connection', methods=['POST'])
def fix_database_connection(project_name):
    """Fix database connection issues for a project"""
    try:
        result = project_manager.fix_database_connection(project_name)
        if result['success']:
            return jsonify(result)
        else:
            return jsonify({'error': result['error']}), 400
    except Exception as e:
        return internal_error(e)

@app.route('/api/projects/<project_name>/fix-install-detection', methods=['POST'])
def fix_install_detection(project_name):
    """Fix WordPress redirecting to install.php when database is already imported"""
    try:
        result = project_manager.fix_wordpress_install_detection(project_name)
        if result['success']:
            return jsonify(result)
        else:
            return jsonify({'error': result['error']}), 400
    except Exception as e:
        return internal_error(e)

@app.route('/api/projects/<project_name>/wp-config')
def get_wp_config(project_name):
    """Get wp-config.php content from the WordPress container"""
    try:
        result = project_manager.get_wp_config(project_name)
        return jsonify(result)
    except Exception as e:
        return internal_error(e)

@app.route('/api/projects/<project_name>/wp-config', methods=['POST'])
def update_wp_config(project_name):
    """Update wp-config.php in the WordPress container"""
    try:
        data = request.get_json()
        if not data or 'content' not in data:
            return jsonify({'success': False, 'error': 'Missing "content" in request body'}), 400
        result = project_manager.update_wp_config(project_name, data['content'])
        return jsonify(result)
    except Exception as e:
        return internal_error(e)

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
        url_search = (request.form.get('url_search') or '').strip() or None
        url_replace = (request.form.get('url_replace') or '').strip() or None

        # Save the uploaded file to project's data directory
        data_dir = project_path / 'data'
        data_dir.mkdir(exist_ok=True)

        filename = safe_upload_filename(file.filename)
        if not filename:
            return jsonify({'error': 'Invalid database file name'}), 400
        db_file_path = data_dir / filename
        file.save(str(db_file_path))

        print(f"🔄 Processing uploaded database file for project: {project_name}")

        # Import database using new fallback strategy (tries original first, then repaired)
        result = project_manager.import_database(
            project_name=project_name,
            db_file_path=str(db_file_path),
            backup_before_import=backup_before_upload,
            url_search=url_search,
            url_replace=url_replace
        )

        if result['success']:
            return jsonify({
                'message': result['message'],
                'logs': result.get('logs', []),
                'details': {
                    'import_successful': True,
                    'final_file': Path(str(db_file_path)).name
                }
            })
        else:
            return jsonify({
                'error': f"Database import failed: {result['error']}",
                'logs': result.get('logs', []),
                'details': {
                    'import_successful': False,
                    'final_file': Path(str(db_file_path)).name
                }
            }), 400

    except Exception as e:
        print(f"❌ Error in upload_database: {str(e)}")
        return internal_error(e)

@app.route('/api/fix-upload-limits/<project_name>', methods=['POST'])
def fix_upload_limits(project_name):
    """Fix PHP upload limits for a project.

    Limits are written at container-creation time; this endpoint is kept for
    the dashboard and returns the current status.
    """
    try:
        result = project_manager.fix_php_upload_limits(project_name)

        if result['success']:
            return jsonify({'message': result['message']})
        else:
            return jsonify({'error': result['error']}), 400

    except Exception as e:
        return internal_error(e)

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
        return internal_error(e)

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
        return internal_error(e)

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
                'error': result.get('error', 'Command failed'),
                'command': result.get('command', command)
            }), 400

    except Exception as e:
        return internal_error(e)

@app.route('/api/projects/<project_name>/update-wordpress-version', methods=['POST'])
def update_wordpress_version(project_name):
    """Update WordPress version for an existing project"""
    try:
        data = request.get_json()
        if not data or 'version' not in data:
            return jsonify({'error': 'WordPress version is required'}), 400

        new_version = data['version']
        if not is_valid_wordpress_version(new_version):
            return jsonify({'error': 'Invalid WordPress version'}), 400
        result = project_manager.update_wordpress_version(project_name, new_version)

        if result['success']:
            return jsonify({
                'message': result['message'],
                'version': new_version
            })
        else:
            return jsonify({'error': result['error']}), 400

    except Exception as e:
        return internal_error(e)

@app.route('/api/projects/<project_name>/sync-wordpress-core', methods=['POST'])
def sync_wordpress_core(project_name):
    """Sync WordPress core files from the image into the project docroot.

    Needed because the docroot lives in a persistent volume that the WordPress
    image only seeds when empty. Pass {"force": true} to overwrite a docroot
    that is newer than the image (i.e. accept a downgrade).
    """
    try:
        data = request.get_json(silent=True) or {}
        force = bool(data.get('force', False))
        result = project_manager.sync_wordpress_core(project_name, force=force)

        if result['success']:
            return jsonify({
                'message': result['message'],
                'synced': result.get('synced', False),
                'version': result.get('version')
            })
        else:
            return jsonify({'error': result['error']}), 400

    except Exception as e:
        return internal_error(e)

@app.route('/api/projects/<project_name>/core-version', methods=['GET'])
def get_core_version(project_name):
    """Report the WordPress version in the image vs. the one actually served"""
    try:
        result = project_manager.get_core_version_status(project_name)

        if result['success']:
            return jsonify({
                'image_version': result['image_version'],
                'docroot_version': result['docroot_version'],
                'in_sync': result['in_sync']
            })
        else:
            return jsonify({'error': result['error']}), 400

    except Exception as e:
        return internal_error(e)

@app.route('/api/projects/<project_name>/update-domain', methods=['POST'])
def update_domain(project_name):
    """Update domain for an existing project"""
    try:
        data = request.get_json()
        if not data or 'domain' not in data:
            return jsonify({'error': 'Domain is required'}), 400

        new_domain = data['domain']
        enable_ssl = data.get('enable_ssl', None)

        result = project_manager.update_domain(project_name, new_domain, enable_ssl)

        if result['success']:
            return jsonify({
                'message': result['message'],
                'domain': new_domain
            })
        else:
            return jsonify({'error': result['error']}), 400

    except Exception as e:
        return internal_error(e)

@app.route('/api/projects/<project_name>/update-repository', methods=['POST'])
def update_repository(project_name):
    """Update repository URL for an existing project"""
    try:
        data = request.get_json()
        if not data or 'repo_url' not in data:
            return jsonify({'error': 'Repository URL is required'}), 400

        new_repo_url = data['repo_url']
        result = project_manager.update_repository(project_name, new_repo_url)

        if result['success']:
            return jsonify({
                'message': result['message'],
                'repo_url': new_repo_url
            })
        else:
            return jsonify({'error': result['error']}), 400

    except Exception as e:
        return internal_error(e)

@app.route('/api/projects/<project_name>/link-repository', methods=['POST'])
def link_repository(project_name):
    """Link an existing manually cloned repository to wp-content"""
    try:
        result = project_manager.link_existing_repository(project_name)

        if result['success']:
            return jsonify({
                'message': result['message']
            })
        else:
            return jsonify({'error': result['error']}), 400

    except Exception as e:
        return internal_error(e)

@app.route('/api/projects/<project_name>/update-config', methods=['POST'])
def update_project_config(project_name):
    """Update project configuration settings"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Configuration data is required'}), 400

        # Extract allowed configuration fields
        updates = {}
        allowed_fields = ['enable_ssl', 'enable_redis', 'subfolder', 'custom_domain']

        for field in allowed_fields:
            if field in data:
                updates[field] = data[field]

        if not updates:
            return jsonify({'error': 'No valid configuration fields provided'}), 400

        result = project_manager.update_project_config(project_name, **updates)

        if result['success']:
            return jsonify({
                'message': result['message'],
                'updated_fields': result.get('updated_fields', [])
            })
        else:
            return jsonify({'error': result['error']}), 400

    except Exception as e:
        return internal_error(e)

@app.route('/api/projects/<project_name>/update-database', methods=['POST'])
def update_project_database(project_name):
    """Add an initial database to a project that was created without one, or replace existing database"""
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

        filename = safe_upload_filename(file.filename)
        if not filename:
            return jsonify({'error': 'Invalid database file name'}), 400
        db_file_path = data_dir / filename
        file.save(str(db_file_path))

        print(f"🔄 Processing database file for project update: {project_name}")

        # Use the update_project_with_database method which handles both initial and replacement cases
        result = project_manager.update_project_with_database(
            project_name=project_name,
            db_file_path=str(db_file_path),
            backup_before_import=backup_before_upload
        )

        if result['success']:
            return jsonify({
                'message': result['message'],
                'logs': result.get('logs', []),
                'details': {
                    'import_successful': True,
                    'final_file': Path(str(db_file_path)).name
                }
            })
        else:
            return jsonify({
                'error': f"Database import failed: {result['error']}",
                'logs': result.get('logs', []),
                'details': {
                    'import_successful': False,
                    'final_file': Path(str(db_file_path)).name
                }
            }), 400

    except Exception as e:
        print(f"❌ Error in update_project_database: {str(e)}")
        return internal_error(e)

@app.route('/api/ssl/setup-mkcert', methods=['POST'])
def setup_mkcert():
    """Help user set up mkcert for trusted SSL certificates"""
    try:
        ssl_generator = SSLGenerator()
        ssl_generator.setup_mkcert()

        return jsonify({
            'message': 'mkcert setup instructions displayed',
            'mkcert_available': ssl_generator.mkcert_available
        })
    except Exception as e:
        return internal_error(e)

@app.route('/api/projects/<project_name>/regenerate-ssl', methods=['POST'])
def regenerate_ssl(project_name):
    """Regenerate SSL certificate for an existing project"""
    try:
        ssl_generator = SSLGenerator()

        # Get project config to find domain
        project_path = project_manager.projects_dir / project_name
        config_path = project_path / "config.json"

        if not config_path.exists():
            return jsonify({'error': 'Project config not found'}), 404

        with open(config_path, 'r') as f:
            config = json.load(f)

        domain = config.get('domain', '').split('/')[0]
        if not domain:
            return jsonify({'error': 'Project domain not found'}), 400

        # Regenerate SSL certificate
        success = ssl_generator.generate_ssl_cert(project_name, domain)

        if success:
            return jsonify({
                'message': f'SSL certificate regenerated for {domain}',
                'mkcert_used': ssl_generator.mkcert_available
            })
        else:
            return jsonify({'error': 'Failed to regenerate SSL certificate'}), 500

    except Exception as e:
        return internal_error(e)

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs('wordpress-projects', exist_ok=True)
    os.makedirs('utils', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)

    print("🚀 Starting WordPress Local Development Environment...")
    print("📂 Projects will be created in: ./wordpress-projects/")
    print("🌐 Open http://localhost:5001 in your browser")

    debug = os.environ.get('FLASK_DEBUG') == '1'
    app.run(debug=debug, host='127.0.0.1', port=5001)