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
import subprocess
import time
from src.ffmpeg_wrapper import get_ffmpeg
from src.glb_converter import (
    convert_to_glb,
    SUPPORTED_GEOMETRY_EXTS,
    find_blender_executable,
    BLENDER_SCRIPT_PATH,
)


class SequenceDetector(object):
    """Detects and parses image sequences based on configurable patterns."""

    DEFAULT_PATTERN = '.####.ext'
    PATTERN_MAP = {
        '.####.ext': {
            'regex': re.compile(r'^(.+)\.(\d+)(\.\w+)$', re.IGNORECASE),
            'separator': '.'
        },
        '_####.ext': {
            'regex': re.compile(r'^(.+)_([0-9]+)(\.\w+)$', re.IGNORECASE),
            'separator': '_'
        },
        ' ####.ext': {
            'regex': re.compile(r'^(.+)\s(\d+)(\.\w+)$', re.IGNORECASE),
            'separator': ' '
        },
        '-####.ext': {
            'regex': re.compile(r'^(.+)-(\d+)(\.\w+)$', re.IGNORECASE),
            'separator': '-'
        }
    }
    PATTERN_ORDER = ['.####.ext', '_####.ext', ' ####.ext', '-####.ext']

    @classmethod
    def _get_pattern_info(cls, pattern_key):
        return cls.PATTERN_MAP.get(pattern_key, cls.PATTERN_MAP[cls.DEFAULT_PATTERN])

    @classmethod
    def detect_sequence(cls, filepath, pattern_key=None, auto_detect=True):
        """Detect if a file belongs to a sequence respecting the configured pattern."""
        if not auto_detect or not filepath:
            return None

        filepath = os.path.normpath(filepath)
        directory = os.path.dirname(filepath)
        if not directory or not os.path.isdir(directory):
            return None

        filename = os.path.basename(filepath)

        if pattern_key and pattern_key in cls.PATTERN_MAP:
            candidate_patterns = [pattern_key]
        elif pattern_key:
            candidate_patterns = [cls.DEFAULT_PATTERN]
        else:
            candidate_patterns = cls.PATTERN_ORDER

        for candidate in candidate_patterns:
            pattern_info = cls._get_pattern_info(candidate)
            regex = pattern_info['regex']

            match = regex.match(filename)
            if not match:
                continue

            base_name = match.group(1).rstrip()
            frame_num = match.group(2)
            extension = match.group(3)
            padding = len(frame_num)

            sequence_files = []
            frame_numbers = []

            try:
                directory_listing = os.listdir(directory)
            except OSError:
                return None

            for item in directory_listing:
                item_match = regex.match(item)
                if not item_match:
                    continue

                item_base = item_match.group(1).rstrip()
                item_digits = item_match.group(2)
                item_ext = item_match.group(3)

                if item_base == base_name and item_ext.lower() == extension.lower():
                    full_path = os.path.normpath(os.path.join(directory, item))
                    sequence_files.append(full_path)
                    try:
                        frame_numbers.append(int(item_digits))
                    except ValueError:
                        continue

            if len(sequence_files) <= 1:
                continue

            paired = sorted(zip(frame_numbers, sequence_files), key=lambda pair: pair[0])
            frame_numbers = [pair[0] for pair in paired]
            sequence_files = [pair[1] for pair in paired]

            frame_pattern = "{}{}{}{}".format(
                base_name,
                pattern_info['separator'],
                '#' * padding,
                extension
            )
            ffmpeg_pattern = "{}{}%0{}d{}".format(
                base_name,
                pattern_info['separator'],
                padding,
                extension
            )

            return {
                'base_name': base_name,
                'frame_pattern': frame_pattern,
                'ffmpeg_pattern': ffmpeg_pattern,
                'files': sequence_files,
                'frame_range': '{}-{}'.format(frame_numbers[0], frame_numbers[-1]),
                'first_frame': frame_numbers[0],
                'last_frame': frame_numbers[-1],
                'start_frame': frame_numbers[0],
                'padding': padding,
                'extension': extension,
                'separator': pattern_info['separator'],
                'pattern_key': candidate,
                'frame_count': len(sequence_files)
            }

        return None

    @staticmethod
    def get_sequence_path(sequence_info):
        """Build the padded pattern path for a detected sequence."""
        if not sequence_info or not sequence_info.get('files'):
            return None

        directory = os.path.dirname(sequence_info['files'][0])
        ffmpeg_pattern = sequence_info.get('ffmpeg_pattern')
        if ffmpeg_pattern:
            return os.path.join(directory, ffmpeg_pattern)

        base_name = sequence_info.get('base_name', '')
        separator = sequence_info.get('separator', '.')
        padding = sequence_info.get('padding', 4)
        extension = sequence_info.get('extension', '')
        frame_pattern = "{}{}%0{}d{}".format(base_name, separator, padding, extension)
        return os.path.join(directory, frame_pattern)


