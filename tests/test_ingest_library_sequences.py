# -*- coding: utf-8 -*-
"""
Test script for IngestLibraryDialog sequence detection with different patterns
Verifies that the scan folder feature properly detects image sequences
using the configured sequence pattern from settings.
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
from src.ui.ingest_library_dialog import IngestLibraryDialog
from src.config import Config
from src.db_manager import DatabaseManager
from PySide2 import QtWidgets


def create_test_sequences(test_dir):
    """Create test sequences with different naming patterns."""
    
    # Pattern 1: .####.ext (e.g., shot001.1001.exr)
    seq1_dir = os.path.join(test_dir, 'pattern_dot')
    os.makedirs(seq1_dir)
    for i in range(1001, 1011):
        filepath = os.path.join(seq1_dir, 'shot001.{}.exr'.format(i))
        with open(filepath, 'w') as f:
            f.write('test')
    
    # Pattern 2: _####.ext (e.g., render_0001.png)
    seq2_dir = os.path.join(test_dir, 'pattern_underscore')
    os.makedirs(seq2_dir)
    for i in range(1, 11):
        filepath = os.path.join(seq2_dir, 'render_{:04d}.png'.format(i))
        with open(filepath, 'w') as f:
            f.write('test')
    
    # Pattern 3: -####.ext (e.g., plate-0100.dpx)
    seq3_dir = os.path.join(test_dir, 'pattern_dash')
    os.makedirs(seq3_dir)
    for i in range(100, 110):
        filepath = os.path.join(seq3_dir, 'plate-{:04d}.dpx'.format(i))
        with open(filepath, 'w') as f:
            f.write('test')
    
    # Single images (should not be treated as sequences)
    singles_dir = os.path.join(test_dir, 'singles')
    os.makedirs(singles_dir)
    with open(os.path.join(singles_dir, 'reference.png'), 'w') as f:
        f.write('test')
    with open(os.path.join(singles_dir, 'matte.exr'), 'w') as f:
        f.write('test')
    
    # Video files (should be treated as singles)
    with open(os.path.join(singles_dir, 'video.mp4'), 'w') as f:
        f.write('test')
    
    # 3D assets (should be treated as singles)
    with open(os.path.join(singles_dir, 'model.fbx'), 'w') as f:
        f.write('test')
    
    return {
        'pattern_dot': (seq1_dir, 10),
        'pattern_underscore': (seq2_dir, 10),
        'pattern_dash': (seq3_dir, 10),
        'singles': (singles_dir, 4)
    }


def test_pattern(pattern_key, pattern_dir, expected_files):
    """Test sequence detection with specific pattern."""
    print("\n" + "=" * 70)
    print("Testing pattern: {}".format(pattern_key))
    print("=" * 70)
    
    config = Config()
    config.set('sequence_pattern', pattern_key)
    db = DatabaseManager(':memory:')
    
    class MockIngestion:
        pass
    
    app = QtWidgets.QApplication.instance()
    if not app:
        app = QtWidgets.QApplication(sys.argv)
    
    dialog = IngestLibraryDialog(db, MockIngestion(), config)
    
    # Test sequence detection
    media_files = dialog._get_media_files(pattern_dir)
    
    print("Expected items: {}".format(expected_files))
    print("Detected items: {}".format(len(media_files)))
    print("\nDetected files:")
    for f in media_files:
        print("  - {}".format(os.path.basename(f)))
    
    if len(media_files) == expected_files:
        print("\n✓ SUCCESS: Pattern '{}' detected correctly".format(pattern_key))
        return True
    else:
        print("\n✗ FAILED: Pattern '{}' detection mismatch".format(pattern_key))
        print("  Expected {} items, got {}".format(expected_files, len(media_files)))
        return False


def run_all_tests():
    """Run comprehensive tests for all sequence patterns."""
    print("\n" + "=" * 70)
    print("IngestLibraryDialog Sequence Detection Test Suite")
    print("=" * 70)
    
    test_dir = tempfile.mkdtemp(prefix='stax_seq_test_')
    
    try:
        # Create test sequences
        test_data = create_test_sequences(test_dir)
        
        results = []
        
        # Test Pattern 1: .####.ext
        results.append(test_pattern(
            '.####.ext',
            test_data['pattern_dot'][0],
            1  # 10 frames should be detected as 1 sequence
        ))
        
        # Test Pattern 2: _####.ext
        results.append(test_pattern(
            '_####.ext',
            test_data['pattern_underscore'][0],
            1  # 10 frames should be detected as 1 sequence
        ))
        
        # Test Pattern 3: -####.ext
        results.append(test_pattern(
            '-####.ext',
            test_data['pattern_dash'][0],
            1  # 10 frames should be detected as 1 sequence
        ))
        
        # Test singles folder (no sequences)
        results.append(test_pattern(
            '.####.ext',  # Pattern doesn't matter for singles
            test_data['singles'][0],
            4  # 4 individual files
        ))
        
        # Summary
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        passed = sum(results)
        total = len(results)
        print("Passed: {}/{}".format(passed, total))
        
        if passed == total:
            print("\n✓ ALL TESTS PASSED")
            print("\nThe scan folder feature now properly detects sequences")
            print("and prevents duplicate GIF generation for each frame.")
            return True
        else:
            print("\n✗ SOME TESTS FAILED")
            return False
    
    finally:
        # Cleanup
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)


if __name__ == '__main__':
    print("Testing IngestLibraryDialog sequence detection...")
    print("This verifies the fix for the duplicate GIF generation issue.")
    success = run_all_tests()
    sys.exit(0 if success else 1)
