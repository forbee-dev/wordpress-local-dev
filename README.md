# WordPress Local Development Environment

A comprehensive web-based tool to quickly spin up and manage local WordPress development environments with Docker. Features a modern UI, real-time Docker Hub integration, and complete project lifecycle management.

## 🌟 Key Features

### 🖥️ **Modern Web Interface**
- **Beautiful UI**: Responsive web interface with real-time updates
- **Project Dashboard**: Visual project cards with status monitoring  
- **Cross-Platform**: Works on Windows, macOS, and Linux
- **Real-Time Monitoring**: Auto-refreshing project status and container health

### 🐳 **Complete Docker Stack**
- **WordPress**: Real-time versions from Docker Hub registry
- **WP CLI**: Command-line WordPress management tools integrated into containers
- **MySQL 8.0**: Reliable database with backup/restore capabilities
- **phpMyAdmin**: Web-based database management interface
- **Redis**: Optional caching layer for improved performance  
- **Nginx**: Reverse proxy with SSL termination and custom routing

### 🔧 **Advanced Project Management**
- **One-Click Creation**: Complete WordPress environment in minutes
- **Project Updates**: Modify WordPress version, domain, repository, and configuration
- **Git Integration**: Automatic wp-content repository cloning
- **Database Management**: File upload, import, export, and replacement
- **Trusted SSL Certificates**: Automatic mkcert CA installation for browser-trusted certificates
- **Local Domains**: Automatic hosts file modification (local.SITENAME.test)
- **Subfolder Support**: Handle WordPress installations in subdirectories

### 💾 **Advanced Database Management**
- **Integrated Upload**: Database upload integrated into Update Project modal
- **Smart Fallback Strategy**: Tries original file first, auto-repairs if needed
- **Real-Time Progress**: Detailed server logs with step-by-step progress tracking
- **Automatic Backup**: Creates database backups before import with error handling
- **UTF-8 Error Handling**: Handles corrupted files with automatic character replacement
- **Database Clearing**: Prevents duplicate key errors by clearing database before import
- **Export Functionality**: One-click database exports with timestamps
- **File Type Support**: Handles both .sql and .sql.gz files automatically

### 🔄 **Live Docker Hub Integration**
- **Real-Time Versions**: Fetches current WordPress versions from Docker Hub API
- **Smart Caching**: 1-hour cache for optimal performance  
- **Intelligent Parsing**: Automatic PHP version detection and descriptions
- **Fallback System**: Graceful degradation if Docker Hub is unavailable

### ⚙️ **Automation & CLI Tools**
- **Makefile Commands**: Standardized project management commands
- **WP CLI Integration**: Full WordPress command-line interface access
- **Container Management**: Start, stop, restart, rebuild with one command
- **Log Viewing**: Real-time container logs via web interface
- **Shell Access**: Direct container access for debugging
- **Cleanup Utilities**: Automated cleanup and resource management

## 🔐 SSL Certificate Management

### **Automatic Trusted SSL Certificates**

The system now provides **automatic trusted SSL certificates** with no browser warnings:

- **mkcert Integration**: Uses mkcert for locally trusted certificates
- **Automatic CA Installation**: mkcert local CA installed automatically during project creation
- **Browser Trusted**: Certificates are automatically trusted by all browsers
- **No Manual Setup**: Works out of the box with no configuration required
- **Wildcard Support**: Includes `*.domain.com` and `localhost` in certificates

### **SSL Features**
- ✅ **No Browser Warnings**: Certificates are automatically trusted
- ✅ **Automatic Installation**: mkcert CA installed during project creation/start
- ✅ **Multiple Domains**: Each certificate includes domain, wildcard, localhost, and 127.0.0.1
- ✅ **Auto-Renewal**: Certificates checked and regenerated every 30 days
- ✅ **Domain Updates**: SSL certificates automatically updated when domain changes

## Requirements

- Docker & Docker Compose
- Python 3.8+
- Administrator/root privileges (for hosts file modification)
- **mkcert** (automatically installed if not present)

