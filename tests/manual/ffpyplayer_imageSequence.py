# from ffpyplayer.player import MediaPlayer
import ffpyplayer
# Path to your image sequence (e.g., 'frames/frame%04d.png')
# %04d means a 4-digit number with leading zeros
image_sequence_path = 'E:\\Temp\\footage\\exr\\v6\\v6.%04d.exr'

# Create a MediaPlayer instance
player = ffpyplayer.player.MediaPlayer(image_sequence_path)
# .MediaPlayer(image_sequence_path)