#!/bin/bash

# WordPress Local Development Environment Startup Script

echo "🚀 WordPress Local Development Environment"
echo "=========================================="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    echo "Please install Python 3.8+ and try again."
    exit 1
fi

# Check if Docker is installed and running
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is required but not installed."
    echo "Please install Docker and try again."
    exit 1
fi

if ! docker info &> /dev/null; then
    echo "❌ Docker is not running."
    echo "Please start Docker and try again."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is required but not installed."
    echo "Please install Docker Compose and try again."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install/upgrade dependencies
echo "📚 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p wordpress-projects
mkdir -p utils
mkdir -p templates
mkdir -p static/css
mkdir -p static/js

# Set executable permissions for the script
chmod +x start.sh

echo ""
echo "✅ Setup complete!"
echo ""
echo "🌐 Starting WordPress Local Development Environment..."
echo "📂 Projects will be created in: ./wordpress-projects/"
echo "🔗 Web interface will be available at: http://localhost:5001"
echo ""
echo "⚠️  Note: You may need administrator privileges for:"
echo "   - Modifying hosts file (for local domains)"
echo "   - Installing SSL certificates"
echo ""

# Start the Flask application
python app.py 