## 🚀 Quick Start

1. **Clone/download this project**
2. **Install dependencies:** `pip install -r requirements.txt`
3. **Run the application:** 
   ```bash
   # macOS/Linux
   ./start.sh
   
   # Windows  
   start.bat
   ```
4. **Open http://localhost:5001 in your browser**
5. **Create your first WordPress project!**

## 🎯 Usage Guide

### Creating a New Project

1. **Project Setup Form:**
   - **Project Name**: Unique identifier (becomes local.PROJECT.test)
   - **Database File**: Upload SQL file via drag & drop (optional)
   - **Repository URL**: Git repo with wp-content files (optional)
   - **WordPress Version**: Select from live Docker Hub versions
   - **Subfolder**: Installation subdirectory (optional)
   - **Redis Caching**: Enable for improved performance

2. **Monitor Creation Progress:**
   - Real-time status updates in the web interface
   - Automatic SSL certificate generation and trust
   - Hosts file modification for local domain access
   - Docker container orchestration and startup

3. **Access Your Site:**
   - **WordPress Frontend**: `https://local.PROJECT-NAME.test`
   - **WordPress Admin**: `https://local.PROJECT-NAME.test/wp-admin`
   - **phpMyAdmin**: `https://local.PROJECT-NAME.test:8443`

### Updating Existing Projects

#### **Project Update Modal**
Click the "Update Project" button on any project card to access the comprehensive update interface:

1. **WordPress Version Tab:**
   - Select from live Docker Hub versions
   - Automatic container rebuild with new version
   - Preserves all data and configuration

2. **Domain Tab:**
   - Change project domain (e.g., `local.mysite.com`)
   - Automatic hosts file update
   - SSL certificate regeneration for new domain
   - Optional SSL enable/disable

3. **Repository Tab:**
   - Update source repository URL
   - Automatic re-cloning of new repository
   - Preserves wp-content linking structure

4. **Database Tab:**
   - Upload new database files (.sql, .sql.gz)
   - Automatic backup before import
   - Real-time progress logs with detailed server feedback
   - Smart fallback strategy (original → repaired if needed)
   - UTF-8 error handling and file repair

5. **Configuration Tab:**
   - Custom domain settings
   - Subfolder configuration
   - SSL enable/disable
   - Redis caching toggle

#### **Automatic SSL Management**
- **CA Installation**: mkcert local CA installed automatically when needed
- **Certificate Generation**: Trusted certificates generated for all domains
- **Domain Updates**: SSL certificates automatically updated when domain changes
- **No Browser Warnings**: All certificates are automatically trusted by browsers

### Managing Existing Projects

#### **Project Dashboard Features**
- **Status Monitoring**: Real-time container health indicators
- **Quick Actions**: Start, stop, delete with one click
- **URL Access**: Direct links to all project endpoints
- **Log Viewing**: Container logs in modal windows
- **Project Updates**: Comprehensive update modal with tabbed interface

#### **Project Update Features**
- **WordPress Version**: Change WordPress version with live Docker Hub integration
- **Domain Management**: Update project domain with automatic SSL regeneration
- **Repository Updates**: Change source repository with automatic re-cloning
- **Configuration**: Modify SSL, Redis, subfolder, and custom domain settings
- **SSL Management**: Automatic certificate regeneration and CA installation

#### **Database Management**
- **Upload New Database**: 
  - Go to Update Project → Database tab
  - Upload .sql or .sql.gz files with drag & drop
  - Automatic backup creation before replacement
  - Real-time progress logs with detailed server feedback
  - Smart fallback strategy handles corrupted files
  - UTF-8 error handling with automatic file repair

- **Export Database**:
  - One-click export from project dashboard
  - Timestamped SQL files with automatic download
  - Compressed exports for large databases

