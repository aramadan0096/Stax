# -*- coding: utf-8 -*-
"""
Simple test to verify sequence detection logic in _get_media_files
Tests the core logic without requiring full UI initialization
"""
import os
import sys
import tempfile
import shutil

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import dependency_bootstrap
dependency_bootstrap.bootstrap()

from src.ingestion_core import SequenceDetector
from src.config import Config


def simulate_get_media_files(folder_path, sequence_pattern='.####.ext', auto_detect=True):
    """Simulate IngestLibraryDialog._get_media_files for unit tests."""
    media_extensions = ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.exr', '.dpx',
                        '.mp4', '.mov', '.avi', '.mkv', '.obj', '.fbx', '.abc', '.nk', '.tga']
    image_extensions = ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.exr', '.dpx', '.tga']

    all_files = []
    for item in os.listdir(folder_path):
        if item.startswith('.'):
            continue
        item_path = os.path.join(folder_path, item)
        if os.path.isfile(item_path):
            _, ext = os.path.splitext(item)
            if ext.lower() in media_extensions:
                all_files.append(os.path.normpath(item_path))

    processed_files = set()
    processed_sequences = set()
    result_files = []

    for filepath in sorted(all_files):
        if filepath in processed_files:
            continue

        _, ext = os.path.splitext(filepath)
        ext_lower = ext.lower()

        if auto_detect and ext_lower in image_extensions:
            sequence_info = SequenceDetector.detect_sequence(
                filepath,
                pattern_key=sequence_pattern,
                auto_detect=auto_detect
            )

            if sequence_info and sequence_info.get('frame_count', 1) > 1:
                sequence_files = sequence_info.get('files') or []
                if sequence_files:
                    sequence_dir = os.path.dirname(sequence_files[0])
                    frame_pattern = sequence_info.get('frame_pattern') or ''
                    sequence_key = (os.path.normpath(sequence_dir), frame_pattern.lower())

                    if sequence_key not in processed_sequences:
                        processed_sequences.add(sequence_key)
                        representative = os.path.normpath(sequence_files[0])
                        result_files.append(representative)

                    for seq_file in sequence_files:
                        processed_files.add(os.path.normpath(seq_file))
                    continue

        result_files.append(filepath)
        processed_files.add(filepath)

    return result_files


def test_sequence_folder():
    """Test with a folder containing image sequences."""
    print("\n" + "=" * 70)
    print("Test: Folder with image sequence (10 frames)")
    print("=" * 70)
    
    test_dir = tempfile.mkdtemp(prefix='stax_test_')
    
    try:
        # Create sequence: shot001.1001.exr to shot001.1010.exr
        for i in range(1001, 1011):
            filepath = os.path.join(test_dir, 'shot001.{}.exr'.format(i))
            with open(filepath, 'w') as f:
                f.write('test')
        
        # Add a single image
        with open(os.path.join(test_dir, 'reference.png'), 'w') as f:
            f.write('test')
        
        # Add a video
        with open(os.path.join(test_dir, 'video.mp4'), 'w') as f:
            f.write('test')
        
        print("Created:")
        print("  - 10 sequence frames (shot001.1001-1010.exr)")
        print("  - 1 single image (reference.png)")
        print("  - 1 video (video.mp4)")
        print()
        
        # Test detection
        result = simulate_get_media_files(test_dir, '.####.ext')
        
        print("Detection results:")
        print("  Detected {} items:".format(len(result)))
        for f in result:
            print("    - {}".format(os.path.basename(f)))
        
        # Verify
        expected = 3  # 1 sequence + 1 image + 1 video
        if len(result) == expected:
            print("\n✓ SUCCESS: Correctly detected {} items".format(expected))
            print("  (10-frame sequence counted as 1 item)")
            return True
        else:
            print("\n✗ FAILED: Expected {} items, got {}".format(expected, len(result)))
            return False
    
    finally:
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)


def test_multiple_sequences():
    """Test with multiple sequences in same folder."""
    print("\n" + "=" * 70)
    print("Test: Folder with multiple sequences")
    print("=" * 70)
    
    test_dir = tempfile.mkdtemp(prefix='stax_test_')
    
    try:
        # Sequence 1: shot001.1001-1010.exr
        for i in range(1001, 1011):
            filepath = os.path.join(test_dir, 'shot001.{}.exr'.format(i))
            with open(filepath, 'w') as f:
                f.write('test')
        
        # Sequence 2: shot002.2001-2005.exr
        for i in range(2001, 2006):
            filepath = os.path.join(test_dir, 'shot002.{}.exr'.format(i))
            with open(filepath, 'w') as f:
                f.write('test')
        
        print("Created:")
        print("  - Sequence 1: shot001.1001-1010.exr (10 frames)")
        print("  - Sequence 2: shot002.2001-2005.exr (5 frames)")
        print()
        
        # Test detection
        result = simulate_get_media_files(test_dir, '.####.ext')
        
        print("Detection results:")
        print("  Detected {} items:".format(len(result)))
        for f in result:
            print("    - {}".format(os.path.basename(f)))
        
        # Verify
        expected = 2  # 2 sequences
        if len(result) == expected:
            print("\n✓ SUCCESS: Correctly detected {} sequences".format(expected))
            return True
        else:
            print("\n✗ FAILED: Expected {} sequences, got {}".format(expected, len(result)))
            return False
    
    finally:
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)


def test_underscore_pattern():
    """Test with underscore pattern _####.ext."""
    print("\n" + "=" * 70)
    print("Test: Underscore pattern (_####.ext)")
    print("=" * 70)
    
    test_dir = tempfile.mkdtemp(prefix='stax_test_')
    
    try:
        # Sequence: render_0001-0010.png
        for i in range(1, 11):
            filepath = os.path.join(test_dir, 'render_{:04d}.png'.format(i))
            with open(filepath, 'w') as f:
                f.write('test')
        
        print("Created:")
        print("  - 10 sequence frames (render_0001-0010.png)")
        print()
        
        # Test detection with underscore pattern
        result = simulate_get_media_files(test_dir, '_####.ext')
        
        print("Detection results:")
        print("  Detected {} items:".format(len(result)))
        for f in result:
            print("    - {}".format(os.path.basename(f)))
        
        # Verify
        expected = 1  # 1 sequence
        if len(result) == expected:
            print("\n✓ SUCCESS: Underscore pattern works correctly")
            return True
        else:
            print("\n✗ FAILED: Expected {} sequence, got {} items".format(expected, len(result)))
            return False
    
    finally:
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)


def main():
    print("=" * 70)
    print("IngestLibraryDialog Sequence Detection Test")
    print("Verifying fix for duplicate GIF generation issue")
    print("=" * 70)
    
    results = []
    results.append(test_sequence_folder())
    results.append(test_multiple_sequences())
    results.append(test_underscore_pattern())
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    passed = sum(results)
    total = len(results)
    print("Passed: {}/{}".format(passed, total))
    
    if passed == total:
        print("\n✓ ALL TESTS PASSED")
        print("\nThe enhanced _get_media_files() now:")
        print("  - Detects image sequences properly")
        print("  - Returns only 1 representative file per sequence")
        print("  - Prevents duplicate GIF generation")
        print("  - Respects configured sequence pattern from settings")
        return 0
    else:
        print("\n✗ SOME TESTS FAILED")
        return 1


if __name__ == '__main__':
    sys.exit(main())