class MetadataExtractor(object):
    """Extracts metadata from media files."""
    
    IMAGE_FORMATS = ['.exr', '.dpx', '.tif', '.tiff', '.jpg', '.jpeg', '.png', '.tga']
    VIDEO_FORMATS = ['.mov', '.mp4', '.avi', '.mxf']
    GEO_FORMATS = ['.abc', '.obj', '.fbx', '.usd', '.usda', '.usdc', '.glb', '.gltf']
    
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
    def generate_image_preview(source_path, preview_path, max_size=None):
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
            
            target_size = max_size or PreviewGenerator.PREVIEW_SIZE
            ffmpeg = get_ffmpeg()
            return ffmpeg.generate_thumbnail(source_path, preview_path, target_size)
        except Exception as e:
            print("Preview generation failed: {}".format(e))
            return False
    
    @staticmethod
    def generate_sequence_preview(sequence_files, preview_path, max_size=None):
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
        
        return PreviewGenerator.generate_image_preview(middle_frame, preview_path, max_size=max_size)
    
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
        # Use previews_path if available, fallback to preview_dir for backward compatibility
        self.preview_dir = config.get('previews_path', config.get('preview_dir', './previews'))
        self.auto_detect_sequences = config.get('auto_detect_sequences', True)
        self.sequence_pattern = config.get('sequence_pattern', SequenceDetector.DEFAULT_PATTERN)
        if self.sequence_pattern not in SequenceDetector.PATTERN_MAP:
            self.sequence_pattern = SequenceDetector.DEFAULT_PATTERN
        
        # Convert relative path to absolute
        if not os.path.isabs(self.preview_dir):
            script_dir = os.path.dirname(os.path.abspath(__file__))
            root_dir = os.path.dirname(script_dir)  # Go up from src/
            self.preview_dir = os.path.join(root_dir, self.preview_dir)
        self.preview_dir = os.path.normpath(self.preview_dir)
        
        # Ensure preview directory exists
        if not os.path.exists(self.preview_dir):
            try:
                print("[IngestionCore] Creating preview directory: {}".format(self.preview_dir))
                os.makedirs(self.preview_dir)
                print("[IngestionCore]   [OK] Preview directory created")
            except OSError as e:
                print("[IngestionCore]   [ERROR] Failed to create preview directory: {}".format(e))
                print("[IngestionCore]   This may cause preview generation to fail!")
        
        print("[IngestionCore] Using preview path: {}".format(self.preview_dir))
        self._refresh_sequence_preferences()

    def _refresh_sequence_preferences(self):
        """Sync runtime sequence detection settings with current configuration."""
        self.auto_detect_sequences = self.config.get('auto_detect_sequences', True)
        pattern_choice = self.config.get('sequence_pattern', SequenceDetector.DEFAULT_PATTERN)
        if pattern_choice not in SequenceDetector.PATTERN_MAP:
            pattern_choice = SequenceDetector.DEFAULT_PATTERN
        self.sequence_pattern = pattern_choice
        return self.auto_detect_sequences, self.sequence_pattern

    def _log_geometry_progress(self, notes, message):
        if message:
            notes.append(message)
            print("[GLB] {}".format(message))

    def _resolve_blender_script_path(self):
        candidate = BLENDER_SCRIPT_PATH if os.path.exists(BLENDER_SCRIPT_PATH) else None
        if candidate:
            return candidate
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        fallback = os.path.join(root_dir, 'dependencies', 'blender', 'convert_to_glb.py')
        fallback = os.path.normpath(fallback)
        if os.path.exists(fallback):
            return fallback
        return None

    def _run_blender_cli_conversion(self, source_path, output_path, blender_override, notes):
        blender_exec = find_blender_executable(blender_override)
        if not blender_exec:
            message = 'Blender executable not found. Set Blender Path in Settings -> Ingestion.'
            self._log_geometry_progress(notes, message)
            return False, message

        script_path = self._resolve_blender_script_path()
        if not script_path:
            message = 'Blender conversion script missing; reinstall dependencies/blender/convert_to_glb.py.'
            self._log_geometry_progress(notes, message)
            return False, message

        dest_dir = os.path.dirname(output_path)
        if dest_dir and not os.path.exists(dest_dir):
            try:
                os.makedirs(dest_dir)
            except OSError:
                pass

        cmd = [
            blender_exec,
            '--background',
            '--python', script_path,
            '--',
            os.path.abspath(source_path),
            os.path.abspath(output_path)
        ]

        self._log_geometry_progress(notes, 'Launching Blender conversion...')
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
        except Exception as exc:
            message = 'Failed to launch Blender: {0}'.format(exc)
            self._log_geometry_progress(notes, message)
            return False, message

        idle_limit = int(self.config.get('blender_idle_timeout', 900))  # seconds
        last_output = time.time()

        try:
            while True:
                line = proc.stdout.readline()
                if line:
                    last_output = time.time()
                    line = line.strip()
                    if line:
                        self._log_geometry_progress(notes, line)
                elif proc.poll() is not None:
                    break
                else:
                    time.sleep(0.5)
                    if idle_limit and (time.time() - last_output) > idle_limit:
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                        message = 'Blender conversion idle timeout after {0} seconds.'.format(idle_limit)
                        self._log_geometry_progress(notes, message)
                        return False, message

            remaining = proc.stdout.read()
            if remaining:
                for chunk in remaining.splitlines():
                    chunk = chunk.strip()
                    if chunk:
                        self._log_geometry_progress(notes, chunk)
        finally:
            try:
                proc.stdout.close()
            except Exception:
                pass

        retcode = proc.poll()
        if retcode != 0:
            message = 'Blender exited with code {0}.'.format(retcode)
            self._log_geometry_progress(notes, message)
            return False, message

        if not os.path.exists(output_path):
            message = 'Blender finished but GLB output not found: {0}'.format(output_path)
            self._log_geometry_progress(notes, message)
            return False, message

        message = 'Blender conversion complete.'
        self._log_geometry_progress(notes, message)
        return True, message

    def _convert_geometry_asset(self, source_path, output_path, blender_override, notes):
        ext_lower = os.path.splitext(source_path)[1].lower()

        if ext_lower in ('.glb', '.gltf'):
            try:
                shutil.copy2(source_path, output_path)
                message = 'Source already {0}; copied into geometry cache.'.format(ext_lower)
                self._log_geometry_progress(notes, message)
                return True, message
            except Exception as exc:
                message = 'Failed to copy existing {0}: {1}'.format(ext_lower, exc)
                self._log_geometry_progress(notes, message)
                return False, message

        script_supported = ext_lower in ('.fbx', '.obj', '.abc')
        if script_supported:
            return self._run_blender_cli_conversion(source_path, output_path, blender_override, notes)

        def _report(message):
            self._log_geometry_progress(notes, message)

        return convert_to_glb(
            source_path,
            output_path,
            blender_path=blender_override,
            reporter=_report
        )
    
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
        # Normalize path separators for consistent handling
        source_path = os.path.normpath(source_path)
        
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
            auto_detect_sequences, sequence_pattern_choice = self._refresh_sequence_preferences()

            # Detect sequence based on configured pattern
            sequence_info = SequenceDetector.detect_sequence(
                source_path,
                pattern_key=sequence_pattern_choice,
                auto_detect=auto_detect_sequences
            )
            
            # Determine paths and metadata
            if sequence_info:
                # This is a sequence
                name = sequence_info['base_name']
                frame_range = sequence_info['frame_range']
                files_to_process = sequence_info['files']
                is_sequence = True
                sequence_pattern_path = SequenceDetector.get_sequence_path(sequence_info)
                filepath_soft = files_to_process[0]
            else:
                # Single file
                name = os.path.splitext(os.path.basename(source_path))[0]
                frame_range = None
                files_to_process = [source_path]
                is_sequence = False
                sequence_pattern_path = None
                filepath_soft = source_path
            
            if filepath_soft:
                filepath_soft = os.path.normpath(filepath_soft)
            
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
                if is_sequence and sequence_info:
                    filepath_hard = os.path.join(target_dir, os.path.basename(files_to_process[0]))
                else:
                    filepath_hard = os.path.join(target_dir, os.path.basename(source_path))
                if filepath_hard:
                    filepath_hard = os.path.normpath(filepath_hard)
            
            element_hash = hashlib.md5(name.encode('utf-8')).hexdigest()[:8]

            geometry_preview_path = None
            geometry_conversion_notes = []
            if asset_type == '3D':
                ext_lower = os.path.splitext(source_path)[1].lower()
                if ext_lower in SUPPORTED_GEOMETRY_EXTS:
                    geometry_dir = os.path.join(self.preview_dir, 'geometry')
                    if not os.path.exists(geometry_dir):
                        try:
                            os.makedirs(geometry_dir)
                        except OSError as create_err:
                            print("[GLB] Failed to create geometry preview directory: {}".format(create_err))
                    geometry_filename = "{}_{}.glb".format(target_list_id, element_hash)
                    geometry_preview_path = os.path.normpath(os.path.join(geometry_dir, geometry_filename))

                    conversion_source = None
                    candidates = [filepath_hard, filepath_soft, source_path]
                    for candidate in candidates:
                        if candidate and os.path.exists(candidate):
                            conversion_source = candidate
                            break
                    if not conversion_source:
                        conversion_source = source_path

                    blender_override = self.config.get('blender_path')
                    success, message = self._convert_geometry_asset(
                        conversion_source,
                        geometry_preview_path,
                        blender_override,
                        geometry_conversion_notes
                    )

                    if not success:
                        if os.path.exists(geometry_preview_path):
                            try:
                                os.remove(geometry_preview_path)
                            except OSError:
                                pass
                        details = message
                        if geometry_conversion_notes:
                            details = "{} | {}".format(message, ' | '.join(geometry_conversion_notes))
                        return {'success': False, 'message': '3D conversion failed: {}'.format(details)}

                    print("[GLB] ✓ {}".format(message))
                else:
                    print("[GLB] Skipping conversion for unsupported extension: {}".format(ext_lower))

            preview_path = None
            if self.config.get('generate_previews', True):
                preview_filename = "{}_{}.png".format(
                    target_list_id,
                    element_hash
                )
                preview_path = os.path.normpath(os.path.join(self.preview_dir, preview_filename))
                try:
                    preview_max_size = int(self.config.get('preview_size', PreviewGenerator.PREVIEW_SIZE))
                except (TypeError, ValueError):
                    preview_max_size = PreviewGenerator.PREVIEW_SIZE

                if is_sequence:
                    PreviewGenerator.generate_sequence_preview(
                        files_to_process,
                        preview_path,
                        max_size=preview_max_size
                    )
                elif asset_type == '2D':
                    PreviewGenerator.generate_image_preview(
                        source_path,
                        preview_path,
                        max_size=preview_max_size
                    )
            
            # Generate animated GIF preview for videos and sequences
            gif_preview_path = None

            # Check if it's a video file
            is_video = file_format.lower() in ['.mp4', '.mov', '.avi', '.mkv', '.mpg', '.mpeg', '.wmv', '.flv']

            try:
                gif_size = int(self.config.get('gif_size', 256))
            except (TypeError, ValueError):
                gif_size = 256

            try:
                gif_fps = int(self.config.get('gif_fps', 10))
            except (TypeError, ValueError):
                gif_fps = 10

            gif_full_duration = bool(self.config.get('gif_full_duration', False))

            if gif_full_duration:
                gif_duration = None
            else:
                gif_duration_setting = self.config.get('gif_duration', 3.0)
                try:
                    gif_duration = float(gif_duration_setting)
                except (TypeError, ValueError):
                    gif_duration = 3.0
            gif_max_frames = self.config.get('gif_max_frames', None)
            if gif_full_duration:
                gif_max_frames = None
            elif gif_max_frames is not None:
                try:
                    gif_max_frames = int(gif_max_frames)
                except (TypeError, ValueError):
                    gif_max_frames = None
            gif_loop_forever = self.config.get('gif_loop_forever', True)
            try:
                sequence_preview_fps = int(self.config.get('sequence_preview_fps', 24))
            except (TypeError, ValueError):
                sequence_preview_fps = 24
            
            if is_video or (is_sequence and asset_type == '2D'):
                print("[GIF] Generating GIF preview for {} (type: {}, is_video: {}, is_sequence: {})".format(
                    name, asset_type, is_video, is_sequence))
                gif_filename = "{}_{}.gif".format(
                    target_list_id,
                    element_hash
                )
                gif_preview_path = os.path.normpath(os.path.join(self.preview_dir, gif_filename))
                print("[GIF] Output path: {}".format(gif_preview_path))
                
                # Determine input path for FFmpeg
                if is_sequence:
                    # Use sequence pattern for FFmpeg operations
                    input_for_gif = sequence_pattern_path or SequenceDetector.get_sequence_path(sequence_info)
                    print("[GIF] Input (sequence): {}".format(input_for_gif))
                else:
                    # Use video file (already normalized at function start)
                    input_for_gif = source_path
                    print("[GIF] Input (video): {}".format(input_for_gif))
                
                # Generate GIF (3 seconds, 256x256px square, 10fps)
                ffmpeg = get_ffmpeg()
                print("[GIF] Calling FFmpeg generate_gif_preview...")
                
                # Pass start_frame for sequences
                start_frame_for_gif = None
                if is_sequence and sequence_info:
                    start_frame_for_gif = sequence_info.get('first_frame') or sequence_info.get('start_frame')
                
                gif_success = ffmpeg.generate_gif_preview(
                    input_for_gif,
                    gif_preview_path,
                    max_duration=gif_duration,
                    size=gif_size,
                    fps=gif_fps,
                    start_frame=start_frame_for_gif,
                    is_sequence=is_sequence and asset_type == '2D',
                    sequence_fps=sequence_preview_fps,
                    max_frames=gif_max_frames,
                    loop_forever=gif_loop_forever
                )
                
                if gif_success and os.path.exists(gif_preview_path):
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
                    element_hash
                )
                video_preview_path = os.path.normpath(os.path.join(self.preview_dir, video_filename))
                print("[VIDEO] Output path: {}".format(video_preview_path))
                
                # Generate low-res MP4 preview (~512px, first 100 frames or 4 seconds)
                video_success = PreviewGenerator.generate_sequence_video_preview(
                    sequence_info,
                    video_preview_path,
                    max_size=512,
                    fps=sequence_preview_fps
                )
                
                if video_success:
                    print("[VIDEO] ✓ Video preview generated successfully: {}".format(video_preview_path))
                else:
                    print("[VIDEO] ✗ Video preview generation failed")
                    video_preview_path = None
            
            # Create element in database
            preview_db_path = preview_path if (preview_path and os.path.exists(preview_path)) else None

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
                preview_path=preview_db_path,
                gif_preview_path=gif_preview_path,
                video_preview_path=video_preview_path,
                geometry_preview_path=geometry_preview_path,
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
                'frame_range': frame_range,
                'sequence_files': files_to_process if is_sequence else None,
                'geometry_preview_path': geometry_preview_path
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
        processed_paths = set()
        for source_path in source_paths:
            normalized_path = os.path.normpath(source_path)
            if normalized_path in processed_paths:
                continue

            result = self.ingest_file(normalized_path, target_list_id, **kwargs)
            results.append(result)

            if result.get('success'):
                processed_paths.add(normalized_path)
                sequence_files = result.get('sequence_files') or []
                for seq_file in sequence_files:
                    processed_paths.add(os.path.normpath(seq_file))
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
        processed_paths = set()

        def _process_path(path):
            normalized = os.path.normpath(path)
            if normalized in processed_paths or not os.path.isfile(normalized):
                return

            result = self.ingest_file(normalized, target_list_id, **kwargs)
            results.append(result)

            if result.get('success'):
                processed_paths.add(normalized)
                sequence_files = result.get('sequence_files') or []
                for seq_file in sequence_files:
                    processed_paths.add(os.path.normpath(seq_file))

        if recursive:
            for root, dirs, files in os.walk(folder_path):
                for filename in files:
                    filepath = os.path.join(root, filename)
                    _process_path(filepath)
        else:
            try:
                directory_listing = sorted(os.listdir(folder_path))
            except OSError:
                directory_listing = []

            for filename in directory_listing:
                filepath = os.path.join(folder_path, filename)
                _process_path(filepath)

        return results
