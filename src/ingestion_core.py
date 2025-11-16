# -*- coding: utf-8 -*-
"""
Ingestion Core for StaX
Handles file operations, sequence detection, metadata extraction, and preview generation
Python 2.7 compatible
"""

import os
import re
import shutil
import hashlib
from src.ffmpeg_wrapper import get_ffmpeg


class SequenceDetector(object):
    """Detects and parses image sequences."""
    
    # Pattern for frame numbers: filename.####.ext or filename_####.ext
    FRAME_PATTERN = re.compile(r'^(.+?)[\._](\d{4,})(\.\w+)$')
    
    @staticmethod
    def detect_sequence(filepath):
        """
        Detect if a file is part of a sequence and find all frames.
        
        Args:
            filepath (str): Path to a single file
            
        Returns:
            dict: Sequence info or None if not a sequence
                {
                    'base_name': str,
                    'frame_pattern': str,  # e.g., 'shot_####.exr'
                    'files': list,
                    'frame_range': str,    # e.g., '1001-1150'
                    'first_frame': int,
                    'last_frame': int,
                    'padding': int
                }
        """
        directory = os.path.dirname(filepath)
        filename = os.path.basename(filepath)
        
        match = SequenceDetector.FRAME_PATTERN.match(filename)
        if not match:
            return None
        
        base_name = match.group(1)
        frame_num = match.group(2)
        extension = match.group(3)
        padding = len(frame_num)
        
        # Search for all files matching pattern
        sequence_files = []
        frame_numbers = []
        
        for item in os.listdir(directory):
            item_match = SequenceDetector.FRAME_PATTERN.match(item)
            if item_match:
                item_base = item_match.group(1)
                item_frame = item_match.group(2)
                item_ext = item_match.group(3)
                
                if (item_base == base_name and 
                    item_ext == extension and 
                    len(item_frame) == padding):
                    full_path = os.path.join(directory, item)
                    sequence_files.append(full_path)
                    frame_numbers.append(int(item_frame))
        
        if len(sequence_files) <= 1:
            return None
        
        frame_numbers.sort()
        frame_pattern = "{}{}{}.{}".format(
            base_name,
            '.' if '.' in filename else '_',
            '#' * padding,
            extension.lstrip('.')
        )
        
        return {
            'base_name': base_name,
            'frame_pattern': frame_pattern,
            'files': sorted(sequence_files),
            'frame_range': '{}-{}'.format(frame_numbers[0], frame_numbers[-1]),
            'first_frame': frame_numbers[0],
            'last_frame': frame_numbers[-1],
            'padding': padding,
            'extension': extension
        }
    
    @staticmethod
    def get_sequence_path(sequence_info):
        """
        Get the sequence path with frame padding pattern.
        
        Args:
            sequence_info (dict): Sequence info from detect_sequence
            
        Returns:
            str: Path with frame padding (e.g., '/path/shot.####.exr')
        """
        if not sequence_info or 'files' not in sequence_info:
            return None
        
        first_file = sequence_info['files'][0]
        directory = os.path.dirname(first_file)
        return os.path.join(directory, sequence_info['frame_pattern'])


