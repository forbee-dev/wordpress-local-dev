import os
import subprocess
import shutil
import time
from pathlib import Path


class RepositoryManager:
    """Handles Git repository operations and repository analysis"""
    
    def __init__(self):
        pass
    
    def clone_repository(self, repo_url, project_path):
        """Clone entire repository into project directory"""
        start_time = time.time()
        repo_dir = None
        
        try:
            # Skip cloning if no repo URL provided
            if not repo_url or not repo_url.strip():
                print("ℹ️  No repository URL provided, skipping Git clone")
                return None
            
            # Create repository directory inside project
            repo_dir = project_path / "repository"
            
            # Check if repository directory already exists
            if repo_dir.exists():
                print(f"   ⚠️  Repository directory already exists, removing it first...")
                shutil.rmtree(repo_dir)
            
            print(f"🔄 Starting repository clone operation")
            print(f"   📍 Repository URL: {repo_url}")
            print(f"   📂 Target directory: {repo_dir}")
            
            # Create environment with credential helpers disabled to avoid prompts
            env = os.environ.copy()
            env['GIT_TERMINAL_PROMPT'] = '0'  # Disable interactive prompts
            env['GIT_ASKPASS'] = 'echo'       # Provide empty password for HTTPS
            
            # Log git version for debugging
            git_version_result = subprocess.run(
                ['git', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if git_version_result.returncode == 0:
                print(f"   🔧 Git version: {git_version_result.stdout.strip()}")
            
            # Clone repository directly to repository directory
            clone_timeout = 300  # 5 minutes for large repos / slow connections
            print(f"   ⏱️  Timeout: {clone_timeout} seconds")
            print(f"   🚀 Executing: git clone --progress {repo_url} {repo_dir}")
            print(f"   ⏳ Cloning repository (this may take a while for large repositories)...")
            print(f"   📡 Streaming git output in real-time:")
            print(f"   {'-' * 60}")
            
            # Use Popen to stream output in real-time
            # Git sends progress to stderr, so we merge it into stdout
            process = subprocess.Popen([
                'git', 'clone', 
                '--progress',                # Show progress
                repo_url, 
                str(repo_dir)
            ], 
            env=env, 
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Merge stderr into stdout
            text=True,
            bufsize=1  # Line buffered
            )
            
            # Stream output line by line
            output_lines = []
            last_output_time = time.time()
            
            try:
                # Read output line by line with timeout checking
                import threading
                import sys
                
                def read_output():
                    """Read output in a separate thread"""
                    nonlocal last_output_time
                    try:
                        for line in iter(process.stdout.readline, ''):
                            if line:
                                line = line.rstrip()
                                output_lines.append(line)
                                last_output_time = time.time()
                                if line.strip():
                                    print(f"   📥 {line}", flush=True)
                                    sys.stdout.flush()
                    except Exception as e:
                        print(f"   ⚠️  Error reading output: {str(e)}", flush=True)
                
                # Start reading output in background thread
                reader_thread = threading.Thread(target=read_output, daemon=True)
                reader_thread.start()
                
                # Wait for process with timeout checking and heartbeat
                heartbeat_interval = 5  # Show heartbeat every 5 seconds
                last_heartbeat = time.time()
                
                while process.poll() is None:
                    # Check for timeout
                    elapsed = time.time() - start_time
                    if elapsed > clone_timeout:
                        process.kill()
                        process.wait()
                        raise subprocess.TimeoutExpired('git clone', clone_timeout)
                    
                    # Show heartbeat if no output for a while
                    if time.time() - last_heartbeat > heartbeat_interval:
                        if time.time() - last_output_time > heartbeat_interval:
                            elapsed_str = f"{elapsed:.0f}s"
                            print(f"   ⏳ Still cloning... ({elapsed_str} elapsed)", flush=True)
                        last_heartbeat = time.time()
                    
                    # Wait a bit before checking again
                    time.sleep(0.2)
                
                # Wait a moment for thread to finish reading
                reader_thread.join(timeout=3)
                
                # Get return code
                returncode = process.returncode
                elapsed_time = time.time() - start_time
                
                print(f"   {'-' * 60}")
                
            except subprocess.TimeoutExpired:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                raise
            
            if returncode != 0:
                # If clone failed, provide helpful error message
                print(f"   ❌ Clone failed after {elapsed_time:.1f} seconds")
                print(f"   🔍 Error details:")
                # Show all output lines that might contain errors
                error_lines = [line for line in output_lines if any(keyword in line.lower() for keyword in ['error', 'fatal', 'failed', 'denied', 'not found'])]
                if error_lines:
                    for line in error_lines:
                        print(f"      {line}")
                else:
                    # Show last few lines if no obvious errors found
                    for line in output_lines[-10:]:
                        if line.strip():
                            print(f"      {line}")
                
                # Combine output for error message
                error_msg = '\n'.join(output_lines) if output_lines else "Unknown error"
                
                if "Authentication failed" in error_msg or "fatal: could not read Username" in error_msg or "could not read Username" in error_msg:
                    raise Exception(
                        f"Git authentication failed. For private repositories:\n"
                        f"• Use SSH URL (git@github.com:user/repo.git) with configured SSH keys\n"
                        f"• Or use personal access token in HTTPS URL\n"
                        f"• Or make the repository public\n"
                        f"Error: {error_msg}"
                    )
                elif "Repository not found" in error_msg or "not found" in error_msg.lower():
                    raise Exception(f"Repository not found or access denied: {repo_url}\nError: {error_msg}")
                elif "fatal:" in error_msg.lower():
                    raise Exception(f"Git clone failed: {error_msg}")
                else:
                    raise Exception(f"Failed to clone repository: {error_msg}")
            
            # Verify repository was cloned successfully
            if not repo_dir.exists():
                print(f"   ❌ Repository directory was not created after clone")
                raise Exception("Repository directory was not created after clone")
            
            # Check if .git directory exists
            git_dir = repo_dir / ".git"
            if not git_dir.exists():
                print(f"   ❌ .git directory not found after clone")
                raise Exception("Repository cloned but .git directory not found - clone may have failed")
            
            print(f"   ✅ Repository cloned successfully in {elapsed_time:.1f} seconds")
            
            # Get repository info for logging
            try:
                branch_result = subprocess.run(
                    ['git', 'branch', '--show-current'],
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"
                print(f"   🌿 Branch: {branch}")
            except:
                pass
            
            # Analyze repository structure
            print(f"   📂 Analyzing repository structure...")
            repo_structure = self.analyze_repository_structure(repo_dir)
            print(f"   📦 Repository type: {repo_structure['type']}")
            if repo_structure['has_wp_content']:
                print(f"   ✓ Contains wp-content directory")
            if repo_structure['is_theme']:
                print(f"   ✓ Detected as WordPress theme")
            if repo_structure['is_plugin']:
                print(f"   ✓ Detected as WordPress plugin")
            if repo_structure['has_composer']:
                print(f"   ✓ Contains composer.json")
            if repo_structure['has_package_json']:
                print(f"   ✓ Contains package.json")
            
            # Set up wp-content linking/copying based on repository structure
            print(f"   🔗 Setting up wp-content from repository...")
            wp_content_path = project_path / "wp-content"
            self.setup_wp_content_from_repo(repo_dir, wp_content_path, repo_structure)
            
            total_time = time.time() - start_time
            print(f"   ✅ Repository setup completed in {total_time:.1f} seconds total")
                
            return repo_structure
            
        except subprocess.TimeoutExpired:
            elapsed_time = time.time() - start_time
            print(f"   ⏱️  Clone timed out after {elapsed_time:.1f} seconds")
            # Clean up on timeout
            if repo_dir and repo_dir.exists():
                print(f"   🧹 Cleaning up partial clone...")
                shutil.rmtree(repo_dir)
            raise Exception(
                f"Git clone timed out after {clone_timeout} seconds. "
                "Large repos or slow connections may need longer. Check repository URL and network."
            )
        except subprocess.CalledProcessError as e:
            elapsed_time = time.time() - start_time
            print(f"   ❌ Git process error after {elapsed_time:.1f} seconds: {str(e)}")
            # Clean up on error
            if repo_dir and repo_dir.exists():
                print(f"   🧹 Cleaning up failed clone...")
                shutil.rmtree(repo_dir)
            raise Exception(f"Failed to clone repository: {str(e)}")
        except Exception as e:
            elapsed_time = time.time() - start_time
            print(f"   ❌ Error after {elapsed_time:.1f} seconds: {str(e)}")
            # Clean up on any error
            if repo_dir and repo_dir.exists():
                print(f"   🧹 Cleaning up after error...")
                try:
                    shutil.rmtree(repo_dir)
                except:
                    pass
            raise e
    
    def analyze_repository_structure(self, repo_dir):
        """Analyze repository structure to determine type and content"""
        structure = {
            'type': 'unknown',
            'has_wp_content': False,
            'is_wp_content': False,
            'has_composer': False,
            'has_package_json': False,
            'is_theme': False,
            'is_plugin': False,
            'wp_content_path': None
        }
        
        if not repo_dir.exists():
            print(f"      ⚠️  Repository directory does not exist: {repo_dir}")
            return structure
        
        # Check for wp-content directory
        wp_content_path = repo_dir / "wp-content"
        if wp_content_path.exists() and wp_content_path.is_dir():
            structure['has_wp_content'] = True
            structure['wp_content_path'] = wp_content_path
            structure['type'] = 'full-wordpress-project'
            print(f"      ✓ Found wp-content/ directory")
        
        # Check for Composer
        composer_file = repo_dir / "composer.json"
        if composer_file.exists():
            structure['has_composer'] = True
            print(f"      ✓ Found composer.json")
        
        # Check for Node.js/NPM
        package_file = repo_dir / "package.json"
        if package_file.exists():
            structure['has_package_json'] = True
            print(f"      ✓ Found package.json")
        
        # Check if the repo root IS the wp-content (has plugins/ and themes/ at root)
        if not structure['has_wp_content']:
            plugins_dir = repo_dir / "plugins"
            themes_dir = repo_dir / "themes"
            if plugins_dir.exists() and plugins_dir.is_dir() and themes_dir.exists() and themes_dir.is_dir():
                structure['is_wp_content'] = True
                structure['wp_content_path'] = repo_dir
                structure['type'] = 'wp-content-root'
                print(f"      ✓ Repository root IS wp-content (has plugins/ and themes/)")

        # If no wp-content, check if it's a theme or plugin
        if not structure['has_wp_content'] and not structure['is_wp_content']:
            # Check for theme indicators
            style_css = repo_dir / "style.css"
            index_php = repo_dir / "index.php"
            if style_css.exists() and index_php.exists():
                structure['is_theme'] = True
                structure['type'] = 'wordpress-theme'
                print(f"      ✓ Detected theme structure (style.css + index.php)")
            
            # Check for plugin indicators
            elif any(repo_dir.glob("*.php")):
                # Look for plugin header in PHP files
                php_files = list(repo_dir.glob("*.php"))
                print(f"      🔍 Checking {len(php_files)} PHP file(s) for plugin header...")
                for php_file in php_files:
                    try:
                        with open(php_file, 'r', encoding='utf-8') as f:
                            content = f.read(1000)  # Read first 1000 chars
                            if "Plugin Name:" in content:
                                structure['is_plugin'] = True
                                structure['type'] = 'wordpress-plugin'
                                print(f"      ✓ Detected plugin structure in {php_file.name}")
                                break
                    except Exception as e:
                        print(f"      ⚠️  Could not read {php_file.name}: {str(e)}")
                        continue
            
            # If still unknown but has development files
            if structure['type'] == 'unknown':
                if structure['has_composer'] or structure['has_package_json']:
                    structure['type'] = 'development-project'
                    print(f"      ℹ️  Classified as development project")
                else:
                    structure['type'] = 'generic-repository'
                    print(f"      ℹ️  Classified as generic repository")
        
        return structure
    
    def setup_wp_content_from_repo(self, repo_dir, wp_content_path, repo_structure):
        """Set up wp-content based on repository structure"""
        
        if repo_structure.get('is_wp_content'):
            # Repository root IS the wp-content directory — symlink directly
            print(f"      📦 Repository root is wp-content, linking directly...")
            if wp_content_path.exists():
                print(f"      🗑️  Removing existing wp-content directory...")
                if wp_content_path.is_symlink():
                    wp_content_path.unlink()
                else:
                    shutil.rmtree(wp_content_path)
            try:
                relative_path = Path("repository")
                print(f"      🔗 Creating symlink: wp-content -> {relative_path}")
                wp_content_path.symlink_to(relative_path, target_is_directory=True)
                print(f"      ✅ Symlink created successfully")
            except OSError as e:
                print(f"      ⚠️  Symlink failed ({str(e)}), copying instead...")
                try:
                    shutil.copytree(str(repo_dir), str(wp_content_path))
                    print(f"      ✅ Copied repository as wp-content")
                except Exception as copy_error:
                    raise Exception(f"Failed to link or copy wp-content: {copy_error}")

        elif repo_structure['has_wp_content']:
            # Repository has a wp-content subdirectory
            repo_wp_content = repo_structure['wp_content_path']
            print(f"      📦 Setting up wp-content from repository...")

            if wp_content_path.exists():
                print(f"      🗑️  Removing existing wp-content directory...")
                if wp_content_path.is_symlink():
                    wp_content_path.unlink()
                else:
                    shutil.rmtree(wp_content_path)

            try:
                relative_path = Path("repository") / "wp-content"
                print(f"      🔗 Creating symlink: wp-content -> {relative_path}")
                wp_content_path.symlink_to(relative_path, target_is_directory=True)
                print(f"      ✅ Symlink created successfully")
            except OSError as e:
                print(f"      ⚠️  Symlink failed ({str(e)}), copying instead...")
                try:
                    shutil.copytree(str(repo_wp_content), str(wp_content_path))
                    print(f"      ✅ Copied wp-content from repository")
                except Exception as copy_error:
                    raise Exception(f"Failed to link or copy wp-content: symlink error: {str(e)}, copy error: {str(copy_error)}")

        elif repo_structure['is_theme']:
            # Repository is a theme - put it in themes directory
            print(f"      🎨 Setting up theme from repository...")
            self._setup_theme_from_repo(repo_dir, wp_content_path)
                
        elif repo_structure['is_plugin']:
            # Repository is a plugin - put it in plugins directory  
            print(f"      🔌 Setting up plugin from repository...")
            self._setup_plugin_from_repo(repo_dir, wp_content_path)
        
        else:
            # Generic repository - just keep default wp-content
            print(f"      📁 Repository available at: repository/ (no automatic wp-content setup)")
            print(f"      ℹ️  You can manually configure how to use the repository content")
    
    def _setup_theme_from_repo(self, repo_dir, wp_content_path):
        """Set up theme from repository"""
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
    
    def _setup_plugin_from_repo(self, repo_dir, wp_content_path):
        """Set up plugin from repository"""
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
    
    def update_repository(self, project_path, new_repo_url):
        """Update repository URL and re-clone content for an existing project"""
        print(f"🔄 Updating repository for project")
        repo_dir = project_path / "repository"
        wp_content_path = project_path / "wp-content"
        
        # Remove old repository if it exists
        if repo_dir.exists():
            print(f"   🗑️  Removing old repository directory...")
            shutil.rmtree(repo_dir)
            print(f"   ✅ Old repository removed")
        
        # Remove old wp-content symlink/copy
        if wp_content_path.exists():
            print(f"   🗑️  Removing old wp-content...")
            if wp_content_path.is_symlink():
                wp_content_path.unlink()
                print(f"      ✓ Removed symlink")
            else:
                shutil.rmtree(wp_content_path)
                print(f"      ✓ Removed directory")
        
        # Create new wp-content directory
        wp_content_path.mkdir()
        print(f"   ✅ Created fresh wp-content directory")
        
        # Clone new repository if URL provided
        repo_structure = None
        if new_repo_url and new_repo_url.strip():
            print(f"   📥 Cloning new repository: {new_repo_url}")
            repo_structure = self.clone_repository(new_repo_url, project_path)
        else:
            print(f"   ℹ️  No repository URL provided, keeping default wp-content")
        
        return repo_structure
    
    def get_repository_info(self, project_path):
        """Get information about the repository in a project"""
        repo_dir = project_path / "repository"
        
        if not repo_dir.exists():
            return {'has_repository': False}
        
        try:
            # Get remote URL
            result = subprocess.run(
                ['git', 'remote', 'get-url', 'origin'],
                cwd=repo_dir,
                capture_output=True,
                text=True
            )
            
            remote_url = result.stdout.strip() if result.returncode == 0 else "Unknown"
            
            # Get current branch
            result = subprocess.run(
                ['git', 'branch', '--show-current'],
                cwd=repo_dir,
                capture_output=True,
                text=True
            )
            
            current_branch = result.stdout.strip() if result.returncode == 0 else "Unknown"
            
            # Get last commit info
            result = subprocess.run(
                ['git', 'log', '-1', '--pretty=format:%h %s (%cr)'],
                cwd=repo_dir,
                capture_output=True,
                text=True
            )
            
            last_commit = result.stdout.strip() if result.returncode == 0 else "Unknown"
            
            # Get repository structure
            repo_structure = self.analyze_repository_structure(repo_dir)
            
            return {
                'has_repository': True,
                'remote_url': remote_url,
                'current_branch': current_branch,
                'last_commit': last_commit,
                'structure': repo_structure
            }
            
        except Exception as e:
            return {
                'has_repository': True,
                'error': str(e)
            }
    
    def pull_repository_updates(self, project_path):
        """Pull the latest changes from the repository"""
        repo_dir = project_path / "repository"
        
        if not repo_dir.exists():
            return {'success': False, 'error': 'No repository found'}
        
        try:
            # Create environment with credential helpers disabled to avoid prompts
            env = os.environ.copy()
            env['GIT_TERMINAL_PROMPT'] = '0'
            env['GIT_ASKPASS'] = 'echo'
            
            # Pull latest changes
            result = subprocess.run(
                ['git', 'pull'],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                env=env
            )
            
            if result.returncode == 0:
                return {
                    'success': True,
                    'message': 'Repository updated successfully',
                    'output': result.stdout
                }
            else:
                return {
                    'success': False,
                    'error': f'Failed to pull updates: {result.stderr}'
                }
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def link_existing_repository(self, project_path):
        """Link an existing manually cloned repository to wp-content"""
        repo_dir = project_path / "repository"
        wp_content_path = project_path / "wp-content"
        
        # Check if repository exists
        if not repo_dir.exists():
            return {'success': False, 'error': 'No repository directory found. Please clone your repository into the repository/ folder first.'}
        
        # Check if wp-content is already a symlink
        if wp_content_path.exists() and wp_content_path.is_symlink():
            return {'success': False, 'error': 'wp-content is already linked to a repository. Remove the existing symlink first if you want to relink.'}
        
        try:
            # Analyze repository structure
            print(f"   📂 Analyzing repository structure...")
            repo_structure = self.analyze_repository_structure(repo_dir)
            
            # Set up wp-content linking based on repository structure
            print(f"   🔗 Linking wp-content to repository...")
            self.setup_wp_content_from_repo(repo_dir, wp_content_path, repo_structure)
            
            return {
                'success': True,
                'message': f'Successfully linked wp-content to repository ({repo_structure["type"]})',
                'repository_structure': repo_structure
            }
            
        except Exception as e:
            return {'success': False, 'error': f'Failed to link repository: {str(e)}'}