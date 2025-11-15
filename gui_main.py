# -*- coding: utf-8 -*-
"""
Main GUI for VFX_Asset_Hub
PySide2-based user interface with drag-and-drop support
Python 2.7 compatible
"""

import os
import sys
from PySide2 import QtWidgets, QtCore, QtGui

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.config import Config
from src.db_manager import DatabaseManager
from src.ingestion_core import IngestionCore
from src.nuke_bridge import NukeBridge, NukeIntegration
from src.extensibility_hooks import ProcessorManager
from src.ffmpeg_wrapper import FFmpegWrapper
from src.preview_cache import get_preview_cache


class AdvancedSearchDialog(QtWidgets.QDialog):
    """Advanced search dialog with property and match type selection."""
    
    def __init__(self, db_manager, parent=None):
        super(AdvancedSearchDialog, self).__init__(parent)
        self.db = db_manager
        self.setWindowTitle("Advanced Search")
        self.setModal(False)  # Non-modal
        self.setup_ui()
        self.results = []
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Search criteria
        criteria_group = QtWidgets.QGroupBox("Search Criteria")
        criteria_layout = QtWidgets.QFormLayout()
        
        # Property selection
        self.property_combo = QtWidgets.QComboBox()
        self.property_combo.addItems(['name', 'format', 'type', 'comment', 'tags'])
        criteria_layout.addRow("Search Property:", self.property_combo)
        
        # Match type selection
        self.match_combo = QtWidgets.QComboBox()
        self.match_combo.addItems(['loose', 'strict'])
        self.match_combo.setCurrentText('loose')
        criteria_layout.addRow("Match Type:", self.match_combo)
        
        # Search text
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Enter search text...")
        self.search_edit.returnPressed.connect(self.perform_search)
        criteria_layout.addRow("Search Text:", self.search_edit)
        
        criteria_group.setLayout(criteria_layout)
        layout.addWidget(criteria_group)
        
        # Search button
        search_btn = QtWidgets.QPushButton("Search")
        search_btn.clicked.connect(self.perform_search)
        search_btn.setDefault(True)
        layout.addWidget(search_btn)
        
        # Results table
        results_label = QtWidgets.QLabel("Search Results:")
        results_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(results_label)
        
        self.results_table = QtWidgets.QTableWidget()
        self.results_table.setColumnCount(5)
        self.results_table.setHorizontalHeaderLabels(['Name', 'Type', 'Format', 'Frames', 'Comment'])
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.setSelectionBehavior(QtWidgets.QTableWidget.SelectRows)
        self.results_table.itemDoubleClicked.connect(self.on_result_double_clicked)
        layout.addWidget(self.results_table)
        
        # Status label
        self.status_label = QtWidgets.QLabel("Enter search criteria and click Search")
        self.status_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(self.status_label)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        
        self.resize(700, 500)
    
    def perform_search(self):
        """Perform search based on criteria."""
        search_text = self.search_edit.text().strip()
        if not search_text:
            QtWidgets.QMessageBox.warning(self, "Empty Search", "Please enter search text.")
            return
        
        property_name = self.property_combo.currentText()
        match_type = self.match_combo.currentText()
        
        # Perform search
        self.results = self.db.search_elements(search_text, property_name, match_type)
        
        # Update results table
        self.results_table.setRowCount(len(self.results))
        for row, element in enumerate(self.results):
            self.results_table.setItem(row, 0, QtWidgets.QTableWidgetItem(element['name']))
            self.results_table.setItem(row, 1, QtWidgets.QTableWidgetItem(element['type']))
            self.results_table.setItem(row, 2, QtWidgets.QTableWidgetItem(element['format'] or ''))
            self.results_table.setItem(row, 3, QtWidgets.QTableWidgetItem(element['frame_range'] or ''))
            self.results_table.setItem(row, 4, QtWidgets.QTableWidgetItem(element['comment'] or ''))
            
            # Store element_id in first column
            self.results_table.item(row, 0).setData(QtCore.Qt.UserRole, element['element_id'])
        
        # Update status
        self.status_label.setText("Found {} results".format(len(self.results)))
        self.status_label.setStyleSheet("color: green;" if len(self.results) > 0 else "color: orange;")
    
    def on_result_double_clicked(self, item):
        """Handle double-click on result."""
        element_id = self.results_table.item(item.row(), 0).data(QtCore.Qt.UserRole)
        if element_id:
            # Emit signal or trigger action
            self.parent().on_advanced_search_result(element_id)


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
        
        self.play_btn = QtWidgets.QPushButton("▶ Play")
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
        
        self.stop_btn = QtWidgets.QPushButton("⏹ Stop")
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
        preview_path = element_data.get('preview_path')
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
            temp_preview = os.path.join(temp_dir, "vah_frame_preview.png")
            
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
    
    def show_element(self, element_data, position=None):
        """
        Show popup with element data.
        
        Args:
            element_data (dict): Element data from database
            position (QPoint): Optional position to show popup
        """
        self.element_data = element_data
        
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
        
        # Show path
        filepath = element_data.get('filepath_hard') if element_data.get('is_hard_copy') else element_data.get('filepath_soft')
        self.path_label.setText(filepath or 'N/A')
        
        # Show comment
        comment = element_data.get('comment', '')
        self.comment_label.setText(comment or 'No comment')
        
        # Load preview
        preview_path = element_data.get('preview_path')
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
                self.reveal_requested.emit(filepath)
    
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


