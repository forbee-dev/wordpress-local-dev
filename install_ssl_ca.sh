#!/bin/bash

# WordPress Local Development Environment - SSL CA Installation Script
# This script helps install the mkcert local CA in your system trust store

echo "🔐 WordPress Local Development Environment - SSL CA Installation"
echo "================================================================"
echo ""

# Check if mkcert is installed
if ! command -v mkcert &> /dev/null; then
    echo "❌ mkcert is not installed"
    echo ""
    echo "📦 Please install mkcert first:"
    echo "   macOS: brew install mkcert"
    echo "   Linux: https://github.com/FiloSottile/mkcert#installation"
    echo "   Windows: https://github.com/FiloSottile/mkcert#installation"
    echo ""
    exit 1
fi

echo "✅ mkcert is installed: $(mkcert -version)"
echo ""

# Get the CA root directory
CA_ROOT=$(mkcert -CAROOT)
CA_FILE="$CA_ROOT/rootCA.pem"

if [ ! -f "$CA_FILE" ]; then
    echo "❌ Local CA not found at: $CA_FILE"
    echo "ℹ️  Run 'mkcert -install' first to create the local CA"
    exit 1
fi

echo "✅ Local CA found at: $CA_FILE"
echo ""

# Detect operating system
OS=$(uname -s)
case $OS in
    Darwin*)
        echo "🍎 Detected macOS - Installing CA in System Keychain..."
        echo ""
        echo "This will add the mkcert CA to your system trust store."
        echo "You'll be prompted for your password (this is safe)."
        echo ""
        read -p "Continue? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain "$CA_FILE"
            if [ $? -eq 0 ]; then
                echo ""
                echo "✅ CA installed successfully in macOS System Keychain!"
                echo "🔄 Please restart your browser for changes to take effect"
            else
                echo ""
                echo "❌ Failed to install CA. You may need to run this manually:"
                echo "   sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain \"$CA_FILE\""
            fi
        else
            echo "Installation cancelled."
        fi
        ;;
    Linux*)
        echo "🐧 Detected Linux - Installing CA in system certificates..."
        echo ""
        echo "This will copy the mkcert CA to your system certificate store."
        echo "You'll be prompted for your password (this is safe)."
        echo ""
        read -p "Continue? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            sudo cp "$CA_FILE" /usr/local/share/ca-certificates/mkcert.crt
            sudo update-ca-certificates
            if [ $? -eq 0 ]; then
                echo ""
                echo "✅ CA installed successfully in Linux certificate store!"
                echo "🔄 Please restart your browser for changes to take effect"
            else
                echo ""
                echo "❌ Failed to install CA. You may need to run this manually:"
                echo "   sudo cp \"$CA_FILE\" /usr/local/share/ca-certificates/mkcert.crt"
                echo "   sudo update-ca-certificates"
            fi
        else
            echo "Installation cancelled."
        fi
        ;;
    MINGW*|CYGWIN*|MSYS*)
        echo "🪟 Detected Windows - Manual installation required"
        echo ""
        echo "Windows requires manual installation:"
        echo "1. Open Certificate Manager (certlm.msc)"
        echo "2. Go to 'Trusted Root Certification Authorities' → 'Certificates'"
        echo "3. Right-click → 'All Tasks' → 'Import'"
        echo "4. Import this file: $CA_FILE"
        echo ""
        echo "CA file location: $CA_FILE"
        ;;
    *)
        echo "❓ Unknown operating system: $OS"
        echo "ℹ️  Please install the CA manually using your system's certificate manager"
        echo "CA file location: $CA_FILE"
        ;;
esac

echo ""
echo "🎯 Next Steps:"
echo "1. Restart your browser completely"
echo "2. Visit https://local.turtlebet.com"
echo "3. You should see a green lock icon (no warnings!)"
echo ""
echo "If you still see warnings, try:"
echo "- Clear browser cache"
echo "- Try incognito/private mode"
echo "- Check system date/time is correct"
