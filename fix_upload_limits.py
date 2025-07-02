#!/usr/bin/env python3
"""
WordPress Local Dev - Fix Upload Limits
======================================

This script fixes PHP upload limits for existing WordPress projects.
Run this script to add proper PHP configuration for file uploads.

Usage:
    python fix_upload_limits.py                    # Fix all projects
    python fix_upload_limits.py project_name       # Fix specific project

"""

import sys
import argparse
from pathlib import Path
from utils.project_manager import ProjectManager

def main():
    parser = argparse.ArgumentParser(description='Fix PHP upload limits for WordPress projects')
    parser.add_argument('project_name', nargs='?', help='Specific project to fix (optional)')
    parser.add_argument('--all', action='store_true', help='Fix all projects')
    
    args = parser.parse_args()
    
    project_manager = ProjectManager()
    
    print("🔧 WordPress Local Dev - Upload Limits Fix")
    print("=" * 50)
    
    if args.project_name:
        # Fix specific project
        print(f"Fixing upload limits for project: {args.project_name}")
        result = project_manager.fix_php_upload_limits(args.project_name)
        
        if result['success']:
            print(f"\n✅ Success: {result['message']}")
        else:
            print(f"\n❌ Error: {result['error']}")
            sys.exit(1)
            
    else:
        # Fix all projects
        projects = project_manager.list_projects()
        
        if not projects:
            print("No WordPress projects found.")
            return
        
        print(f"Found {len(projects)} projects. Fixing upload limits for all...")
        print()
        
        success_count = 0
        error_count = 0
        
        for project in projects:
            project_name = project['name']
            print(f"Processing project: {project_name}")
            
            result = project_manager.fix_php_upload_limits(project_name)
            
            if result['success']:
                success_count += 1
                print(f"  ✅ {result['message']}")
            else:
                error_count += 1
                print(f"  ❌ {result['error']}")
            
            print()  # Add spacing between projects
        
        print("=" * 50)
        print(f"Summary:")
        print(f"  ✅ Successfully fixed: {success_count} projects")
        print(f"  ❌ Errors: {error_count} projects")
        
        if error_count == 0:
            print(f"\n🎉 All projects are now configured with 100MB upload limits!")
        else:
            print(f"\n⚠️  Some projects had errors. Please check the output above.")

if __name__ == '__main__':
    main() 