class MetadataExtractor(object):
    """Extracts metadata from media files."""
    
    IMAGE_FORMATS = ['.exr', '.dpx', '.tif', '.tiff', '.jpg', '.jpeg', '.png', '.tga']
    VIDEO_FORMATS = ['.mov', '.mp4', '.avi', '.mxf']
    GEO_FORMATS = ['.abc', '.obj', '.fbx', '.usd', '.usda', '.usdc']
    
    @staticmethod
    def get_asset_type(filepath):
        """
        Determine asset type from file extension.
        
        Args:
            filepath (str): File path
            
        Returns:
            str: '2D', '3D', or 'Toolset'
        """
        ext = os.path.splitext(filepath)[1].lower()
        
        if ext == '.nk':
            return 'Toolset'
        elif ext in MetadataExtractor.GEO_FORMATS:
            return '3D'
        elif ext in MetadataExtractor.IMAGE_FORMATS or ext in MetadataExtractor.VIDEO_FORMATS:
            return '2D'
        else:
            return '2D'  # Default
    
    @staticmethod
    def get_file_size(filepath):
        """Get file size in bytes."""
        try:
            return os.path.getsize(filepath)
        except OSError:
            return 0
    
    @staticmethod
    def get_sequence_size(sequence_files):
        """Get total size of sequence files."""
        total = 0
        for f in sequence_files:
            total += MetadataExtractor.get_file_size(f)
        return total
    
    @staticmethod
    def get_image_info(filepath):
        """
        Get image dimensions and format using FFmpeg.
        
        Args:
            filepath (str): Image file path
            
        Returns:
            dict: {'width': int, 'height': int, 'format': str}
        """
        try:
            ffmpeg = get_ffmpeg()
            info = ffmpeg.get_media_info(filepath)
            if info:
                return {
                    'width': info.get('width'),
                    'height': info.get('height'),
                    'format': info.get('format')
                }
            return None
        except Exception:
            return None


class PreviewGenerator(object):
    """Generates preview thumbnails for assets using FFmpeg."""
    
    PREVIEW_SIZE = 512
    
    @staticmethod
    def generate_image_preview(source_path, preview_path):
        """
        Generate thumbnail for image file using FFmpeg.
        
        Args:
            source_path (str): Source image path
            preview_path (str): Output preview path (PNG)
            
        Returns:
            bool: True if successful
        """
        try:
            # Ensure preview directory exists
            preview_dir = os.path.dirname(preview_path)
            if not os.path.exists(preview_dir):
                os.makedirs(preview_dir)
            
            # Ensure output is PNG
            if not preview_path.lower().endswith('.png'):
                preview_path = os.path.splitext(preview_path)[0] + '.png'
            
            ffmpeg = get_ffmpeg()
            return ffmpeg.generate_thumbnail(source_path, preview_path, PreviewGenerator.PREVIEW_SIZE)
        except Exception as e:
            print("Preview generation failed: {}".format(e))
            return False
    
    @staticmethod
    def generate_sequence_preview(sequence_files, preview_path):
        """
        Generate preview from middle frame of sequence using FFmpeg.
        
        Args:
            sequence_files (list): List of sequence file paths
            preview_path (str): Output preview path (PNG)
            
        Returns:
            bool: True if successful
        """
        if not sequence_files:
            return False
        
        # Use middle frame
        middle_index = len(sequence_files) // 2
        middle_frame = sequence_files[middle_index]
        
        return PreviewGenerator.generate_image_preview(middle_frame, preview_path)
    
    @staticmethod
    def generate_sequence_video_preview(sequence_info, output_path, max_size=512, fps=24):
        """
        Generate low-res video preview from image sequence.
        
        Args:
            sequence_info (dict): Sequence info from SequenceDetector with 'pattern', 'start_frame', etc.
            output_path (str): Output MP4 path
            max_size (int): Maximum dimension in pixels
            fps (int): Frames per second
            
        Returns:
            bool: True if successful
        """
        try:
            # Ensure preview directory exists
            preview_dir = os.path.dirname(output_path)
            if not os.path.exists(preview_dir):
                os.makedirs(preview_dir)
            
            # Get sequence pattern from sequence_info
            sequence_pattern = SequenceDetector.get_sequence_path(sequence_info)
            start_frame = sequence_info.get('start_frame', 1)
            frame_count = sequence_info.get('frame_count', 0)
            
            # Limit to first 100 frames for preview (about 4 seconds at 24fps)
            max_frames = min(frame_count, 100) if frame_count > 0 else None
            
            ffmpeg = get_ffmpeg()
            return ffmpeg.generate_sequence_video_preview(
                sequence_pattern,
                output_path,
                max_size=max_size,
                fps=fps,
                start_frame=start_frame,
                max_frames=max_frames
            )
        except Exception as e:
            print("Sequence video preview generation failed: {}".format(e))
            return False
    
    @staticmethod
    def generate_video_preview(source_path, preview_path):
        """
        Generate video preview using FFmpeg.
        
        Args:
            source_path (str): Source video path
            preview_path (str): Output preview path (MP4 or PNG for thumbnail)
            
        Returns:
            bool: True if successful
        """
        try:
            # Ensure preview directory exists
            preview_dir = os.path.dirname(preview_path)
            if not os.path.exists(preview_dir):
                os.makedirs(preview_dir)
            
            ffmpeg = get_ffmpeg()
            
            # For thumbnails, extract middle frame as PNG
            if preview_path.lower().endswith('.png'):
                return ffmpeg.generate_thumbnail(source_path, preview_path, PreviewGenerator.PREVIEW_SIZE)
            # For video previews, generate short MP4
            else:
                return ffmpeg.generate_video_preview(source_path, preview_path, PreviewGenerator.PREVIEW_SIZE)
        except Exception as e:
            print("Video preview generation failed: {}".format(e))
            return False


