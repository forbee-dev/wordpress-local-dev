# Database Import Guide

## Overview

This guide explains how to import database files into your WordPress projects, including handling of problematic files that may cause UTF-8 decode errors.

## Supported File Formats

The system now supports both regular and gzipped SQL files:

- `.sql` - Plain text SQL files
- `.sql.gz` - Gzipped SQL files
- `.mysql` - MySQL dump files
- `.db` - Generic database files

## Automatic File Handling

The import system automatically:

1. **Detects file type** - Identifies gzipped files by extension or file headers
2. **Validates encoding** - Automatically checks for UTF-8 decode issues
3. **Repairs corrupted files** - Automatically cleans and repairs problematic files
4. **Handles encoding issues** - Uses multiple fallback strategies for corrupted files
5. **Provides detailed feedback** - Shows progress and any issues encountered
6. **Creates backups** - Optionally backs up existing database before import
7. **Cleans up files** - Removes temporary and original files after successful import

## Common Issues and Solutions

### UTF-8 Decode Errors

**Problem**: Files containing invalid UTF-8 characters cause import failures.

**Solution**: The system now automatically handles these issues using:
- UTF-8 decoding with error replacement
- Binary mode fallback with latin1 encoding
- Character replacement for corrupted bytes

### Large Gzipped Files

**Problem**: Large compressed files may take time to process.

**Solution**: The system provides progress feedback and handles files of any size.

## Database Validation Tool

Use the `utils/validate_database.py` script to check files before import:

### Basic Validation
```bash
python utils/validate_database.py path/to/database.sql
python utils/validate_database.py path/to/database.sql.gz
```

### Repair Corrupted Files
```bash
python utils/validate_database.py --repair path/to/problematic_database.sql.gz
```

The repair function:
- Creates a cleaned version of the file
- Replaces invalid UTF-8 characters
- Maintains SQL structure and functionality
- Reduces file size by removing corrupted bytes

## Import Methods

### 1. Via Web Interface (Recommended)

1. Navigate to your WordPress Local Dev interface
2. Click "Upload Database" for an existing project
3. Select your `.sql` or `.sql.gz` file
4. Choose whether to backup current database
5. Click "Upload & Import"

**The system will automatically:**
- Validate the file for encoding issues
- Repair the file if corrupted (removes invalid characters)
- Import the cleaned version
- Show detailed feedback about any repairs made
- Clean up temporary files

### 2. Via Command Line

```bash
cd wordpress-projects/your-project
make db-import  # If database file is in data/ folder
```

### 3. Direct Project Manager

```python
from utils.project_manager import ProjectManager
pm = ProjectManager()
result = pm.import_database('project_name', 'path/to/database.sql.gz')
```

## Best Practices

### Before Import

1. **Backup existing data**: Always backup before importing (automatic option available)
2. **Check file integrity**: Ensure files aren't corrupted during transfer
3. **Manual validation (optional)**: Use `utils/validate_database.py` for detailed analysis
4. **Test with small samples**: For very large databases, test with a subset first

**Note**: File validation and repair now happens automatically during upload!

## Automatic Validation and Repair Process

When you upload a database file through the web interface, the system automatically:

### 1. **File Detection**
- Analyzes file headers to detect gzip compression
- Checks file extensions (.sql, .sql.gz, etc.)
- Determines the appropriate reading method

### 2. **Encoding Validation**
- Tests the entire file for UTF-8 compatibility
- Identifies problematic byte sequences
- Reports the number of encoding issues found

### 3. **Automatic Repair (if needed)**
- Reads the file with error replacement
- Removes invalid UTF-8 characters (� symbols)
- Cleans control characters that shouldn't be in SQL
- Creates a cleaned version with "_repaired" suffix
- Validates the repaired file for clean import

### 4. **Import Process**
- Uses the cleaned version for database import
- Provides feedback about repairs performed
- Reports file size changes and characters removed
- Cleans up temporary files after successful import

### 5. **User Feedback**
The interface shows detailed information about:
- Whether validation passed or repair was needed
- Number of characters cleaned/removed
- Final file used for import
- Import success status

### During Import

1. **Monitor progress**: Watch for encoding warnings or errors
2. **Check container status**: Ensure all containers are running
3. **Verify disk space**: Large imports need adequate storage

### After Import

1. **Test website functionality**: Verify the import was successful
2. **Check debug logs**: Look for any WordPress errors
3. **Validate database**: Ensure all tables imported correctly

## Troubleshooting

### Import Fails with "Project must be running"

**Solution**: Start the project first:
```bash
cd wordpress-projects/your-project
docker-compose up -d
```

### Import Succeeds but Site Doesn't Work

**Possible Issues**:
- URL mismatch in database
- Plugin compatibility issues
- Theme file corruption

**Solutions**:
1. Check debug logs: `make debug-logs`
2. Use WP CLI to fix URLs: `wp search-replace old-url.com new-url.com`
3. Deactivate all plugins temporarily

### Large Files Time Out

**Solutions**:
1. Increase Docker memory limits
2. Use repair tool to reduce file size
3. Import during off-peak hours

## File Size Limits

The system supports files up to 100MB by default. For larger files:

1. **Split the database**: Use mysqldump with `--where` conditions
2. **Use repair tool**: Often reduces file size significantly
3. **Import tables individually**: Break down into smaller chunks

## Security Considerations

1. **Validate sources**: Only import databases from trusted sources
2. **Scan for malware**: Check for suspicious content in SQL files
3. **Review user accounts**: Audit imported user data
4. **Update passwords**: Change admin passwords after import

## Performance Tips

1. **Use gzipped files**: Faster transfer and storage
2. **Repair before import**: Cleaned files import faster
3. **Monitor resources**: Watch CPU and memory usage
4. **Schedule large imports**: Run during maintenance windows

## Support

For additional help:

1. Check the debug logs in your project
2. Use the validation tool for file analysis
3. Review the project's Docker container status
4. Consult WordPress debug.log for application errors

Remember: The system is designed to handle problematic files automatically, but validation and repair tools are available for additional confidence and control.
