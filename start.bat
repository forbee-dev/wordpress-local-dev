@echo off
echo 🚀 WordPress Local Development Environment
echo ==========================================

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python 3 is required but not installed.
    echo Please install Python 3.8+ and try again.
    pause
    exit /b 1
)

REM Check if Docker is installed and running
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker is required but not installed.
    echo Please install Docker Desktop and try again.
    pause
    exit /b 1
)

docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker is not running.
    echo Please start Docker Desktop and try again.
    pause
    exit /b 1
)

REM Check if Docker Compose is installed
docker-compose --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker Compose is required but not installed.
    echo Please install Docker Compose and try again.
    pause
    exit /b 1
)

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo 🔧 Activating virtual environment...
call venv\Scripts\activate.bat

REM Install/upgrade dependencies
echo 📚 Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt

REM Create necessary directories
echo 📁 Creating directories...
if not exist "wordpress-projects" mkdir wordpress-projects
if not exist "utils" mkdir utils
if not exist "templates" mkdir templates
if not exist "static\css" mkdir static\css
if not exist "static\js" mkdir static\js

echo.
echo ✅ Setup complete!
echo.
echo 🌐 Starting WordPress Local Development Environment...
echo 📂 Projects will be created in: .\wordpress-projects\
echo 🔗 Web interface will be available at: http://localhost:5001
echo.
echo ⚠️  Note: You may need administrator privileges for:
echo    - Modifying hosts file (for local domains)
echo    - Installing SSL certificates
echo.

REM Start the Flask application
python app.py

pause 