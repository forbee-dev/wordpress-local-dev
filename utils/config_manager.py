from pathlib import Path


class ConfigManager:
    """Handles creation of configuration files (nginx, Makefile, etc.)"""
    
    def __init__(self):
        pass
    
    def create_nginx_config(self, project_path, project_name, domain, enable_ssl, subfolder=""):
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
    
    def create_makefile(self, project_path, project_name, domain, db_file_path=None):
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
    
    def create_project_config(self, project_path, config_data):
        """Create project configuration JSON file"""
        import json
        
        with open(project_path / "config.json", 'w') as f:
            json.dump(config_data, f, indent=2)
    
    def read_project_config(self, project_path):
        """Read project configuration from JSON file"""
        import json
        
        config_file = project_path / "config.json"
        if not config_file.exists():
            return None
        
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except:
            return None
    
    def update_project_config(self, project_path, updates):
        """Update project configuration file with new values"""
        import json
        
        config = self.read_project_config(project_path)
        if config is None:
            return False
        
        # Update config with new values
        config.update(updates)
        
        # Save updated config
        try:
            with open(project_path / "config.json", 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except:
            return False
    
    def create_env_file(self, project_path, env_vars):
        """Create .env file with environment variables"""
        env_content = ""
        for key, value in env_vars.items():
            env_content += f"{key}={value}\n"
        
        with open(project_path / ".env", 'w') as f:
            f.write(env_content)
    
    def read_env_file(self, project_path):
        """Read environment variables from .env file"""
        env_file = project_path / '.env'
        env_vars = {}
        
        if env_file.exists():
            try:
                with open(env_file, 'r') as f:
                    for line in f:
                        if '=' in line and not line.startswith('#'):
                            key, value = line.strip().split('=', 1)
                            env_vars[key] = value
            except Exception:
                pass
        
        return env_vars
    
    def create_gitignore(self, project_path):
        """Create .gitignore file for WordPress projects"""
        gitignore_content = """# WordPress
wp-config.php
wp-content/uploads/
wp-content/upgrade/
wp-content/backup-db/
wp-content/advanced-cache.php
wp-content/wp-cache-config.php
wp-content/cache/
wp-content/cache/supercache/

# Plugin and theme development
*.log
.DS_Store
Thumbs.db

# IDE and editor files
.vscode/
.idea/
*.swp
*.swo
*~

# Node modules
node_modules/
npm-debug.log*

# Composer
vendor/

# Environment files
.env
.env.local
.env.production

# Docker
.docker/

# SSL certificates
ssl/

# Database backups
data/*.sql
data/*.sql.gz
!data/.gitkeep

# Temporary files
*.tmp
*.temp
"""
        
        with open(project_path / ".gitignore", 'w') as f:
            f.write(gitignore_content)
    
    def create_readme(self, project_path, project_name, domain):
        """Create README.md file for the project"""
        readme_content = f"""# {project_name}

WordPress local development environment for {project_name}.

## Quick Start

1. Start the environment:
   ```bash
   make start
   ```

2. Access your site:
   - Website: https://{domain}
   - phpMyAdmin: http://localhost:8080

## Available Commands

- `make start` - Start the environment
- `make stop` - Stop the environment
- `make restart` - Restart containers
- `make logs` - View container logs
- `make shell` - Access WordPress container shell
- `make db-export` - Export database
- `make db-import` - Import database
- `make debug-logs` - View WordPress debug logs
- `make clean` - Clean up containers and volumes

## Development

### File Structure
- `wp-content/` - WordPress content (themes, plugins, uploads)
- `data/` - Database files and backups
- `ssl/` - SSL certificates
- `nginx.conf` - Nginx configuration
- `docker-compose.yml` - Docker services configuration

### Database
- Database files can be placed in the `data/` folder
- Use `make db-import` to import database files
- Backups are automatically created in `data/` when importing

### SSL
SSL certificates are automatically generated for local development.

## Troubleshooting

### Containers won't start
```bash
make clean
make start
```

### Database import issues
1. Check file encoding (should be UTF-8)
2. Try importing through phpMyAdmin
3. Check container logs: `make logs`

### SSL Certificate issues
Delete and regenerate certificates:
```bash
rm -rf ssl/
make restart
```
"""
        
        with open(project_path / "README.md", 'w') as f:
            f.write(readme_content)
