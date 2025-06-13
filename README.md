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
- **MySQL 8.0**: Reliable database with backup/restore capabilities
- **phpMyAdmin**: Web-based database management interface
- **Redis**: Optional caching layer for improved performance  
- **Nginx**: Reverse proxy with SSL termination and custom routing

### 🔧 **Advanced Project Management**
- **One-Click Creation**: Complete WordPress environment in minutes
- **Git Integration**: Automatic wp-content repository cloning
- **Database Management**: File upload, import, export, and replacement
- **SSL Certificates**: Self-signed certificates with system trust integration
- **Local Domains**: Automatic hosts file modification (local.SITENAME.test)
- **Subfolder Support**: Handle WordPress installations in subdirectories

### 💾 **Database Operations**
- **File Upload**: Drag & drop SQL file uploads via web interface
- **Automatic Import**: Database files imported during project creation
- **Live Updates**: Replace databases in existing projects with backup option
- **Export Functionality**: One-click database exports with timestamps
- **Backup System**: Automatic backups before database replacements

### 🔄 **Live Docker Hub Integration**
- **Real-Time Versions**: Fetches current WordPress versions from Docker Hub API
- **Smart Caching**: 1-hour cache for optimal performance  
- **Intelligent Parsing**: Automatic PHP version detection and descriptions
- **Fallback System**: Graceful degradation if Docker Hub is unavailable

### ⚙️ **Automation & CLI Tools**
- **Makefile Commands**: Standardized project management commands
- **Container Management**: Start, stop, restart, rebuild with one command
- **Log Viewing**: Real-time container logs via web interface
- **Shell Access**: Direct container access for debugging
- **Cleanup Utilities**: Automated cleanup and resource management

## Requirements

- Docker & Docker Compose
- Python 3.8+
- Administrator/root privileges (for hosts file modification)

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

### Managing Existing Projects

#### **Project Dashboard Features**
- **Status Monitoring**: Real-time container health indicators
- **Quick Actions**: Start, stop, delete with one click
- **URL Access**: Direct links to all project endpoints
- **Log Viewing**: Container logs in modal windows

#### **Database Management**
- **Upload New Database**: 
  - Click "Upload Database" on any project card
  - Drag & drop SQL files or browse to select
  - Automatic backup creation before replacement
  - Real-time import progress with error handling

- **Export Database**:
  - One-click export from project dashboard
  - Timestamped SQL files with automatic download
  - Compressed exports for large databases

#### **Advanced Operations**
- **Git Repository Updates**: Re-clone wp-content repositories
- **SSL Certificate Renewal**: Regenerate certificates as needed
- **Container Management**: Individual service control (WordPress, MySQL, Redis, etc.)
- **Environment Variables**: Modify project configuration via config.json

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
- `make clean` - Clean up containers/volumes
- `make status` - Show container status 