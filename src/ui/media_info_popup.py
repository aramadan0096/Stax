# -*- coding: utf-8 -*-
"""
Media Info Popup Widget
Non-modal popup for displaying media information with video playback controls
"""

import os
from PySide2 import QtWidgets, QtCore, QtGui
from src.ffmpeg_wrapper import FFmpegWrapper
from src.icon_loader import get_icon


class MediaInfoPopup(QtWidgets.QDialog):
    """
    Non-modal popup for displaying media information.
    Triggered by Alt+Hover over element.
    Enhanced with video playback controls and frame scrubbing.
    """
    
    # Signals
    insert_requested = QtCore.Signal(int)  # element_id
    reveal_requested = QtCore.Signal(str)  # filepath
    
    def __init__(self, parent=None):
        super(MediaInfoPopup, self).__init__(parent)
        self.element_data = None
        self.ffmpeg = FFmpegWrapper()  # FFmpeg wrapper instance
        self.playback_process = None  # FFplay process handle
        self.is_video = False  # Track if current element is video
        self.is_sequence = False  # Track if element is sequence
        self.frame_count = 0  # Total frames for scrubbing
        self.current_frame = 0  # Current frame position
        self.media_filepath = None  # Full path to media
        self._project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        
        self.setWindowFlags(
            QtCore.Qt.Tool | 
            QtCore.Qt.FramelessWindowHint | 
            QtCore.Qt.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        self.setFixedSize(400, 700)  # Increased height for video controls
        
        # Main layout with border
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Container with styling
        container = QtWidgets.QWidget()
        container.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                border: 2px solid #555555;
                border-radius: 4px;
            }
        """)
        container_layout = QtWidgets.QVBoxLayout(container)
        container_layout.setContentsMargins(10, 10, 10, 10)
        
        # Title
        self.title_label = QtWidgets.QLabel("Element Info")
        self.title_label.setStyleSheet("""
            font-weight: bold; 
            font-size: 14px; 
            color: #ffffff;
            border: none;
        """)
        container_layout.addWidget(self.title_label)
        
        # Preview image
        self.preview_label = QtWidgets.QLabel()
        self.preview_label.setFixedSize(380, 280)
        self.preview_label.setAlignment(QtCore.Qt.AlignCenter)
        self.preview_label.setStyleSheet("""
            background-color: #1e1e1e;
            border: 1px solid #444444;
            color: #888888;
        """)
        self.preview_label.setText("No Preview")
        container_layout.addWidget(self.preview_label)
        
        # Video/Sequence Controls (initially hidden)
        self.video_controls_widget = QtWidgets.QWidget()
        self.video_controls_widget.setStyleSheet("border: none;")
        self.video_controls_widget.setVisible(False)
        video_controls_layout = QtWidgets.QVBoxLayout(self.video_controls_widget)
        video_controls_layout.setContentsMargins(0, 5, 0, 5)
        
        # Frame scrubber
        scrubber_layout = QtWidgets.QHBoxLayout()
        self.frame_label = QtWidgets.QLabel("Frame: 0")
        self.frame_label.setStyleSheet("color: #aaaaaa; border: none; font-size: 11px;")
        scrubber_layout.addWidget(self.frame_label)
        
        self.frame_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.frame_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #444444;
                height: 6px;
                background: #1e1e1e;
                margin: 2px 0;
            }
            QSlider::handle:horizontal {
                background: #16c6b0;
                border: 1px solid #16c6b0;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:hover {
                background: #1ed4be;
            }
        """)
        self.frame_slider.setMinimum(0)
        self.frame_slider.valueChanged.connect(self.on_frame_slider_changed)
        scrubber_layout.addWidget(self.frame_slider)
        
        video_controls_layout.addLayout(scrubber_layout)
        
        # Playback buttons
        playback_layout = QtWidgets.QHBoxLayout()
        
        self.play_btn = QtWidgets.QPushButton("Play")
        self.play_btn.setIcon(get_icon('play', size=20))
        self.play_btn.setStyleSheet("""
            QPushButton {
                background-color: #16c6b0;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1ed4be; }
            QPushButton:pressed { background-color: #12a393; }
        """)
        self.play_btn.clicked.connect(self.on_play_clicked)
        playback_layout.addWidget(self.play_btn)
        
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.setIcon(get_icon('stop', size=20))
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff9a3c;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #ffaa5c; }
            QPushButton:pressed { background-color: #e58a2c; }
        """)
        self.stop_btn.clicked.connect(self.on_stop_clicked)
        self.stop_btn.setEnabled(False)
        playback_layout.addWidget(self.stop_btn)
        
        playback_layout.addStretch()
        video_controls_layout.addLayout(playback_layout)
        
        container_layout.addWidget(self.video_controls_widget)
        
        # Metadata section
        metadata_widget = QtWidgets.QWidget()
        metadata_widget.setStyleSheet("border: none;")
        metadata_layout = QtWidgets.QFormLayout(metadata_widget)
        metadata_layout.setContentsMargins(0, 10, 0, 10)
        
        label_style = "color: #aaaaaa; border: none;"
        value_style = "color: #ffffff; border: none; font-weight: bold;"
        
        self.name_label = QtWidgets.QLabel()
        self.name_label.setStyleSheet(value_style)
        self.name_label.setWordWrap(True)
        metadata_layout.addRow(self._create_label("Name:", label_style), self.name_label)
        
        self.type_label = QtWidgets.QLabel()
        self.type_label.setStyleSheet(value_style)
        metadata_layout.addRow(self._create_label("Type:", label_style), self.type_label)
        
        self.format_label = QtWidgets.QLabel()
        self.format_label.setStyleSheet(value_style)
        metadata_layout.addRow(self._create_label("Format:", label_style), self.format_label)
        
        self.frames_label = QtWidgets.QLabel()
        self.frames_label.setStyleSheet(value_style)
        metadata_layout.addRow(self._create_label("Frames:", label_style), self.frames_label)
        
        self.size_label = QtWidgets.QLabel()
        self.size_label.setStyleSheet(value_style)
        metadata_layout.addRow(self._create_label("Size:", label_style), self.size_label)
        
        self.path_label = QtWidgets.QLabel()
        self.path_label.setStyleSheet(value_style)
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        metadata_layout.addRow(self._create_label("Path:", label_style), self.path_label)
        
        self.comment_label = QtWidgets.QLabel()
        self.comment_label.setStyleSheet(value_style)
        self.comment_label.setWordWrap(True)
        metadata_layout.addRow(self._create_label("Comment:", label_style), self.comment_label)
        
        container_layout.addWidget(metadata_widget)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        self.insert_btn = QtWidgets.QPushButton("Insert into Nuke")
        self.insert_btn.setIcon(get_icon('add', size=20))
        self.insert_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QPushButton:pressed {
                background-color: #2868a6;
            }
        """)
        self.insert_btn.clicked.connect(self.on_insert_clicked)
        button_layout.addWidget(self.insert_btn)
        
        self.reveal_btn = QtWidgets.QPushButton("Reveal in Explorer")
        self.reveal_btn.setIcon(get_icon('folder', size=20))
        self.reveal_btn.setStyleSheet("""
            QPushButton {
                background-color: #5a5a5a;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #6a6a6a;
            }
            QPushButton:pressed {
                background-color: #4a4a4a;
            }
        """)
        self.reveal_btn.clicked.connect(self.on_reveal_clicked)
        button_layout.addWidget(self.reveal_btn)
        
        container_layout.addLayout(button_layout)
        
        main_layout.addWidget(container)
    
    def _create_label(self, text, style):
        """Helper to create styled label."""
        label = QtWidgets.QLabel(text)
        label.setStyleSheet(style)
        return label
    
    def show_element(self, element_data, position=None):
        """
        Show popup with element data.
        
        Args:
            element_data (dict): Element data from database
            position (QPoint): Optional position to show popup
        """
        self.element_data = element_data
        
        # Stop any existing playback
        self.stop_playback()
        
        # Update title
        self.title_label.setText(element_data.get('name', 'Unknown'))
        
        # Update metadata
        self.name_label.setText(element_data.get('name', 'N/A'))
        self.type_label.setText(element_data.get('type', 'N/A'))
        self.format_label.setText(element_data.get('format', 'N/A') or 'N/A')
        self.frames_label.setText(element_data.get('frame_range', 'N/A') or 'N/A')
        
        # Format file size
        file_size = element_data.get('file_size', 0)
        if file_size:
            size_mb = file_size / (1024.0 * 1024.0)
            if size_mb < 1024:
                size_str = "{:.1f} MB".format(size_mb)
            else:
                size_str = "{:.2f} GB".format(size_mb / 1024.0)
        else:
            size_str = 'N/A'
        self.size_label.setText(size_str)
        
        # Get filepath
        self.media_filepath = element_data.get('filepath_hard') if element_data.get('is_hard_copy') else element_data.get('filepath_soft')
        self.media_filepath = self._resolve_path(self.media_filepath)
        self.path_label.setText(self.media_filepath or 'N/A')
        
        # Show comment
        comment = element_data.get('comment', '')
        self.comment_label.setText(comment or 'No comment')
        
        # Determine if video or sequence
        element_type = element_data.get('type', '').lower()
        self.is_video = element_type == 'video'
        self.is_sequence = element_type == 'sequence'
        
        # Show/hide video controls
        if self.is_video or self.is_sequence:
            self.video_controls_widget.setVisible(True)
            self._setup_video_controls()
        else:
            self.video_controls_widget.setVisible(False)
        
        # Load preview
        preview_path = self._resolve_path(element_data.get('preview_path'))
        if preview_path and os.path.exists(preview_path):
            pixmap = QtGui.QPixmap(preview_path)
            scaled_pixmap = pixmap.scaled(
                380, 280,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
            self.preview_label.setPixmap(scaled_pixmap)
        else:
            self.preview_label.clear()
            self.preview_label.setText("No Preview Available")
        
        # Position popup
        if position:
            # Offset to the right and down a bit from cursor
            self.move(position.x() + 20, position.y() + 20)
        
        # Show popup
        self.show()
        self.raise_()
    
    def _setup_video_controls(self):
        """Setup video/sequence controls based on element type."""
        if not self.media_filepath or not os.path.exists(self.media_filepath):
            return
        
        # Get media info
        try:
            info = self.ffmpeg.get_media_info(self.media_filepath)
            
            if self.is_video and info:
                # For videos, get frame count
                self.frame_count = self.ffmpeg.get_frame_count(self.media_filepath)
                if self.frame_count:
                    self.frame_slider.setMaximum(self.frame_count - 1)
                    self.frame_slider.setValue(0)
                    self.frame_label.setText("Frame: 0 / {}".format(self.frame_count))
                else:
                    # Fallback to duration-based scrubbing
                    duration = info.get('duration', 0)
                    if duration:
                        fps = info.get('fps', 24)
                        self.frame_count = int(duration * fps)
                        self.frame_slider.setMaximum(self.frame_count - 1)
                        self.frame_slider.setValue(0)
                        self.frame_label.setText("Frame: 0 / {}".format(self.frame_count))
            
            elif self.is_sequence:
                # For sequences, parse frame range
                frame_range = self.element_data.get('frame_range', '')
                if frame_range and '-' in frame_range:
                    try:
                        start_frame, end_frame = frame_range.split('-')
                        start_frame = int(start_frame.strip())
                        end_frame = int(end_frame.strip())
                        self.frame_count = end_frame - start_frame + 1
                        self.frame_slider.setMinimum(start_frame)
                        self.frame_slider.setMaximum(end_frame)
                        self.frame_slider.setValue(start_frame)
                        self.current_frame = start_frame
                        self.frame_label.setText("Frame: {} / {}".format(start_frame, end_frame))
                    except:
                        pass
        except Exception as e:
            print("Error setting up video controls: {}".format(str(e)))
    
    def on_frame_slider_changed(self, value):
        """Handle frame slider value change."""
        self.current_frame = value
        
        if self.is_sequence:
            frame_range = self.element_data.get('frame_range', '')
            if frame_range and '-' in frame_range:
                start_frame, end_frame = frame_range.split('-')
                self.frame_label.setText("Frame: {} / {}".format(value, end_frame.strip()))
        else:
            self.frame_label.setText("Frame: {} / {}".format(value, self.frame_count))
        
        # Update preview for current frame (optional - resource intensive)
        # self._update_frame_preview(value)
    
    def on_play_clicked(self):
        """Handle Play button click."""
        if not self.media_filepath or not os.path.exists(self.media_filepath):
            return
        
        # Use FFmpeg to play media
        try:
            # Get start time from current frame
            if self.is_video and self.frame_count > 0:
                info = self.ffmpeg.get_media_info(self.media_filepath)
                fps = info.get('fps', 24) if info else 24
                start_time = self.current_frame / float(fps)
            else:
                start_time = 0
            
            # Start playback
            self.playback_process = self.ffmpeg.play_media(
                self.media_filepath,
                loop=False,
                start_time=start_time
            )
            
            if self.playback_process:
                self.play_btn.setEnabled(False)
                self.stop_btn.setEnabled(True)
        except Exception as e:
            print("Error playing media: {}".format(str(e)))
    
    def on_stop_clicked(self):
        """Handle Stop button click."""
        self.stop_playback()
    
    def stop_playback(self):
        """Stop any active playback."""
        if self.playback_process:
            try:
                self.playback_process.terminate()
                self.playback_process.wait(timeout=2)
            except:
                try:
                    self.playback_process.kill()
                except:
                    pass
            finally:
                self.playback_process = None
        
        self.play_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
    
    def _update_frame_preview(self, frame_number):
        """Update preview to show specific frame (optional, resource intensive)."""
        if not self.media_filepath:
            return
        
        import tempfile
        try:
            # Generate temp file for frame
            temp_dir = tempfile.gettempdir()
            temp_preview = os.path.join(temp_dir, "stax_frame_preview.png")
            
            # Extract frame
            success = self.ffmpeg.extract_frame(self.media_filepath, frame_number, temp_preview)
            
            if success and os.path.exists(temp_preview):
                pixmap = QtGui.QPixmap(temp_preview)
                scaled_pixmap = pixmap.scaled(
                    380, 280,
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation
                )
                self.preview_label.setPixmap(scaled_pixmap)
                
                # Clean up
                try:
                    os.remove(temp_preview)
                except:
                    pass
        except Exception as e:
            print("Error updating frame preview: {}".format(str(e)))
    
    def on_insert_clicked(self):
        """Handle Insert button click."""
        if self.element_data:
            self.insert_requested.emit(self.element_data['element_id'])
            self.hide()
    
    def on_reveal_clicked(self):
        """Handle Reveal button click."""
        if self.element_data:
            filepath = self.element_data.get('filepath_hard') if self.element_data.get('is_hard_copy') else self.element_data.get('filepath_soft')
            if filepath:
                resolved = self._resolve_path(filepath)
                self.reveal_requested.emit(resolved or filepath)
    
    def mousePressEvent(self, event):
        """Close popup on click anywhere."""
        self.hide()
    
    def hideEvent(self, event):
        """Cleanup when hiding popup."""
        self.stop_playback()
        super(MediaInfoPopup, self).hideEvent(event)
    
    def closeEvent(self, event):
        """Cleanup when closing popup."""
        self.stop_playback()
        super(MediaInfoPopup, self).closeEvent(event)

    def _resolve_path(self, path):
        """Resolve project-relative paths to absolute ones for file access."""
        if not path:
            return None
        path = path.strip()
        if not path:
            return None
        if os.path.isabs(path):
            return os.path.normpath(path)
        return os.path.normpath(os.path.join(self._project_root, path))