class IngestionCore(object):
    """
    Core ingestion engine for StaX.
    Handles file operations, metadata extraction, and preview generation.
    """
    
    def __init__(self, db_manager, config):
        """
        Initialize ingestion core.
        
        Args:
            db_manager: DatabaseManager instance
            config (dict): Configuration dictionary
        """
        self.db = db_manager
        self.config = config
        self.preview_dir = config.get('preview_dir', './previews')
        
        # Ensure preview directory exists
        if not os.path.exists(self.preview_dir):
            try:
                # Convert relative path to absolute to avoid permission issues in Nuke
                if not os.path.isabs(self.preview_dir):
                    # Get the root directory (where the main script is located)
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    root_dir = os.path.dirname(script_dir)  # Go up from src/
                    abs_preview_dir = os.path.join(root_dir, self.preview_dir)
                else:
                    abs_preview_dir = self.preview_dir
                
                print("[IngestionCore] Creating preview directory: {}".format(abs_preview_dir))
                os.makedirs(abs_preview_dir)
                print("[IngestionCore]   [OK] Preview directory created")
                
                # Update preview_dir to use absolute path
                self.preview_dir = abs_preview_dir
                print("[IngestionCore] Using absolute preview path: {}".format(self.preview_dir))
            except OSError as e:
                print("[IngestionCore]   [WARN] Failed to create preview directory: {}".format(e))
                # Try to use absolute path anyway
                if not os.path.isabs(self.preview_dir):
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    root_dir = os.path.dirname(script_dir)
                    self.preview_dir = os.path.join(root_dir, self.preview_dir)
    
    def ingest_file(self, source_path, target_list_id, copy_policy='soft', 
                    comment=None, tags=None, pre_hook=None, post_hook=None):
        """
        Ingest a single file or sequence into the database.
        
        Args:
            source_path (str): Source file path
            target_list_id (int): Target list ID
            copy_policy (str): 'soft' or 'hard'
            comment (str): Optional comment
            tags (str): Optional comma-separated tags
            pre_hook (callable): Optional pre-ingestion hook function
            post_hook (callable): Optional post-ingestion hook function
            
        Returns:
            dict: Result with 'success', 'element_id', 'message'
        """
        # Validate source
        if not os.path.exists(source_path):
            return {'success': False, 'message': 'Source file does not exist'}
        
        # Get target list info
        target_list = self.db.get_list_by_id(target_list_id)
        if not target_list:
            return {'success': False, 'message': 'Target list not found'}
        
        # Get stack for repository path
        stack = self.db.get_stack_by_id(target_list['stack_fk'])
        if not stack:
            return {'success': False, 'message': 'Stack not found'}
        
        try:
            # Detect sequence
            sequence_info = SequenceDetector.detect_sequence(source_path)
            
            # Determine paths and metadata
            if sequence_info:
                # This is a sequence
                name = sequence_info['base_name']
                frame_range = sequence_info['frame_range']
                files_to_process = sequence_info['files']
                is_sequence = True
                
                # Use sequence path pattern
                filepath_soft = SequenceDetector.get_sequence_path(sequence_info)
            else:
                # Single file
                name = os.path.splitext(os.path.basename(source_path))[0]
                frame_range = None
                files_to_process = [source_path]
                is_sequence = False
                filepath_soft = source_path
            
            # Extract metadata
            asset_type = MetadataExtractor.get_asset_type(source_path)
            file_format = os.path.splitext(source_path)[1]
            
            if is_sequence:
                file_size = MetadataExtractor.get_sequence_size(files_to_process)
            else:
                file_size = MetadataExtractor.get_file_size(source_path)
            
            # Execute pre-ingestion hook
            if pre_hook:
                hook_result = pre_hook({
                    'source_path': source_path,
                    'name': name,
                    'type': asset_type,
                    'is_sequence': is_sequence,
                    'files': files_to_process
                })
                if not hook_result.get('continue', True):
                    return {'success': False, 'message': hook_result.get('message', 'Pre-hook cancelled')}
            
            # Handle copy policy
            is_hard_copy = (copy_policy == 'hard')
            filepath_hard = None
            
            if is_hard_copy:
                # Create target directory in stack
                target_dir = os.path.join(stack['path'], target_list['name'], name)
                if not os.path.exists(target_dir):
                    os.makedirs(target_dir)
                
                # Copy files
                for src_file in files_to_process:
                    filename = os.path.basename(src_file)
                    dest_file = os.path.join(target_dir, filename)
                    shutil.copy2(src_file, dest_file)
                
                # Set hard copy path
                if is_sequence:
                    filepath_hard = os.path.join(target_dir, sequence_info['frame_pattern'])
                else:
                    filepath_hard = os.path.join(target_dir, os.path.basename(source_path))
            
            # Generate preview
            preview_filename = "{}_{}.jpg".format(
                target_list_id,
                hashlib.md5(name.encode('utf-8')).hexdigest()[:8]
            )
            preview_path = os.path.join(self.preview_dir, preview_filename)
            
            if is_sequence:
                PreviewGenerator.generate_sequence_preview(files_to_process, preview_path)
            else:
                if asset_type == '2D':
                    PreviewGenerator.generate_image_preview(source_path, preview_path)
            
            # Generate animated GIF preview for videos and sequences
            gif_preview_path = None
            
            # Check if it's a video file
            is_video = file_format.lower() in ['.mp4', '.mov', '.avi', '.mkv', '.mpg', '.mpeg', '.wmv', '.flv']
            
            if is_video or (is_sequence and asset_type == '2D'):
                print("[GIF] Generating GIF preview for {} (type: {}, is_video: {}, is_sequence: {})".format(
                    name, asset_type, is_video, is_sequence))
                gif_filename = "{}_{}.gif".format(
                    target_list_id,
                    hashlib.md5(name.encode('utf-8')).hexdigest()[:8]
                )
                gif_preview_path = os.path.join(self.preview_dir, gif_filename)
                print("[GIF] Output path: {}".format(gif_preview_path))
                
                # Determine input path for FFmpeg
                if is_sequence:
                    # Use sequence pattern
                    input_for_gif = SequenceDetector.get_sequence_path(sequence_info)
                    print("[GIF] Input (sequence): {}".format(input_for_gif))
                else:
                    # Use video file
                    input_for_gif = source_path
                    print("[GIF] Input (video): {}".format(input_for_gif))
                
                # Generate GIF (3 seconds, 256x256px square, 10fps)
                from src.ffmpeg_wrapper import get_ffmpeg
                ffmpeg = get_ffmpeg()
                print("[GIF] Calling FFmpeg generate_gif_preview...")
                gif_success = ffmpeg.generate_gif_preview(
                    input_for_gif, 
                    gif_preview_path,
                    max_duration=3.0,
                    size=256,
                    fps=10
                )
                
                if gif_success:
                    print("[GIF] ✓ GIF generated successfully: {}".format(gif_preview_path))
                else:
                    print("[GIF] ✗ GIF generation failed")
                    gif_preview_path = None
            else:
                print("[GIF] Skipping GIF generation for {} (type: {}, format: {})".format(
                    name, asset_type, file_format))
            
            # Generate low-res video preview for sequences (MP4)
            video_preview_path = None
            if is_sequence and asset_type == '2D':
                print("[VIDEO] Generating video preview for sequence: {}".format(name))
                video_filename = "{}_{}.mp4".format(
                    target_list_id,
                    hashlib.md5(name.encode('utf-8')).hexdigest()[:8]
                )
                video_preview_path = os.path.join(self.preview_dir, video_filename)
                print("[VIDEO] Output path: {}".format(video_preview_path))
                
                # Generate low-res MP4 preview (~512px, first 100 frames or 4 seconds)
                video_success = PreviewGenerator.generate_sequence_video_preview(
                    sequence_info,
                    video_preview_path,
                    max_size=512,
                    fps=24
                )
                
                if video_success:
                    print("[VIDEO] ✓ Video preview generated successfully: {}".format(video_preview_path))
                else:
                    print("[VIDEO] ✗ Video preview generation failed")
                    video_preview_path = None
            
            # Create element in database
            element_id = self.db.create_element(
                list_id=target_list_id,
                name=name,
                element_type=asset_type,
                filepath_soft=filepath_soft,
                filepath_hard=filepath_hard,
                is_hard_copy=is_hard_copy,
                frame_range=frame_range,
                format=file_format,
                comment=comment,
                tags=tags,
                preview_path=preview_path if os.path.exists(preview_path) else None,
                gif_preview_path=gif_preview_path,
                video_preview_path=video_preview_path,
                file_size=file_size
            )
            
            # Log ingestion
            self.db.log_ingestion(
                action='ingest',
                source_path=source_path,
                target_list=target_list['name'],
                status='success',
                message='Ingested as {}'.format('hard copy' if is_hard_copy else 'soft copy'),
                element_id=element_id
            )
            
            # Execute post-ingestion hook
            if post_hook:
                post_hook({
                    'element_id': element_id,
                    'name': name,
                    'type': asset_type,
                    'filepath_soft': filepath_soft,
                    'filepath_hard': filepath_hard
                })
            
            return {
                'success': True,
                'element_id': element_id,
                'message': 'Successfully ingested {}'.format(name),
                'is_sequence': is_sequence,
                'frame_range': frame_range
            }
            
        except Exception as e:
            error_msg = 'Ingestion failed: {}'.format(str(e))
            
            # Log error
            self.db.log_ingestion(
                action='ingest',
                source_path=source_path,
                target_list=target_list['name'],
                status='error',
                message=error_msg
            )
            
            return {'success': False, 'message': error_msg}
    
    def ingest_multiple(self, source_paths, target_list_id, **kwargs):
        """
        Ingest multiple files.
        
        Args:
            source_paths (list): List of source file paths
            target_list_id (int): Target list ID
            **kwargs: Additional arguments for ingest_file
            
        Returns:
            list: List of ingestion results
        """
        results = []
        for source_path in source_paths:
            result = self.ingest_file(source_path, target_list_id, **kwargs)
            results.append(result)
        return results
    
    def ingest_folder(self, folder_path, target_list_id, recursive=False, **kwargs):
        """
        Ingest all files from a folder.
        
        Args:
            folder_path (str): Folder path
            target_list_id (int): Target list ID
            recursive (bool): Recursively process subfolders
            **kwargs: Additional arguments for ingest_file
            
        Returns:
            list: List of ingestion results
        """
        results = []
        
        if recursive:
            for root, dirs, files in os.walk(folder_path):
                for filename in files:
                    filepath = os.path.join(root, filename)
                    result = self.ingest_file(filepath, target_list_id, **kwargs)
                    results.append(result)
        else:
            for filename in os.listdir(folder_path):
                filepath = os.path.join(folder_path, filename)
                if os.path.isfile(filepath):
                    result = self.ingest_file(filepath, target_list_id, **kwargs)
                    results.append(result)
        
        return results
