#!/usr/bin/env python3
"""
Test script to verify WordPress Local Development Environment setup
"""

import sys
import os
import subprocess
from pathlib import Path

def test_python_version():
    """Test if Python version is 3.8 or higher"""
    version = sys.version_info
    if version.major >= 3 and version.minor >= 8:
        print("✅ Python version:", f"{version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print("❌ Python 3.8+ required, found:", f"{version.major}.{version.minor}.{version.micro}")
        return False

def test_required_modules():
    """Test if required Python modules can be imported"""
    modules = [
        'flask',
        'cryptography',
        'yaml',
        'pathlib',
        'subprocess',
        'json',
        'platform'
    ]
    
    failed = []
    for module in modules:
        try:
            __import__(module)
            print(f"✅ Module {module} - OK")
        except ImportError:
            print(f"❌ Module {module} - MISSING")
            failed.append(module)
    
    return len(failed) == 0

def test_docker():
    """Test if Docker is installed and running"""
    try:
        result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Docker installed: {result.stdout.strip()}")
            
            # Test if Docker is running
            result = subprocess.run(['docker', 'info'], capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ Docker is running")
                return True
            else:
                print("❌ Docker is not running")
                return False
        else:
            print("❌ Docker not found")
            return False
    except FileNotFoundError:
        print("❌ Docker not installed")
        return False

def test_docker_compose():
    """Test if Docker Compose is installed"""
    try:
        result = subprocess.run(['docker-compose', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Docker Compose installed: {result.stdout.strip()}")
            return True
        else:
            print("❌ Docker Compose not found")
            return False
    except FileNotFoundError:
        print("❌ Docker Compose not installed")
        return False

def test_file_structure():
    """Test if required files and directories exist"""
    required_files = [
        'app.py',
        'requirements.txt',
        'templates/index.html',
        'static/css/style.css',
        'static/js/app.js',
        'utils/__init__.py',
        'utils/project_manager.py',
        'utils/ssl_generator.py',
        'utils/hosts_manager.py',
        'start.sh',
        'start.bat'
    ]
    
    missing = []
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"✅ {file_path} - OK")
        else:
            print(f"❌ {file_path} - MISSING")
            missing.append(file_path)
    
    return len(missing) == 0

def test_permissions():
    """Test if scripts have correct permissions"""
    scripts = ['start.sh']
    for script in scripts:
        if Path(script).exists():
            if os.access(script, os.X_OK):
                print(f"✅ {script} is executable")
            else:
                print(f"❌ {script} is not executable (run: chmod +x {script})")
        else:
            print(f"❌ {script} not found")

def main():
    """Run all tests"""
    print("🧪 WordPress Local Development Environment - Setup Test")
    print("=" * 60)
    
    tests = [
        ("Python Version", test_python_version),
        ("Required Modules", test_required_modules),
        ("Docker", test_docker),
        ("Docker Compose", test_docker_compose),
        ("File Structure", test_file_structure),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n📋 Testing {test_name}...")
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"❌ Error in {test_name}: {str(e)}")
            results.append(False)
    
    # Additional permission test (non-blocking)
    print(f"\n📋 Testing Script Permissions...")
    test_permissions()
    
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print("🎉 All tests passed! Your setup is ready.")
        print("\nTo start the application:")
        print("   ./start.sh (macOS/Linux)")
        print("   start.bat (Windows)")
        return True
    else:
        print(f"⚠️  {passed}/{total} tests passed. Please fix the issues above.")
        if not test_required_modules():
            print("\n💡 To install missing modules:")
            print("   pip install -r requirements.txt")
        return False

if __name__ == "__main__":
    sys.exit(0 if main() else 1) 