#### **Advanced Operations**
- **WP CLI Commands**: Full WordPress CLI access for plugins, themes, users, and database operations
- **Project Updates**: Comprehensive update system for WordPress version, domain, repository, database, and configuration
- **Database Import Features**: 
  - Smart fallback strategy (original → repaired if needed)
  - Automatic UTF-8 error handling and file repair
  - Database clearing to prevent duplicate key errors
  - Real-time progress logs with detailed server feedback
  - Support for both .sql and .sql.gz files
- **SSL Certificate Management**: Automatic mkcert CA installation and trusted certificate generation
- **Container Management**: Individual service control (WordPress, MySQL, Redis, etc.)
- **Environment Variables**: Modify project configuration via config.json
- **Automatic SSL**: Trusted certificates generated automatically with no browser warnings

## 📁 Project Structure

```
wordpress-projects/
├── project-name/
│   ├── docker-compose.yml    # Container orchestration
│   ├── Makefile             # Automation commands  
│   ├── nginx.conf           # Web server config
│   ├── .env                 # Environment variables
│   ├── config.json          # Project metadata
│   ├── wp-content/          # WordPress content (symlinked or copied from repository)
│   ├── repository/          # 🔗 Your Git repository (intact with all files)
│   │   ├── composer.json    # PHP dependencies
│   │   ├── vendor/          # Composer packages
│   │   ├── .git/            # Version control
│   │   ├── wp-content/      # Original repository wp-content
│   │   └── ...all repo files
│   ├── data/                # Database files & imports
│   └── ssl/                 # SSL certificates
└── ...
```

### 🔗 Repository Integration

The system intelligently handles your repository:

- **Full WordPress Projects**: `repository/wp-content/` → symlinked to `wp-content/`
- **Theme Repositories**: `repository/` → symlinked to `wp-content/themes/theme-name/`  
- **Plugin Repositories**: `repository/` → symlinked to `wp-content/plugins/plugin-name/`
- **Development Projects**: Repository preserved as-is for manual integration

Your repository remains **completely intact** with all development files preserved!

## Makefile Commands

- `make start` - Start the environment
- `make stop` - Stop containers
- `make build` - Build/rebuild containers
- `make logs` - View logs
- `make shell` - Access WordPress container shell
- `make db-import` - Import database
- `make db-export` - Export database
- `make wp-cli` - Access WP CLI interface
- `make clean` - Clean up containers/volumes
- `make status` - Show container status

## 🔧 WP CLI Integration

### **WordPress Command Line Interface**

Every project now includes full WP CLI support for advanced WordPress management:

#### **Quick Start with WP CLI**
```bash
# Navigate to your project directory
cd wordpress-projects/your-project-name

# Check WordPress info
docker-compose --profile cli run --rm wpcli --info

# List all plugins
docker-compose --profile cli run --rm wpcli plugin list

# Install and activate a plugin
docker-compose --profile cli run --rm wpcli plugin install contact-form-7 --activate

# Update WordPress core
docker-compose --profile cli run --rm wpcli core update
```

#### **Common WP CLI Commands**

**Plugin Management:**
```bash
# List all plugins
docker-compose --profile cli run --rm wpcli plugin list

# Install plugins
docker-compose --profile cli run --rm wpcli plugin install akismet --activate
docker-compose --profile cli run --rm wpcli plugin install woocommerce

# Update plugins
docker-compose --profile cli run --rm wpcli plugin update --all

# Deactivate/delete plugins
docker-compose --profile cli run --rm wpcli plugin deactivate akismet
docker-compose --profile cli run --rm wpcli plugin delete akismet
```

**Theme Management:**
```bash
# List themes
docker-compose --profile cli run --rm wpcli theme list

# Install themes
docker-compose --profile cli run --rm wpcli theme install twentytwentyfour --activate

# Update themes
docker-compose --profile cli run --rm wpcli theme update --all
```

**User Management:**
```bash
# List users
docker-compose --profile cli run --rm wpcli user list

# Create new user
docker-compose --profile cli run --rm wpcli user create john john@example.com --role=editor

# Change user password
docker-compose --profile cli run --rm wpcli user update admin --user_pass=newpassword
```