class StacksListsPanel(QtWidgets.QWidget):
    """Left sidebar panel for Stacks, Lists, Favorites, and Playlists navigation."""
    
    # Signals
    stack_selected = QtCore.Signal(int)  # stack_id
    list_selected = QtCore.Signal(int)   # list_id
    favorites_selected = QtCore.Signal()  # Show favorites
    playlist_selected = QtCore.Signal(int)  # playlist_id
    
    def __init__(self, db_manager, config, parent=None):
        super(StacksListsPanel, self).__init__(parent)
        self.db = db_manager
        self.config = config
        self.setup_ui()
        self.load_data()
    
    def setup_ui(self):
        """Setup the UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Title
        title = QtWidgets.QLabel("Navigation")
        title.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        title.setProperty("class", "title")
        layout.addWidget(title)
        
        # Favorites button
        self.favorites_btn = QtWidgets.QPushButton("⭐ Favorites")
        self.favorites_btn.setProperty("class", "primary")
        self.favorites_btn.clicked.connect(self.on_favorites_clicked)
        layout.addWidget(self.favorites_btn)
        
        # Separator
        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(separator)
        
        # Playlists section
        playlists_header = QtWidgets.QHBoxLayout()
        playlists_label = QtWidgets.QLabel("Playlists")
        playlists_label.setStyleSheet("font-weight: bold; padding: 5px;")
        playlists_header.addWidget(playlists_label)
        
        self.add_playlist_btn = QtWidgets.QPushButton("+ New")
        self.add_playlist_btn.setMaximumWidth(60)
        self.add_playlist_btn.clicked.connect(self.add_playlist)
        playlists_header.addWidget(self.add_playlist_btn)
        
        layout.addLayout(playlists_header)
        
        # Playlists list
        self.playlists_list = QtWidgets.QListWidget()
        self.playlists_list.setMaximumHeight(150)
        self.playlists_list.itemClicked.connect(self.on_playlist_clicked)
        layout.addWidget(self.playlists_list)
        
        # Separator
        separator2 = QtWidgets.QFrame()
        separator2.setFrameShape(QtWidgets.QFrame.HLine)
        separator2.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(separator2)
        
        # Stacks & Lists label
        stacks_label = QtWidgets.QLabel("Stacks & Lists")
        stacks_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(stacks_label)
        
        # Tree widget
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.itemClicked.connect(self.on_item_clicked)
        layout.addWidget(self.tree)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        self.add_stack_btn = QtWidgets.QPushButton("+ Stack")
        self.add_stack_btn.clicked.connect(self.add_stack)
        button_layout.addWidget(self.add_stack_btn)
        
        self.add_list_btn = QtWidgets.QPushButton("+ List")
        self.add_list_btn.clicked.connect(self.add_list)
        button_layout.addWidget(self.add_list_btn)
        
        layout.addLayout(button_layout)
    
    def on_favorites_clicked(self):
        """Handle favorites button click."""
        self.favorites_selected.emit()
    
    def on_playlist_clicked(self, item):
        """Handle playlist click."""
        playlist_id = item.data(QtCore.Qt.UserRole)
        if playlist_id:
            self.playlist_selected.emit(playlist_id)
    
    def add_playlist(self):
        """Add new playlist dialog."""
        dialog = CreatePlaylistDialog(self.db, self.config, self)
        if dialog.exec_():
            self.load_playlists()
    
    def load_playlists(self):
        """Load playlists from database."""
        self.playlists_list.clear()
        
        playlists = self.db.get_all_playlists()
        for playlist in playlists:
            item = QtWidgets.QListWidgetItem("📋 " + playlist['name'])
            item.setData(QtCore.Qt.UserRole, playlist['playlist_id'])
            self.playlists_list.addItem(item)
    
    def load_data(self):
        """Load stacks, lists, and playlists from database."""
        self.tree.clear()
        
        # Load playlists
        self.load_playlists()
        
        # Load stacks and lists
        stacks = self.db.get_all_stacks()
        for stack in stacks:
            stack_item = QtWidgets.QTreeWidgetItem([stack['name']])
            stack_item.setData(0, QtCore.Qt.UserRole, ('stack', stack['stack_id']))
            stack_item.setIcon(0, self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon))
            self.tree.addTopLevelItem(stack_item)
            
            # Load lists for this stack
            lists = self.db.get_lists_by_stack(stack['stack_id'])
            for lst in lists:
                list_item = QtWidgets.QTreeWidgetItem([lst['name']])
                list_item.setData(0, QtCore.Qt.UserRole, ('list', lst['list_id']))
                list_item.setIcon(0, self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon))
                stack_item.addChild(list_item)
            
            stack_item.setExpanded(True)
    
    def on_item_clicked(self, item, column):
        """Handle item click."""
        data = item.data(0, QtCore.Qt.UserRole)
        if data:
            item_type, item_id = data
            if item_type == 'stack':
                self.stack_selected.emit(item_id)
            elif item_type == 'list':
                self.list_selected.emit(item_id)
    
    def add_stack(self):
        """Add new stack dialog."""
        dialog = AddStackDialog(self.db, self)
        if dialog.exec_():
            self.load_data()
    
    def add_list(self):
        """Add new list dialog."""
        # Get selected stack
        current_item = self.tree.currentItem()
        stack_id = None
        
        if current_item:
            data = current_item.data(0, QtCore.Qt.UserRole)
            if data:
                item_type, item_id = data
                if item_type == 'stack':
                    stack_id = item_id
                elif item_type == 'list':
                    # Get parent stack
                    parent = current_item.parent()
                    if parent:
                        parent_data = parent.data(0, QtCore.Qt.UserRole)
                        if parent_data:
                            stack_id = parent_data[1]
        
        dialog = AddListDialog(self.db, stack_id, self)
        if dialog.exec_():
            self.load_data()


class MediaDisplayWidget(QtWidgets.QWidget):
    """Central widget for displaying media elements."""
    
    # Signals
    element_selected = QtCore.Signal(int)  # element_id
    element_double_clicked = QtCore.Signal(int)  # element_id
    
    def __init__(self, db_manager, config, parent=None):
        super(MediaDisplayWidget, self).__init__(parent)
        self.db = db_manager
        self.config = config
        self.current_list_id = None
        self.view_mode = 'gallery'  # 'gallery' or 'list'
        self.alt_pressed = False  # Track Alt key state
        self.hover_timer = QtCore.QTimer()
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self.show_info_popup)
        self.hover_item = None
        self.media_popup = MediaInfoPopup(self)
        self.media_popup.insert_requested.connect(self.on_popup_insert)
        self.media_popup.reveal_requested.connect(self.on_popup_reveal)
        self.preview_cache = get_preview_cache()  # Initialize preview cache
        self.setup_ui()
        
        # Enable mouse tracking for hover events
        self.setMouseTracking(True)
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        toolbar = QtWidgets.QHBoxLayout()
        
        # Search bar
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText("Search elements...")
        self.search_box.textChanged.connect(self.on_search)
        toolbar.addWidget(self.search_box)
        
        # View mode toggle
        self.gallery_btn = QtWidgets.QPushButton("Gallery")
        self.gallery_btn.setCheckable(True)
        self.gallery_btn.setChecked(True)
        self.gallery_btn.clicked.connect(lambda: self.set_view_mode('gallery'))
        toolbar.addWidget(self.gallery_btn)
        
        self.list_btn = QtWidgets.QPushButton("List")
        self.list_btn.setCheckable(True)
        self.list_btn.clicked.connect(lambda: self.set_view_mode('list'))
        toolbar.addWidget(self.list_btn)
        
        # Element size slider
        self.size_label = QtWidgets.QLabel("Size:")
        toolbar.addWidget(self.size_label)
        
        self.size_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.size_slider.setMinimum(64)
        self.size_slider.setMaximum(512)
        self.size_slider.setValue(256)
        self.size_slider.setMaximumWidth(150)
        self.size_slider.valueChanged.connect(self.on_size_changed)
        toolbar.addWidget(self.size_slider)
        
        toolbar.addStretch()
        
        # Bulk operations button
        self.bulk_btn = QtWidgets.QPushButton("Bulk Operations ▼")
        self.bulk_btn.setToolTip("Perform actions on selected elements")
        self.bulk_btn.clicked.connect(self.show_bulk_menu)
        toolbar.addWidget(self.bulk_btn)
        
        layout.addLayout(toolbar)
        
        # Stacked widget for different views
        self.view_stack = QtWidgets.QStackedWidget()
        
        # Gallery view (grid of thumbnails)
        self.gallery_view = QtWidgets.QListWidget()
        self.gallery_view.setViewMode(QtWidgets.QListView.IconMode)
        self.gallery_view.setResizeMode(QtWidgets.QListView.Adjust)
        self.gallery_view.setIconSize(QtCore.QSize(256, 256))
        self.gallery_view.setSpacing(10)
        self.gallery_view.setDragEnabled(True)
        self.gallery_view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)  # Multi-select
        self.gallery_view.itemClicked.connect(self.on_item_clicked)
        self.gallery_view.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.gallery_view.setMouseTracking(True)  # Enable hover tracking
        self.gallery_view.viewport().installEventFilter(self)  # Install event filter
        self.view_stack.addWidget(self.gallery_view)
        
        # List view (table)
        self.table_view = QtWidgets.QTableWidget()
        self.table_view.setColumnCount(6)
        self.table_view.setHorizontalHeaderLabels(['Name', 'Format', 'Frames', 'Type', 'Size', 'Comment'])
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.setSelectionBehavior(QtWidgets.QTableWidget.SelectRows)
        self.table_view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)  # Multi-select
        self.table_view.itemClicked.connect(self.on_table_item_clicked)
        self.table_view.itemDoubleClicked.connect(self.on_table_item_double_clicked)
        self.table_view.setMouseTracking(True)  # Enable hover tracking
        self.table_view.viewport().installEventFilter(self)  # Install event filter
        self.view_stack.addWidget(self.table_view)
        
        layout.addWidget(self.view_stack)
        
        # Info label
        self.info_label = QtWidgets.QLabel("Select a list to view elements")
        self.info_label.setAlignment(QtCore.Qt.AlignCenter)
        self.info_label.setStyleSheet("color: gray; font-size: 12px; padding: 20px;")
        layout.addWidget(self.info_label)
    
    def set_view_mode(self, mode):
        """Switch between gallery and list view."""
        self.view_mode = mode
        
        if mode == 'gallery':
            self.view_stack.setCurrentWidget(self.gallery_view)
            self.gallery_btn.setChecked(True)
            self.list_btn.setChecked(False)
            self.size_slider.setEnabled(True)
        else:
            self.view_stack.setCurrentWidget(self.table_view)
            self.list_btn.setChecked(True)
            self.gallery_btn.setChecked(False)
            self.size_slider.setEnabled(False)
    
    def on_size_changed(self, value):
        """Handle thumbnail size change."""
        self.gallery_view.setIconSize(QtCore.QSize(value, value))
    
    def load_elements(self, list_id):
        """Load elements for a list with preview caching."""
        self.current_list_id = list_id
        elements = self.db.get_elements_by_list(list_id)
        
        self.info_label.setVisible(len(elements) == 0)
        
        if len(elements) > 0:
            self.info_label.setText("")
        else:
            lst = self.db.get_list_by_id(list_id)
            if lst:
                self.info_label.setText("No elements in '{}'".format(lst['name']))
        
        # Update gallery view with cached previews
        self.gallery_view.clear()
        for element in elements:
            item = QtWidgets.QListWidgetItem()
            item.setText(element['name'])
            item.setData(QtCore.Qt.UserRole, element['element_id'])
            
            # Load preview with caching
            if element['preview_path'] and os.path.exists(element['preview_path']):
                # Try cache first
                cached_pixmap = self.preview_cache.get(element['preview_path'])
                if cached_pixmap:
                    item.setIcon(QtGui.QIcon(cached_pixmap))
                else:
                    # Load from disk and cache
                    pixmap = QtGui.QPixmap(element['preview_path'])
                    self.preview_cache.put(element['preview_path'], pixmap)
                    item.setIcon(QtGui.QIcon(pixmap))
            else:
                # Default icon based on type
                if element['type'] == '2D':
                    item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon))
                elif element['type'] == '3D':
                    item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DriveFDIcon))
                else:
                    item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogDetailedView))
            
            self.gallery_view.addItem(item)
        
        # Update table view
        self.table_view.setRowCount(len(elements))
        for row, element in enumerate(elements):
            self.table_view.setItem(row, 0, QtWidgets.QTableWidgetItem(element['name']))
            self.table_view.setItem(row, 1, QtWidgets.QTableWidgetItem(element['format'] or ''))
            self.table_view.setItem(row, 2, QtWidgets.QTableWidgetItem(element['frame_range'] or ''))
            self.table_view.setItem(row, 3, QtWidgets.QTableWidgetItem(element['type']))
            
            # Format file size
            size_str = ''
            if element['file_size']:
                size_mb = element['file_size'] / (1024.0 * 1024.0)
                if size_mb < 1024:
                    size_str = "{:.1f} MB".format(size_mb)
                else:
                    size_str = "{:.2f} GB".format(size_mb / 1024.0)
            self.table_view.setItem(row, 4, QtWidgets.QTableWidgetItem(size_str))
            
            self.table_view.setItem(row, 5, QtWidgets.QTableWidgetItem(element['comment'] or ''))
            
            # Store element_id in first column
            self.table_view.item(row, 0).setData(QtCore.Qt.UserRole, element['element_id'])
    
    def on_search(self, text):
        """Handle search text change (live filter)."""
        if not self.current_list_id:
            return
        
        # Get all elements
        elements = self.db.get_elements_by_list(self.current_list_id)
        
        # Filter by search text
        if text:
            filtered = [e for e in elements if text.lower() in e['name'].lower()]
        else:
            filtered = elements
        
        # Update gallery view
        self.gallery_view.clear()
        for element in filtered:
            item = QtWidgets.QListWidgetItem()
            item.setText(element['name'])
            item.setData(QtCore.Qt.UserRole, element['element_id'])
            
            if element['preview_path'] and os.path.exists(element['preview_path']):
                pixmap = QtGui.QPixmap(element['preview_path'])
                item.setIcon(QtGui.QIcon(pixmap))
            else:
                if element['type'] == '2D':
                    item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon))
                elif element['type'] == '3D':
                    item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DriveFDIcon))
                else:
                    item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogDetailedView))
            
            self.gallery_view.addItem(item)
        
        # Update table view
        self.table_view.setRowCount(len(filtered))
        for row, element in enumerate(filtered):
            self.table_view.setItem(row, 0, QtWidgets.QTableWidgetItem(element['name']))
            self.table_view.setItem(row, 1, QtWidgets.QTableWidgetItem(element['format'] or ''))
            self.table_view.setItem(row, 2, QtWidgets.QTableWidgetItem(element['frame_range'] or ''))
            self.table_view.setItem(row, 3, QtWidgets.QTableWidgetItem(element['type']))
            
            size_str = ''
            if element['file_size']:
                size_mb = element['file_size'] / (1024.0 * 1024.0)
                if size_mb < 1024:
                    size_str = "{:.1f} MB".format(size_mb)
                else:
                    size_str = "{:.2f} GB".format(size_mb / 1024.0)
            self.table_view.setItem(row, 4, QtWidgets.QTableWidgetItem(size_str))
            
            self.table_view.setItem(row, 5, QtWidgets.QTableWidgetItem(element['comment'] or ''))
            self.table_view.item(row, 0).setData(QtCore.Qt.UserRole, element['element_id'])
    
    def on_item_clicked(self, item):
        """Handle gallery item click."""
        element_id = item.data(QtCore.Qt.UserRole)
        self.element_selected.emit(element_id)
    
    def on_item_double_clicked(self, item):
        """Handle gallery item double-click."""
        element_id = item.data(QtCore.Qt.UserRole)
        self.element_double_clicked.emit(element_id)
    
    def on_table_item_clicked(self, item):
        """Handle table item click."""
        element_id = self.table_view.item(item.row(), 0).data(QtCore.Qt.UserRole)
        self.element_selected.emit(element_id)
    
    def on_table_item_double_clicked(self, item):
        """Handle table item double-click."""
        element_id = self.table_view.item(item.row(), 0).data(QtCore.Qt.UserRole)
        self.element_double_clicked.emit(element_id)
    
    def eventFilter(self, obj, event):
        """Event filter to handle Alt+Hover."""
        # Check if widgets are initialized
        if not hasattr(self, 'gallery_view') or not hasattr(self, 'table_view'):
            return super(MediaDisplayWidget, self).eventFilter(obj, event)
        
        if obj in [self.gallery_view.viewport(), self.table_view.viewport()]:
            if event.type() == QtCore.QEvent.MouseMove:
                # Check if Alt is pressed
                modifiers = QtWidgets.QApplication.keyboardModifiers()
                self.alt_pressed = (modifiers & QtCore.Qt.AltModifier)
                
                if self.alt_pressed:
                    # Get item under cursor
                    pos = event.pos()
                    
                    if obj == self.gallery_view.viewport():
                        item = self.gallery_view.itemAt(pos)
                        if item and item != self.hover_item:
                            self.hover_item = item
                            self.hover_timer.stop()
                            self.hover_timer.start(500)  # 500ms delay
                    elif obj == self.table_view.viewport():
                        item = self.table_view.itemAt(pos)
                        if item and item != self.hover_item:
                            self.hover_item = item
                            self.hover_timer.stop()
                            self.hover_timer.start(500)  # 500ms delay
                else:
                    # Hide popup if Alt released
                    if self.media_popup.isVisible():
                        self.media_popup.hide()
                    self.hover_timer.stop()
                    self.hover_item = None
            
            elif event.type() == QtCore.QEvent.Leave:
                # Hide popup when leaving widget
                self.hover_timer.stop()
                self.hover_item = None
        
        return super(MediaDisplayWidget, self).eventFilter(obj, event)
    
    def keyPressEvent(self, event):
        """Handle key press events."""
        if event.key() == QtCore.Qt.Key_Alt:
            self.alt_pressed = True
        super(MediaDisplayWidget, self).keyPressEvent(event)
    
    def keyReleaseEvent(self, event):
        """Handle key release events."""
        if event.key() == QtCore.Qt.Key_Alt:
            self.alt_pressed = False
            if self.media_popup.isVisible():
                self.media_popup.hide()
            self.hover_timer.stop()
        super(MediaDisplayWidget, self).keyReleaseEvent(event)
    
    def show_info_popup(self):
        """Show media info popup for hovered item."""
        if not self.hover_item or not self.alt_pressed:
            return
        
        # Get element ID from item
        element_id = None
        
        if self.view_mode == 'gallery':
            element_id = self.hover_item.data(QtCore.Qt.UserRole)
        else:  # list view
            element_id = self.table_view.item(self.hover_item.row(), 0).data(QtCore.Qt.UserRole)
        
        if element_id:
            element_data = self.db.get_element_by_id(element_id)
            if element_data:
                # Get global cursor position
                cursor_pos = QtGui.QCursor.pos()
                self.media_popup.show_element(element_data, cursor_pos)
    
    def on_popup_insert(self, element_id):
        """Handle insert request from popup."""
        self.element_double_clicked.emit(element_id)
    
    def on_popup_reveal(self, filepath):
        """Handle reveal request from popup."""
        if filepath and os.path.exists(filepath):
            # Reveal in file explorer
            import subprocess
            import platform
            
            # Get directory path
            if os.path.isfile(filepath):
                directory = os.path.dirname(filepath)
            else:
                directory = filepath
            
            # Open in OS file explorer
            if platform.system() == 'Windows':
                subprocess.Popen(['explorer', '/select,', os.path.normpath(filepath)])
            elif platform.system() == 'Darwin':  # macOS
                subprocess.Popen(['open', '-R', filepath])
            else:  # Linux
                subprocess.Popen(['xdg-open', directory])
    
    def show_context_menu(self, position, element_id):
        """
        Show context menu for element.
        
        Args:
            position (QPoint): Position to show menu
            element_id (int): Element ID
        """
        menu = QtWidgets.QMenu(self)
        
        # Check if already favorited
        is_fav = self.db.is_favorite(
            element_id,
            self.config.get('user_name'),
            self.config.get('machine_name')
        )
        
        # Add/Remove favorite action
        if is_fav:
            fav_action = menu.addAction("⭐ Remove from Favorites")
        else:
            fav_action = menu.addAction("☆ Add to Favorites")
        
        # Add to playlist action
        add_playlist_action = menu.addAction("📋 Add to Playlist...")
        
        menu.addSeparator()
        
        # Insert into Nuke action
        insert_action = menu.addAction("Insert into Nuke")
        
        # Edit metadata action
        edit_action = menu.addAction("✏ Edit Metadata...")
        
        menu.addSeparator()
        
        # Get element to check deprecated status
        element = self.db.get_element_by_id(element_id)
        
        # Toggle deprecated action
        if element and element.get('is_deprecated'):
            deprecated_action = menu.addAction("↺ Unmark as Deprecated")
        else:
            deprecated_action = menu.addAction("⚠ Mark as Deprecated")
        
        # Delete action
        delete_action = menu.addAction("🗑 Delete Element")
        delete_action.setStyleSheet("color: #ff5555;")
        
        # Execute menu
        action = menu.exec_(position)
        
        if action == fav_action:
            self.toggle_favorite(element_id)
        elif action == add_playlist_action:
            self.add_to_playlist(element_id)
        elif action == insert_action:
            self.element_double_clicked.emit(element_id)
        elif action == edit_action:
            self.edit_element(element_id)
        elif action == deprecated_action:
            self.toggle_deprecated(element_id)
        elif action == delete_action:
            self.delete_element(element_id)
    
    def add_to_playlist(self, element_id):
        """Show dialog to add element to playlist."""
        dialog = AddToPlaylistDialog(self.db, element_id, self)
        dialog.exec_()
    
    def toggle_favorite(self, element_id):
        """Toggle favorite status of element."""
        user = self.config.get('user_name')
        machine = self.config.get('machine_name')
        
        is_fav = self.db.is_favorite(element_id, user, machine)
        
        if is_fav:
            self.db.remove_favorite(element_id, user, machine)
        else:
            self.db.add_favorite(element_id, user, machine)
        
        # Refresh display to update star icons
        if self.current_list_id:
            self.load_elements(self.current_list_id)
    
    def edit_element(self, element_id):
        """Show edit element dialog."""
        try:
            dialog = EditElementDialog(self.db, element_id, self)
            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                # Refresh display
                if self.current_list_id:
                    self.load_elements(self.current_list_id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to open edit dialog: {}".format(str(e)))
    
    def toggle_deprecated(self, element_id):
        """Toggle deprecated status of element."""
        try:
            element = self.db.get_element_by_id(element_id)
            if not element:
                return
            
            # Toggle deprecated status
            new_status = 0 if element.get('is_deprecated') else 1
            self.db.update_element(element_id, is_deprecated=new_status)
            
            status_text = "deprecated" if new_status else "active"
            QtWidgets.QMessageBox.information(self, "Success", "Element marked as {}.".format(status_text))
            
            # Refresh display
            if self.current_list_id:
                self.load_elements(self.current_list_id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to update element: {}".format(str(e)))
    
    def delete_element(self, element_id):
        """Delete element after confirmation."""
        try:
            element = self.db.get_element_by_id(element_id)
            if not element:
                return
            
            # Confirmation dialog
            reply = QtWidgets.QMessageBox.question(
                self,
                "Confirm Deletion",
                "Are you sure you want to delete '{}'?\n\nThis action cannot be undone.".format(element['name']),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )
            
            if reply == QtWidgets.QMessageBox.Yes:
                # Delete from database
                self.db.delete_element(element_id)
                
                # TODO: Optionally delete physical files
                # filepath = element.get('filepath_hard') or element.get('filepath_soft')
                # if filepath and os.path.exists(filepath):
                #     os.remove(filepath)
                
                QtWidgets.QMessageBox.information(self, "Success", "Element deleted successfully.")
                
                # Refresh display
                if self.current_list_id:
                    self.load_elements(self.current_list_id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to delete element: {}".format(str(e)))
    
    def show_bulk_menu(self):
        """Show bulk operations menu."""
        # Get selected elements
        selected_ids = self.get_selected_element_ids()
        
        if not selected_ids:
            QtWidgets.QMessageBox.information(self, "No Selection", "Please select one or more elements.\n\nTip: Hold Ctrl/Cmd to select multiple items.")
            return
        
        # Create menu
        menu = QtWidgets.QMenu(self)
        
        # Bulk add to favorites
        bulk_fav_action = menu.addAction("⭐ Add All to Favorites")
        
        # Bulk add to playlist
        bulk_playlist_action = menu.addAction("📋 Add All to Playlist...")
        
        menu.addSeparator()
        
        # Bulk mark as deprecated
        bulk_deprecate_action = menu.addAction("⚠ Mark All as Deprecated")
        
        # Bulk delete
        bulk_delete_action = menu.addAction("🗑 Delete All Selected")
        bulk_delete_action.setStyleSheet("color: #ff5555;")
        
        # Execute menu
        action = menu.exec_(QtGui.QCursor.pos())
        
        if action == bulk_fav_action:
            self.bulk_add_to_favorites(selected_ids)
        elif action == bulk_playlist_action:
            self.bulk_add_to_playlist(selected_ids)
        elif action == bulk_deprecate_action:
            self.bulk_mark_deprecated(selected_ids)
        elif action == bulk_delete_action:
            self.bulk_delete(selected_ids)
    
    def get_selected_element_ids(self):
        """Get list of selected element IDs from current view."""
        selected_ids = []
        
        if self.view_mode == 'gallery':
            for item in self.gallery_view.selectedItems():
                element_id = item.data(QtCore.Qt.UserRole)
                if element_id:
                    selected_ids.append(element_id)
        else:  # list view
            for item in self.table_view.selectedItems():
                # Only get from first column to avoid duplicates
                if item.column() == 0:
                    element_id = item.data(QtCore.Qt.UserRole)
                    if element_id:
                        selected_ids.append(element_id)
        
        return selected_ids
    
    def bulk_add_to_favorites(self, element_ids):
        """Add multiple elements to favorites."""
        user = self.config.get('user_name')
        machine = self.config.get('machine_name')
        
        added_count = 0
        for element_id in element_ids:
            if not self.db.is_favorite(element_id, user, machine):
                self.db.add_favorite(element_id, user, machine)
                added_count += 1
        
        QtWidgets.QMessageBox.information(
            self,
            "Success",
            "Added {} element(s) to favorites.".format(added_count)
        )
        
        # Refresh display
        if self.current_list_id:
            self.load_elements(self.current_list_id)
    
    def bulk_add_to_playlist(self, element_ids):
        """Add multiple elements to a playlist."""
        # Get all playlists
        playlists = self.db.get_all_playlists()
        
        if not playlists:
            QtWidgets.QMessageBox.warning(self, "No Playlists", "No playlists available. Create one first.")
            return
        
        # Simple selection dialog
        playlist_names = [p['name'] for p in playlists]
        playlist_name, ok = QtWidgets.QInputDialog.getItem(
            self,
            "Select Playlist",
            "Choose playlist to add {} element(s) to:".format(len(element_ids)),
            playlist_names,
            0,
            False
        )
        
        if ok and playlist_name:
            # Find playlist ID
            playlist_id = None
            for p in playlists:
                if p['name'] == playlist_name:
                    playlist_id = p['playlist_id']
                    break
            
            if playlist_id:
                added_count = 0
                for element_id in element_ids:
                    result = self.db.add_element_to_playlist(playlist_id, element_id)
                    if result is not None:
                        added_count += 1
                
                QtWidgets.QMessageBox.information(
                    self,
                    "Success",
                    "Added {} element(s) to playlist '{}'.".format(added_count, playlist_name)
                )
    
    def bulk_mark_deprecated(self, element_ids):
        """Mark multiple elements as deprecated."""
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Bulk Operation",
            "Mark {} element(s) as deprecated?".format(len(element_ids)),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            for element_id in element_ids:
                self.db.update_element(element_id, is_deprecated=1)
            
            QtWidgets.QMessageBox.information(
                self,
                "Success",
                "Marked {} element(s) as deprecated.".format(len(element_ids))
            )
            
            # Refresh display
            if self.current_list_id:
                self.load_elements(self.current_list_id)
    
    def bulk_delete(self, element_ids):
        """Delete multiple elements."""
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Bulk Deletion",
            "Are you sure you want to delete {} element(s)?\n\nThis action cannot be undone.".format(len(element_ids)),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            for element_id in element_ids:
                self.db.delete_element(element_id)
            
            QtWidgets.QMessageBox.information(
                self,
                "Success",
                "Deleted {} element(s).".format(len(element_ids))
            )
            
            # Refresh display
            if self.current_list_id:
                self.load_elements(self.current_list_id)
    
    def load_favorites(self):
        """Load and display favorite elements."""
        user = self.config.get('user_name')
        machine = self.config.get('machine_name')
        
        favorites = self.db.get_favorites(user, machine)
        
        self.current_list_id = None  # Clear current list
        self.info_label.setText("Favorites ({} items)".format(len(favorites)))
        
        # Update gallery view
        self.gallery_view.clear()
        for element in favorites:
            item = QtWidgets.QListWidgetItem()
            item.setText("⭐ " + element['name'])  # Add star prefix
            item.setData(QtCore.Qt.UserRole, element['element_id'])
            
            if element['preview_path'] and os.path.exists(element['preview_path']):
                pixmap = QtGui.QPixmap(element['preview_path'])
                item.setIcon(QtGui.QIcon(pixmap))
            else:
                if element['type'] == '2D':
                    item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon))
                elif element['type'] == '3D':
                    item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DriveFDIcon))
                else:
                    item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogDetailedView))
            
            self.gallery_view.addItem(item)
        
        # Update table view
        self.table_view.setRowCount(len(favorites))
        for row, element in enumerate(favorites):
            self.table_view.setItem(row, 0, QtWidgets.QTableWidgetItem("⭐ " + element['name']))
            self.table_view.setItem(row, 1, QtWidgets.QTableWidgetItem(element['format'] or ''))
            self.table_view.setItem(row, 2, QtWidgets.QTableWidgetItem(element['frame_range'] or ''))
            self.table_view.setItem(row, 3, QtWidgets.QTableWidgetItem(element['type']))
            
            size_str = ''
            if element['file_size']:
                size_mb = element['file_size'] / (1024.0 * 1024.0)
                if size_mb < 1024:
                    size_str = "{:.1f} MB".format(size_mb)
                else:
                    size_str = "{:.2f} GB".format(size_mb / 1024.0)
            self.table_view.setItem(row, 4, QtWidgets.QTableWidgetItem(size_str))
            
            self.table_view.setItem(row, 5, QtWidgets.QTableWidgetItem(element['comment'] or ''))
            self.table_view.item(row, 0).setData(QtCore.Qt.UserRole, element['element_id'])
    
    def load_playlist(self, playlist_id):
        """Load and display playlist elements."""
        playlist = self.db.get_playlist_by_id(playlist_id)
        if not playlist:
            return
        
        elements = self.db.get_playlist_elements(playlist_id)
        
        self.current_list_id = None  # Clear current list
        self.info_label.setText("Playlist: {} ({} items)".format(playlist['name'], len(elements)))
        
        # Update gallery view
        self.gallery_view.clear()
        for element in elements:
            item = QtWidgets.QListWidgetItem()
            item.setText("📋 " + element['name'])  # Add playlist prefix
            item.setData(QtCore.Qt.UserRole, element['element_id'])
            
            if element['preview_path'] and os.path.exists(element['preview_path']):
                pixmap = QtGui.QPixmap(element['preview_path'])
                item.setIcon(QtGui.QIcon(pixmap))
            else:
                if element['type'] == '2D':
                    item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon))
                elif element['type'] == '3D':
                    item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DriveFDIcon))
                else:
                    item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogDetailedView))
            
            self.gallery_view.addItem(item)
        
        # Update table view
        self.table_view.setRowCount(len(elements))
        for row, element in enumerate(elements):
            self.table_view.setItem(row, 0, QtWidgets.QTableWidgetItem("📋 " + element['name']))
            self.table_view.setItem(row, 1, QtWidgets.QTableWidgetItem(element['format'] or ''))
            self.table_view.setItem(row, 2, QtWidgets.QTableWidgetItem(element['frame_range'] or ''))
            self.table_view.setItem(row, 3, QtWidgets.QTableWidgetItem(element['type']))
            
            size_str = ''
            if element['file_size']:
                size_mb = element['file_size'] / (1024.0 * 1024.0)
                if size_mb < 1024:
                    size_str = "{:.1f} MB".format(size_mb)
                else:
                    size_str = "{:.2f} GB".format(size_mb / 1024.0)
            self.table_view.setItem(row, 4, QtWidgets.QTableWidgetItem(size_str))
            
            self.table_view.setItem(row, 5, QtWidgets.QTableWidgetItem(element['comment'] or ''))
            self.table_view.item(row, 0).setData(QtCore.Qt.UserRole, element['element_id'])
    
    def contextMenuEvent(self, event):
        """Handle context menu request."""
        # Get item under cursor
        if self.view_mode == 'gallery':
            item = self.gallery_view.itemAt(self.gallery_view.viewport().mapFromGlobal(event.globalPos()))
            if item:
                element_id = item.data(QtCore.Qt.UserRole)
                self.show_context_menu(event.globalPos(), element_id)
        else:
            item = self.table_view.itemAt(self.table_view.viewport().mapFromGlobal(event.globalPos()))
            if item:
                element_id = self.table_view.item(item.row(), 0).data(QtCore.Qt.UserRole)
                self.show_context_menu(event.globalPos(), element_id)


class HistoryPanel(QtWidgets.QWidget):
    """Panel for displaying ingestion history."""
    
    def __init__(self, db_manager, parent=None):
        super(HistoryPanel, self).__init__(parent)
        self.db = db_manager
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Title
        title_layout = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Ingestion History")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(title)
        
        # Export button
        export_btn = QtWidgets.QPushButton("Export CSV")
        export_btn.clicked.connect(self.export_csv)
        title_layout.addWidget(export_btn)
        title_layout.addStretch()
        
        layout.addLayout(title_layout)
        
        # Table
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(['Date/Time', 'Action', 'Source', 'Target', 'Status'])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        
        # Refresh button
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_history)
        layout.addWidget(refresh_btn)
    
    def load_history(self, limit=100):
        """Load history from database."""
        history = self.db.get_ingestion_history(limit)
        
        self.table.setRowCount(len(history))
        for row, entry in enumerate(history):
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(entry['ingested_at']))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(entry['action']))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(entry['source_path'] or ''))
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(entry['target_list'] or ''))
            
            status_item = QtWidgets.QTableWidgetItem(entry['status'])
            if entry['status'] == 'error':
                status_item.setForeground(QtGui.QColor('red'))
            else:
                status_item.setForeground(QtGui.QColor('green'))
            self.table.setItem(row, 4, status_item)
    
    def export_csv(self):
        """Export history to CSV."""
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export History", "", "CSV Files (*.csv)"
        )
        if filename:
            self.db.export_history_to_csv(filename)
            QtWidgets.QMessageBox.information(self, "Export Complete", "History exported to {}".format(filename))


class SettingsPanel(QtWidgets.QWidget):
    """Panel for application settings."""
    
    settings_changed = QtCore.Signal()
    
    def __init__(self, config, parent=None):
        super(SettingsPanel, self).__init__(parent)
        self.config = config
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Title
        title = QtWidgets.QLabel("Settings")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        # Scroll area for settings
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QFormLayout(scroll_widget)
        
        # Ingestion settings
        group1 = QtWidgets.QGroupBox("Ingestion Settings")
        group1_layout = QtWidgets.QFormLayout()
        
        self.copy_policy = QtWidgets.QComboBox()
        self.copy_policy.addItems(['soft', 'hard'])
        self.copy_policy.setCurrentText(self.config.get('default_copy_policy'))
        group1_layout.addRow("Default Copy Policy:", self.copy_policy)
        
        self.auto_detect = QtWidgets.QCheckBox()
        self.auto_detect.setChecked(self.config.get('auto_detect_sequences'))
        group1_layout.addRow("Auto-detect Sequences:", self.auto_detect)
        
        self.gen_previews = QtWidgets.QCheckBox()
        self.gen_previews.setChecked(self.config.get('generate_previews'))
        group1_layout.addRow("Generate Previews:", self.gen_previews)
        
        group1.setLayout(group1_layout)
        scroll_layout.addRow(group1)
        
        # Processor hooks
        group2 = QtWidgets.QGroupBox("Custom Processors")
        group2_layout = QtWidgets.QFormLayout()
        
        self.pre_ingest = QtWidgets.QLineEdit(self.config.get('pre_ingest_processor') or '')
        pre_ingest_browse = QtWidgets.QPushButton("Browse...")
        pre_ingest_browse.clicked.connect(lambda: self.browse_file(self.pre_ingest))
        pre_layout = QtWidgets.QHBoxLayout()
        pre_layout.addWidget(self.pre_ingest)
        pre_layout.addWidget(pre_ingest_browse)
        group2_layout.addRow("Pre-Ingest Hook:", pre_layout)
        
        self.post_ingest = QtWidgets.QLineEdit(self.config.get('post_ingest_processor') or '')
        post_ingest_browse = QtWidgets.QPushButton("Browse...")
        post_ingest_browse.clicked.connect(lambda: self.browse_file(self.post_ingest))
        post_layout = QtWidgets.QHBoxLayout()
        post_layout.addWidget(self.post_ingest)
        post_layout.addWidget(post_ingest_browse)
        group2_layout.addRow("Post-Ingest Hook:", post_layout)
        
        self.post_import = QtWidgets.QLineEdit(self.config.get('post_import_processor') or '')
        post_import_browse = QtWidgets.QPushButton("Browse...")
        post_import_browse.clicked.connect(lambda: self.browse_file(self.post_import))
        import_layout = QtWidgets.QHBoxLayout()
        import_layout.addWidget(self.post_import)
        import_layout.addWidget(post_import_browse)
        group2_layout.addRow("Post-Import Hook:", import_layout)
        
        group2.setLayout(group2_layout)
        scroll_layout.addRow(group2)
        
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        save_btn = QtWidgets.QPushButton("Save")
        save_btn.clicked.connect(self.save_settings)
        button_layout.addWidget(save_btn)
        
        reset_btn = QtWidgets.QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self.reset_settings)
        button_layout.addWidget(reset_btn)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
    
    def browse_file(self, line_edit):
        """Browse for processor script file."""
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Processor Script", "", "Python Files (*.py)"
        )
        if filename:
            line_edit.setText(filename)
    
    def save_settings(self):
        """Save settings to config."""
        self.config.set('default_copy_policy', self.copy_policy.currentText())
        self.config.set('auto_detect_sequences', self.auto_detect.isChecked())
        self.config.set('generate_previews', self.gen_previews.isChecked())
        self.config.set('pre_ingest_processor', self.pre_ingest.text() or None)
        self.config.set('post_ingest_processor', self.post_ingest.text() or None)
        self.config.set('post_import_processor', self.post_import.text() or None)
        
        QtWidgets.QMessageBox.information(self, "Settings Saved", "Settings have been saved successfully.")
        self.settings_changed.emit()
    
    def reset_settings(self):
        """Reset settings to defaults."""
        reply = QtWidgets.QMessageBox.question(
            self, "Reset Settings",
            "Are you sure you want to reset all settings to defaults?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            self.config.reset_to_defaults()
            self.setup_ui()  # Reload UI
            QtWidgets.QMessageBox.information(self, "Settings Reset", "Settings have been reset to defaults.")
            self.settings_changed.emit()


class AddStackDialog(QtWidgets.QDialog):
    """Dialog for adding a new stack."""
    
    def __init__(self, db_manager, parent=None):
        super(AddStackDialog, self).__init__(parent)
        self.db = db_manager
        self.setWindowTitle("Add Stack")
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QFormLayout(self)
        
        self.name_edit = QtWidgets.QLineEdit()
        layout.addRow("Stack Name:", self.name_edit)
        
        path_layout = QtWidgets.QHBoxLayout()
        self.path_edit = QtWidgets.QLineEdit()
        path_layout.addWidget(self.path_edit)
        
        browse_btn = QtWidgets.QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_path)
        path_layout.addWidget(browse_btn)
        
        layout.addRow("Repository Path:", path_layout)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)
    
    def browse_path(self):
        """Browse for repository path."""
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Repository Path")
        if path:
            self.path_edit.setText(path)
    
    def accept(self):
        """Validate and create stack."""
        name = self.name_edit.text().strip()
        path = self.path_edit.text().strip()
        
        if not name or not path:
            QtWidgets.QMessageBox.warning(self, "Invalid Input", "Please provide both name and path.")
            return
        
        try:
            self.db.create_stack(name, path)
            super(AddStackDialog, self).accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to create stack: {}".format(str(e)))


class AddListDialog(QtWidgets.QDialog):
    """Dialog for adding a new list."""
    
    def __init__(self, db_manager, default_stack_id=None, parent=None):
        super(AddListDialog, self).__init__(parent)
        self.db = db_manager
        self.default_stack_id = default_stack_id
        self.setWindowTitle("Add List")
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QFormLayout(self)
        
        # Stack selection
        self.stack_combo = QtWidgets.QComboBox()
        stacks = self.db.get_all_stacks()
        for stack in stacks:
            self.stack_combo.addItem(stack['name'], stack['stack_id'])
        
        if self.default_stack_id:
            index = self.stack_combo.findData(self.default_stack_id)
            if index >= 0:
                self.stack_combo.setCurrentIndex(index)
        
        layout.addRow("Parent Stack:", self.stack_combo)
        
        self.name_edit = QtWidgets.QLineEdit()
        layout.addRow("List Name:", self.name_edit)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)
    
    def accept(self):
        """Validate and create list."""
        name = self.name_edit.text().strip()
        stack_id = self.stack_combo.currentData()
        
        if not name:
            QtWidgets.QMessageBox.warning(self, "Invalid Input", "Please provide a list name.")
            return
        
        try:
            self.db.create_list(stack_id, name)
            super(AddListDialog, self).accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to create list: {}".format(str(e)))


class CreatePlaylistDialog(QtWidgets.QDialog):
    """Dialog for creating a new playlist."""
    
    def __init__(self, db_manager, config, parent=None):
        super(CreatePlaylistDialog, self).__init__(parent)
        self.db = db_manager
        self.config = config
        self.setWindowTitle("Create Playlist")
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QFormLayout(self)
        
        self.name_edit = QtWidgets.QLineEdit()
        layout.addRow("Playlist Name:", self.name_edit)
        
        self.desc_edit = QtWidgets.QTextEdit()
        self.desc_edit.setMaximumHeight(80)
        self.desc_edit.setPlaceholderText("Optional description...")
        layout.addRow("Description:", self.desc_edit)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)
    
    def accept(self):
        """Validate and create playlist."""
        name = self.name_edit.text().strip()
        description = self.desc_edit.toPlainText().strip()
        
        if not name:
            QtWidgets.QMessageBox.warning(self, "Invalid Input", "Please provide a playlist name.")
            return
        
        try:
            self.db.create_playlist(
                name,
                description,
                self.config.get('user_name'),
                self.config.get('machine_name')
            )
            super(CreatePlaylistDialog, self).accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to create playlist: {}".format(str(e)))


class AddToPlaylistDialog(QtWidgets.QDialog):
    """Dialog for adding element to playlist."""
    
    def __init__(self, db_manager, element_id, parent=None):
        super(AddToPlaylistDialog, self).__init__(parent)
        self.db = db_manager
        self.element_id = element_id
        self.setWindowTitle("Add to Playlist")
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        
        label = QtWidgets.QLabel("Select playlist to add element:")
        layout.addWidget(label)
        
        # List of playlists
        self.playlist_list = QtWidgets.QListWidget()
        playlists = self.db.get_all_playlists()
        
        for playlist in playlists:
            # Check if element already in playlist
            is_in = self.db.is_element_in_playlist(playlist['playlist_id'], self.element_id)
            
            item = QtWidgets.QListWidgetItem()
            if is_in:
                item.setText("✓ " + playlist['name'] + " (already added)")
                item.setForeground(QtGui.QColor('gray'))
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEnabled)
            else:
                item.setText(playlist['name'])
            
            item.setData(QtCore.Qt.UserRole, playlist['playlist_id'])
            self.playlist_list.addItem(item)
        
        layout.addWidget(self.playlist_list)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def accept(self):
        """Add element to selected playlist."""
        current = self.playlist_list.currentItem()
        if not current:
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select a playlist.")
            return
        
        playlist_id = current.data(QtCore.Qt.UserRole)
        
        try:
            result = self.db.add_element_to_playlist(playlist_id, self.element_id)
            if result is None:
                QtWidgets.QMessageBox.information(self, "Already Added", "Element is already in this playlist.")
            else:
                super(AddToPlaylistDialog, self).accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to add element: {}".format(str(e)))


class EditElementDialog(QtWidgets.QDialog):
    """Dialog for editing element metadata."""
    
    def __init__(self, db_manager, element_id, parent=None):
        super(EditElementDialog, self).__init__(parent)
        self.db = db_manager
        self.element_id = element_id
        self.element_data = self.db.get_element_by_id(element_id)
        
        if not self.element_data:
            raise ValueError("Element not found")
        
        self.setWindowTitle("Edit Element: {}".format(self.element_data['name']))
        self.setModal(True)
        self.setup_ui()
        self.load_data()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Form layout for fields
        form = QtWidgets.QFormLayout()
        
        # Name (read-only for display)
        self.name_label = QtWidgets.QLabel(self.element_data['name'])
        self.name_label.setStyleSheet("font-weight: bold; color: #ffffff;")
        form.addRow("Name:", self.name_label)
        
        # Type (read-only)
        self.type_label = QtWidgets.QLabel(self.element_data['type'])
        form.addRow("Type:", self.type_label)
        
        # Format (read-only)
        format_str = self.element_data.get('format', 'N/A') or 'N/A'
        self.format_label = QtWidgets.QLabel(format_str)
        form.addRow("Format:", self.format_label)
        
        # Frame Range (editable for sequences)
        self.frame_range_edit = QtWidgets.QLineEdit()
        self.frame_range_edit.setPlaceholderText("e.g., 1001-1100")
        form.addRow("Frame Range:", self.frame_range_edit)
        
        # Comment (editable)
        self.comment_edit = QtWidgets.QTextEdit()
        self.comment_edit.setPlaceholderText("Add descriptive comment...")
        self.comment_edit.setMaximumHeight(80)
        form.addRow("Comment:", self.comment_edit)
        
        # Tags (editable)
        self.tags_edit = QtWidgets.QLineEdit()
        self.tags_edit.setPlaceholderText("Comma-separated tags")
        form.addRow("Tags:", self.tags_edit)
        
        # Deprecated checkbox
        self.deprecated_checkbox = QtWidgets.QCheckBox("Mark as Deprecated")
        self.deprecated_checkbox.setStyleSheet("color: #ff9a3c;")
        form.addRow("", self.deprecated_checkbox)
        
        layout.addLayout(form)
        
        # Info label
        info_label = QtWidgets.QLabel("Note: Name, type, and format cannot be changed after ingestion.")
        info_label.setStyleSheet("color: #888888; font-style: italic; font-size: 11px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Button box
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.save_changes)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def load_data(self):
        """Load element data into form fields."""
        self.frame_range_edit.setText(self.element_data.get('frame_range', '') or '')
        self.comment_edit.setPlainText(self.element_data.get('comment', '') or '')
        self.tags_edit.setText(self.element_data.get('tags', '') or '')
        self.deprecated_checkbox.setChecked(self.element_data.get('is_deprecated', 0) == 1)
    
    def save_changes(self):
        """Save changes to database."""
        try:
            # Gather updated data
            updates = {
                'frame_range': self.frame_range_edit.text().strip() or None,
                'comment': self.comment_edit.toPlainText().strip() or None,
                'tags': self.tags_edit.text().strip() or None,
                'is_deprecated': 1 if self.deprecated_checkbox.isChecked() else 0
            }
            
            # Update database
            self.db.update_element(self.element_id, **updates)
            
            QtWidgets.QMessageBox.information(self, "Success", "Element updated successfully!")
            self.accept()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to update element: {}".format(str(e)))


class MainWindow(QtWidgets.QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super(MainWindow, self).__init__()
        
        # Initialize core components
        self.config = Config()
        self.config.ensure_directories()
        
        self.db = DatabaseManager(self.config.get('database_path'))
        self.nuke_bridge = NukeBridge(mock_mode=self.config.get('nuke_mock_mode'))
        self.nuke_integration = NukeIntegration(self.nuke_bridge, self.db)
        self.ingestion = IngestionCore(self.db, self.config.get_all())
        self.processor_manager = ProcessorManager(self.config.get_all())
        
        self.setWindowTitle("VFX Asset Hub")
        self.resize(1400, 800)
        
        self.setup_ui()
        self.setup_shortcuts()
    
    def setup_ui(self):
        """Setup the main window UI."""
        # Central widget
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Splitter for main content
        main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        
        # Left: Stacks/Lists panel
        self.stacks_panel = StacksListsPanel(self.db, self.config)
        self.stacks_panel.list_selected.connect(self.on_list_selected)
        self.stacks_panel.favorites_selected.connect(self.on_favorites_selected)
        self.stacks_panel.playlist_selected.connect(self.on_playlist_selected)
        main_splitter.addWidget(self.stacks_panel)
        
        # Center: Media display
        self.media_display = MediaDisplayWidget(self.db, self.config)
        self.media_display.element_double_clicked.connect(self.on_element_double_clicked)
        main_splitter.addWidget(self.media_display)
        
        # Set splitter sizes
        main_splitter.setSizes([250, 1150])
        
        layout.addWidget(main_splitter)
        
        # Create dockable panels
        
        # History panel (dockable)
        self.history_dock = QtWidgets.QDockWidget("History", self)
        self.history_panel = HistoryPanel(self.db)
        self.history_dock.setWidget(self.history_panel)
        self.history_dock.setVisible(False)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.history_dock)
        
        # Settings panel (dockable)
        self.settings_dock = QtWidgets.QDockWidget("Settings", self)
        self.settings_panel = SettingsPanel(self.config)
        self.settings_panel.settings_changed.connect(self.on_settings_changed)
        self.settings_dock.setWidget(self.settings_panel)
        self.settings_dock.setVisible(False)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.settings_dock)
        
        # Menu bar
        self.create_menus()
        
        # Status bar
        self.statusBar().showMessage("Ready")
    
    def create_menus(self):
        """Create menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        ingest_action = QtWidgets.QAction("Ingest Files...", self)
        ingest_action.setShortcut("Ctrl+I")
        ingest_action.triggered.connect(self.ingest_files)
        file_menu.addAction(ingest_action)
        
        file_menu.addSeparator()
        
        exit_action = QtWidgets.QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Search menu
        search_menu = menubar.addMenu("Search")
        
        advanced_search_action = QtWidgets.QAction("Advanced Search...", self)
        advanced_search_action.setShortcut("Ctrl+F")
        advanced_search_action.triggered.connect(self.show_advanced_search)
        search_menu.addAction(advanced_search_action)
        
        # View menu
        view_menu = menubar.addMenu("View")
        
        history_action = QtWidgets.QAction("History Panel", self)
        history_action.setShortcut("Ctrl+2")
        history_action.setCheckable(True)
        history_action.triggered.connect(self.toggle_history)
        view_menu.addAction(history_action)
        
        settings_action = QtWidgets.QAction("Settings Panel", self)
        settings_action.setShortcut("Ctrl+3")
        settings_action.setCheckable(True)
        settings_action.triggered.connect(self.toggle_settings)
        view_menu.addAction(settings_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        about_action = QtWidgets.QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Ctrl+2 for history
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+2"), self, self.toggle_history)
        
        # Ctrl+3 for settings
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+3"), self, self.toggle_settings)
    
    def toggle_history(self):
        """Toggle history panel visibility."""
        visible = not self.history_dock.isVisible()
        self.history_dock.setVisible(visible)
        if visible:
            self.history_panel.load_history()
    
    def toggle_settings(self):
        """Toggle settings panel visibility."""
        self.settings_dock.setVisible(not self.settings_dock.isVisible())
    
    def on_list_selected(self, list_id):
        """Handle list selection."""
        self.media_display.load_elements(list_id)
        
        lst = self.db.get_list_by_id(list_id)
        if lst:
            stack = self.db.get_stack_by_id(lst['stack_fk'])
            if stack:
                self.statusBar().showMessage("Viewing: {} > {}".format(stack['name'], lst['name']))
    
    def on_favorites_selected(self):
        """Handle favorites button click."""
        self.media_display.load_favorites()
        self.statusBar().showMessage("Viewing: Favorites")
    
    def on_playlist_selected(self, playlist_id):
        """Handle playlist selection."""
        self.media_display.load_playlist(playlist_id)
        playlist = self.db.get_playlist_by_id(playlist_id)
        if playlist:
            self.statusBar().showMessage("Viewing Playlist: {}".format(playlist['name']))
    
    def on_element_double_clicked(self, element_id):
        """Handle element double-click (insert into Nuke)."""
        try:
            self.nuke_integration.insert_element(element_id)
            element = self.db.get_element_by_id(element_id)
            if element:
                self.statusBar().showMessage("Inserted: {}".format(element['name']))
                QtWidgets.QMessageBox.information(
                    self,
                    "Element Inserted",
                    "Element '{}' has been inserted into Nuke.".format(element['name'])
                )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to insert element: {}".format(str(e)))
    
    def ingest_files(self):
        """Open file dialog to ingest files."""
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select Files to Ingest", "", "All Files (*.*)"
        )
        
        if not files:
            return
        
        # Ask for target list
        dialog = SelectListDialog(self.db, self)
        if dialog.exec_():
            target_list_id = dialog.get_selected_list()
            if target_list_id:
                self.perform_ingestion(files, target_list_id)
    
    def perform_ingestion(self, files, target_list_id):
        """Perform ingestion of files."""
        progress = QtWidgets.QProgressDialog("Ingesting files...", "Cancel", 0, len(files), self)
        progress.setWindowModality(QtCore.Qt.WindowModal)
        
        success_count = 0
        error_count = 0
        
        for i, filepath in enumerate(files):
            if progress.wasCanceled():
                break
            
            progress.setValue(i)
            progress.setLabelText("Ingesting: {}".format(os.path.basename(filepath)))
            
            result = self.ingestion.ingest_file(
                filepath,
                target_list_id,
                copy_policy=self.config.get('default_copy_policy')
            )
            
            if result['success']:
                success_count += 1
            else:
                error_count += 1
        
        progress.setValue(len(files))
        
        # Show result
        QtWidgets.QMessageBox.information(
            self,
            "Ingestion Complete",
            "Ingested {} files successfully.\n{} errors.".format(success_count, error_count)
        )
        
        # Refresh current view
        if self.media_display.current_list_id:
            self.media_display.load_elements(self.media_display.current_list_id)
    
    def on_settings_changed(self):
        """Handle settings change."""
        # Reload processor manager
        self.processor_manager = ProcessorManager(self.config.get_all())
        self.statusBar().showMessage("Settings updated")
    
    def show_advanced_search(self):
        """Show advanced search dialog."""
        if not hasattr(self, 'advanced_search_dialog') or self.advanced_search_dialog is None:
            self.advanced_search_dialog = AdvancedSearchDialog(self.db, self)
        self.advanced_search_dialog.show()
        self.advanced_search_dialog.raise_()
    
    def on_advanced_search_result(self, element_id):
        """Handle result selection from advanced search."""
        try:
            self.nuke_integration.insert_element(element_id)
            element = self.db.get_element_by_id(element_id)
            if element:
                self.statusBar().showMessage("Inserted from search: {}".format(element['name']))
                QtWidgets.QMessageBox.information(
                    self,
                    "Element Inserted",
                    "Element '{}' has been inserted into Nuke.".format(element['name'])
                )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to insert element: {}".format(str(e)))
    
    def show_about(self):
        """Show about dialog."""
        QtWidgets.QMessageBox.about(
            self,
            "About VFX Asset Hub",
            "<h3>VFX Asset Hub</h3>"
            "<p>Version 0.1.0 (Alpha)</p>"
            "<p>Professional VFX asset management pipeline.</p>"
            "<p>Python 2.7 | PySide2</p>"
        )


