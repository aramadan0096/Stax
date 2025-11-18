# -*- coding: utf-8 -*-
"""
Test GIF generation with non-standard start frame
"""
import sys
import os

sys.path.insert(0, r'E:\Scripts\Stax')

from src.ffmpeg_wrapper import get_ffmpeg
from src.ingestion_core import SequenceDetector

# Test sequence that starts at frame 8 (not frame 1)
test_file = r'E:\Temp\colorwgeel\imgs\2\img.0008.png'

print("="*60)
print("GIF GENERATION TEST (NON-STANDARD START FRAME)")
print("="*60)

# Detect sequence
print("\n1. Detecting sequence...")
sequence_info = SequenceDetector.detect_sequence(test_file, pattern_key=None, auto_detect=True)

if not sequence_info:
    print("✗ Failed to detect sequence")
    sys.exit(1)

print("✓ Sequence detected:")
print("  Pattern: {}".format(sequence_info['frame_pattern']))
print("  Frame range: {}".format(sequence_info['frame_range']))
print("  Start frame: {}".format(sequence_info['first_frame']))
print("  Frame count: {}".format(sequence_info['frame_count']))

# Get FFmpeg pattern
sequence_pattern = SequenceDetector.get_sequence_path(sequence_info)
print("  FFmpeg pattern: {}".format(sequence_pattern))

# Generate GIF
print("\n2. Generating GIF with start_frame={}...".format(sequence_info['first_frame']))
output_path = r'E:\Temp\test_gif_startframe.gif'

if os.path.exists(output_path):
    os.remove(output_path)

ffmpeg = get_ffmpeg()
success = ffmpeg.generate_gif_preview(
    sequence_pattern,
    output_path,
    max_duration=3.0,
    size=256,
    fps=10,
    start_frame=sequence_info['first_frame'],
    is_sequence=True,
    sequence_fps=24,
    max_frames=12,
    loop_forever=True
)

print("="*60)
if success and os.path.exists(output_path):
    file_size = os.path.getsize(output_path)
    print("✓ SUCCESS - GIF generated")
    print("  File: {}".format(output_path))
    print("  Size: {:.2f} KB".format(file_size / 1024.0))
else:
    print("✗ FAILED - GIF generation failed")
print("="*60)
