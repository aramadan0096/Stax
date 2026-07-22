# -*- coding: utf-8 -*-
"""
Test Script for Sequence Detection Features
Tests all four requirements from the user
"""

import os
import sys
import tempfile
import shutil

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.ingestion_core import SequenceDetector

def create_test_sequences(temp_dir):
    """Create test image files with different patterns."""
    
    # Pattern 1: .####.ext (dot separator)
    dot_dir = os.path.join(temp_dir, 'dot_pattern')
    os.makedirs(dot_dir)
    for i in range(1001, 1011):
        open(os.path.join(dot_dir, 'image.{}.exr'.format(i)), 'w').close()
    
    # Pattern 2: _####.ext (underscore separator)
    underscore_dir = os.path.join(temp_dir, 'underscore_pattern')
    os.makedirs(underscore_dir)
    for i in range(1001, 1011):
        open(os.path.join(underscore_dir, 'plate_{}.dpx'.format(i)), 'w').close()
    
    # Pattern 3: <space>####.ext (space separator)
    space_dir = os.path.join(temp_dir, 'space_pattern')
    os.makedirs(space_dir)
    for i in range(1001, 1011):
        open(os.path.join(space_dir, 'render {}.png'.format(i)), 'w').close()
    
    # Pattern 4: -####.ext (dash separator)
    dash_dir = os.path.join(temp_dir, 'dash_pattern')
    os.makedirs(dash_dir)
    for i in range(1001, 1011):
        open(os.path.join(dash_dir, 'shot-{}.jpg'.format(i)), 'w').close()
    
    # Non-sequence files (should NOT be detected as sequence)
    single_dir = os.path.join(temp_dir, 'single_files')
    os.makedirs(single_dir)
    open(os.path.join(single_dir, 'image_1001.exr'), 'w').close()  # Wrong pattern for .####.ext
    open(os.path.join(single_dir, 'standalone.jpg'), 'w').close()
    
    # Mixed pattern (should only detect correct pattern)
    mixed_dir = os.path.join(temp_dir, 'mixed')
    os.makedirs(mixed_dir)
    for i in range(1001, 1006):
        open(os.path.join(mixed_dir, 'correct.{}.exr'.format(i)), 'w').close()
    open(os.path.join(mixed_dir, 'wrong_1001.exr'), 'w').close()
    
    return {
        'dot': dot_dir,
        'underscore': underscore_dir,
        'space': space_dir,
        'dash': dash_dir,
        'single': single_dir,
        'mixed': mixed_dir
    }


