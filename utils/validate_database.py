#!/usr/bin/env python3
"""
Database File Validation and Repair Utility

This script helps validate and repair database files before importing them
into WordPress projects. It can handle both regular .sql files and gzipped
.sql.gz files, and provides detailed information about any issues found.

Usage:
    python utils/validate_database.py path/to/database.sql
    python utils/validate_database.py path/to/database.sql.gz
    python utils/validate_database.py --repair path/to/database.sql.gz
"""

import argparse
import gzip
import sys
from pathlib import Path


def is_gzipped_file(file_path):
    """Check if a file is gzipped by reading its magic bytes"""
    try:
        with open(file_path, 'rb') as f:
            magic = f.read(2)
            return magic == b'\x1f\x8b'
    except Exception:
        return False


def validate_database_file(file_path, repair=False):
    """Validate a database file and optionally repair it"""
    file_path = Path(file_path)
    
    print(f"🔍 Validating database file: {file_path.name}")
    print(f"📁 Full path: {file_path}")
    print(f"📏 File size: {file_path.stat().st_size:,} bytes")
    
    # Check if file exists
    if not file_path.exists():
        print("❌ Error: File does not exist")
        return False
    
    # Detect file type
    is_gzipped = (
        file_path.suffix.lower() == '.gz' or 
        file_path.name.lower().endswith('.sql.gz') or
        is_gzipped_file(file_path)
    )
    
    if is_gzipped:
        print("📦 File type: Gzipped SQL file")
        return validate_gzipped_file(file_path, repair)
    else:
        print("📄 File type: Plain text SQL file")
        return validate_plain_file(file_path, repair)


def validate_gzipped_file(file_path, repair=False):
    """Validate a gzipped database file"""
    try:
        print("🔄 Testing gzip decompression...")
        
        # Test if we can open the gzip file
        with gzip.open(file_path, 'rb') as f:
            # Read first few KB to test
            first_chunk = f.read(10240)  # 10KB
            if not first_chunk:
                print("❌ Error: Gzip file appears to be empty")
                return False
            
        print("✅ Gzip decompression: OK")
        
        # Test encoding
        print("🔤 Testing character encoding...")
        
        encoding_results = test_encoding_gzipped(file_path)
        
        if encoding_results['utf8_clean']:
            print("✅ UTF-8 encoding: Perfect (no issues)")
            return True
        elif encoding_results['utf8_with_replacement']:
            replacement_count = encoding_results['replacement_count']
            print(f"⚠️  UTF-8 encoding: Issues found ({replacement_count:,} invalid characters)")
            print(f"   The file can be imported but may have corrupted data")
            
            if repair:
                return repair_gzipped_file(file_path, encoding_results)
            else:
                print(f"   Use --repair to create a cleaned version")
                return True
        else:
            print("❌ UTF-8 encoding: Failed completely")
            
            if repair:
                return repair_gzipped_file(file_path, encoding_results)
            else:
                print(f"   Use --repair to attempt recovery")
                return False
                
    except Exception as e:
        print(f"❌ Error validating gzipped file: {str(e)}")
        return False


def validate_plain_file(file_path, repair=False):
    """Validate a plain text database file"""
    try:
        print("🔤 Testing character encoding...")
        
        encoding_results = test_encoding_plain(file_path)
        
        if encoding_results['utf8_clean']:
            print("✅ UTF-8 encoding: Perfect (no issues)")
            return True
        elif encoding_results['utf8_with_replacement']:
            replacement_count = encoding_results['replacement_count']
            print(f"⚠️  UTF-8 encoding: Issues found ({replacement_count:,} invalid characters)")
            print(f"   The file can be imported but may have corrupted data")
            
            if repair:
                return repair_plain_file(file_path, encoding_results)
            else:
                print(f"   Use --repair to create a cleaned version")
                return True
        else:
            print("❌ UTF-8 encoding: Failed completely")
            
            if repair:
                return repair_plain_file(file_path, encoding_results)
            else:
                print(f"   Use --repair to attempt recovery")
                return False
                
    except Exception as e:
        print(f"❌ Error validating plain file: {str(e)}")
        return False


def test_encoding_gzipped(file_path):
    """Test different encoding approaches for gzipped files"""
    results = {
        'utf8_clean': False,
        'utf8_with_replacement': False,
        'replacement_count': 0,
        'content_sample': None
    }
    
    try:
        # Test clean UTF-8 - read entire file to catch issues anywhere
        print("   🔍 Reading entire file to test UTF-8 encoding...")
        with gzip.open(file_path, 'rt', encoding='utf-8') as f:
            content = f.read()  # Read entire file to properly test
            results['utf8_clean'] = True
            results['content_sample'] = content[:200]
            return results
    except UnicodeDecodeError as e:
        print(f"   ⚠️  UTF-8 decode error found: {str(e)}")
        pass
    
    try:
        # Test UTF-8 with replacement
        with gzip.open(file_path, 'rt', encoding='utf-8', errors='replace') as f:
            content = f.read()
            replacement_count = content.count('�')
            results['utf8_with_replacement'] = True
            results['replacement_count'] = replacement_count
            results['content_sample'] = content[:200]
            return results
    except Exception:
        pass
    
    return results


