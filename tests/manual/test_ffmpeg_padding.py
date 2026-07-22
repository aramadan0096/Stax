# -*- coding: utf-8 -*-
"""
Test FFmpeg video generation with padding filter
"""
import sys
import os

sys.path.insert(0, r'E:\Scripts\Stax')

from src.ffmpeg_wrapper import get_ffmpeg

# Test sequence video generation
ffmpeg = get_ffmpeg()

sequence_pattern = r'E:\Temp\colorwgeel\imgs\3\img.%04d.png'
output_path = r'E:\Temp\test_video_with_padding.mp4'

print("="*60)
print("FFMPEG VIDEO GENERATION TEST")
print("="*60)
print("Input pattern: {}".format(sequence_pattern))
print("Output: {}".format(output_path))
print("Testing video generation with padding filter...")
print("="*60)

# Clean up old output if exists
if os.path.exists(output_path):
    os.remove(output_path)
    print("Removed old output file")

# Generate video with new padding logic
success = ffmpeg.generate_sequence_video_preview(
    sequence_pattern=sequence_pattern,
    output_path=output_path,
    max_size=512,
    fps=24,
    start_frame=15,
    max_frames=12
)

print("="*60)
if success and os.path.exists(output_path):
    file_size = os.path.getsize(output_path)
    print("✓ SUCCESS - Video generated")
    print("  File: {}".format(output_path))
    print("  Size: {:.2f} KB".format(file_size / 1024.0))
else:
    print("✗ FAILED - Video generation failed")
print("="*60)