**Database Operations:**
```bash
# Export database
docker-compose --profile cli run --rm wpcli db export backup.sql

# Search and replace URLs
docker-compose --profile cli run --rm wpcli search-replace 'oldurl.com' 'newurl.com'

# Optimize database
docker-compose --profile cli run --rm wpcli db optimize
```

**Content Management:**
```bash
# Create posts
docker-compose --profile cli run --rm wpcli post create --post_title="Hello World" --post_content="This is a test post" --post_status=publish

# List posts
docker-compose --profile cli run --rm wpcli post list

# Delete posts
docker-compose --profile cli run --rm wpcli post delete 123 --force
```

**Cache Management:**
```bash
# Flush object cache
docker-compose --profile cli run --rm wpcli cache flush

# Clear transients
docker-compose --profile cli run --rm wpcli transient delete --all
```

#### **API Integration**

You can also run WP CLI commands and project updates via the web API:

**WP CLI Commands:**
```bash
# Add WP CLI to a project
curl -X POST http://localhost:5001/api/add-wpcli/your-project-name

# Run WP CLI commands via API
curl -X POST http://localhost:5001/api/wp-cli/your-project-name \
  -H "Content-Type: application/json" \
  -d '{"command": "plugin list"}'
```

**Project Update API:**
```bash
# Update WordPress version
curl -X POST http://localhost:5001/api/projects/your-project/update-wordpress-version \
  -H "Content-Type: application/json" \
  -d '{"version": "php8.3"}'

# Update domain
curl -X POST http://localhost:5001/api/projects/your-project/update-domain \
  -H "Content-Type: application/json" \
  -d '{"domain": "local.newsite.com", "enable_ssl": true}'

# Update repository
curl -X POST http://localhost:5001/api/projects/your-project/update-repository \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "git@github.com:user/new-repo.git"}'

# Update configuration
curl -X POST http://localhost:5001/api/projects/your-project/update-config \
  -H "Content-Type: application/json" \
  -d '{"enable_ssl": true, "enable_redis": true, "subfolder": "wp"}'

# Regenerate SSL certificates
curl -X POST http://localhost:5001/api/projects/your-project/regenerate-ssl
```

#### **Technical Details**

- **Image**: Uses official `wordpress:cli-php8.3` Docker image
- **Network**: Connected to the same network as WordPress and MySQL
- **Volumes**: Shares WordPress data and wp-content volumes
- **Profiles**: Uses Docker Compose profiles (CLI service only runs when explicitly called)
- **Permissions**: Runs as www-data user (33:33) for proper file permissions
- **Working Directory**: Pre-configured to WordPress root (`/var/www/html`)

## 🔧 Troubleshooting

### SSL Certificate Issues

If you encounter SSL certificate warnings:

1. **Check mkcert Installation:**
   ```bash
   mkcert -version
   ```

2. **Install mkcert CA manually:**
   ```bash
   mkcert -install
   ```

3. **Regenerate SSL certificates:**
   - Use the "Regenerate SSL" option in the project update modal
   - Or via API: `curl -X POST http://localhost:5001/api/projects/your-project/regenerate-ssl`

4. **Manual CA installation (macOS):**
   ```bash
   sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain \
     "/Users/$(whoami)/Library/Application Support/mkcert/rootCA.pem"
   ```

### Project Update Issues

If project updates fail:

1. **Check project status:** Ensure project is stopped before major updates
2. **Verify permissions:** Ensure Docker has proper permissions
3. **Check logs:** Use the "View Logs" option in the project dashboard
4. **Manual update:** Use the Makefile commands in the project directory

### Common Solutions

- **Port conflicts:** Change ports in docker-compose.yml if 80/443 are in use
- **Permission issues:** Run with appropriate user permissions
- **Network issues:** Check Docker network connectivity
- **SSL warnings:** Ensure mkcert CA is installed in system trust store 