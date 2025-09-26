import os
import subprocess
import shutil
from pathlib import Path


class RepositoryManager:
    """Handles Git repository operations and repository analysis"""
    
    def __init__(self):
        pass
    
    def clone_repository(self, repo_url, project_path):
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
            repo_structure = self.analyze_repository_structure(repo_dir)
            print(f"   📂 Repository type: {repo_structure['type']}")
            
            # Set up wp-content linking/copying based on repository structure
            wp_content_path = project_path / "wp-content"
            self.setup_wp_content_from_repo(repo_dir, wp_content_path, repo_structure)
                
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
    
    def analyze_repository_structure(self, repo_dir):
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
    
    def setup_wp_content_from_repo(self, repo_dir, wp_content_path, repo_structure):
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
            self._setup_theme_from_repo(repo_dir, wp_content_path)
                
        elif repo_structure['is_plugin']:
            # Repository is a plugin - put it in plugins directory  
            self._setup_plugin_from_repo(repo_dir, wp_content_path)
        
        else:
            # Generic repository - just keep default wp-content
            print(f"   📁 Repository available at: repository/ (no automatic wp-content setup)")
            print(f"   ℹ️  You can manually configure how to use the repository content")
    
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
        repo_dir = project_path / "repository"
        wp_content_path = project_path / "wp-content"
        
        # Remove old repository if it exists
        if repo_dir.exists():
            print(f"   🗑️  Removing old repository...")
            shutil.rmtree(repo_dir)
        
        # Remove old wp-content symlink/copy
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
