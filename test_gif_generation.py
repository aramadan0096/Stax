#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script to verify GIF generation functionality
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.ffmpeg_wrapper import get_ffmpeg
from src.db_manager import DatabaseManager

def test_ffmpeg_availability():
    """Test if FFmpeg binaries are available."""
    print("=" * 60)
    print("Testing FFmpeg Availability")
    print("=" * 60)
    
    try:
        ffmpeg = get_ffmpeg()
        print("✓ FFmpeg wrapper initialized successfully")
        print("  FFmpeg path: {}".format(ffmpeg.ffmpeg_path))
        print("  FFprobe path: {}".format(ffmpeg.ffprobe_path))
        print("  FFplay path: {}".format(ffmpeg.ffplay_path))
        
        # Check if files exist
        if os.path.exists(ffmpeg.ffmpeg_path):
            print("  ✓ ffmpeg.exe found")
        else:
            print("  ✗ ffmpeg.exe NOT FOUND")
            
        if os.path.exists(ffmpeg.ffprobe_path):
            print("  ✓ ffprobe.exe found")
        else:
            print("  ✗ ffprobe.exe NOT FOUND")
            
        return True
    except Exception as e:
        print("✗ FFmpeg initialization failed: {}".format(str(e)))
        return False

def test_database_migration():
    """Test if database has gif_preview_path column."""
    print("\n" + "=" * 60)
    print("Testing Database Migration")
    print("=" * 60)
    
    try:
        db_path = "./data/vah_database.db"
        if not os.path.exists(db_path):
            print("⚠ Database not found at: {}".format(db_path))
            print("  Creating new database with migrations...")
        
        db = DatabaseManager(db_path, enable_logging=True)
        
        # Check if gif_preview_path column exists
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(elements)")
            columns = cursor.fetchall()
            
            print("\nElements table columns:")
            gif_column_found = False
            for col in columns:
                col_name = col[1]
                col_type = col[2]
                print("  - {} ({})".format(col_name, col_type))
                if col_name == 'gif_preview_path':
                    gif_column_found = True
            
            if gif_column_found:
                print("\n✓ gif_preview_path column exists")
            else:
                print("\n✗ gif_preview_path column MISSING")
                
            return gif_column_found
    except Exception as e:
        print("✗ Database check failed: {}".format(str(e)))
        return False

def test_ingestion_code():
    """Check if ingestion code includes GIF generation."""
    print("\n" + "=" * 60)
    print("Testing Ingestion Code")
    print("=" * 60)
    
    ingestion_file = "./src/ingestion_core.py"
    
    if not os.path.exists(ingestion_file):
        print("✗ ingestion_core.py not found")
        return False
    
    with open(ingestion_file, 'r') as f:
        content = f.read()
        
    # Check for key elements
    checks = [
        ('generate_gif_preview', 'GIF generation method call'),
        ('gif_preview_path', 'GIF preview path variable'),
        ('asset_type == \'video\'', 'Video asset type check'),
        ('is_sequence and asset_type == \'2D\'', 'Sequence GIF generation check'),
    ]
    
    all_present = True
    for check_str, description in checks:
        if check_str in content:
            print("✓ Found: {}".format(description))
        else:
            print("✗ Missing: {}".format(description))
            all_present = False
    
    return all_present

def test_preview_directory():
    """Check if preview directory exists."""
    print("\n" + "=" * 60)
    print("Testing Preview Directory")
    print("=" * 60)
    
    preview_dir = "./data/previews"
    
    if os.path.exists(preview_dir):
        print("✓ Preview directory exists: {}".format(preview_dir))
        
        # Check for GIF files
        gif_files = [f for f in os.listdir(preview_dir) if f.endswith('.gif')]
        
        if gif_files:
            print("\n✓ Found {} GIF file(s):".format(len(gif_files)))
            for gif in gif_files[:5]:  # Show first 5
                gif_path = os.path.join(preview_dir, gif)
                size = os.path.getsize(gif_path)
                print("  - {} ({} bytes)".format(gif, size))
            if len(gif_files) > 5:
                print("  ... and {} more".format(len(gif_files) - 5))
        else:
            print("\n⚠ No GIF files found in preview directory")
            print("  This is expected if no videos/sequences have been ingested yet")
        
        return True
    else:
        print("⚠ Preview directory doesn't exist yet: {}".format(preview_dir))
        print("  This will be created on first ingestion")
        return False

def main():
    """Run all tests."""
    print("\n")
    print("#" * 60)
    print("# GIF GENERATION DIAGNOSTICS")
    print("#" * 60)
    print("\n")
    
    results = []
    
    # Test 1: FFmpeg availability
    results.append(("FFmpeg Availability", test_ffmpeg_availability()))
    
    # Test 2: Database migration
    results.append(("Database Migration", test_database_migration()))
    
    # Test 3: Ingestion code
    results.append(("Ingestion Code", test_ingestion_code()))
    
    # Test 4: Preview directory
    results.append(("Preview Directory", test_preview_directory()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print("{:<30} {}".format(test_name, status))
    
    all_passed = all(result for _, result in results)
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ All tests passed!")
        print("\nGIF generation should work for newly ingested videos/sequences.")
        print("Note: Existing assets won't have GIFs (only new ingestions).")
    else:
        print("✗ Some tests failed!")
        print("\nPlease review the failures above.")
    print("=" * 60)
    print("\n")

if __name__ == "__main__":
    main()
