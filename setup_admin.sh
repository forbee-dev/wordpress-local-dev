#!/bin/bash

# WordPress Local Development Environment - Admin Setup
# Run this script to configure system-level settings that require admin privileges

echo "🔐 WordPress Local Development Environment - Admin Setup"
echo "========================================================"
echo ""
echo "This script will configure system-level settings that require admin privileges:"
echo "1. Trust SSL certificates in system keychain"
echo "2. Configure hosts file entries for local domains"
echo ""

# Function to add domain to hosts file
add_domain_to_hosts() {
    local domain=$1
    local hosts_file="/etc/hosts"
    
    if ! grep -q "$domain" "$hosts_file"; then
        echo "Adding $domain to hosts file..."
        echo "127.0.0.1    $domain" | sudo tee -a "$hosts_file" > /dev/null
        echo "✅ Added $domain to hosts file"
    else
        echo "ℹ️  $domain already exists in hosts file"
    fi
}

# Function to trust SSL certificate
trust_ssl_cert() {
    local cert_file=$1
    local domain=$2
    
    if [[ -f "$cert_file" ]]; then
        echo "Trusting SSL certificate for $domain..."
        sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain "$cert_file"
        echo "✅ SSL certificate trusted for $domain"
    else
        echo "⚠️  Certificate file not found: $cert_file"
    fi
}

# Check for existing projects and configure them
if [[ -d "wordpress-projects" ]]; then
    echo "🔍 Scanning for existing WordPress projects..."
    
    for project_dir in wordpress-projects/*/; do
        if [[ -d "$project_dir" ]]; then
            project_name=$(basename "$project_dir")
            config_file="$project_dir/config.json"
            cert_file="$project_dir/ssl/cert.pem"
            
            if [[ -f "$config_file" ]]; then
                # Extract domain from config file
                domain=$(python3 -c "import json; print(json.load(open('$config_file')).get('domain', 'local.$project_name.test'))" 2>/dev/null || echo "local.$project_name.test")
                
                # Remove subfolder from domain for hosts file
                clean_domain=$(echo "$domain" | cut -d'/' -f1)
                
                echo ""
                echo "📂 Configuring project: $project_name"
                echo "   Domain: $clean_domain"
                
                # Add to hosts file
                add_domain_to_hosts "$clean_domain"
                
                # Trust SSL certificate
                if [[ -f "$cert_file" ]]; then
                    trust_ssl_cert "$cert_file" "$clean_domain"
                fi
            fi
        fi
    done
else
    echo "ℹ️  No WordPress projects found. Create a project first, then run this script."
fi

echo ""
echo "✅ Admin setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Create WordPress projects through the web interface at http://localhost:5001"
echo "2. Run this script again after creating new projects to configure them"
echo "3. Your sites will be accessible at https://local.PROJECT_NAME.test"
echo "" 