class SelectListDialog(QtWidgets.QDialog):
    """Dialog for selecting a target list for ingestion."""
    
    def __init__(self, db_manager, parent=None):
        super(SelectListDialog, self).__init__(parent)
        self.db = db_manager
        self.setWindowTitle("Select Target List")
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        
        label = QtWidgets.QLabel("Select target list for ingestion:")
        layout.addWidget(label)
        
        # Tree widget showing stacks and lists
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        layout.addWidget(self.tree)
        
        # Load data
        stacks = self.db.get_all_stacks()
        for stack in stacks:
            stack_item = QtWidgets.QTreeWidgetItem([stack['name']])
            stack_item.setData(0, QtCore.Qt.UserRole, ('stack', stack['stack_id']))
            stack_item.setFlags(stack_item.flags() & ~QtCore.Qt.ItemIsSelectable)
            self.tree.addTopLevelItem(stack_item)
            
            lists = self.db.get_lists_by_stack(stack['stack_id'])
            for lst in lists:
                list_item = QtWidgets.QTreeWidgetItem([lst['name']])
                list_item.setData(0, QtCore.Qt.UserRole, ('list', lst['list_id']))
                stack_item.addChild(list_item)
            
            stack_item.setExpanded(True)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def get_selected_list(self):
        """Get selected list ID."""
        current = self.tree.currentItem()
        if current:
            data = current.data(0, QtCore.Qt.UserRole)
            if data and data[0] == 'list':
                return data[1]
        return None


def main():
    """Main entry point."""
    app = QtWidgets.QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Load and apply stylesheet
    stylesheet_path = os.path.join(os.path.dirname(__file__), 'resources', 'style.qss')
    if os.path.exists(stylesheet_path):
        try:
            with open(stylesheet_path, 'r') as f:
                stylesheet = f.read()
                app.setStyleSheet(stylesheet)
                print("Applied stylesheet from: {}".format(stylesheet_path))
        except Exception as e:
            print("Failed to load stylesheet: {}".format(e))
    else:
        print("Stylesheet not found at: {}".format(stylesheet_path))
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
