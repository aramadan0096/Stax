#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Preview Worker Module
Background thread workers for generating media previews without blocking the UI.
"""

import os
try:
    # Python 2/3 compatibility
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty

from PySide2 import QtCore

from src.ffmpeg_wrapper import FFmpegWrapper


class PreviewWorker(QtCore.QThread):
    """
    Background worker thread for generating media previews.
    Uses a queue system to process multiple preview requests.
    """
    
    # Signals
    preview_generated = QtCore.Signal(str, str, bool)  # (element_id, preview_path, success)
    progress_updated = QtCore.Signal(int, int)  # (current, total)
    error_occurred = QtCore.Signal(str, str)  # (element_id, error_message)
    
    def __init__(self, config, parent=None):
        super(PreviewWorker, self).__init__(parent)
        self.config = config
        self.ffmpeg = FFmpegWrapper()
        self.queue = Queue()
        self.is_running = True
        self.current_task = None
        self.total_tasks = 0
        self.completed_tasks = 0
    
    def add_task(self, element_id, source_path, preview_path, media_type):
        """
        Add a preview generation task to the queue.
        
        Args:
            element_id (str): Element ID for tracking
            source_path (str): Source media file path
            preview_path (str): Output preview file path
            media_type (str): Type of media ('image', 'sequence', 'video', 'gif')
        """
        self.queue.put({
            'element_id': element_id,
            'source_path': source_path,
            'preview_path': preview_path,
            'media_type': media_type
        })
        self.total_tasks += 1
    
    def clear_queue(self):
        """Clear all pending tasks from the queue."""
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except Empty:
                break
        self.total_tasks = 0
        self.completed_tasks = 0
    
    def stop(self):
        """Stop the worker thread gracefully."""
        self.is_running = False
        self.clear_queue()
        self.wait()
    
    def run(self):
        """Main worker loop - processes tasks from queue."""
        while self.is_running:
            try:
                # Get task from queue with timeout
                task = self.queue.get(timeout=0.5)
                self.current_task = task
                
                # Generate preview based on media type
                success = self._generate_preview(task)
                
                # Emit completion signal
                self.preview_generated.emit(
                    task['element_id'],
                    task['preview_path'],
                    success
                )
                
                # Update progress
                self.completed_tasks += 1
                self.progress_updated.emit(self.completed_tasks, self.total_tasks)
                
                self.current_task = None
                
            except Empty:
                # No tasks in queue, continue waiting
                continue
            except Exception as e:
                if self.current_task:
                    self.error_occurred.emit(
                        self.current_task['element_id'],
                        str(e)
                    )
                continue
    
    def _generate_preview(self, task):
        """
        Generate preview for a single task.
        
        Args:
            task (dict): Task dictionary with element_id, source_path, preview_path, media_type
        
        Returns:
            bool: True if preview generated successfully, False otherwise
        """
        try:
            media_type = task['media_type']
            source_path = task['source_path']
            preview_path = task['preview_path']
            
            # Get thread count from config
            threads = self.config.get('ffmpeg_threads', 4)
            
            # Create preview directory if it doesn't exist
            preview_dir = os.path.dirname(preview_path)
            if not os.path.exists(preview_dir):
                os.makedirs(preview_dir)
            
            # Generate preview based on media type
            if media_type == 'image':
                # Single image preview
                max_size = self.config.get('preview_size', 512)
                self.ffmpeg.generate_thumbnail(
                    source_path,
                    preview_path,
                    max_size=max_size,
                    threads=threads
                )
            
            elif media_type == 'sequence':
                # Image sequence preview (middle frame)
                max_size = self.config.get('preview_size', 512)
                # TODO: Determine sequence pattern and frame number
                self.ffmpeg.generate_sequence_thumbnail(
                    source_path,  # Should be pattern like "file.%04d.exr"
                    preview_path,
                    max_size=max_size,
                    threads=threads
                )
            
            elif media_type == 'video':
                # Video preview (static thumbnail)
                max_size = self.config.get('preview_size', 512)
                self.ffmpeg.generate_thumbnail(
                    source_path,
                    preview_path,
                    max_size=max_size,
                    frame_time=1.0,  # Get frame at 1 second
                    threads=threads
                )
            
            elif media_type == 'gif':
                # Animated GIF preview
                gif_size = self.config.get('gif_size', 256)
                gif_fps = self.config.get('gif_fps', 10)
                gif_full_duration = self.config.get('gif_full_duration', False)
                gif_duration = None if gif_full_duration else self.config.get('gif_duration', 3.0)
                
                self.ffmpeg.generate_gif_preview(
                    source_path,
                    preview_path,
                    max_duration=gif_duration,
                    size=gif_size,
                    fps=gif_fps,
                    threads=threads
                )
            
            return os.path.exists(preview_path)
        
        except Exception as e:
            print("Preview generation error for {}: {}".format(task['element_id'], str(e)))
            return False


class PreviewManager(QtCore.QObject):
    """
    Manager class for coordinating multiple preview worker threads.
    Implements a worker pool for parallel preview generation.
    """
    
    preview_generated = QtCore.Signal(str, str, bool)  # Forwarded from workers
    all_previews_complete = QtCore.Signal()
    progress_updated = QtCore.Signal(int, int)  # (completed, total)
    
    def __init__(self, config, num_workers=2, parent=None):
        super(PreviewManager, self).__init__(parent)
        self.config = config
        self.workers = []
        self.num_workers = num_workers
        self.pending_tasks = []
        self.total_tasks = 0
        self.completed_tasks = 0
        
        # Create worker pool
        for i in range(num_workers):
            worker = PreviewWorker(config, self)
            worker.preview_generated.connect(self.on_preview_generated)
            worker.error_occurred.connect(self.on_error)
            self.workers.append(worker)
            worker.start()
    
    def generate_preview(self, element_id, source_path, preview_path, media_type):
        """
        Add a preview generation request.
        Distributes tasks across worker pool using round-robin.
        
        Args:
            element_id (str): Element ID
            source_path (str): Source media path
            preview_path (str): Output preview path
            media_type (str): Media type ('image', 'sequence', 'video', 'gif')
        """
        # Find worker with smallest queue
        min_queue_size = min(worker.queue.qsize() for worker in self.workers)
        target_worker = next(w for w in self.workers if w.queue.qsize() == min_queue_size)
        
        # Add task to worker
        target_worker.add_task(element_id, source_path, preview_path, media_type)
        self.total_tasks += 1
        
        print("Added preview task for {} to worker (queue size: {})".format(
            element_id, target_worker.queue.qsize()
        ))
    
    def generate_batch(self, tasks):
        """
        Generate previews for a batch of elements.
        
        Args:
            tasks (list): List of task dictionaries with keys:
                         element_id, source_path, preview_path, media_type
        """
        for task in tasks:
            self.generate_preview(
                task['element_id'],
                task['source_path'],
                task['preview_path'],
                task['media_type']
            )
    
    def on_preview_generated(self, element_id, preview_path, success):
        """Handle preview generation completion from worker."""
        self.completed_tasks += 1
        self.progress_updated.emit(self.completed_tasks, self.total_tasks)
        
        # Forward signal
        self.preview_generated.emit(element_id, preview_path, success)
        
        # Check if all tasks complete
        if self.completed_tasks >= self.total_tasks:
            self.all_previews_complete.emit()
            self.reset_counters()
    
    def on_error(self, element_id, error_message):
        """Handle preview generation error from worker."""
        print("Preview error for {}: {}".format(element_id, error_message))
        
        # Count as completed (failed)
        self.completed_tasks += 1
        self.progress_updated.emit(self.completed_tasks, self.total_tasks)
        
        if self.completed_tasks >= self.total_tasks:
            self.all_previews_complete.emit()
            self.reset_counters()
    
    def clear_queue(self):
        """Clear all pending tasks from all workers."""
        for worker in self.workers:
            worker.clear_queue()
        self.reset_counters()
    
    def reset_counters(self):
        """Reset task counters."""
        self.total_tasks = 0
        self.completed_tasks = 0
    
    def stop_all(self):
        """Stop all worker threads."""
        for worker in self.workers:
            worker.stop()
        self.workers = []
