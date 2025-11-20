# -*- coding: utf-8 -*-
"""
Test script for IngestLibraryDialog image sequence detection
Verifies that bulk folder ingestion properly detects image sequences
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

def test_sequence_detection_in_folder():
    """Test that _get_media_files detects sequences correctly."""
    # Create temporary test folder structure
    test_dir = tempfile.mkdtemp(prefix='stax_test_')
    
    try:
        # Create test sequence files
        sequence_dir = os.path.join(test_dir, 'test_sequence')
        os.makedirs(sequence_dir)
        
        # Create sequence: shot001.1001.exr to shot001.1010.exr
        for i in range(1001, 1011):
            filepath = os.path.join(sequence_dir, 'shot001.{}.exr'.format(i))
            with open(filepath, 'w') as f:
                f.write('test')
        
        # Create single image
        single_img = os.path.join(sequence_dir, 'reference.png')
        with open(single_img, 'w') as f:
            f.write('test')
        
        # Create video file
        video_file = os.path.join(sequence_dir, 'video.mp4')
        with open(video_file, 'w') as f:
            f.write('test')
        
        # Initialize dialog (mock components)
        config = Config()
        db = DatabaseManager(':memory:')  # In-memory database for testing
        
        # Create mock ingestion_core
        class MockIngestion:
            pass
        
        from PySide2 import QtWidgets
        app = QtWidgets.QApplication.instance()
        if not app:
            app = QtWidgets.QApplication(sys.argv)
        
        dialog = IngestLibraryDialog(db, MockIngestion(), config)
        
        # Test sequence detection
        media_files = dialog._get_media_files(sequence_dir)
        
        print("\nTest Results:")
        print("=" * 60)
        print("Created 10 sequence files (shot001.1001-1010.exr)")
        print("Created 1 single image (reference.png)")
        print("Created 1 video file (video.mp4)")
        print("-" * 60)
        print("Files detected by _get_media_files: {}".format(len(media_files)))
        print("\nDetected files:")
        for f in media_files:
            print("  - {}".format(os.path.basename(f)))
        
        print("\n" + "=" * 60)
        
        # Verify results
        expected_count = 3  # 1 sequence (as single representative), 1 image, 1 video
        if len(media_files) == expected_count:
            print("✓ SUCCESS: Correctly detected {} media items".format(expected_count))
            print("  (10-frame sequence counted as 1 item)")
            return True
        else:
            print("✗ FAILED: Expected {} items, got {}".format(expected_count, len(media_files)))
            print("  Sequence detection may not be working in bulk ingest")
            return False
    
    finally:
        # Cleanup
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)


if __name__ == '__main__':
    print("Testing IngestLibraryDialog sequence detection...")
    success = test_sequence_detection_in_folder()
    sys.exit(0 if success else 1)