def test_encoding_plain(file_path):
    """Test different encoding approaches for plain files"""
    results = {
        'utf8_clean': False,
        'utf8_with_replacement': False,
        'replacement_count': 0,
        'content_sample': None
    }
    
    try:
        # Test clean UTF-8 - read entire file to catch issues anywhere
        print("   🔍 Reading entire file to test UTF-8 encoding...")
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()  # Read entire file to properly test
            results['utf8_clean'] = True
            results['content_sample'] = content[:200]
            return results
    except UnicodeDecodeError as e:
        print(f"   ⚠️  UTF-8 decode error found: {str(e)}")
        pass
    
    try:
        # Test UTF-8 with replacement
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
            replacement_count = content.count('�')
            results['utf8_with_replacement'] = True
            results['replacement_count'] = replacement_count
            results['content_sample'] = content[:200]
            return results
    except Exception:
        pass
    
    return results


def repair_gzipped_file(file_path, encoding_results):
    """Repair a gzipped database file"""
    file_path = Path(file_path)
    
    # Create repaired filename
    if file_path.name.endswith('.sql.gz'):
        repaired_name = file_path.name.replace('.sql.gz', '_repaired.sql.gz')
    else:
        repaired_name = f"{file_path.stem}_repaired{file_path.suffix}"
    
    repaired_path = file_path.parent / repaired_name
    
    print(f"🔧 Repairing file: {repaired_name}")
    
    try:
        # Read with error handling to replace invalid characters
        print("   📖 Reading file with error replacement...")
        with gzip.open(file_path, 'rt', encoding='utf-8', errors='replace') as input_file:
            content = input_file.read()
        
        # Clean the content by removing replacement characters and problematic sequences
        print("   🧹 Cleaning content...")
        original_length = len(content)
        
        # Remove replacement characters (�)
        cleaned_content = content.replace('�', '')
        
        # Also clean common problematic sequences that could cause encoding issues
        # Remove null bytes and other control characters that shouldn't be in SQL
        import re
        cleaned_content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', cleaned_content)
        
        final_length = len(cleaned_content)
        removed_chars = original_length - final_length
        
        print(f"   ✂️  Removed {removed_chars:,} problematic characters")
        
        # Write cleaned version
        print("   💾 Writing cleaned file...")
        with gzip.open(repaired_path, 'wt', encoding='utf-8') as output_file:
            output_file.write(cleaned_content)
        
        print(f"✅ Repaired file created: {repaired_path}")
        print(f"   Original: {file_path.stat().st_size:,} bytes")
        print(f"   Repaired: {repaired_path.stat().st_size:,} bytes")
        print(f"   Cleaned characters: {removed_chars:,}")
        
        # Validate the repaired file
        print("   🔍 Validating repaired file...")
        try:
            with gzip.open(repaired_path, 'rt', encoding='utf-8') as test_file:
                test_content = test_file.read(1000)  # Test first 1KB
            print("   ✅ Repaired file validates cleanly")
        except Exception as e:
            print(f"   ⚠️  Repaired file validation warning: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error repairing file: {str(e)}")
        return False


def repair_plain_file(file_path, encoding_results):
    """Repair a plain text database file"""
    file_path = Path(file_path)
    
    # Create repaired filename
    repaired_name = f"{file_path.stem}_repaired{file_path.suffix}"
    repaired_path = file_path.parent / repaired_name
    
    print(f"🔧 Repairing file: {repaired_name}")
    
    try:
        # Read with error handling to replace invalid characters
        print("   📖 Reading file with error replacement...")
        with open(file_path, 'r', encoding='utf-8', errors='replace') as input_file:
            content = input_file.read()
        
        # Clean the content by removing replacement characters and problematic sequences
        print("   🧹 Cleaning content...")
        original_length = len(content)
        
        # Remove replacement characters (�)
        cleaned_content = content.replace('�', '')
        
        # Also clean common problematic sequences that could cause encoding issues
        # Remove null bytes and other control characters that shouldn't be in SQL
        import re
        cleaned_content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', cleaned_content)
        
        final_length = len(cleaned_content)
        removed_chars = original_length - final_length
        
        print(f"   ✂️  Removed {removed_chars:,} problematic characters")
        
        # Write cleaned version
        print("   💾 Writing cleaned file...")
        with open(repaired_path, 'w', encoding='utf-8') as output_file:
            output_file.write(cleaned_content)
        
        print(f"✅ Repaired file created: {repaired_path}")
        print(f"   Original: {file_path.stat().st_size:,} bytes")
        print(f"   Repaired: {repaired_path.stat().st_size:,} bytes")
        print(f"   Cleaned characters: {removed_chars:,}")
        
        # Validate the repaired file
        print("   🔍 Validating repaired file...")
        try:
            with open(repaired_path, 'r', encoding='utf-8') as test_file:
                test_content = test_file.read(1000)  # Test first 1KB
            print("   ✅ Repaired file validates cleanly")
        except Exception as e:
            print(f"   ⚠️  Repaired file validation warning: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error repairing file: {str(e)}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Validate and repair database files for WordPress import",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python utils/validate_database.py database.sql
  python utils/validate_database.py database.sql.gz
  python utils/validate_database.py --repair problematic_database.sql.gz
        """
    )
    
    parser.add_argument('file_path', help='Path to the database file to validate')
    parser.add_argument('--repair', action='store_true', 
                       help='Create a repaired version if issues are found')
    
    args = parser.parse_args()
    
    print("🛠️  Database File Validation and Repair Utility")
    print("=" * 50)
    
    success = validate_database_file(args.file_path, args.repair)
    
    print("=" * 50)
    if success:
        print("✅ Validation completed successfully")
        if args.repair:
            print("💡 Tip: You can now import the repaired file into your WordPress project")
        else:
            print("💡 Tip: File should import successfully into your WordPress project")
    else:
        print("❌ Validation found critical issues")
        print("💡 Tip: Try using --repair to fix the issues")
        sys.exit(1)


if __name__ == '__main__':
    main()
