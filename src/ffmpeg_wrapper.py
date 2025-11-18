#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FFmpeg Wrapper Module
Handles all media processing using FFmpeg binaries.
Replaces Pillow for preview generation and adds video support.
"""

import os
import sys
import subprocess
import json
import tempfile


class FFmpegWrapper(object):
    """
    Wrapper for FFmpeg, FFprobe, and FFplay operations.
    Provides preview generation, video playback, and media information extraction.
    """
    
    def __init__(self, ffmpeg_bin_path=None):
        """
        Initialize FFmpeg wrapper.
        
        Args:
            ffmpeg_bin_path (str): Path to FFmpeg binaries directory.
                                   Defaults to bin/ffmpeg/bin/ relative to project root.
        """
        if ffmpeg_bin_path is None:
            # Get project root (2 levels up from src/)
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ffmpeg_bin_path = os.path.join(project_root, 'bin', 'ffmpeg', 'bin')
        
        self.ffmpeg_path = os.path.join(ffmpeg_bin_path, 'ffmpeg.exe')
        self.ffprobe_path = os.path.join(ffmpeg_bin_path, 'ffprobe.exe')
        self.ffplay_path = os.path.join(ffmpeg_bin_path, 'ffplay.exe')
        
        # Verify binaries exist
        if not os.path.exists(self.ffmpeg_path):
            raise RuntimeError("FFmpeg not found at: {}".format(self.ffmpeg_path))
        if not os.path.exists(self.ffprobe_path):
            raise RuntimeError("FFprobe not found at: {}".format(self.ffprobe_path))
        if not os.path.exists(self.ffplay_path):
            raise RuntimeError("FFplay not found at: {}".format(self.ffplay_path))
    
    def get_media_info(self, filepath):
        """
        Extract media information using ffprobe.
        
        Args:
            filepath (str): Path to media file
            
        Returns:
            dict: Media information including duration, format, codec, resolution
        """
        cmd = [
            self.ffprobe_path,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            filepath
        ]
        
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            data = json.loads(output.decode('utf-8'))
            
            # Extract useful information
            info = {
                'duration': None,
                'width': None,
                'height': None,
                'codec': None,
                'format': None,
                'fps': None,
                'is_video': False,
                'is_image': False
            }
            
            if 'format' in data:
                info['format'] = data['format'].get('format_name', '')
                if 'duration' in data['format']:
                    info['duration'] = float(data['format']['duration'])
            
            if 'streams' in data and len(data['streams']) > 0:
                video_stream = None
                for stream in data['streams']:
                    if stream.get('codec_type') == 'video':
                        video_stream = stream
                        break
                
                if video_stream:
                    info['width'] = video_stream.get('width')
                    info['height'] = video_stream.get('height')
                    info['codec'] = video_stream.get('codec_name')
                    
                    # Detect if video or image
                    if info['duration'] and info['duration'] > 0.1:
                        info['is_video'] = True
                    else:
                        info['is_image'] = True
                    
                    # Extract FPS
                    if 'r_frame_rate' in video_stream:
                        try:
                            num, den = video_stream['r_frame_rate'].split('/')
                            info['fps'] = float(num) / float(den)
                        except:
                            pass
            
            return info
            
        except subprocess.CalledProcessError as e:
            print("FFprobe error: {}".format(str(e)))
            return None
        except Exception as e:
            print("Error parsing media info: {}".format(str(e)))
            return None
    
    def generate_thumbnail(self, input_path, output_path, max_size=512, frame_time=None, threads=4):
        """
        Generate a thumbnail image from video or image file.
        
        Args:
            input_path (str): Source media file
            output_path (str): Output thumbnail path (PNG)
            max_size (int): Maximum dimension in pixels
            frame_time (float): Time in seconds to extract frame (for videos)
                                If None, extracts middle frame
            threads (int): Number of threads for FFmpeg to use
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Get media info to determine middle frame if needed
        if frame_time is None:
            info = self.get_media_info(input_path)
            if info and info.get('is_video') and info.get('duration'):
                frame_time = info['duration'] / 2.0
            else:
                frame_time = 0.0
        
        cmd = [
            self.ffmpeg_path,
            '-threads', str(threads),  # Set thread count
            '-y',  # Overwrite output
            '-ss', str(frame_time),  # Seek to frame
            '-i', input_path,
            '-vframes', '1',  # Extract single frame
            '-vf', 'scale={}:{}:force_original_aspect_ratio=decrease'.format(max_size, max_size),
            '-q:v', '2',  # High quality
            output_path
        ]
        
        try:
            subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            return os.path.exists(output_path)
        except subprocess.CalledProcessError as e:
            print("FFmpeg thumbnail error: {}".format(str(e)))
            return False
        except Exception as e:
            print("Error generating thumbnail: {}".format(str(e)))
            return False
    
    def generate_sequence_thumbnail(self, sequence_pattern, output_path, max_size=512, frame_number=None, threads=4):
        """
        Generate thumbnail from image sequence.
        
        Args:
            sequence_pattern (str): Pattern like "plate.%04d.exr"
            output_path (str): Output thumbnail path (PNG)
            max_size (int): Maximum dimension in pixels
            frame_number (int): Frame number to extract (middle if None)
            threads (int): Number of threads for FFmpeg to use
            
        Returns:
            bool: True if successful, False otherwise
        """
        # For sequences, we need to determine the frame number
        if frame_number is None:
            # Try to detect frame range from pattern
            # For now, use frame 0 as fallback
            frame_number = 0
        
        # Convert pattern to FFmpeg format (e.g., plate.%04d.exr)
        cmd = [
            self.ffmpeg_path,
            '-threads', str(threads),  # Set thread count
            '-y',
            '-start_number', str(frame_number),
            '-i', sequence_pattern,
            '-vframes', '1',
            '-vf', 'scale={}:{}:force_original_aspect_ratio=decrease'.format(max_size, max_size),
            '-q:v', '2',
            output_path
        ]
        
        try:
            subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            return os.path.exists(output_path)
        except subprocess.CalledProcessError as e:
            print("FFmpeg sequence thumbnail error: {}".format(str(e)))
            return False
        except Exception as e:
            print("Error generating sequence thumbnail: {}".format(str(e)))
            return False
    
    def generate_video_preview(self, input_path, output_path, max_size=512, duration=10, threads=4):
        """
        Generate a short video preview (low-res, limited duration).
        
        Args:
            input_path (str): Source video file
            output_path (str): Output preview video (MP4)
            max_size (int): Maximum dimension in pixels
            duration (int): Maximum duration in seconds
            threads (int): Number of threads for FFmpeg to use
            
        Returns:
            bool: True if successful, False otherwise
        """
        cmd = [
            self.ffmpeg_path,
            '-threads', str(threads),  # Set thread count
            '-y',
            '-i', input_path,
            '-t', str(duration),  # Limit duration
            '-vf', 'scale={}:{}:force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2'.format(max_size, max_size),
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '28',  # Lower quality for preview
            '-an',  # No audio
            output_path
        ]
        
        try:
            subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            return os.path.exists(output_path)
        except subprocess.CalledProcessError as e:
            print("FFmpeg video preview error: {}".format(str(e)))
            return False
        except Exception as e:
            print("Error generating video preview: {}".format(str(e)))
            return False
    
    def play_media(self, filepath, loop=False, start_time=0):
        """
        Play media file using FFplay.
        
        Args:
            filepath (str): Path to media file
            loop (bool): Loop playback
            start_time (float): Start time in seconds
            
        Returns:
            subprocess.Popen: Process handle for playback control
        """
        cmd = [
            self.ffplay_path,
            '-autoexit',  # Exit when playback finishes
        ]
        
        if loop:
            cmd.extend(['-loop', '0'])
        
        if start_time > 0:
            cmd.extend(['-ss', str(start_time)])
        
        cmd.append(filepath)
        
        try:
            # Start in background, return process handle
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            return process
        except Exception as e:
            print("Error playing media: {}".format(str(e)))
            return None
    
    def extract_frame(self, input_path, frame_number, output_path):
        """
        Extract a specific frame from video or sequence.
        
        Args:
            input_path (str): Source file or sequence pattern
            frame_number (int): Frame number to extract
            output_path (str): Output image path
            
        Returns:
            bool: True if successful, False otherwise
        """
        cmd = [
            self.ffmpeg_path,
            '-y',
            '-i', input_path,
            '-vf', 'select=eq(n\\,{})'.format(frame_number),
            '-vframes', '1',
            output_path
        ]
        
        try:
            subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            return os.path.exists(output_path)
        except subprocess.CalledProcessError as e:
            print("FFmpeg frame extraction error: {}".format(str(e)))
            return False
        except Exception as e:
            print("Error extracting frame: {}".format(str(e)))
            return False
    
    def get_frame_count(self, filepath):
        """
        Get total frame count from video.
        
        Args:
            filepath (str): Path to video file
            
        Returns:
            int: Frame count or None if error
        """
        cmd = [
            self.ffprobe_path,
            '-v', 'error',
            '-select_streams', 'v:0',
            '-count_packets',
            '-show_entries', 'stream=nb_read_packets',
            '-of', 'csv=p=0',
            filepath
        ]
        
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            return int(output.decode('utf-8').strip())
        except:
            return None
    
    def generate_gif_preview(self, input_path, output_path, max_duration=None, size=256,
                             fps=10, threads=4, start_frame=None, is_sequence=False,
                             sequence_fps=24, max_frames=None, loop_forever=True):
        """
        Generate animated GIF preview from video or sequence.
        
        Args:
            input_path (str): Input video or sequence pattern
            output_path (str): Output GIF path
            max_duration (float or None): Maximum GIF duration in seconds. None = full duration/default limit
            size (int): Target size (width and height) in pixels - maintains aspect ratio with padding
            fps (int): GIF frame rate
            threads (int): Number of threads for FFmpeg to use
            start_frame (int): Starting frame number for sequences (None for videos)
            is_sequence (bool): True if input is an image sequence pattern
            sequence_fps (int): Playback framerate for sequences (applied via -framerate)
            max_frames (int or None): Limit total frames used for palette & GIF generation
            loop_forever (bool): Whether to emit GIFs that loop infinitely (uses -loop 0)
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Generate palette first for better quality GIF
        palette_path = os.path.join(tempfile.gettempdir(), 'palette.png')
        scale_filter = 'scale={0}:-1:flags=lanczos'.format(size)
        sequence_rate = sequence_fps or fps
        start_number = start_frame if (start_frame is not None) else 1
        
        try:
            # Step 1: Generate color palette from source
            # Scale to requested width while letting FFmpeg preserve aspect ratio
            palette_cmd = [
                self.ffmpeg_path,
                '-threads', str(threads),  # Set thread count
                '-y'
            ]
            
            # Add start_number for sequences
            if is_sequence:
                palette_cmd.extend(['-start_number', str(start_number)])
                palette_cmd.extend(['-framerate', str(sequence_rate)])
            elif start_frame is not None:
                palette_cmd.extend(['-ss', str(max(start_frame, 0))])

            palette_cmd.extend(['-i', input_path])
            
            # Add duration limit only if specified
            if max_duration is not None:
                palette_cmd.extend(['-t', str(max_duration)])
            
            if max_frames is not None:
                palette_cmd.extend(['-frames:v', str(max_frames)])
            
            palette_cmd.extend([
                '-vf', 'fps={},{},palettegen'.format(fps, scale_filter),
                palette_path
            ])
            subprocess.check_output(palette_cmd, stderr=subprocess.STDOUT)
            
            # Step 2: Generate GIF using palette with same scaling
            gif_cmd = [
                self.ffmpeg_path,
                '-threads', str(threads),  # Set thread count
                '-y'
            ]
            
            # Add start_number for sequences
            if is_sequence:
                gif_cmd.extend(['-start_number', str(start_number)])
                gif_cmd.extend(['-framerate', str(sequence_rate)])
            elif start_frame is not None:
                gif_cmd.extend(['-ss', str(max(start_frame, 0))])
            
            gif_cmd.extend([
                '-i', input_path,
                '-i', palette_path
            ])
            
            # Add duration limit only if specified
            if max_duration is not None:
                gif_cmd.extend(['-t', str(max_duration)])
            
            if max_frames is not None:
                gif_cmd.extend(['-frames:v', str(max_frames)])
            
            gif_cmd.extend([
                '-filter_complex', 'fps={},{}[x];[x][1:v]paletteuse'.format(
                    fps,
                    scale_filter
                )
            ])
            if loop_forever:
                gif_cmd.extend(['-loop', '0'])
            gif_cmd.append(output_path)
            subprocess.check_output(gif_cmd, stderr=subprocess.STDOUT)
            
            # Cleanup palette
            if os.path.exists(palette_path):
                os.remove(palette_path)
            
            return os.path.exists(output_path)
            
        except subprocess.CalledProcessError as e:
            print("FFmpeg GIF generation error: {}".format(str(e)))
            if os.path.exists(palette_path):
                os.remove(palette_path)
            return False
        except Exception as e:
            print("Error generating GIF preview: {}".format(str(e)))
            if os.path.exists(palette_path):
                os.remove(palette_path)
            return False
    
    def convert_sequence_to_video(self, sequence_pattern, output_path, fps=24, start_frame=1):
        """
        Convert image sequence to video file.
        
        Args:
            sequence_pattern (str): Pattern like "plate.%04d.exr"
            output_path (str): Output video path (MP4)
            fps (int): Frames per second
            start_frame (int): Starting frame number
            
        Returns:
            bool: True if successful, False otherwise
        """
        cmd = [
            self.ffmpeg_path,
            '-y',
            '-start_number', str(start_frame),
            '-framerate', str(fps),
            '-i', sequence_pattern,
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '18',
            '-pix_fmt', 'yuv420p',
            output_path
        ]
        
        try:
            subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            return os.path.exists(output_path)
        except subprocess.CalledProcessError as e:
            print("FFmpeg sequence conversion error: {}".format(str(e)))
            return False
        except Exception as e:
            print("Error converting sequence: {}".format(str(e)))
            return False
    
    def generate_sequence_video_preview(self, sequence_pattern, output_path, max_size=512, fps=24, start_frame=1, max_frames=None):
        """
        Generate low-res video preview from image sequence.
        
        Args:
            sequence_pattern (str): Pattern like "plate.%04d.exr"
            output_path (str): Output MP4 video path
            max_size (int): Maximum dimension in pixels (width or height)
            fps (int): Frames per second for preview video
            start_frame (int): Starting frame number
            max_frames (int): Maximum number of frames to include (None = all frames)
            
        Returns:
            bool: True if successful, False otherwise
        """
        cmd = [
            self.ffmpeg_path,
            '-y',
            '-start_number', str(start_frame),
            '-framerate', str(fps),
            '-i', sequence_pattern
        ]
        
        # Add frame limit if specified
        if max_frames:
            cmd.extend(['-frames:v', str(max_frames)])
        
        # Add scaling and encoding options with padding to ensure even dimensions (required by libx264)
        cmd.extend([
            '-vf', 'scale={}:{}:force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2'.format(max_size, max_size),
            '-c:v', 'libx264',
            '-preset', 'fast',  # Fast encoding for previews
            '-crf', '28',  # Lower quality for smaller files
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',  # Enable web streaming
            output_path
        ])
        
        try:
            subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            return os.path.exists(output_path)
        except subprocess.CalledProcessError as e:
            print("FFmpeg sequence video preview error: {}".format(str(e)))
            return False
        except Exception as e:
            print("Error generating sequence video preview: {}".format(str(e)))
            return False


# Singleton instance
_ffmpeg_instance = None

def get_ffmpeg():
    """Get or create FFmpeg wrapper singleton."""
    global _ffmpeg_instance
    if _ffmpeg_instance is None:
        _ffmpeg_instance = FFmpegWrapper()
    return _ffmpeg_instance
