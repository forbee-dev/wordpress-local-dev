# WordPress Local Development Environment - Setup Guide

## Prerequisites

Before using this tool, ensure you have the following installed:

### Required Software

1. **Docker & Docker Compose**
   - **macOS**: Install [Docker Desktop for Mac](https://docs.docker.com/desktop/mac/install/)
   - **Windows**: Install [Docker Desktop for Windows](https://docs.docker.com/desktop/windows/install/)
   - **Linux**: Install [Docker Engine](https://docs.docker.com/engine/install/) and [Docker Compose](https://docs.docker.com/compose/install/)

2. **Python 3.8+**
   - **macOS**: Install via [Homebrew](https://brew.sh/): `brew install python`
   - **Windows**: Download from [python.org](https://python.org/downloads/)
   - **Linux**: Usually pre-installed, or install via package manager: `sudo apt install python3 python3-pip`

3. **Git** (for cloning repositories)
   - Install from [git-scm.com](https://git-scm.com/downloads)

### Administrator Privileges

This tool requires administrator/root privileges for:
- Modifying the system hosts file (to set up local domains)
- Installing SSL certificates in the system trust store

## Quick Start

### 1. Download/Clone the Project

```bash
# If you have the project files
cd wordpress-local-dev

# Or clone from repository
git clone <repository-url> wordpress-local-dev
cd wordpress-local-dev
```

### 2. Start the Application

**On macOS/Linux:**
```bash
chmod +x start.sh
./start.sh
```

**On Windows:**
```batch
start.bat
```

The startup script will:
- Check system requirements
- Create a Python virtual environment
- Install dependencies
- Create necessary directories
- Start the web interface

### 3. Access the Web Interface

Open your browser and go to: **http://localhost:5001**

> **Note**: The application runs on port 5001 to avoid conflicts with macOS AirPlay Receiver on port 5000.

## Creating Your First Project

1. **Fill out the project form:**
   - **Project Name**: Use letters, numbers, hyphens, and underscores only
   - **WordPress Version**: Select from live Docker Hub versions with real-time updates
   - **Repository URL**: Git repository containing your wp-content or theme/plugin files
   - **Database File**: Upload SQL file directly via web interface (drag & drop supported)
   - **Subfolder**: (Optional) For sites living in subfolders
   - **Redis Caching**: Enable/disable Redis for improved performance

2. **Monitor real-time progress:**
   - Watch as containers are created and configured
   - SSL certificates are generated automatically
   - Local domain is added to your hosts file
   - Database is imported if provided

3. **Click "Create Project"** and wait for setup to complete (usually under 2 minutes)

## Project Structure

Each project creates the following structure:

```
wordpress-projects/
├── your-project-name/
│   ├── docker-compose.yml    # Docker services configuration
│   ├── Makefile              # Automation commands
│   ├── nginx.conf            # Nginx configuration
│   ├── .env                  # Environment variables
│   ├── config.json           # Project configuration
│   ├── wp-content/           # Your WordPress content
│   ├── data/                 # Database files/imports
│   └── ssl/                  # SSL certificates
```

## Using Makefile Commands

Navigate to your project directory and use these commands:

```bash
cd wordpress-projects/your-project-name

# Start the environment
make start

# Stop the environment
make stop

# Restart services
make restart

# Build/rebuild containers
make build

# View logs
make logs

# Access WordPress container shell
make shell

# Export database
make db-export

# Import database (if db file specified during creation)
make db-import

# Show container status
make status

# Clean up containers and volumes
make clean

# Show all available commands
make help
```

## Accessing Your Sites

### Local Domains

Projects are automatically accessible via:
- **HTTP**: `http://local.PROJECT_NAME.test`
- **HTTPS**: `https://local.PROJECT_NAME.test` (if SSL enabled)

### Services

- **WordPress Site**: `https://local.PROJECT_NAME.test`
- **WordPress Admin**: `https://local.PROJECT_NAME.test/wp-admin`
- **phpMyAdmin**: `https://local.PROJECT_NAME.test:8443` (project-specific)
- **MySQL**: `localhost:3306` (project-specific port)
- **Redis**: `localhost:6379` (if enabled, project-specific port)

> **Note**: Each project uses unique ports to allow multiple projects running simultaneously.

### Default Credentials

**MySQL/WordPress Database:**
- **Database**: `local_PROJECT_NAME`
- **Username**: `wordpress`
- **Password**: `wordpress_password`
- **Root Password**: `root_password`

**phpMyAdmin:**
- **Username**: `wordpress`
- **Password**: `wordpress_password`

## Repository Requirements

Your Git repository should contain:

1. **Option A**: A `wp-content` folder with your themes, plugins, and uploads
2. **Option B**: Direct theme/plugin files (will be moved to wp-content)

### Example Repository Structures

**Option A - Full wp-content:**
```
your-repo/
└── wp-content/
    ├── themes/
    │   └── your-theme/
    ├── plugins/
    │   └── your-plugin/
    └── uploads/
```

**Option B - Theme only:**
```
your-repo/
├── style.css
├── index.php
├── functions.php
└── ...theme files
```

## Database Management

### During Project Creation

1. **Upload SQL File**: Use the web interface to upload database files directly
   - **Drag & Drop**: Simply drag your `.sql` file onto the upload area
   - **Browse**: Click to select files from your computer
   - **Large Files**: Supports multi-gigabyte database files
   - **Progress Tracking**: Real-time upload and import progress

2. **Automatic Import**: Database files are imported automatically during project setup

### Managing Existing Projects

#### **Upload New Database**
1. **Access Project Dashboard**: View all projects at `http://localhost:5001`
2. **Click "Upload Database"** on any project card
3. **Select SQL File**: Drag & drop or browse to select database file
4. **Automatic Backup**: System creates timestamped backup before replacement
5. **Monitor Progress**: Real-time status updates and error handling

#### **Export Database**
1. **From Web Interface**: Click "Export Database" on project cards
2. **Via Makefile**: Run `make db-export` in project directory
3. **Timestamped Files**: Automatic filename with date/time stamps

#### **Command Line Options**
```bash
# Export current database
make db-export

# Import specific database file (if placed in data/ directory)
make db-import

# View database logs
make logs db
```

## SSL Certificates

The tool automatically generates self-signed SSL certificates for each project. You may see browser warnings initially.

### Trusting Certificates

**macOS:**
```bash
# Certificates are automatically added to Keychain
# You may need to manually trust them in Keychain Access
```

**Windows:**
```bash
# Run as Administrator and manually trust the certificate in browser
```

**Linux:**
```bash
# Certificates are added to system trust store automatically
# Restart browser after project creation
```

## Troubleshooting

### Common Issues

**"Permission denied" errors:**
- Run the startup script with `sudo` (macOS/Linux) or as Administrator (Windows)

**"Docker not running" error:**
- Ensure Docker Desktop is started and running

**"Port already in use" errors:**
- Stop other web servers (Apache, Nginx) running on ports 80/443
- Or modify the port settings in the project's `.env` file

**SSL certificate warnings:**
- This is normal for self-signed certificates
- Click "Advanced" → "Proceed to site" in your browser
- Or manually trust the certificate in your browser settings

**Site not loading:**
- Check if the domain was added to hosts file: `cat /etc/hosts` (macOS/Linux) or `type C:\Windows\System32\drivers\etc\hosts` (Windows)
- Flush DNS cache: `sudo dscacheutil -flushcache` (macOS) or `ipconfig /flushdns` (Windows)

### Getting Help

1. **Check container status**: `make status` in project directory
2. **View logs**: `make logs` in project directory
3. **Restart services**: `make restart` in project directory
4. **Clean and rebuild**: `make clean && make build` in project directory

## Advanced Configuration

### Custom Ports

Edit the `.env` file in your project directory:

```env
HTTP_PORT=8080
HTTPS_PORT=8443
MYSQL_PORT=3307
PHPMYADMIN_PORT=8081
REDIS_PORT=6380
```

### Custom Nginx Configuration

Edit the `nginx.conf` file in your project directory to customize the web server configuration.

### Environment Variables

All project settings are stored in:
- `config.json` - Project metadata
- `.env` - Environment variables
- `docker-compose.yml` - Docker services

## Removing Projects

1. **Via Web Interface**: Click on a project card → Delete button
2. **Manual Cleanup**:
   ```bash
   # Stop containers
   cd wordpress-projects/PROJECT_NAME
   make clean
   
   # Remove project directory
   cd ..
   rm -rf PROJECT_NAME
   
   # Remove from hosts file (manual)
   sudo nano /etc/hosts  # Remove the line with your domain
   ```

## Performance Tips

1. **Use SSD storage** for better Docker performance
2. **Allocate sufficient RAM** to Docker (4GB+ recommended)
3. **Use Redis caching** for better WordPress performance
4. **Keep projects stopped** when not in use to save resources

## Security Notes

- This tool is designed for **local development only**
- Default passwords are weak and should **never be used in production**
- SSL certificates are self-signed and **not suitable for production**
- Always use strong passwords for production deployments 