def test_pattern_detection():
    """Test all pattern detection scenarios."""
    
    print("="*80)
    print("SEQUENCE DETECTION TEST SUITE")
    print("="*80)
    
    temp_dir = tempfile.mkdtemp(prefix='stax_test_')
    
    try:
        test_dirs = create_test_sequences(temp_dir)
        
        # TEST 1: Dot pattern (.####.ext)
        print("\n[TEST 1] Dot Pattern Detection (.####.ext)")
        print("-" * 80)
        test_file = os.path.join(test_dirs['dot'], 'image.1001.exr')
        result = SequenceDetector.detect_sequence(test_file, pattern_key='.####.ext', auto_detect=True)
        
        if result:
            print("✓ PASS: Detected sequence")
            print("  Base name: {}".format(result['base_name']))
            print("  Frame pattern: {}".format(result['frame_pattern']))
            print("  FFmpeg pattern: {}".format(result['ffmpeg_pattern']))
            print("  Frame range: {}".format(result['frame_range']))
            print("  File count: {}".format(result['frame_count']))
            print("  Pattern key: {}".format(result['pattern_key']))
            assert result['frame_count'] == 10, "Expected 10 frames"
            assert result['pattern_key'] == '.####.ext', "Wrong pattern detected"
        else:
            print("✗ FAIL: No sequence detected")
            return False
        
        # TEST 2: Underscore pattern (_####.ext)
        print("\n[TEST 2] Underscore Pattern Detection (_####.ext)")
        print("-" * 80)
        test_file = os.path.join(test_dirs['underscore'], 'plate_1001.dpx')
        result = SequenceDetector.detect_sequence(test_file, pattern_key='_####.ext', auto_detect=True)
        
        if result:
            print("✓ PASS: Detected sequence")
            print("  Base name: {}".format(result['base_name']))
            print("  Frame pattern: {}".format(result['frame_pattern']))
            print("  Frame range: {}".format(result['frame_range']))
            assert result['frame_count'] == 10, "Expected 10 frames"
            assert result['pattern_key'] == '_####.ext', "Wrong pattern detected"
        else:
            print("✗ FAIL: No sequence detected")
            return False
        
        # TEST 3: Space pattern ( ####.ext)
        print("\n[TEST 3] Space Pattern Detection ( ####.ext)")
        print("-" * 80)
        test_file = os.path.join(test_dirs['space'], 'render 1001.png')
        result = SequenceDetector.detect_sequence(test_file, pattern_key=' ####.ext', auto_detect=True)
        
        if result:
            print("✓ PASS: Detected sequence")
            print("  Base name: {}".format(result['base_name']))
            print("  Frame pattern: {}".format(result['frame_pattern']))
            print("  Frame range: {}".format(result['frame_range']))
            assert result['frame_count'] == 10, "Expected 10 frames"
            assert result['pattern_key'] == ' ####.ext', "Wrong pattern detected"
        else:
            print("✗ FAIL: No sequence detected")
            return False
        
        # TEST 4: Dash pattern (-####.ext)
        print("\n[TEST 4] Dash Pattern Detection (-####.ext)")
        print("-" * 80)
        test_file = os.path.join(test_dirs['dash'], 'shot-1001.jpg')
        result = SequenceDetector.detect_sequence(test_file, pattern_key='-####.ext', auto_detect=True)
        
        if result:
            print("✓ PASS: Detected sequence")
            print("  Base name: {}".format(result['base_name']))
            print("  Frame pattern: {}".format(result['frame_pattern']))
            print("  Frame range: {}".format(result['frame_range']))
            assert result['frame_count'] == 10, "Expected 10 frames"
            assert result['pattern_key'] == '-####.ext', "Wrong pattern detected"
        else:
            print("✗ FAIL: No sequence detected")
            return False
        
        # TEST 5: Single file (should NOT detect sequence)
        print("\n[TEST 5] Single File Detection (should NOT be sequence)")
        print("-" * 80)
        test_file = os.path.join(test_dirs['single'], 'image_1001.exr')
        result = SequenceDetector.detect_sequence(test_file, pattern_key='.####.ext', auto_detect=True)
        
        if result is None:
            print("✓ PASS: Correctly identified as non-sequence")
        else:
            print("✗ FAIL: Incorrectly detected as sequence")
            return False
        
        # TEST 6: Auto-detect (no pattern specified)
        print("\n[TEST 6] Auto-Detect Pattern (no pattern_key specified)")
        print("-" * 80)
        test_file = os.path.join(test_dirs['dot'], 'image.1001.exr')
        result = SequenceDetector.detect_sequence(test_file, pattern_key=None, auto_detect=True)
        
        if result:
            print("✓ PASS: Auto-detected sequence")
            print("  Detected pattern: {}".format(result['pattern_key']))
            assert result['pattern_key'] == '.####.ext', "Wrong pattern auto-detected"
        else:
            print("✗ FAIL: Auto-detect failed")
            return False
        
        # TEST 7: Mixed patterns (should only detect correct one)
        print("\n[TEST 7] Mixed Pattern Handling")
        print("-" * 80)
        test_file = os.path.join(test_dirs['mixed'], 'correct.1001.exr')
        result = SequenceDetector.detect_sequence(test_file, pattern_key='.####.ext', auto_detect=True)
        
        if result:
            print("✓ PASS: Detected only correct pattern files")
            print("  File count: {}".format(result['frame_count']))
            assert result['frame_count'] == 5, "Should only detect 5 files with correct pattern"
        else:
            print("✗ FAIL: Failed to detect sequence")
            return False
        
        # TEST 8: FFmpeg pattern generation
        print("\n[TEST 8] FFmpeg Pattern Path Generation")
        print("-" * 80)
        test_file = os.path.join(test_dirs['dot'], 'image.1001.exr')
        result = SequenceDetector.detect_sequence(test_file, pattern_key='.####.ext', auto_detect=True)
        
        if result:
            ffmpeg_path = SequenceDetector.get_sequence_path(result)
            print("  FFmpeg path: {}".format(ffmpeg_path))
            assert '%04d' in ffmpeg_path, "FFmpeg pattern should contain %04d"
            print("✓ PASS: FFmpeg pattern generated correctly")
        else:
            print("✗ FAIL: No sequence to generate pattern from")
            return False
        
        print("\n" + "="*80)
        print("ALL TESTS PASSED!")
        print("="*80)
        return True
        
    finally:
        # Cleanup
        shutil.rmtree(temp_dir)


if __name__ == '__main__':
    success = test_pattern_detection()
    sys.exit(0 if success else 1)
