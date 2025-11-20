# -*- coding: utf-8 -*-
"""
Test script for ffpyplayer image sequence playback
Tests that ffpyplayer can open and play image sequences using pattern notation
"""
import time
from ffpyplayer.player import MediaPlayer

# Path to your image sequence (e.g., 'frames/frame%04d.png')
# %04d means a 4-digit number with leading zeros
image_sequence_path = 'E:\\Temp\\footage\\exr\\v6\\v6.%04d.exr'

print("Testing ffpyplayer with image sequence pattern: {}".format(image_sequence_path))
print("Creating MediaPlayer...")

# Create a MediaPlayer instance with the sequence pattern
try:
    player = MediaPlayer(image_sequence_path)
    print("SUCCESS: MediaPlayer created for image sequence")
    
    # Try to get metadata
    metadata = player.get_metadata()
    print("Metadata: {}".format(metadata))
    
    # Try to get a few frames
    print("\nFetching first 5 frames...")
    for i in range(5):
        frame, val = player.get_frame()
        if frame:
            img, pts = frame
            print("Frame {}: pts={:.3f}, size={}, format={}".format(
                i, pts, img.get_size(), img.get_pixel_format()
            ))
        elif val == 'eof':
            print("Reached end of sequence")
            break
        else:
            print("Frame not ready, waiting...")
            time.sleep(0.01)
    
    # Clean up
    player.close_player()
    print("\nTest completed successfully!")
    
except Exception as e:
    print("ERROR: Failed to create MediaPlayer: {}".format(e))
    import traceback
    traceback.print_exc()