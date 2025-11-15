# -*- coding: utf-8 -*-
"""
Main GUI for StaX
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
from src.icon_loader import get_icon, get_pixmap


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
        search_btn.setIcon(get_icon('search', size=20))
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
        self.favorites_btn = QtWidgets.QPushButton("Favorites")
        self.favorites_btn.setIcon(get_icon('favorite', size=20))
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
        
        self.add_playlist_btn = QtWidgets.QPushButton("New")
        self.add_playlist_btn.setIcon(get_icon('playlist', size=16))
        self.add_playlist_btn.setMaximumWidth(80)
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
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_tree_context_menu)
        layout.addWidget(self.tree)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        self.add_stack_btn = QtWidgets.QPushButton("Stack")
        self.add_stack_btn.setIcon(get_icon('stack', size=20))
        self.add_stack_btn.setToolTip("Add new Stack")
        self.add_stack_btn.clicked.connect(self.add_stack)
        button_layout.addWidget(self.add_stack_btn)
        
        self.add_list_btn = QtWidgets.QPushButton("List")
        self.add_list_btn.setIcon(get_icon('add', size=20))
        self.add_list_btn.setToolTip("Add new List")
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
            item = QtWidgets.QListWidgetItem(playlist['name'])
            item.setIcon(get_icon('playlist', size=16))
            item.setData(QtCore.Qt.UserRole, playlist['playlist_id'])
            self.playlists_list.addItem(item)
    
    def load_data(self):
        """Load stacks, lists, and playlists from database with hierarchical sub-lists."""
        self.tree.clear()
        
        # Load playlists
        self.load_playlists()
        
        # Load stacks and lists
        stacks = self.db.get_all_stacks()
        for stack in stacks:
            stack_item = QtWidgets.QTreeWidgetItem([stack['name']])
            stack_item.setData(0, QtCore.Qt.UserRole, ('stack', stack['stack_id']))
            stack_item.setIcon(0, get_icon('stack', size=18))
            self.tree.addTopLevelItem(stack_item)
            
            # Load top-level lists for this stack (no parent)
            lists = self.db.get_lists_by_stack(stack['stack_id'], parent_list_id=None)
            for lst in lists:
                list_item = self._create_list_item(lst, stack['stack_id'])
                stack_item.addChild(list_item)
            
            stack_item.setExpanded(True)
    
    def _create_list_item(self, lst, stack_id):
        """
        Recursively create list item with sub-lists.
        
        Args:
            lst (dict): List data
            stack_id (int): Parent stack ID
            
        Returns:
            QTreeWidgetItem: Tree item with children
        """
        list_item = QtWidgets.QTreeWidgetItem([lst['name']])
        list_item.setData(0, QtCore.Qt.UserRole, ('list', lst['list_id'], stack_id))
        list_item.setIcon(0, get_icon('list', size=16))
        
        # Recursively load sub-lists
        sub_lists = self.db.get_sub_lists(lst['list_id'])
        for sub_lst in sub_lists:
            sub_item = self._create_list_item(sub_lst, stack_id)
            list_item.addChild(sub_item)
        
        return list_item
    
    def on_item_clicked(self, item, column):
        """Handle item click."""
        data = item.data(0, QtCore.Qt.UserRole)
        if data and len(data) >= 2:
            item_type = data[0]
            item_id = data[1]
            
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
        """Add new list or sub-list dialog."""
        # Get selected item
        current_item = self.tree.currentItem()
        stack_id = None
        list_id = None
        
        if current_item:
            data = current_item.data(0, QtCore.Qt.UserRole)
            if data and len(data) >= 2:
                item_type = data[0]
                item_id = data[1]
                
                if item_type == 'stack':
                    stack_id = item_id
                elif item_type == 'list':
                    # List is selected - offer to create sub-list
                    list_id = item_id
                    # Stack ID is the 3rd element if present, otherwise get from parent
                    if len(data) >= 3:
                        stack_id = data[2]
                    else:
                        parent = current_item.parent()
                        if parent:
                            parent_data = parent.data(0, QtCore.Qt.UserRole)
                            if parent_data and len(parent_data) >= 2:
                                stack_id = parent_data[1]
        
        # If a list is selected, create sub-list
        if list_id and stack_id:
            dialog = AddSubListDialog(self.db, list_id, stack_id, self)
            if dialog.exec_():
                self.load_data()
        else:
            # Otherwise, create top-level list
            dialog = AddListDialog(self.db, stack_id, self)
            if dialog.exec_():
                self.load_data()
    
    def show_tree_context_menu(self, position):
        """Show context menu for tree items."""
        item = self.tree.itemAt(position)
        if not item:
            return
        
        data = item.data(0, QtCore.Qt.UserRole)
        if not data:
            return
        
        menu = QtWidgets.QMenu(self)
        
        if len(data) >= 2:
            item_type = data[0]
            item_id = data[1]
            
            if item_type == 'stack':
                # Stack context menu
                add_list_action = menu.addAction(get_icon('add', size=16), "Add List")
                menu.addSeparator()
                delete_stack_action = menu.addAction(get_icon('delete', size=16), "Delete Stack")
                
                action = menu.exec_(self.tree.viewport().mapToGlobal(position))
                
                if action == add_list_action:
                    self.add_list_to_stack(item_id)
                elif action == delete_stack_action:
                    self.delete_stack(item_id)
                    
            elif item_type == 'list':
                # List context menu
                stack_id = data[2] if len(data) > 2 else None
                
                add_sublist_action = menu.addAction(get_icon('add', size=16), "Add Sub-List")
                menu.addSeparator()
                delete_list_action = menu.addAction(get_icon('delete', size=16), "Delete List")
                
                action = menu.exec_(self.tree.viewport().mapToGlobal(position))
                
                if action == add_sublist_action:
                    self.add_sub_list(item_id, stack_id)
                elif action == delete_list_action:
                    self.delete_list(item_id)
    
    def add_list_to_stack(self, stack_id):
        """Add a new list to a stack."""
        dialog = AddListDialog(self.db, stack_id, self)
        if dialog.exec_():
            self.load_data()
    
    def add_sub_list(self, parent_list_id, stack_id):
        """Add a sub-list under a parent list."""
        dialog = AddSubListDialog(self.db, parent_list_id, stack_id, self)
        if dialog.exec_():
            self.load_data()
    
    def delete_stack(self, stack_id):
        """Delete a stack after confirmation."""
        stack = self.db.get_stack_by_id(stack_id)
        if not stack:
            return
        
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Deletion",
            "Are you sure you want to delete Stack '{}'?\n\nThis will delete ALL lists and elements in this stack.\n\nThis action cannot be undone.".format(stack['name']),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            try:
                self.db.delete_stack(stack_id)
                QtWidgets.QMessageBox.information(self, "Success", "Stack deleted successfully.")
                self.load_data()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", "Failed to delete stack: {}".format(str(e)))
    
    def delete_list(self, list_id):
        """Delete a list after confirmation."""
        lst = self.db.get_list_by_id(list_id)
        if not lst:
            return
        
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Deletion",
            "Are you sure you want to delete List '{}'?\n\nThis will delete ALL sub-lists and elements in this list.\n\nThis action cannot be undone.".format(lst['name']),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            try:
                self.db.delete_list(list_id)
                QtWidgets.QMessageBox.information(self, "Success", "List deleted successfully.")
                self.load_data()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", "Failed to delete list: {}".format(str(e)))


class DragGalleryView(QtWidgets.QListWidget):
    """Custom QListWidget with drag & drop support for Nuke integration."""
    
    def __init__(self, db_manager, nuke_bridge, parent=None):
        super(DragGalleryView, self).__init__(parent)
        self.db = db_manager
        self.nuke_bridge = nuke_bridge
        self.setDragEnabled(True)
        self.setAcceptDrops(False)  # We don't accept drops, only drag out
    
    def startDrag(self, supportedActions):
        """Override startDrag to set custom mime data with element info."""
        selected_items = self.selectedItems()
        if not selected_items:
            return
        
        # Get element IDs from selected items
        element_ids = []
        for item in selected_items:
            element_id = item.data(QtCore.Qt.UserRole)
            if element_id:
                element_ids.append(element_id)
        
        if not element_ids:
            return
        
        # Create mime data with element information
        mime_data = QtCore.QMimeData()
        
        # Store element IDs as text (for external drops)
        mime_data.setText(','.join(str(eid) for eid in element_ids))
        
        # Create file paths list for elements
        file_paths = []
        for element_id in element_ids:
            element = self.db.get_element_by_id(element_id)
            if element:
                # Get appropriate file path (hard copy if exists, else soft copy)
                if element.get('is_hard_copy') and element.get('filepath_hard'):
                    file_paths.append(element['filepath_hard'])
                elif element.get('filepath_soft'):
                    file_paths.append(element['filepath_soft'])
        
        # Set URL list for file paths (standard for drag & drop)
        urls = [QtCore.QUrl.fromLocalFile(path) for path in file_paths]
        mime_data.setUrls(urls)
        
        # Store custom data for internal processing
        mime_data.setData('application/x-vah-elements', ','.join(str(eid) for eid in element_ids).encode('utf-8'))
        
        # Create drag object
        drag = QtGui.QDrag(self)
        drag.setMimeData(mime_data)
        
        # Set drag icon (use first item's icon)
        if selected_items:
            pixmap = selected_items[0].icon().pixmap(64, 64)
            drag.setPixmap(pixmap)
            drag.setHotSpot(QtCore.QPoint(32, 32))
        
        # Execute drag
        drag.exec_(QtCore.Qt.CopyAction | QtCore.Qt.MoveAction)
    
    def insert_to_nuke(self, element_ids):
        """
        Insert elements into Nuke as nodes.
        
        Args:
            element_ids (list): List of element IDs to insert
        """
        if not self.nuke_bridge.is_available():
            print("[MOCK] Would insert {} elements into Nuke".format(len(element_ids)))
        
        for element_id in element_ids:
            element = self.db.get_element_by_id(element_id)
            if not element:
                continue
            
            # Get file path
            if element.get('is_hard_copy') and element.get('filepath_hard'):
                filepath = element['filepath_hard']
            else:
                filepath = element.get('filepath_soft')
            
            if not filepath:
                continue
            
            # Determine node type based on element type
            element_type = element.get('type', '2D')
            
            if element_type == '3D':
                # Create ReadGeo node for 3D assets
                self.nuke_bridge.create_read_geo_node(
                    filepath,
                    node_name=element['name']
                )
            elif element_type == 'toolset':
                # Paste toolset (.nk file) into DAG
                self.nuke_bridge.paste_nodes_from_file(filepath)
            else:
                # Create Read node for 2D assets (images, sequences, videos)
                frame_range = None
                if element.get('frames'):
                    try:
                        frames = int(element['frames'])
                        if frames > 1:
                            # Detect frame range from sequence
                            frame_range = "1-{}".format(frames)
                    except (ValueError, TypeError):
                        pass
                
                self.nuke_bridge.create_read_node(
                    filepath,
                    frame_range=frame_range,
                    node_name=element['name']
                )


class MediaDisplayWidget(QtWidgets.QWidget):
    """Central widget for displaying media elements."""
    
    # Signals
    element_selected = QtCore.Signal(int)  # element_id
    element_double_clicked = QtCore.Signal(int)  # element_id
    
    def __init__(self, db_manager, config, nuke_bridge, main_window=None, parent=None):
        super(MediaDisplayWidget, self).__init__(parent)
        self.db = db_manager
        self.config = config
        self.nuke_bridge = nuke_bridge
        self.main_window = main_window  # Reference to MainWindow for permission checks
        self.current_list_id = None
        self.current_elements = []  # Store all elements for pagination
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
        self.gif_movies = {}  # Cache for QMovie objects {element_id: QMovie}
        self.current_gif_item = None  # Currently hovering item with GIF
        self.element_items = {}  # Map element_id -> QListWidgetItem
        self.element_flags = {}  # Map element_id -> status flags (favorite/deprecated)
        self.setup_ui()
        
        # Enable mouse tracking for hover events
        self.setMouseTracking(True)
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        toolbar = QtWidgets.QHBoxLayout()
        
        # Search bar with tag filtering support
        search_container = QtWidgets.QWidget()
        search_layout = QtWidgets.QVBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText("Search elements... (use #tag or tag:fire for tag filtering)")
        self.search_box.textChanged.connect(self.on_search)
        search_layout.addWidget(self.search_box)
        
        # Search hint label
        self.search_hint_label = QtWidgets.QLabel()
        self.search_hint_label.setStyleSheet("color: #888888; font-size: 10px; font-style: italic;")
        self.search_hint_label.hide()  # Hidden by default
        search_layout.addWidget(self.search_hint_label)
        
        toolbar.addWidget(search_container, 1)  # Give it stretch priority
        
        # View mode toggle
        self.gallery_btn = QtWidgets.QPushButton()
        self.gallery_btn.setIcon(get_icon('gallery', size=20))
        self.gallery_btn.setToolTip("Gallery View")
        self.gallery_btn.setCheckable(True)
        self.gallery_btn.setChecked(True)
        self.gallery_btn.clicked.connect(lambda: self.set_view_mode('gallery'))
        toolbar.addWidget(self.gallery_btn)
        
        self.list_btn = QtWidgets.QPushButton()
        self.list_btn.setIcon(get_icon('list', size=20))
        self.list_btn.setToolTip("List View")
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
        
        layout.addLayout(toolbar)
        
        # Stacked widget for different views
        self.view_stack = QtWidgets.QStackedWidget()
        
        # Gallery view (grid of thumbnails with drag & drop)
        self.gallery_view = DragGalleryView(self.db, self.nuke_bridge)
        self.gallery_view.setViewMode(QtWidgets.QListView.IconMode)
        self.gallery_view.setResizeMode(QtWidgets.QListView.Adjust)
        self.gallery_view.setIconSize(QtCore.QSize(256, 256))
        self.gallery_view.setSpacing(10)
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
        
        # Pagination widget
        self.pagination = PaginationWidget()
        self.pagination.page_changed.connect(self.on_page_changed)
        self.pagination.setVisible(self.config.get('pagination_enabled', True))
        layout.addWidget(self.pagination)
        
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
        """Handle thumbnail size change - reload elements with new size."""
        self.gallery_view.setIconSize(QtCore.QSize(value, value))
        
        # Reload visible items to rescale images
        if not self.current_elements:
            return
        if self.config.get('pagination_enabled', True) and self.current_list_id:
            self._display_current_page()
        else:
            self._update_views_with_elements(self.current_elements)
    
    def load_elements(self, list_id):
        """Load elements for a list with preview caching and pagination."""
        self.current_list_id = list_id
        elements = self.db.get_elements_by_list(list_id)
        
        # Store all elements for pagination
        self.current_elements = elements
        
        self.info_label.setVisible(len(elements) == 0)
        
        if len(elements) > 0:
            self.info_label.setText("")
        else:
            lst = self.db.get_list_by_id(list_id)
            if lst:
                self.info_label.setText("No elements in '{}'".format(lst['name']))
        
        # Setup pagination
        if self.config.get('pagination_enabled', True):
            self.pagination.set_total_items(len(elements))
            self.pagination.set_items_per_page(self.config.get('items_per_page', 100))
            self.pagination.setVisible(len(elements) > 0)
        else:
            self.pagination.setVisible(False)
        
        # Display current page
        self._display_current_page()
    
    def on_page_changed(self, page):
        """Handle page change event."""
        self._display_current_page()
    
    def _display_current_page(self):
        """Display elements for the current page."""
        if not self.current_elements:
            return
        
        # Get page slice
        if self.config.get('pagination_enabled', True):
            start, end = self.pagination.get_page_slice()
            page_elements = self.current_elements[start:end]
        else:
            page_elements = self.current_elements
        
        # Use shared method to update both views
        self._update_views_with_elements(page_elements)
    
    def on_search(self, text):
        """Handle search text change (live filter) with tag support and pagination."""
        if not self.current_list_id:
            return
        
        # Parse search query for tags
        # Supports: #tag, tag:value, or plain text
        text = text.strip()
        tags_to_search = []
        name_search = text
        
        # Check for tag patterns
        if text.startswith('#'):
            # Format: #fire or #fire,explosion
            tags_str = text[1:]  # Remove #
            tags_to_search = [t.strip() for t in tags_str.split(',') if t.strip()]
            name_search = ''
            self.search_hint_label.setText("Filtering by tags: " + ", ".join(tags_to_search))
            self.search_hint_label.show()
        elif 'tag:' in text.lower():
            # Format: tag:fire or tag:fire,explosion
            parts = text.lower().split('tag:', 1)
            if len(parts) > 1:
                tags_str = parts[1]
                tags_to_search = [t.strip() for t in tags_str.split(',') if t.strip()]
                name_search = parts[0].strip()
                self.search_hint_label.setText("Filtering by tags: " + ", ".join(tags_to_search))
                self.search_hint_label.show()
        else:
            self.search_hint_label.hide()
        
        # Get elements
        if tags_to_search:
            # Search by tags first
            elements = self.db.search_elements_by_tags(tags_to_search, match_all=False)
            # Filter by list
            elements = [e for e in elements if e['list_fk'] == self.current_list_id]
            
            # Further filter by name if provided
            if name_search:
                elements = [e for e in elements if name_search.lower() in e['name'].lower()]
        else:
            # Regular name search
            elements = self.db.get_elements_by_list(self.current_list_id)
            if name_search:
                elements = [e for e in elements if name_search.lower() in e['name'].lower()]
        
        # Store filtered elements for pagination
        self.current_elements = elements
        
        # Setup pagination for filtered results
        if self.config.get('pagination_enabled', True):
            self.pagination.set_total_items(len(elements))
            self.pagination.setVisible(len(elements) > 0)
        else:
            self.pagination.setVisible(False)
        
        # Display current page
        self._display_current_page()
    
    
    def _update_views_with_elements(self, elements):
        """Update gallery and table views with given elements."""
        self.stop_current_gif()
        self.current_gif_item = None
        self.gallery_view.clear()
        icon_size = self.gallery_view.iconSize()
        self.element_items = {}
        self.element_flags = {}

        for element in elements:
            element_id = element.get('element_id')
            is_favorite = bool(element_id and self.db.is_favorite(element_id))
            is_deprecated = bool(element.get('is_deprecated'))
            if element_id:
                self.element_flags[element_id] = {
                    'favorite': is_favorite,
                    'deprecated': is_deprecated
                }

            item = QtWidgets.QListWidgetItem()
            display_name = element['name']
            if element.get('tags'):
                tag_list = [t.strip() for t in element['tags'].split(',') if t.strip()]
                if tag_list:
                    display_name += " [" + ", ".join(tag_list[:3]) + "]"

            item.setText(display_name)
            item.setData(QtCore.Qt.UserRole, element_id)
            if element_id:
                self.element_items[element_id] = item

            gif_path = element.get('gif_preview_path')
            has_gif = bool(gif_path and element_id and os.path.exists(gif_path))

            if has_gif:
                movie = self.gif_movies.get(element_id)
                if not movie:
                    movie = QtGui.QMovie(gif_path)
                    if movie.isValid():
                        movie.setCacheMode(QtGui.QMovie.CacheAll)
                        movie.frameChanged.connect(lambda frame_num, eid=element_id: self._update_gif_frame(eid))
                        self.gif_movies[element_id] = movie
                    else:
                        movie = None

                if movie and movie.isValid():
                    movie.jumpToFrame(0)
                    pixmap = movie.currentPixmap()
                    if not pixmap.isNull():
                        scaled_pixmap = pixmap.scaled(
                            icon_size,
                            QtCore.Qt.KeepAspectRatio,
                            QtCore.Qt.SmoothTransformation
                        )
                        scaled_pixmap = self._apply_status_badges(scaled_pixmap, element_id)
                        item.setIcon(QtGui.QIcon(scaled_pixmap))
                else:
                    has_gif = False

            if not has_gif:
                static_pixmap = self._load_preview_pixmap(element, icon_size)
                if static_pixmap:
                    item.setIcon(QtGui.QIcon(static_pixmap))
                else:
                    item.setIcon(self._get_default_icon_for_type(element.get('type')))

            self.gallery_view.addItem(item)

        self.table_view.setRowCount(len(elements))
        for row, element in enumerate(elements):
            element_id = element.get('element_id')
            flags = self.element_flags.get(element_id, {})

            name_item = QtWidgets.QTableWidgetItem(element['name'])
            if flags.get('favorite'):
                name_item.setIcon(get_icon('favorite', size=16))
            if flags.get('deprecated'):
                name_item.setForeground(QtGui.QColor('#d88400'))
            self.table_view.setItem(row, 0, name_item)

            self.table_view.setItem(row, 1, QtWidgets.QTableWidgetItem(element.get('format') or ''))
            self.table_view.setItem(row, 2, QtWidgets.QTableWidgetItem(element.get('frame_range') or ''))
            self.table_view.setItem(row, 3, QtWidgets.QTableWidgetItem(element.get('type') or ''))

            size_str = ''
            if element.get('file_size'):
                size_mb = element['file_size'] / (1024.0 * 1024.0)
                if size_mb < 1024:
                    size_str = "{:.1f} MB".format(size_mb)
                else:
                    size_str = "{:.2f} GB".format(size_mb / 1024.0)
            self.table_view.setItem(row, 4, QtWidgets.QTableWidgetItem(size_str))

            comment_text = element.get('comment') or ''
            if element.get('tags'):
                comment_text += " [Tags: " + element['tags'] + "]"
            self.table_view.setItem(row, 5, QtWidgets.QTableWidgetItem(comment_text))

            self.table_view.item(row, 0).setData(QtCore.Qt.UserRole, element_id)

    def _load_preview_pixmap(self, element, icon_size):
        """Load and scale a static preview pixmap for an element."""
        preview_path = element.get('preview_path')
        if not preview_path or not os.path.exists(preview_path):
            return None

        cached_pixmap = self.preview_cache.get(preview_path)
        if not cached_pixmap:
            cached_pixmap = QtGui.QPixmap(preview_path)
            if not cached_pixmap.isNull():
                self.preview_cache.put(preview_path, cached_pixmap)

        if cached_pixmap and not cached_pixmap.isNull():
            scaled_pixmap = cached_pixmap.scaled(
                icon_size,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
            element_id = element.get('element_id')
            if element_id:
                scaled_pixmap = self._apply_status_badges(scaled_pixmap, element_id)
            return scaled_pixmap
        return None

    def _get_default_icon_for_type(self, element_type):
        """Return a fallback icon when no preview is available."""
        if element_type == '2D':
            return self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)
        if element_type == '3D':
            return self.style().standardIcon(QtWidgets.QStyle.SP_DriveFDIcon)
        return self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogDetailedView)

    def _apply_status_badges(self, pixmap, element_id):
        """Overlay favorite/deprecated badges onto a pixmap."""
        flags = self.element_flags.get(element_id)
        if not flags:
            return pixmap

        overlays = []
        if flags.get('favorite'):
            overlays.append(get_pixmap('favorite', size=18))
        if flags.get('deprecated'):
            overlays.append(get_pixmap('deprecated', size=18))

        overlays = [ov for ov in overlays if ov and not ov.isNull()]
        if not overlays:
            return pixmap

        result = QtGui.QPixmap(pixmap)
        painter = QtGui.QPainter(result)
        margin = 6
        offset = margin
        for overlay in overlays:
            badge = overlay.scaled(
                18,
                18,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
            painter.drawPixmap(offset, margin, badge)
            offset += badge.width() + 4
        painter.end()

        return result
    
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
                    
                # Handle GIF preview on hover (without Alt key)
                if not self.alt_pressed and obj == self.gallery_view.viewport():
                    pos = event.pos()
                    item = self.gallery_view.itemAt(pos)
                    
                    if item and item != self.current_gif_item:
                        # Stop previous GIF
                        self.stop_current_gif()
                        
                        # Start new GIF if available
                        element_id = item.data(QtCore.Qt.UserRole)
                        if element_id:
                            self.play_gif_for_item(item, element_id)
                            self.current_gif_item = item
                    elif not item and self.current_gif_item:
                        # Mouse left all items, stop GIF
                        self.stop_current_gif()
                        self.current_gif_item = None
            
            elif event.type() == QtCore.QEvent.Leave:
                # Hide popup when leaving widget
                self.hover_timer.stop()
                self.hover_item = None
                
                # Stop GIF playback
                self.stop_current_gif()
                self.current_gif_item = None
        
        return super(MediaDisplayWidget, self).eventFilter(obj, event)
    
    def play_gif_for_item(self, item, element_id):
        """
        Play animated GIF for gallery item on hover (Ulaavi pattern).
        
        Args:
            item (QListWidgetItem): Gallery item
            element_id (int): Element ID
        """
        # Get pre-loaded movie from cache
        if element_id not in self.gif_movies:
            return
        
        movie = self.gif_movies[element_id]
        
        # Jump to first frame and start playback
        movie.jumpToFrame(0)
        movie.start()
    
    def _update_gif_frame(self, element_id):
        """Update the gallery icon with the current GIF frame."""
        if element_id not in self.gif_movies:
            return
        movie = self.gif_movies.get(element_id)
        item = self.element_items.get(element_id)
        if not movie or not item:
            return

        try:
            _ = item.data(QtCore.Qt.UserRole)
        except RuntimeError:
            movie.stop()
            return

        pixmap = movie.currentPixmap()
        if pixmap.isNull():
            return

        icon_size = self.gallery_view.iconSize()
        scaled_pixmap = pixmap.scaled(
            icon_size,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation
        )
        scaled_pixmap = self._apply_status_badges(scaled_pixmap, element_id)

        try:
            item.setIcon(QtGui.QIcon(scaled_pixmap))
        except RuntimeError:
            movie.stop()
    
    def stop_current_gif(self):
        """Stop currently playing GIF and return to static first frame (Ulaavi pattern)."""
        if self.current_gif_item:
            element_id = self.current_gif_item.data(QtCore.Qt.UserRole)
            
            # Stop movie and jump to first frame
            if element_id and element_id in self.gif_movies:
                movie = self.gif_movies[element_id]
                movie.stop()
                movie.jumpToFrame(0)
                # Update icon to show first frame
                self._update_gif_frame(element_id)
    
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
        """Handle insert request from popup - insert element into Nuke."""
        self.gallery_view.insert_to_nuke([element_id])
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
        Show context menu for element(s).
        Supports both single and bulk operations.
        
        Args:
            position (QPoint): Position to show menu
            element_id (int): Element ID (for single selection)
        """
        # Get all selected element IDs
        selected_ids = self.get_selected_element_ids()
        
        menu = QtWidgets.QMenu(self)
        
        # If multiple items selected, show bulk operations menu
        if len(selected_ids) > 1:
            # Bulk operations header
            header_label = QtWidgets.QLabel("  {} items selected  ".format(len(selected_ids)))
            header_label.setStyleSheet("font-weight: bold; color: #16c6b0; padding: 5px;")
            header_action = QtWidgets.QWidgetAction(self)
            header_action.setDefaultWidget(header_label)
            menu.addAction(header_action)
            
            menu.addSeparator()
            
            # Bulk add to favorites
            bulk_fav_action = menu.addAction(get_icon('favorite', size=16), "Add All to Favorites")
            
            # Bulk add to playlist
            bulk_playlist_action = menu.addAction(get_icon('playlist', size=16), "Add All to Playlist...")
            
            menu.addSeparator()
            
            # Bulk mark as deprecated (admin only)
            bulk_deprecate_action = menu.addAction(get_icon('deprecated', size=16), "Mark All as Deprecated")
            if not self.parent().is_admin:
                bulk_deprecate_action.setEnabled(False)
            
            # Bulk delete (admin only)
            bulk_delete_action = menu.addAction(get_icon('delete', size=16), "Delete All Selected")
            if not self.parent().is_admin:
                bulk_delete_action.setEnabled(False)
            
            # Execute menu
            action = menu.exec_(position)
            
            if action == bulk_fav_action:
                self.bulk_add_to_favorites(selected_ids)
            elif action == bulk_playlist_action:
                self.bulk_add_to_playlist(selected_ids)
            elif action == bulk_deprecate_action:
                self.bulk_mark_deprecated(selected_ids)
            elif action == bulk_delete_action:
                self.bulk_delete(selected_ids)
        
        else:
            # Single item context menu (existing behavior)
            # Check if already favorited
            is_fav = self.db.is_favorite(
                element_id,
                self.config.get('user_name'),
                self.config.get('machine_name')
            )
            
            # Add/Remove favorite action
            if is_fav:
                fav_action = menu.addAction(get_icon('favorite', size=16), "Remove from Favorites")
            else:
                fav_action = menu.addAction(get_icon('favorite', size=16), "Add to Favorites")
            
            # Add to playlist action
            add_playlist_action = menu.addAction(get_icon('playlist', size=16), "Add to Playlist...")
            
            menu.addSeparator()
            
            # Insert into Nuke action
            insert_action = menu.addAction("Insert into Nuke")
            
            # Edit metadata action
            edit_action = menu.addAction(get_icon('edit', size=16), "Edit Metadata...")
            
            menu.addSeparator()
            
            # Get element to check deprecated status
            element = self.db.get_element_by_id(element_id)
            
            # Toggle deprecated action
            if element and element.get('is_deprecated'):
                deprecated_action = menu.addAction(get_icon('deprecated', size=16), "Unmark as Deprecated")
            else:
                deprecated_action = menu.addAction(get_icon('deprecated', size=16), "Mark as Deprecated")

            # Delete action
            delete_action = menu.addAction(get_icon('delete', size=16), "Delete Element")

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
        """Delete element after confirmation (admin only)."""
        # Check admin permission
        if self.main_window and not self.main_window.check_admin_permission("delete elements"):
            return
        
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
        bulk_fav_action = menu.addAction(get_icon('favorite', size=16), "Add All to Favorites")
        
        # Bulk add to playlist
        bulk_playlist_action = menu.addAction(get_icon('playlist', size=16), "Add All to Playlist...")
        
        menu.addSeparator()
        
        # Bulk mark as deprecated
        bulk_deprecate_action = menu.addAction(get_icon('deprecated', size=16), "Mark All as Deprecated")
        
        # Bulk delete
        bulk_delete_action = menu.addAction(get_icon('delete', size=16), "Delete All Selected")
        
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
        self.current_elements = favorites
        self.pagination.setVisible(False)
        self.info_label.setText("Favorites ({} items)".format(len(favorites)))
        self._update_views_with_elements(favorites)
    
    def load_playlist(self, playlist_id):
        """Load and display playlist elements."""
        playlist = self.db.get_playlist_by_id(playlist_id)
        if not playlist:
            return
        
        elements = self.db.get_playlist_elements(playlist_id)
        
        self.current_list_id = None  # Clear current list
        self.current_elements = elements
        self.pagination.setVisible(False)
        self.info_label.setText("Playlist: {} ({} items)".format(playlist['name'], len(elements)))
        self._update_views_with_elements(elements)
    
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
        refresh_btn.setIcon(get_icon('refresh', size=20))
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
    """Comprehensive panel for application settings with tabbed interface."""
    
    settings_changed = QtCore.Signal()
    
    def __init__(self, config, db_manager, main_window=None, parent=None):
        super(SettingsPanel, self).__init__(parent)
        self.config = config
        self.db = db_manager
        self.main_window = main_window  # For permission checks
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components with tabs."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Title
        title = QtWidgets.QLabel("Application Settings")
        title.setStyleSheet("font-weight: bold; font-size: 16px; color: #16c6b0; padding: 10px;")
        layout.addWidget(title)
        
        # Tab widget for organized settings
        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.setStyleSheet("QTabWidget::pane { border: 1px solid #333; }")
        
        # Tab 1: General Settings
        self.setup_general_tab()
        
        # Tab 2: Ingestion Settings
        self.setup_ingestion_tab()
        
        # Tab 3: Preview & Media Settings
        self.setup_preview_tab()
        
        # Tab 4: Network & Performance
        self.setup_network_tab()
        
        # Tab 5: Custom Processors
        self.setup_processors_tab()
        
        # Tab 6: Security & Admin (Admin only)
        self.setup_security_tab()
        
        layout.addWidget(self.tab_widget)
        
        # Bottom buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        save_btn = QtWidgets.QPushButton("Save All Settings")
        save_btn.setIcon(get_icon('settings', size=20))
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #16c6b0;
                color: white;
                font-weight: bold;
                padding: 8px 20px;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #14b39e; }
        """)
        save_btn.clicked.connect(self.save_all_settings)
        button_layout.addWidget(save_btn)
        
        reset_btn = QtWidgets.QPushButton("Reset to Defaults")
        reset_btn.setIcon(get_icon('refresh', size=20))
        reset_btn.clicked.connect(self.reset_settings)
        button_layout.addWidget(reset_btn)
        
        button_layout.addStretch()
        
        # Current user indicator
        if self.main_window and self.main_window.current_user:
            user_label = QtWidgets.QLabel("Logged in as: {}".format(
                self.main_window.current_user['username']
            ))
            user_label.setStyleSheet("color: #888; font-size: 11px;")
            button_layout.addWidget(user_label)
        
        layout.addLayout(button_layout)
    
    def setup_general_tab(self):
        """Setup general settings tab."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setSpacing(15)
        
        # Database location
        db_group = QtWidgets.QGroupBox("Database Configuration")
        db_layout = QtWidgets.QFormLayout()
        
        self.db_path_edit = QtWidgets.QLineEdit(self.config.get('database_path'))
        self.db_path_edit.setReadOnly(True)
        db_path_layout = QtWidgets.QHBoxLayout()
        db_path_layout.addWidget(self.db_path_edit)
        
        browse_db_btn = QtWidgets.QPushButton("Browse...")
        browse_db_btn.clicked.connect(self.browse_database_path)
        db_path_layout.addWidget(browse_db_btn)
        
        db_layout.addRow("Database Path:", db_path_layout)
        
        # Environment variable hint
        env_hint = QtWidgets.QLabel("Tip: Set STOCK_DB environment variable to override")
        env_hint.setStyleSheet("color: #16c6b0; font-size: 10px; font-style: italic;")
        db_layout.addRow("", env_hint)
        
        db_group.setLayout(db_layout)
        layout.addWidget(db_group)
        
        # User preferences
        pref_group = QtWidgets.QGroupBox("User Preferences")
        pref_layout = QtWidgets.QFormLayout()
        
        self.user_name_edit = QtWidgets.QLineEdit(self.config.get('user_name') or '')
        pref_layout.addRow("User Name:", self.user_name_edit)
        
        import socket
        self.machine_name_edit = QtWidgets.QLineEdit(self.config.get('machine_name') or socket.gethostname())
        self.machine_name_edit.setReadOnly(True)
        pref_layout.addRow("Machine Name:", self.machine_name_edit)
        
        pref_group.setLayout(pref_layout)
        layout.addWidget(pref_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "General")
    
    def setup_ingestion_tab(self):
        """Setup ingestion settings tab."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        
        # Copy policy
        policy_group = QtWidgets.QGroupBox("File Copy Policy")
        policy_layout = QtWidgets.QFormLayout()
        
        self.copy_policy = QtWidgets.QComboBox()
        self.copy_policy.addItems(['soft', 'hard'])
        self.copy_policy.setCurrentText(self.config.get('default_copy_policy'))
        policy_layout.addRow("Default Copy Policy:", self.copy_policy)
        
        policy_help = QtWidgets.QLabel(
            "- Soft: Store reference to original file location\n"
            "- Hard: Copy file to repository"
        )
        policy_help.setStyleSheet("color: #888; font-size: 11px;")
        policy_layout.addRow("", policy_help)
        
        policy_group.setLayout(policy_layout)
        layout.addWidget(policy_group)
        
        # Sequence detection
        seq_group = QtWidgets.QGroupBox("Sequence Detection")
        seq_layout = QtWidgets.QFormLayout()
        
        self.auto_detect = QtWidgets.QCheckBox("Auto-detect image sequences")
        self.auto_detect.setChecked(self.config.get('auto_detect_sequences'))
        seq_layout.addRow("", self.auto_detect)
        
        seq_group.setLayout(seq_layout)
        layout.addWidget(seq_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Ingestion")
    
    def setup_preview_tab(self):
        """Setup preview and media settings tab."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        
        # Preview generation
        prev_group = QtWidgets.QGroupBox("Preview Generation")
        prev_layout = QtWidgets.QFormLayout()
        
        self.gen_previews = QtWidgets.QCheckBox("Generate preview thumbnails")
        self.gen_previews.setChecked(self.config.get('generate_previews'))
        prev_layout.addRow("", self.gen_previews)
        
        self.preview_size = QtWidgets.QSpinBox()
        self.preview_size.setRange(128, 2048)
        self.preview_size.setValue(self.config.get('preview_size', 512))
        self.preview_size.setSuffix(" px")
        prev_layout.addRow("Preview Size:", self.preview_size)
        
        self.preview_quality = QtWidgets.QSpinBox()
        self.preview_quality.setRange(1, 100)
        self.preview_quality.setValue(self.config.get('preview_quality', 85))
        self.preview_quality.setSuffix(" %")
        prev_layout.addRow("JPEG Quality:", self.preview_quality)
        
        prev_group.setLayout(prev_layout)
        layout.addWidget(prev_group)
        
        # GIF settings
        gif_group = QtWidgets.QGroupBox("Animated GIF Settings")
        gif_layout = QtWidgets.QFormLayout()
        
        self.gif_size = QtWidgets.QSpinBox()
        self.gif_size.setRange(128, 512)
        self.gif_size.setValue(self.config.get('gif_size', 256))
        self.gif_size.setSuffix(" px")
        gif_layout.addRow("GIF Size:", self.gif_size)
        
        self.gif_fps = QtWidgets.QSpinBox()
        self.gif_fps.setRange(5, 30)
        self.gif_fps.setValue(self.config.get('gif_fps', 10))
        self.gif_fps.setSuffix(" fps")
        gif_layout.addRow("GIF Frame Rate:", self.gif_fps)
        
        self.gif_duration = QtWidgets.QDoubleSpinBox()
        self.gif_duration.setRange(1.0, 10.0)
        self.gif_duration.setValue(self.config.get('gif_duration', 3.0))
        self.gif_duration.setSuffix(" sec")
        gif_layout.addRow("GIF Duration:", self.gif_duration)
        
        gif_group.setLayout(gif_layout)
        layout.addWidget(gif_group)
        
        # FFmpeg settings
        ffmpeg_group = QtWidgets.QGroupBox("FFmpeg Settings")
        ffmpeg_layout = QtWidgets.QFormLayout()
        
        self.ffmpeg_threads = QtWidgets.QSpinBox()
        self.ffmpeg_threads.setRange(1, 16)
        self.ffmpeg_threads.setValue(self.config.get('ffmpeg_threads', 4))
        self.ffmpeg_threads.setSuffix(" threads")
        ffmpeg_layout.addRow("Thread Count:", self.ffmpeg_threads)
        
        thread_help = QtWidgets.QLabel("Higher values = faster processing, more CPU usage")
        thread_help.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        ffmpeg_layout.addRow("", thread_help)
        
        ffmpeg_group.setLayout(ffmpeg_layout)
        layout.addWidget(ffmpeg_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Preview & Media")
    
    def setup_network_tab(self):
        """Setup network and performance settings tab."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        
        # Network settings
        net_group = QtWidgets.QGroupBox("Network Database Settings")
        net_layout = QtWidgets.QFormLayout()
        
        self.db_retries = QtWidgets.QSpinBox()
        self.db_retries.setRange(1, 50)
        self.db_retries.setValue(self.config.get('db_max_retries', 10))
        net_layout.addRow("Max Connection Retries:", self.db_retries)
        
        self.db_timeout = QtWidgets.QSpinBox()
        self.db_timeout.setRange(5, 300)
        self.db_timeout.setValue(self.config.get('db_timeout', 60))
        self.db_timeout.setSuffix(" sec")
        net_layout.addRow("Connection Timeout:", self.db_timeout)
        
        net_help = QtWidgets.QLabel(
            "These settings help handle network database access.\n"
            "Increase values for slow/unreliable network connections."
        )
        net_help.setStyleSheet("color: #888; font-size: 11px;")
        net_layout.addRow("", net_help)
        
        net_group.setLayout(net_layout)
        layout.addWidget(net_group)
        
        # Performance settings
        perf_group = QtWidgets.QGroupBox("Performance & Caching")
        perf_layout = QtWidgets.QFormLayout()
        
        self.cache_size = QtWidgets.QSpinBox()
        self.cache_size.setRange(50, 1000)
        self.cache_size.setValue(self.config.get('preview_cache_size', 200))
        self.cache_size.setSuffix(" items")
        perf_layout.addRow("Preview Cache Size:", self.cache_size)
        
        self.cache_memory = QtWidgets.QSpinBox()
        self.cache_memory.setRange(50, 1000)
        self.cache_memory.setValue(self.config.get('preview_cache_memory_mb', 200))
        self.cache_memory.setSuffix(" MB")
        perf_layout.addRow("Cache Memory Limit:", self.cache_memory)
        
        # Pagination settings
        self.pagination_enabled = QtWidgets.QCheckBox()
        self.pagination_enabled.setChecked(self.config.get('pagination_enabled', True))
        perf_layout.addRow("Enable Pagination:", self.pagination_enabled)
        
        self.items_per_page = QtWidgets.QComboBox()
        self.items_per_page.addItems(['50', '100', '200', '500'])
        self.items_per_page.setCurrentText(str(self.config.get('items_per_page', 100)))
        perf_layout.addRow("Items Per Page:", self.items_per_page)
        
        self.background_loading = QtWidgets.QCheckBox()
        self.background_loading.setChecked(self.config.get('background_thumbnail_loading', True))
        perf_layout.addRow("Background Thumbnail Loading:", self.background_loading)
        
        perf_help = QtWidgets.QLabel(
            "Pagination reduces memory usage and improves performance\n"
            "for large element collections. Background loading prevents UI freezing."
        )
        perf_help.setStyleSheet("color: #888; font-size: 11px;")
        perf_layout.addRow("", perf_help)
        
        perf_group.setLayout(perf_layout)
        layout.addWidget(perf_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Network & Performance")
    
    def setup_processors_tab(self):
        """Setup custom processors tab."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        
        help_label = QtWidgets.QLabel(
            "Custom processors allow you to run Python scripts at key points in the workflow.\n"
            "Leave blank to disable."
        )
        help_label.setStyleSheet("color: #16c6b0; font-size: 11px; padding: 10px;")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        
        # Processor hooks
        proc_group = QtWidgets.QGroupBox("Processor Hooks")
        proc_layout = QtWidgets.QFormLayout()
        
        # Pre-ingest
        self.pre_ingest = QtWidgets.QLineEdit(self.config.get('pre_ingest_processor') or '')
        pre_layout = QtWidgets.QHBoxLayout()
        pre_layout.addWidget(self.pre_ingest)
        pre_browse = QtWidgets.QPushButton("Browse...")
        pre_browse.clicked.connect(lambda: self.browse_file(self.pre_ingest))
        pre_layout.addWidget(pre_browse)
        proc_layout.addRow("Pre-Ingest Hook:", pre_layout)
        
        pre_help = QtWidgets.QLabel("Runs before file copy/metadata extraction")
        pre_help.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        proc_layout.addRow("", pre_help)
        
        # Post-ingest
        self.post_ingest = QtWidgets.QLineEdit(self.config.get('post_ingest_processor') or '')
        post_layout = QtWidgets.QHBoxLayout()
        post_layout.addWidget(self.post_ingest)
        post_browse = QtWidgets.QPushButton("Browse...")
        post_browse.clicked.connect(lambda: self.browse_file(self.post_ingest))
        post_layout.addWidget(post_browse)
        proc_layout.addRow("Post-Ingest Hook:", post_layout)
        
        post_help = QtWidgets.QLabel("Runs after asset is cataloged in database")
        post_help.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        proc_layout.addRow("", post_help)
        
        # Post-import
        self.post_import = QtWidgets.QLineEdit(self.config.get('post_import_processor') or '')
        import_layout = QtWidgets.QHBoxLayout()
        import_layout.addWidget(self.post_import)
        import_browse = QtWidgets.QPushButton("Browse...")
        import_browse.clicked.connect(lambda: self.browse_file(self.post_import))
        import_layout.addWidget(import_browse)
        proc_layout.addRow("Post-Import Hook:", import_layout)
        
        import_help = QtWidgets.QLabel("Runs after Nuke node creation")
        import_help.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        proc_layout.addRow("", import_help)
        
        proc_group.setLayout(proc_layout)
        layout.addWidget(proc_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Custom Processors")
    
    def setup_security_tab(self):
        """Setup security and admin settings tab (Admin only)."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        
        # Check if admin
        is_admin = False
        if self.main_window and self.main_window.is_admin:
            is_admin = True
        
        if not is_admin:
            # Show locked message for non-admin users
            lock_label = QtWidgets.QLabel(
                "Administrator Privileges Required\n\n"
                "This section contains sensitive settings that can only\n"
                "be modified by users with administrator privileges.\n\n"
                "Current user: {}\n"
                "Role: {}".format(
                    self.main_window.current_user['username'] if self.main_window and self.main_window.current_user else 'guest',
                    self.main_window.current_user.get('role', 'guest') if self.main_window and self.main_window.current_user else 'guest'
                )
            )
            lock_label.setAlignment(QtCore.Qt.AlignCenter)
            lock_label.setStyleSheet("color: #ff9a3c; font-size: 13px; padding: 50px;")
            layout.addWidget(lock_label)
        else:
            # Admin password change
            pwd_group = QtWidgets.QGroupBox("Change Admin Password")
            pwd_layout = QtWidgets.QFormLayout()
            
            self.current_pwd = QtWidgets.QLineEdit()
            self.current_pwd.setEchoMode(QtWidgets.QLineEdit.Password)
            pwd_layout.addRow("Current Password:", self.current_pwd)
            
            self.new_pwd = QtWidgets.QLineEdit()
            self.new_pwd.setEchoMode(QtWidgets.QLineEdit.Password)
            pwd_layout.addRow("New Password:", self.new_pwd)
            
            self.confirm_pwd = QtWidgets.QLineEdit()
            self.confirm_pwd.setEchoMode(QtWidgets.QLineEdit.Password)
            pwd_layout.addRow("Confirm Password:", self.confirm_pwd)
            
            change_pwd_btn = QtWidgets.QPushButton("Change Password")
            change_pwd_btn.clicked.connect(self.change_admin_password)
            pwd_layout.addRow("", change_pwd_btn)
            
            pwd_group.setLayout(pwd_layout)
            layout.addWidget(pwd_group)
            
            # User management
            user_group = QtWidgets.QGroupBox("User Management")
            user_layout = QtWidgets.QVBoxLayout()
            
            users_label = QtWidgets.QLabel("Registered Users:")
            users_label.setStyleSheet("font-weight: bold;")
            user_layout.addWidget(users_label)
            
            self.users_list = QtWidgets.QTableWidget()
            self.users_list.setColumnCount(4)
            self.users_list.setHorizontalHeaderLabels(['Username', 'Role', 'Email', 'Active'])
            self.users_list.horizontalHeader().setStretchLastSection(True)
            self.load_users_list()
            user_layout.addWidget(self.users_list)
            
            user_btn_layout = QtWidgets.QHBoxLayout()
            
            add_user_btn = QtWidgets.QPushButton("Add User")
            add_user_btn.clicked.connect(self.add_user)
            user_btn_layout.addWidget(add_user_btn)
            
            edit_user_btn = QtWidgets.QPushButton("Edit User")
            edit_user_btn.clicked.connect(self.edit_user)
            user_btn_layout.addWidget(edit_user_btn)
            
            deactivate_user_btn = QtWidgets.QPushButton("Deactivate User")
            deactivate_user_btn.clicked.connect(self.deactivate_user)
            user_btn_layout.addWidget(deactivate_user_btn)
            
            user_btn_layout.addStretch()
            user_layout.addLayout(user_btn_layout)
            
            user_group.setLayout(user_layout)
            layout.addWidget(user_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Security & Admin")
    
    def browse_database_path(self):
        """Browse for database file."""
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Select Database File", self.db_path_edit.text(), "SQLite Database (*.db)"
        )
        if filename:
            self.db_path_edit.setText(filename)
    
    def browse_file(self, line_edit):
        """Browse for processor script file."""
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Processor Script", "", "Python Files (*.py)"
        )
        if filename:
            line_edit.setText(filename)
    
    def load_users_list(self):
        """Load users into table."""
        if not hasattr(self, 'users_list'):
            return
        
        users = self.db.get_all_users()
        self.users_list.setRowCount(len(users))
        
        for row, user in enumerate(users):
            self.users_list.setItem(row, 0, QtWidgets.QTableWidgetItem(user['username']))
            self.users_list.setItem(row, 1, QtWidgets.QTableWidgetItem(user['role']))
            self.users_list.setItem(row, 2, QtWidgets.QTableWidgetItem(user.get('email', '') or ''))
            self.users_list.setItem(row, 3, QtWidgets.QTableWidgetItem('Yes' if user['is_active'] else 'No'))
            
            # Store user_id in first column
            self.users_list.item(row, 0).setData(QtCore.Qt.UserRole, user['user_id'])
    
    def add_user(self):
        """Add new user dialog."""
        # TODO: Implement AddUserDialog
        QtWidgets.QMessageBox.information(self, "Coming Soon", "User management dialog will be implemented.")
    
    def edit_user(self):
        """Edit selected user."""
        # TODO: Implement EditUserDialog
        QtWidgets.QMessageBox.information(self, "Coming Soon", "User editing dialog will be implemented.")
    
    def deactivate_user(self):
        """Deactivate selected user."""
        current_row = self.users_list.currentRow()
        if current_row < 0:
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select a user to deactivate.")
            return
        
        user_id = self.users_list.item(current_row, 0).data(QtCore.Qt.UserRole)
        username = self.users_list.item(current_row, 0).text()
        
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Deactivation",
            "Are you sure you want to deactivate user '{}'?".format(username),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            self.db.delete_user(user_id)
            self.load_users_list()
            QtWidgets.QMessageBox.information(self, "Success", "User deactivated successfully.")
    
    def change_admin_password(self):
        """Change admin password."""
        current = self.current_pwd.text()
        new = self.new_pwd.text()
        confirm = self.confirm_pwd.text()
        
        if not current or not new or not confirm:
            QtWidgets.QMessageBox.warning(self, "Invalid Input", "Please fill all password fields.")
            return
        
        if new != confirm:
            QtWidgets.QMessageBox.warning(self, "Password Mismatch", "New password and confirmation do not match.")
            return
        
        if len(new) < 4:
            QtWidgets.QMessageBox.warning(self, "Weak Password", "Password must be at least 4 characters.")
            return
        
        # Verify current password
        if self.main_window and self.main_window.current_user:
            user = self.db.authenticate_user(
                self.main_window.current_user['username'],
                current
            )
            
            if not user:
                QtWidgets.QMessageBox.warning(self, "Invalid Password", "Current password is incorrect.")
                return
            
            # Change password
            self.db.change_user_password(user['user_id'], new)
            
            # Clear fields
            self.current_pwd.clear()
            self.new_pwd.clear()
            self.confirm_pwd.clear()
            
            QtWidgets.QMessageBox.information(self, "Success", "Admin password changed successfully!")
    
    def save_all_settings(self):
        """Save all settings to config."""
        # General settings
        self.config.set('database_path', self.db_path_edit.text())
        self.config.set('user_name', self.user_name_edit.text())
        
        # Ingestion settings
        self.config.set('default_copy_policy', self.copy_policy.currentText())
        self.config.set('auto_detect_sequences', self.auto_detect.isChecked())
        
        # Preview settings
        self.config.set('generate_previews', self.gen_previews.isChecked())
        self.config.set('preview_size', self.preview_size.value())
        self.config.set('preview_quality', self.preview_quality.value())
        self.config.set('gif_size', self.gif_size.value())
        self.config.set('gif_fps', self.gif_fps.value())
        self.config.set('gif_duration', self.gif_duration.value())
        self.config.set('ffmpeg_threads', self.ffmpeg_threads.value())
        
        # Network and performance settings
        self.config.set('db_max_retries', self.db_retries.value())
        self.config.set('db_timeout', self.db_timeout.value())
        self.config.set('preview_cache_size', self.cache_size.value())
        self.config.set('preview_cache_memory_mb', self.cache_memory.value())
        self.config.set('pagination_enabled', self.pagination_enabled.isChecked())
        self.config.set('items_per_page', int(self.items_per_page.currentText()))
        self.config.set('background_thumbnail_loading', self.background_loading.isChecked())
        
        # Processor hooks
        self.config.set('pre_ingest_processor', self.pre_ingest.text() or None)
        self.config.set('post_ingest_processor', self.post_ingest.text() or None)
        self.config.set('post_import_processor', self.post_import.text() or None)
        
        QtWidgets.QMessageBox.information(
            self,
            "Settings Saved",
            "All settings have been saved successfully.\n\n"
            "Some changes may require restarting the application."
        )
        self.settings_changed.emit()
    
    def reset_settings(self):
        """Reset settings to defaults."""
        reply = QtWidgets.QMessageBox.question(
            self, "Reset Settings",
            "Are you sure you want to reset all settings to defaults?\n\n"
            "This will not affect your database or user accounts.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            self.config.reset_to_defaults()
            
            # Recreate UI to reload defaults
            # Clear layout
            while self.layout().count():
                child = self.layout().takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            
            # Rebuild UI
            self.setup_ui()
            
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


class AddSubListDialog(QtWidgets.QDialog):
    """Dialog for adding a sub-list under a parent list."""
    
    def __init__(self, db_manager, parent_list_id, stack_id, parent=None):
        super(AddSubListDialog, self).__init__(parent)
        self.db = db_manager
        self.parent_list_id = parent_list_id
        self.stack_id = stack_id
        self.setWindowTitle("Add Sub-List")
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QFormLayout(self)
        
        # Show parent list info
        parent_list = self.db.get_list_by_id(self.parent_list_id)
        if parent_list:
            parent_label = QtWidgets.QLabel(parent_list['name'])
            parent_label.setStyleSheet("font-weight: bold; color: #16c6b0;")
            layout.addRow("Parent List:", parent_label)
        
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("e.g., 'Aerial Explosions'")
        layout.addRow("Sub-List Name:", self.name_edit)
        
        # Info label
        info_label = QtWidgets.QLabel("This sub-list will be nested under the parent list.")
        info_label.setStyleSheet("color: #888888; font-style: italic; font-size: 11px;")
        info_label.setWordWrap(True)
        layout.addRow("", info_label)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)
    
    def accept(self):
        """Validate and create sub-list."""
        name = self.name_edit.text().strip()
        
        if not name:
            QtWidgets.QMessageBox.warning(self, "Invalid Input", "Please provide a sub-list name.")
            return
        
        try:
            self.db.create_list(self.stack_id, name, parent_list_id=self.parent_list_id)
            QtWidgets.QMessageBox.information(self, "Success", "Sub-list '{}' created successfully!".format(name))
            super(AddSubListDialog, self).accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to create sub-list: {}".format(str(e)))


class IngestLibraryDialog(QtWidgets.QDialog):
    """Dialog for bulk-ingesting an existing library folder structure."""
    
    def __init__(self, db_manager, ingestion_core, config, parent=None):
        super(IngestLibraryDialog, self).__init__(parent)
        self.db = db_manager
        self.ingestion = ingestion_core
        self.config = config
        self.setWindowTitle("Ingest Library")
        self.resize(600, 400)
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Instructions
        instructions = QtWidgets.QLabel(
            "<b>Bulk Library Ingestion</b><br/>"
            "This feature scans a folder hierarchy and automatically creates:<br/>"
            "- <b>Stacks</b> from top-level folders<br/>"
            "- <b>Lists</b> from subfolders<br/>"
            "- <b>Sub-Lists</b> from nested subfolders<br/>"
            "- Ingests all media files in each folder<br/><br/>"
            "<i>Example: ActionFX/explosions/aerial -> Stack: 'ActionFX', List: 'explosions', Sub-List: 'aerial'</i>"
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: #cccccc; padding: 10px; background-color: #2a2a2a; border-radius: 5px;")
        layout.addWidget(instructions)
        
        # Folder selection
        folder_layout = QtWidgets.QHBoxLayout()
        folder_label = QtWidgets.QLabel("Library Folder:")
        folder_label.setStyleSheet("font-weight: bold;")
        self.folder_path_edit = QtWidgets.QLineEdit()
        self.folder_path_edit.setReadOnly(True)
        self.folder_path_edit.setPlaceholderText("Click 'Browse' to select library folder...")
        browse_btn = QtWidgets.QPushButton("Browse...")
        browse_btn.clicked.connect(self.select_folder)
        
        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.folder_path_edit)
        folder_layout.addWidget(browse_btn)
        layout.addLayout(folder_layout)
        
        # Options group
        options_group = QtWidgets.QGroupBox("Ingestion Options")
        options_layout = QtWidgets.QFormLayout()
        
        # Stack/List prefix
        self.stack_prefix_edit = QtWidgets.QLineEdit()
        self.stack_prefix_edit.setPlaceholderText("Optional prefix (e.g., 'Studio_')")
        options_layout.addRow("Stack Prefix:", self.stack_prefix_edit)
        
        self.list_prefix_edit = QtWidgets.QLineEdit()
        self.list_prefix_edit.setPlaceholderText("Optional prefix (e.g., 'cat_')")
        options_layout.addRow("List Prefix:", self.list_prefix_edit)
        
        # Copy policy
        self.copy_policy_combo = QtWidgets.QComboBox()
        self.copy_policy_combo.addItems(["hard_copy", "soft_copy"])
        self.copy_policy_combo.setCurrentText(self.config.get('default_copy_policy', 'hard_copy'))
        options_layout.addRow("Copy Policy:", self.copy_policy_combo)
        
        # Max depth
        self.max_depth_spin = QtWidgets.QSpinBox()
        self.max_depth_spin.setMinimum(1)
        self.max_depth_spin.setMaximum(10)
        self.max_depth_spin.setValue(3)
        options_layout.addRow("Max Nesting Depth:", self.max_depth_spin)
        
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        # Preview area (shows planned structure)
        preview_label = QtWidgets.QLabel("<b>Preview Structure:</b>")
        layout.addWidget(preview_label)
        
        self.preview_tree = QtWidgets.QTreeWidget()
        self.preview_tree.setHeaderLabels(["Name", "Type", "Media Files"])
        self.preview_tree.setAlternatingRowColors(True)
        self.preview_tree.setMaximumHeight(200)
        layout.addWidget(self.preview_tree)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        self.scan_btn = QtWidgets.QPushButton("Scan Folder")
        self.scan_btn.clicked.connect(self.scan_folder)
        self.scan_btn.setEnabled(False)
        
        self.ingest_btn = QtWidgets.QPushButton("Start Ingestion")
        self.ingest_btn.clicked.connect(self.start_ingestion)
        self.ingest_btn.setEnabled(False)
        self.ingest_btn.setStyleSheet("background-color: #16c6b0; font-weight: bold;")
        
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(self.scan_btn)
        button_layout.addWidget(self.ingest_btn)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        # Store scanned structure
        self.scanned_structure = None
    
    def select_folder(self):
        """Open folder selection dialog."""
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Library Folder", ""
        )
        
        if folder:
            self.folder_path_edit.setText(folder)
            self.scan_btn.setEnabled(True)
            self.preview_tree.clear()
            self.scanned_structure = None
            self.ingest_btn.setEnabled(False)
    
    def scan_folder(self):
        """Scan folder structure and show preview."""
        folder_path = self.folder_path_edit.text()
        if not folder_path or not os.path.exists(folder_path):
            QtWidgets.QMessageBox.warning(self, "Invalid Folder", "Please select a valid folder.")
            return
        
        # Show progress
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        
        try:
            # Scan structure
            self.scanned_structure = self._scan_directory_structure(
                folder_path,
                self.max_depth_spin.value()
            )
            
            # Display preview
            self._display_preview(self.scanned_structure)
            
            # Enable ingest button
            self.ingest_btn.setEnabled(True)
            
            QtWidgets.QMessageBox.information(
                self, "Scan Complete",
                "Found {} stacks, {} lists/sub-lists, {} media files".format(
                    len(self.scanned_structure),
                    sum(self._count_lists(stack) for stack in self.scanned_structure.values()),
                    sum(self._count_files(stack) for stack in self.scanned_structure.values())
                )
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Scan Error", "Failed to scan folder: {}".format(str(e)))
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
    
    def _scan_directory_structure(self, root_path, max_depth):
        """
        Recursively scan directory structure.
        
        Returns:
            dict: {stack_name: {'lists': {list_name: {'sub_lists': {...}, 'files': [...]}, ...}, 'files': []}}
        """
        structure = {}
        
        # Get top-level folders (these become Stacks)
        for item in os.listdir(root_path):
            item_path = os.path.join(root_path, item)
            
            if os.path.isdir(item_path):
                stack_name = self.stack_prefix_edit.text() + item
                structure[stack_name] = {
                    'path': item_path,
                    'lists': {},
                    'files': []
                }
                
                # Scan Lists and Sub-Lists
                self._scan_lists_recursive(
                    item_path,
                    structure[stack_name]['lists'],
                    current_depth=1,
                    max_depth=max_depth
                )
                
                # Get media files in stack root
                structure[stack_name]['files'] = self._get_media_files(item_path)
        
        return structure
    
    def _scan_lists_recursive(self, folder_path, lists_dict, current_depth, max_depth):
        """Recursively scan lists and sub-lists."""
        if current_depth > max_depth:
            return
        
        for item in os.listdir(folder_path):
            item_path = os.path.join(folder_path, item)
            
            if os.path.isdir(item_path):
                list_name = self.list_prefix_edit.text() + item
                lists_dict[list_name] = {
                    'path': item_path,
                    'sub_lists': {},
                    'files': []
                }
                
                # Scan sub-lists
                self._scan_lists_recursive(
                    item_path,
                    lists_dict[list_name]['sub_lists'],
                    current_depth + 1,
                    max_depth
                )
                
                # Get media files
                lists_dict[list_name]['files'] = self._get_media_files(item_path)
    
    def _get_media_files(self, folder_path):
        """Get all media files in folder (non-recursive)."""
        media_extensions = ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.exr', '.dpx', 
                           '.mp4', '.mov', '.avi', '.mkv', '.obj', '.fbx', '.abc', '.nk']
        
        media_files = []
        for item in os.listdir(folder_path):
            item_path = os.path.join(folder_path, item)
            if os.path.isfile(item_path):
                _, ext = os.path.splitext(item)
                if ext.lower() in media_extensions:
                    media_files.append(item_path)
        
        return media_files
    
    def _display_preview(self, structure):
        """Display scanned structure in tree widget."""
        self.preview_tree.clear()
        
        for stack_name, stack_data in structure.items():
            stack_item = QtWidgets.QTreeWidgetItem([
                stack_name, "Stack", str(len(stack_data['files']))
            ])
            stack_item.setIcon(0, self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon))
            stack_item.setForeground(0, QtGui.QBrush(QtGui.QColor("#ff9a3c")))
            self.preview_tree.addTopLevelItem(stack_item)
            
            # Add lists
            self._add_lists_to_tree(stack_item, stack_data['lists'])
        
        self.preview_tree.expandAll()
    
    def _add_lists_to_tree(self, parent_item, lists_dict):
        """Recursively add lists to tree widget."""
        for list_name, list_data in lists_dict.items():
            list_item = QtWidgets.QTreeWidgetItem([
                list_name, "List", str(len(list_data['files']))
            ])
            list_item.setIcon(0, self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon))
            list_item.setForeground(0, QtGui.QBrush(QtGui.QColor("#16c6b0")))
            parent_item.addChild(list_item)
            
            # Add sub-lists recursively
            if list_data['sub_lists']:
                self._add_lists_to_tree(list_item, list_data['sub_lists'])
    
    def _count_lists(self, stack_data):
        """Count total lists in stack."""
        count = len(stack_data['lists'])
        for list_data in stack_data['lists'].values():
            count += self._count_sub_lists(list_data)
        return count
    
    def _count_sub_lists(self, list_data):
        """Count total sub-lists recursively."""
        count = len(list_data['sub_lists'])
        for sub_list_data in list_data['sub_lists'].values():
            count += self._count_sub_lists(sub_list_data)
        return count
    
    def _count_files(self, stack_data):
        """Count total files in stack."""
        count = len(stack_data['files'])
        for list_data in stack_data['lists'].values():
            count += self._count_files_in_list(list_data)
        return count
    
    def _count_files_in_list(self, list_data):
        """Count total files in list recursively."""
        count = len(list_data['files'])
        for sub_list_data in list_data['sub_lists'].values():
            count += self._count_files_in_list(sub_list_data)
        return count
    
    def start_ingestion(self):
        """Start bulk ingestion process."""
        if not self.scanned_structure:
            QtWidgets.QMessageBox.warning(self, "No Structure", "Please scan a folder first.")
            return
        
        # Confirm
        reply = QtWidgets.QMessageBox.question(
            self, "Confirm Ingestion",
            "Start bulk ingestion?\n\nThis will create Stacks/Lists and ingest all media files.\n"
            "This operation may take several minutes.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply != QtWidgets.QMessageBox.Yes:
            return
        
        # Count total files for progress
        total_files = sum(self._count_files(stack) for stack in self.scanned_structure.values())
        
        # Create progress dialog
        progress = QtWidgets.QProgressDialog("Ingesting library...", "Cancel", 0, total_files, self)
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setMinimumDuration(0)
        
        success_count = 0
        error_count = 0
        processed = 0
        
        copy_policy = self.copy_policy_combo.currentText()
        
        try:
            # Process each stack
            for stack_name, stack_data in self.scanned_structure.items():
                if progress.wasCanceled():
                    break
                
                # Create stack
                stack_id = self.db.create_stack(stack_name, stack_data['path'])
                
                # Ingest stack files
                for filepath in stack_data['files']:
                    if progress.wasCanceled():
                        break
                    
                    progress.setValue(processed)
                    progress.setLabelText("Ingesting: {}".format(os.path.basename(filepath)))
                    
                    # Create temporary list for stack-level files
                    if not stack_data['lists']:
                        temp_list_id = self.db.create_list(stack_id, "_root")
                    
                    processed += 1
                
                # Process lists
                s, e, processed = self._ingest_lists_recursive(
                    stack_id, None, stack_data['lists'], copy_policy, progress, processed
                )
                success_count += s
                error_count += e
            
            progress.setValue(total_files)
            
            # Show result
            QtWidgets.QMessageBox.information(
                self, "Ingestion Complete",
                "Library ingested successfully!\n\n"
                "{} files ingested\n{} errors".format(success_count, error_count)
            )
            
            self.accept()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ingestion Error", "Failed: {}".format(str(e)))
    
    def _ingest_lists_recursive(self, stack_id, parent_list_id, lists_dict, copy_policy, progress, processed):
        """Recursively ingest lists and their files."""
        success_count = 0
        error_count = 0
        
        for list_name, list_data in lists_dict.items():
            if progress.wasCanceled():
                break
            
            # Create list
            list_id = self.db.create_list(stack_id, list_name, parent_list_id=parent_list_id)
            
            # Ingest files
            for filepath in list_data['files']:
                if progress.wasCanceled():
                    break
                
                progress.setValue(processed)
                progress.setLabelText("Ingesting: {}".format(os.path.basename(filepath)))
                
                result = self.ingestion.ingest_file(filepath, list_id, copy_policy=copy_policy)
                
                if result['success']:
                    success_count += 1
                else:
                    error_count += 1
                
                processed += 1
            
            # Process sub-lists
            s, e, processed = self._ingest_lists_recursive(
                stack_id, list_id, list_data['sub_lists'], copy_policy, progress, processed
            )
            success_count += s
            error_count += e
        
        return success_count, error_count, processed


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
                item.setText("[Added] " + playlist['name'] + " (already added)")
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


class LoginDialog(QtWidgets.QDialog):
    """Login dialog for user authentication."""
    
    def __init__(self, db_manager, parent=None):
        super(LoginDialog, self).__init__(parent)
        self.db = db_manager
        self.authenticated_user = None
        
        self.setWindowTitle("Stax - Login")
        self.setModal(True)
        self.setFixedSize(400, 250)
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Logo/Title
        title_label = QtWidgets.QLabel("Stax")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #16c6b0; padding: 10px;")
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title_label)
        
        subtitle_label = QtWidgets.QLabel("Please login to continue")
        subtitle_label.setStyleSheet("color: #888888; font-size: 12px;")
        subtitle_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(subtitle_label)
        
        # Form layout
        form = QtWidgets.QFormLayout()
        form.setSpacing(10)
        
        # Username
        self.username_edit = QtWidgets.QLineEdit()
        self.username_edit.setPlaceholderText("Enter username")
        self.username_edit.setMinimumHeight(30)
        form.addRow("Username:", self.username_edit)
        
        # Password
        self.password_edit = QtWidgets.QLineEdit()
        self.password_edit.setPlaceholderText("Enter password")
        self.password_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.password_edit.setMinimumHeight(30)
        self.password_edit.returnPressed.connect(self.attempt_login)
        form.addRow("Password:", self.password_edit)
        
        layout.addLayout(form)
        
        # Error label
        self.error_label = QtWidgets.QLabel()
        self.error_label.setStyleSheet("color: #ff6b6b; font-size: 11px;")
        self.error_label.setAlignment(QtCore.Qt.AlignCenter)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        
        layout.addStretch()
        
        # Button box
        button_layout = QtWidgets.QHBoxLayout()
        
        login_btn = QtWidgets.QPushButton("Login")
        login_btn.setMinimumHeight(35)
        login_btn.setStyleSheet("""
            QPushButton {
                background-color: #16c6b0;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 3px;
                padding: 5px 20px;
            }
            QPushButton:hover {
                background-color: #14b39e;
            }
            QPushButton:pressed {
                background-color: #129a87;
            }
        """)
        login_btn.clicked.connect(self.attempt_login)
        button_layout.addWidget(login_btn)
        
        guest_btn = QtWidgets.QPushButton("Continue as Guest")
        guest_btn.setMinimumHeight(35)
        guest_btn.clicked.connect(self.continue_as_guest)
        button_layout.addWidget(guest_btn)
        
        layout.addLayout(button_layout)
        
        # Info label
        info_label = QtWidgets.QLabel("Default: admin / admin")
        info_label.setStyleSheet("color: #666666; font-size: 10px; font-style: italic;")
        info_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(info_label)
        
        # Focus username
        self.username_edit.setFocus()
    
    def attempt_login(self):
        """Attempt to authenticate user."""
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        
        if not username or not password:
            self.show_error("Please enter both username and password")
            return
        
        # Authenticate
        user = self.db.authenticate_user(username, password)
        
        if user:
            self.authenticated_user = user
            
            # Create session
            import socket
            machine_name = socket.gethostname()
            self.db.create_session(user['user_id'], machine_name)
            
            self.accept()
        else:
            self.show_error("Invalid username or password")
            self.password_edit.clear()
            self.password_edit.setFocus()
    
    def continue_as_guest(self):
        """Continue without authentication (read-only mode)."""
        # Create a guest user object
        self.authenticated_user = {
            'user_id': None,
            'username': 'guest',
            'role': 'user',
            'email': None
        }
        self.accept()
    
    def show_error(self, message):
        """Show error message."""
        self.error_label.setText(message)
        self.error_label.show()


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
        
        # Tags (editable with autocomplete)
        tags_container = QtWidgets.QWidget()
        tags_layout = QtWidgets.QVBoxLayout(tags_container)
        tags_layout.setContentsMargins(0, 0, 0, 0)
        
        self.tags_edit = QtWidgets.QLineEdit()
        self.tags_edit.setPlaceholderText("Comma-separated tags (e.g., fire, explosion, outdoor)")
        
        # Setup autocomplete for tags
        all_tags = self.db.get_all_tags()
        completer = QtWidgets.QCompleter(all_tags)
        completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
        self.tags_edit.setCompleter(completer)
        
        tags_layout.addWidget(self.tags_edit)
        
        # Tag suggestions label
        self.tag_suggestions_label = QtWidgets.QLabel()
        self.tag_suggestions_label.setStyleSheet("color: #16c6b0; font-size: 10px; font-style: italic;")
        self.tag_suggestions_label.setWordWrap(True)
        if all_tags:
            popular_tags = all_tags[:10]  # Show first 10
            self.tag_suggestions_label.setText("Popular tags: " + ", ".join(popular_tags))
        tags_layout.addWidget(self.tag_suggestions_label)
        
        form.addRow("Tags:", tags_container)
        
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


class PaginationWidget(QtWidgets.QWidget):
    """Pagination control widget for large element lists."""
    
    page_changed = QtCore.Signal(int)  # Emits current page number (0-indexed)
    
    def __init__(self, parent=None):
        super(PaginationWidget, self).__init__(parent)
        self.current_page = 0
        self.total_pages = 0
        self.items_per_page = 100
        self.total_items = 0
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup pagination UI."""
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # First page button
        self.first_btn = QtWidgets.QPushButton()
        self.first_btn.setIcon(get_icon('previous', size=16))
        self.first_btn.setToolTip("First Page")
        self.first_btn.setMaximumWidth(40)
        self.first_btn.clicked.connect(lambda: self.go_to_page(0))
        layout.addWidget(self.first_btn)
        
        # Previous button
        self.prev_btn = QtWidgets.QPushButton()
        self.prev_btn.setIcon(get_icon('previous', size=16))
        self.prev_btn.setToolTip("Previous Page")
        self.prev_btn.setMaximumWidth(40)
        self.prev_btn.clicked.connect(self.previous_page)
        layout.addWidget(self.prev_btn)
        
        # Page info label
        self.page_label = QtWidgets.QLabel("Page 0 of 0")
        self.page_label.setAlignment(QtCore.Qt.AlignCenter)
        self.page_label.setMinimumWidth(150)
        layout.addWidget(self.page_label)
        
        # Next button
        self.next_btn = QtWidgets.QPushButton()
        self.next_btn.setIcon(get_icon('next', size=16))
        self.next_btn.setToolTip("Next Page")
        self.next_btn.setMaximumWidth(40)
        self.next_btn.clicked.connect(self.next_page)
        layout.addWidget(self.next_btn)
        
        # Last page button
        self.last_btn = QtWidgets.QPushButton()
        self.last_btn.setIcon(get_icon('next', size=16))
        self.last_btn.setToolTip("Last Page")
        self.last_btn.setMaximumWidth(40)
        self.last_btn.clicked.connect(lambda: self.go_to_page(self.total_pages - 1))
        layout.addWidget(self.last_btn)
        
        layout.addStretch()
        
        # Items per page selector
        layout.addWidget(QtWidgets.QLabel("Items per page:"))
        self.items_combo = QtWidgets.QComboBox()
        self.items_combo.addItems(['50', '100', '200', '500'])
        self.items_combo.setCurrentText('100')
        self.items_combo.currentTextChanged.connect(self.on_items_per_page_changed)
        layout.addWidget(self.items_combo)
        
        # Info label (showing X-Y of Z)
        self.info_label = QtWidgets.QLabel("")
        self.info_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.info_label)
        
        self.update_buttons()
    
    def set_total_items(self, total):
        """Set total number of items and recalculate pages."""
        self.total_items = total
        self.total_pages = max(1, (total + self.items_per_page - 1) // self.items_per_page)
        
        # Reset to first page if current page is out of range
        if self.current_page >= self.total_pages:
            self.current_page = 0
        
        self.update_ui()
    
    def set_items_per_page(self, count):
        """Set items per page."""
        self.items_per_page = count
        self.items_combo.setCurrentText(str(count))
        self.set_total_items(self.total_items)  # Recalculate
    
    def on_items_per_page_changed(self, text):
        """Handle items per page change."""
        self.items_per_page = int(text)
        self.set_total_items(self.total_items)  # Recalculate
        self.page_changed.emit(self.current_page)
    
    def go_to_page(self, page):
        """Navigate to specific page."""
        if 0 <= page < self.total_pages and page != self.current_page:
            self.current_page = page
            self.update_ui()
            self.page_changed.emit(self.current_page)
    
    def next_page(self):
        """Go to next page."""
        if self.current_page < self.total_pages - 1:
            self.go_to_page(self.current_page + 1)
    
    def previous_page(self):
        """Go to previous page."""
        if self.current_page > 0:
            self.go_to_page(self.current_page - 1)
    
    def update_ui(self):
        """Update pagination UI elements."""
        if self.total_items == 0:
            self.page_label.setText("Page 0 of 0")
            self.info_label.setText("")
        else:
            self.page_label.setText("Page {} of {}".format(self.current_page + 1, self.total_pages))
            
            # Calculate item range
            start_item = self.current_page * self.items_per_page + 1
            end_item = min((self.current_page + 1) * self.items_per_page, self.total_items)
            self.info_label.setText("Showing {}-{} of {} items".format(start_item, end_item, self.total_items))
        
        self.update_buttons()
    
    def update_buttons(self):
        """Enable/disable buttons based on current page."""
        self.first_btn.setEnabled(self.current_page > 0)
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < self.total_pages - 1)
        self.last_btn.setEnabled(self.current_page < self.total_pages - 1)
    
    def get_page_slice(self):
        """Get (start, end) indices for current page."""
        start = self.current_page * self.items_per_page
        end = min(start + self.items_per_page, self.total_items)
        return start, end


class RegisterToolsetDialog(QtWidgets.QDialog):
    """Dialog for registering selected Nuke nodes as a toolset."""
    
    def __init__(self, db_manager, nuke_bridge, config, parent=None):
        super(RegisterToolsetDialog, self).__init__(parent)
        self.db = db_manager
        self.nuke_bridge = nuke_bridge
        self.config = config
        self.toolset_path = None
        
        self.setWindowTitle("Register Toolset")
        self.setMinimumWidth(500)
        self.setup_ui()
    
    def setup_ui(self):
        """Setup dialog UI."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Info label
        info_label = QtWidgets.QLabel(
            "Save the currently selected nodes in Nuke as a reusable toolset.\n"
            "The toolset will be saved as a .nk file and cataloged for easy access."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #888; font-size: 11px; padding: 10px; background: #2a2a2a; border-radius: 5px;")
        layout.addWidget(info_label)
        
        # Form layout
        form = QtWidgets.QFormLayout()
        form.setSpacing(10)
        
        # Toolset name
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("e.g., 'Glow and Sharpen'")
        form.addRow("Toolset Name:", self.name_edit)
        
        # List selection
        self.list_combo = QtWidgets.QComboBox()
        self.load_lists()
        form.addRow("Save to List:", self.list_combo)
        
        # Comment
        self.comment_edit = QtWidgets.QTextEdit()
        self.comment_edit.setPlaceholderText("Optional description of the toolset...")
        self.comment_edit.setMaximumHeight(80)
        form.addRow("Comment:", self.comment_edit)
        
        # Generate preview option
        self.gen_preview_check = QtWidgets.QCheckBox("Generate preview image")
        self.gen_preview_check.setChecked(True)
        self.gen_preview_check.setToolTip("Capture a preview of the node graph")
        form.addRow("", self.gen_preview_check)
        
        layout.addLayout(form)
        
        # Button box
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept_toolset)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def load_lists(self):
        """Load available lists into combo box."""
        # Get all lists from all stacks
        stacks = self.db.get_all_stacks()
        for stack in stacks:
            lists = self.db.get_lists_by_stack(stack['stack_id'])
            for lst in lists:
                self.list_combo.addItem(
                    "{} > {}".format(stack['name'], lst['name']),
                    lst['list_id']
                )
    
    def accept_toolset(self):
        """Save toolset and ingest into database."""
        name = self.name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Missing Name", "Please enter a toolset name.")
            return
        
        list_id = self.list_combo.currentData()
        if not list_id:
            QtWidgets.QMessageBox.warning(self, "No List", "Please select a list to save the toolset to.")
            return
        
        try:
            # Create toolset file path
            import tempfile
            import hashlib
            import time
            
            # Generate unique filename
            timestamp = str(int(time.time()))
            name_hash = hashlib.md5(name.encode('utf-8')).hexdigest()[:8]
            filename = "toolset_{}_{}.nk".format(name_hash, timestamp)
            
            # Save to temporary location first
            temp_path = os.path.join(tempfile.gettempdir(), filename)
            
            # Save selected nodes as toolset
            success = self.nuke_bridge.save_selected_as_toolset(temp_path)
            
            if not success or not os.path.exists(temp_path):
                QtWidgets.QMessageBox.critical(self, "Error", "Failed to save toolset from Nuke.")
                return
            
            # Determine final storage path
            repository_path = self.config.get('default_repository_path')
            if not os.path.exists(repository_path):
                os.makedirs(repository_path)
            
            final_path = os.path.join(repository_path, filename)
            
            # Move toolset file to repository
            import shutil
            shutil.move(temp_path, final_path)
            
            # Generate preview if requested
            preview_path = None
            if self.gen_preview_check.isChecked():
                preview_dir = self.config.get('preview_dir')
                if not os.path.exists(preview_dir):
                    os.makedirs(preview_dir)
                
                preview_filename = "toolset_{}_{}.png".format(name_hash, timestamp)
                preview_path = os.path.join(preview_dir, preview_filename)
                
                # Capture node graph preview (if available)
                try:
                    self.nuke_bridge.capture_node_graph_preview(preview_path)
                except Exception as e:
                    print("Preview generation failed: {}".format(str(e)))
                    preview_path = None
            
            # Ingest toolset into database
            element_data = {
                'name': name,
                'list_fk': list_id,
                'type': 'toolset',
                'format': 'nk',
                'filepath_soft': None,  # Toolset is always hard copy
                'filepath_hard': final_path,
                'is_hard_copy': True,
                'preview_path': preview_path,
                'comment': self.comment_edit.toPlainText().strip() or None,
                'frames': 1,
                'width': None,
                'height': None,
                'size_bytes': os.path.getsize(final_path)
            }
            
            element_id = self.db.add_element(**element_data)
            
            # Log to history
            self.db.add_history_entry(
                'toolset_registered',
                "Registered toolset: {}".format(name),
                {'element_id': element_id, 'list_id': list_id}
            )
            
            QtWidgets.QMessageBox.information(
                self,
                "Toolset Registered",
                "Toolset '{}' has been saved and cataloged successfully!".format(name)
            )
            
            self.accept()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                "Failed to register toolset: {}".format(str(e))
            )


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
        
        # User authentication
        self.current_user = None
        self.is_admin = False
        
        self.setWindowTitle("Stax")
        self.resize(1400, 800)
        
        # Set application icon
        icon_path = os.path.join(os.path.dirname(__file__), 'resources', 'logo.png')
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))
        
        self.setup_ui()
        self.setup_shortcuts()
        
        # Show login dialog
        self.show_login()
    
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
        self.media_display = MediaDisplayWidget(self.db, self.config, self.nuke_bridge, main_window=self)
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
        self.settings_panel = SettingsPanel(self.config, self.db, main_window=self)
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
        ingest_action.setIcon(get_icon('upload', size=16))
        ingest_action.setShortcut("Ctrl+I")
        ingest_action.triggered.connect(self.ingest_files)
        file_menu.addAction(ingest_action)
        
        ingest_library_action = QtWidgets.QAction("Ingest Library...", self)
        ingest_library_action.setIcon(get_icon('folder', size=16))
        ingest_library_action.setShortcut("Ctrl+Shift+I")
        ingest_library_action.triggered.connect(self.ingest_library)
        file_menu.addAction(ingest_library_action)
        
        file_menu.addSeparator()
        
        logout_action = QtWidgets.QAction("Logout", self)
        logout_action.setShortcut("Ctrl+L")
        logout_action.triggered.connect(self.logout)
        file_menu.addAction(logout_action)
        
        exit_action = QtWidgets.QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Search menu
        search_menu = menubar.addMenu("Search")
        
        advanced_search_action = QtWidgets.QAction("Advanced Search...", self)
        advanced_search_action.setIcon(get_icon('search', size=16))
        advanced_search_action.setShortcut("Ctrl+F")
        advanced_search_action.triggered.connect(self.show_advanced_search)
        search_menu.addAction(advanced_search_action)
        
        # Nuke menu
        nuke_menu = menubar.addMenu("Nuke")
        
        register_toolset_action = QtWidgets.QAction("Register Selection as Toolset...", self)
        register_toolset_action.setIcon(get_icon('add', size=16))
        register_toolset_action.setShortcut("Ctrl+Shift+T")
        register_toolset_action.triggered.connect(self.register_toolset)
        register_toolset_action.setToolTip("Save selected Nuke nodes as a reusable toolset")
        nuke_menu.addAction(register_toolset_action)
        
        # View menu
        view_menu = menubar.addMenu("View")
        
        history_action = QtWidgets.QAction("History Panel", self)
        history_action.setIcon(get_icon('history', size=16))
        history_action.setShortcut("Ctrl+2")
        history_action.setCheckable(True)
        history_action.triggered.connect(self.toggle_history)
        view_menu.addAction(history_action)
        
        settings_action = QtWidgets.QAction("Settings Panel", self)
        settings_action.setIcon(get_icon('settings', size=16))
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
    
    def show_login(self):
        """Show login dialog."""
        login_dialog = LoginDialog(self.db, self)
        if login_dialog.exec_():
            self.current_user = login_dialog.authenticated_user
            self.is_admin = self.current_user and self.current_user.get('role') == 'admin'
            
            # Update window title with username
            username = self.current_user['username'] if self.current_user else 'Guest'
            role_text = ' (Admin)' if self.is_admin else ''
            self.setWindowTitle("Stax - {}{}".format(username, role_text))
            
            self.statusBar().showMessage("Logged in as: {}".format(username))
        else:
            # User cancelled login - exit application
            QtWidgets.QApplication.quit()
    
    def check_admin_permission(self, action_name="this action"):
        """
        Check if current user has admin permissions.
        Shows error dialog if not.
        
        Args:
            action_name (str): Name of the action being attempted
            
        Returns:
            bool: True if user is admin
        """
        if not self.is_admin:
            QtWidgets.QMessageBox.warning(
                self,
                "Permission Denied",
                "You need administrator privileges to perform {}.\n\n"
                "Current user: {} ({})\n\n"
                "Please login as an administrator.".format(
                    action_name,
                    self.current_user['username'] if self.current_user else 'guest',
                    self.current_user.get('role', 'guest') if self.current_user else 'guest'
                )
            )
            return False
        return True
    
    def logout(self):
        """Logout current user and show login dialog."""
        if self.current_user and self.current_user.get('user_id'):
            # End session
            import socket
            machine_name = socket.gethostname()
            session = self.db.get_active_session(self.current_user['user_id'], machine_name)
            if session:
                self.db.end_session(session['session_id'])
        
        # Show login again
        self.show_login()
    
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
    
    def ingest_library(self):
        """Open Library Ingest dialog to bulk-ingest folder structures."""
        dialog = IngestLibraryDialog(self.db, self.ingestion, self.config, self)
        if dialog.exec_():
            # Refresh stacks/lists after library ingestion
            self.stacks_panel.load_data()
    
    def register_toolset(self):
        """Open Register Toolset dialog to save selected Nuke nodes as a toolset."""
        dialog = RegisterToolsetDialog(self.db, self.nuke_bridge, self.config, self)
        if dialog.exec_():
            # Refresh media display to show new toolset
            if hasattr(self.media_display, 'current_list_id') and self.media_display.current_list_id:
                self.media_display.load_elements(self.media_display.current_list_id)
            self.statusBar().showMessage("Toolset registered successfully")
    
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
            "About Stax",
            "<h3>Stax</h3>"
            "<p>Version 0.1.0 (Alpha)</p>"
            "<p>Advanced solution for mass production stock footage management.</p>"
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
