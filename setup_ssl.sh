#!/bin/bash

# WordPress Local Development Environment - SSL Setup Script
# This script helps set up trusted SSL certificates using mkcert

echo "🔐 WordPress Local Development Environment - SSL Setup"
echo "======================================================"
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

# Check if local CA is already installed
if mkcert -CAROOT &> /dev/null; then
    echo "✅ Local CA is already installed"
    echo "ℹ️  SSL certificates will be automatically trusted by browsers"
    echo ""
    echo "🚀 You can now create WordPress projects with trusted SSL!"
    echo "   Run: python app.py"
    exit 0
fi

echo "🔧 Installing local CA (requires sudo access)..."
echo ""

# Install the local CA
echo "Running: mkcert -install"
echo "This will add a local CA to your system trust store."
echo ""

if mkcert -install; then
    echo ""
    echo "✅ Local CA installed successfully!"
    echo "ℹ️  SSL certificates will now be automatically trusted by browsers"
    echo ""
    echo "🚀 You can now create WordPress projects with trusted SSL!"
    echo "   Run: python app.py"
else
    echo ""
    echo "❌ Failed to install local CA"
    echo "ℹ️  You can still use SSL, but browsers will show security warnings"
    echo "   To install manually, run: mkcert -install"
    echo ""
    echo "🚀 You can still create WordPress projects with SSL!"
    echo "   Run: python app.py"
fi
