# -*- coding: utf-8 -*-
"""
Video Player Widget with embedded video playback using ffpyplayer
Provides video playback with timeline scrubbing and metadata display
Python 2.7/3+ compatible
"""

import os
import sys

try:
    import dependency_bootstrap
except ImportError:
    project_root_guess = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if project_root_guess not in sys.path:
        sys.path.insert(0, project_root_guess)
    import dependency_bootstrap

dependency_bootstrap.bootstrap()

from PySide2 import QtWidgets, QtCore, QtGui
import subprocess
import json
import ctypes

_FFPY_IMPORT_ERROR = None


def _import_ffpyplayer():
    """Attempt to import ffpyplayer MediaPlayer."""
    global _FFPY_IMPORT_ERROR
    try:
        from ffpyplayer.player import MediaPlayer as _MediaPlayer  # pylint: disable=import-error
        _FFPY_IMPORT_ERROR = None
        return _MediaPlayer
    except ImportError as err:
        _FFPY_IMPORT_ERROR = err
        return None


FFMediaPlayer = _import_ffpyplayer()

if FFMediaPlayer is None:
    # Try to load bundled wheels from ../dependencies
    _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    _dependencies_root = os.path.join(_project_root, 'dependencies')
    if os.path.isdir(_dependencies_root) and _dependencies_root not in sys.path:
        sys.path.insert(0, _dependencies_root)
    _ffpy_pkg = os.path.join(_dependencies_root, 'ffpyplayer')
    if os.path.isdir(_ffpy_pkg) and _ffpy_pkg not in sys.path:
        sys.path.insert(0, _ffpy_pkg)
    FFMediaPlayer = _import_ffpyplayer()

if FFMediaPlayer is None:
    print("Warning: ffpyplayer not available ({}). Install with: pip install ffpyplayer".format(_FFPY_IMPORT_ERROR or 'unknown error'))


class FFpyVideoWidget(QtWidgets.QLabel):
    """Custom QLabel-based widget that shows QPixmap frames from raw RGB byte data."""
    
    def __init__(self, parent=None):
        super(FFpyVideoWidget, self).__init__(parent)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setMinimumSize(320, 240)
        self._last_pixmap = None
        self.setStyleSheet("""
            QLabel {
                background-color: #1e1e1e;
                border: 2px solid #16c6b0;
                border-radius: 5px;
            }
        """)
        self.setText("No media loaded")
        self.setStyleSheet(self.styleSheet() + "QLabel { color: #888; }")
    
    def show_frame_rgb24(self, data, width, height):
        """Display a frame from RGB24 byte data."""
        try:
            bytes_per_line = width * 3
            image = QtGui.QImage(data, width, height, bytes_per_line, QtGui.QImage.Format_RGB888)
            pix = QtGui.QPixmap.fromImage(image)
            self._last_pixmap = pix
            self._update_scaled_pixmap()
            if self.text():
                self.setText("")
        except Exception as e:
            print("Failed to show frame: {}".format(e))
    
    def resizeEvent(self, event):
        """Handle resize to rescale pixmap."""
        super(FFpyVideoWidget, self).resizeEvent(event)
        self._update_scaled_pixmap()

    def clear_frame(self, message="No media loaded"):
        """Clear the currently displayed frame."""
        self._last_pixmap = None
        self.setPixmap(QtGui.QPixmap())
        self.setText(message)

    def _update_scaled_pixmap(self):
        """Scale and show the cached pixmap for the current widget size."""
        if self._last_pixmap and not self._last_pixmap.isNull():
            scaled = self._last_pixmap.scaled(self.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            self.setPixmap(scaled)


class PlayerController(QtCore.QObject):
    """Controller that wraps ffpyplayer.MediaPlayer and emits frames as Qt signals."""
    
    frame_ready = QtCore.Signal(bytes, int, int)  # data, width, height
    finished = QtCore.Signal()
    duration_changed = QtCore.Signal(float)  # duration in seconds
    position_changed = QtCore.Signal(float)  # position in seconds
    
    def __init__(self, parent=None):
        super(PlayerController, self).__init__(parent)
        self.player = None
        self._timer = QtCore.QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timer)
        self._playing = False
        self._duration = 0.0
        self._current_position = 0.0
    
    def open(self, filename):
        """Open a media file."""
        if FFMediaPlayer is None:
            raise RuntimeError(
                "ffpyplayer not available ({}). Install with: pip install ffpyplayer".format(
                    _FFPY_IMPORT_ERROR or 'unknown import error'
                )
            )
        
        self.close()
        self._duration = 0.0
        self._current_position = 0.0
        
        try:
            # Request rgb24 output to simplify conversion to QImage
            self.player = FFMediaPlayer(filename, ff_opts={'out_fmt': 'rgb24'})
            self._playing = True
            
            # Try to get duration from metadata
            try:
                if hasattr(self.player, 'get_metadata'):
                    metadata = self.player.get_metadata()
                    if metadata and 'duration' in metadata:
                        self._duration = float(metadata['duration'])
                    else:
                        self._duration = 0.0
                else:
                    self._duration = 0.0
            except Exception:
                self._duration = 0.0
            
            if self._duration and self._duration > 0:
                self.duration_changed.emit(self._duration)
            
            # Start polling loop
            QtCore.QTimer.singleShot(0, self._on_timer)
        except Exception as e:
            raise RuntimeError("Failed to open file: {}".format(str(e)))
    
    def play(self):
        """Resume playback."""
        if not self.player:
            return
        try:
            self.player.set_pause(False)
        except Exception:
            pass
        self._playing = True
        QtCore.QTimer.singleShot(0, self._on_timer)
    
    def pause(self):
        """Pause playback."""
        if not self.player:
            return
        try:
            self.player.set_pause(True)
        except Exception:
            pass
        self._playing = False
    
    def stop(self):
        """Stop playback and close player."""
        self.close()
    
    def seek(self, position_seconds, relative=False, accurate=True):
        """Seek to a specific position in seconds."""
        if not self.player:
            return
        try:
            self.player.seek(position_seconds, relative=relative, accurate=accurate)
            if relative:
                self._current_position += position_seconds
            else:
                self._current_position = position_seconds

            if self._duration:
                self._current_position = max(0.0, min(self._current_position, self._duration))
            else:
                self._current_position = max(0.0, self._current_position)
            self.position_changed.emit(self._current_position)
        except Exception as e:
            print("Seek failed: {}".format(e))
    
    def get_position(self):
        """Get current playback position in seconds."""
        return self._current_position
    
    def get_duration(self):
        """Get media duration in seconds."""
        return self._duration
    
    def is_playing(self):
        """Check if currently playing."""
        return self._playing
    
    def close(self):
        """Close the player and clean up."""
        self._timer.stop()
        if self.player:
            try:
                self.player.close_player()
            except Exception:
                pass
            try:
                del self.player
            except Exception:
                pass
            self.player = None
        self._playing = False
        self._current_position = 0.0
        self._duration = 0.0
    
    def _on_timer(self):
        """Timer callback to fetch and emit frames."""
        if not self.player or not self._playing:
            return
        
        try:
            frame, val = self.player.get_frame()
        except Exception as e:
            print("Error reading frame: {}".format(e))
            return
        
        if val == 'eof':
            self.finished.emit()
            self._playing = False
            return
        
        if frame is None:
            # Not ready yet - poll soon
            self._timer.start(10)
            return
        
        # frame is a tuple (ffpyplayer.pic.Image, pts)
        try:
            img, pts = frame
            self._current_position = pts
            self.position_changed.emit(pts)
            
            # Try to update duration if we haven't gotten it yet
            if self._duration == 0.0:
                try:
                    if hasattr(self.player, 'get_metadata'):
                        metadata = self.player.get_metadata()
                        if metadata and 'duration' in metadata:
                            self._duration = float(metadata['duration'])
                            if self._duration > 0:
                                self.duration_changed.emit(self._duration)
                except Exception:
                    pass
            
            # Extract RGB24 byte data
            planes = img.to_bytearray()
            if isinstance(planes, (list, tuple)):
                data = planes[0]
            else:
                data = planes
            
            # Ensure bytes
            if isinstance(data, memoryview):
                data = bytes(data)
            elif isinstance(data, bytearray):
                data = bytes(data)
            
            width, height = img.get_size()
            
            # Emit frame for Qt UI
            self.frame_ready.emit(data, width, height)
            
            # Schedule next frame according to val (seconds to wait)
            ms = max(1, int(val * 1000)) if isinstance(val, (float, int)) and val > 0 else 10
            self._timer.start(ms)
        except Exception as e:
            print("Failed to convert ffpyplayer image: {}".format(e))
            # Fallback small delay
            self._timer.start(10)


class VideoPlayerWidget(QtWidgets.QWidget):
    """
    Video player widget with embedded video playback using ffpyplayer.
    Displays video with playback controls, timeline, and metadata.
    """
    
    # Signals
    closed = QtCore.Signal()
    
    def __init__(self, db_manager, config, parent=None):
        super(VideoPlayerWidget, self).__init__(parent)
        self.db = db_manager
        self.config = config
        self.current_element = None
        self._resume_after_scrub = False
        self._duration_known = False
        
        # Create player controller
        self.player_controller = PlayerController(self)
        self.player_controller.frame_ready.connect(self.on_frame_ready)
        self.player_controller.finished.connect(self.on_playback_finished)
        self.player_controller.duration_changed.connect(self.on_duration_changed)
        self.player_controller.position_changed.connect(self.on_position_changed)
        
        # Create video widget
        self.video_widget = FFpyVideoWidget()
        
        self.setup_ui()
        self.setMinimumWidth(400)
        self.setMaximumWidth(600)
    
    def setup_ui(self):
        """Setup the UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Header with close button
        header_layout = QtWidgets.QHBoxLayout()
        
        title_label = QtWidgets.QLabel("Preview")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #16c6b0;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # Close/Exit button (use clearer exit SVG icon)
        close_btn = QtWidgets.QPushButton()
        close_icon_path = os.path.join(os.path.dirname(__file__), '..', 'resources', 'icons', 'exit.svg')
        if not os.path.exists(close_icon_path):
            # Fallback to delete.svg if exit.svg is not yet present
            close_icon_path = os.path.join(os.path.dirname(__file__), '..', 'resources', 'icons', 'delete.svg')
        if os.path.exists(close_icon_path):
            close_btn.setIcon(QtGui.QIcon(close_icon_path))
            close_btn.setIconSize(QtCore.QSize(16, 16))
        close_btn.setMaximumWidth(30)
        close_btn.setStyleSheet("""
            QPushButton { background-color: transparent; border: none; }
            QPushButton:hover { background-color: rgba(255,85,85,0.12); border-radius: 3px; }
        """)
        close_btn.clicked.connect(self.close_panel)
        header_layout.addWidget(close_btn)
        
        layout.addLayout(header_layout)
        
        # Separator
        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(separator)
        
        # Video widget for embedded playback (using FFpyVideoWidget)
        self.video_widget.setMinimumHeight(300)
        layout.addWidget(self.video_widget)
        
        # Timeline slider
        timeline_layout = QtWidgets.QHBoxLayout()
        
        self.current_time_label = QtWidgets.QLabel("00:00:00")
        self.current_time_label.setStyleSheet("color: #16c6b0; font-family: monospace;")
        timeline_layout.addWidget(self.current_time_label)
        
        self.timeline_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.timeline_slider.setMinimum(0)
        self.timeline_slider.setMaximum(0)
        self.timeline_slider.setValue(0)
        self.timeline_slider.setEnabled(False)
        self.timeline_slider.sliderPressed.connect(self.on_slider_pressed)
        self.timeline_slider.sliderReleased.connect(self.on_slider_released)
        self.timeline_slider.sliderMoved.connect(self.on_timeline_scrub)
        self.timeline_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #16c6b0;
                height: 8px;
                background: #2a2a2a;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #16c6b0;
                border: 1px solid #16c6b0;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #1ed4be;
            }
        """)
        timeline_layout.addWidget(self.timeline_slider, 1)
        
        self.total_time_label = QtWidgets.QLabel("00:00:00")
        self.total_time_label.setStyleSheet("color: #888; font-family: monospace;")
        timeline_layout.addWidget(self.total_time_label)
        
        layout.addLayout(timeline_layout)
        
        # Playback controls
        controls_layout = QtWidgets.QHBoxLayout()
        controls_layout.setSpacing(10)
        
        # Play/Pause button (SVG)
        self.play_pause_btn = QtWidgets.QPushButton()
        play_icon_path = os.path.join(os.path.dirname(__file__), '..', 'resources', 'icons', 'play.svg')
        pause_icon_path = os.path.join(os.path.dirname(__file__), '..', 'resources', 'icons', 'pause.svg')
        self._play_icon_path = play_icon_path
        self._pause_icon_path = pause_icon_path
        if os.path.exists(play_icon_path):
            self.play_pause_btn.setIcon(QtGui.QIcon(play_icon_path))
        self.play_pause_btn.setIconSize(QtCore.QSize(20, 20))
        self.play_pause_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                padding: 6px;
            }
            QPushButton:hover { background-color: rgba(22,198,176,0.08); border-radius: 4px; }
        """)
        self.play_pause_btn.clicked.connect(self.toggle_playback)
        self.play_pause_btn.setEnabled(False)
        controls_layout.addWidget(self.play_pause_btn)
        
        # Stop button (SVG)
        self.stop_btn = QtWidgets.QPushButton()
        stop_icon_path = os.path.join(os.path.dirname(__file__), '..', 'resources', 'icons', 'stop_filled.svg')
        if os.path.exists(stop_icon_path):
            self.stop_btn.setIcon(QtGui.QIcon(stop_icon_path))
        self.stop_btn.setIconSize(QtCore.QSize(18, 18))
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton { background-color: transparent; border: none; padding: 6px; }
            QPushButton:hover { background-color: rgba(255,154,60,0.08); border-radius: 4px; }
        """)
        self.stop_btn.clicked.connect(self.stop_playback)
        controls_layout.addWidget(self.stop_btn)
        
        # External player / Fullscreen button
        self.external_btn = QtWidgets.QPushButton()
        ext_icon_path = os.path.join(os.path.dirname(__file__), '..', 'resources', 'icons', 'external_player.svg')
        if os.path.exists(ext_icon_path):
            self.external_btn.setIcon(QtGui.QIcon(ext_icon_path))
        self.external_btn.setIconSize(QtCore.QSize(18, 18))
        self.external_btn.setToolTip('Open in external player')
        self.external_btn.clicked.connect(self.open_in_external_player)
        self.external_btn.setEnabled(False)
        controls_layout.addWidget(self.external_btn)
        
        # Frame navigation
        # Previous frame button (SVG)
        self.prev_frame_btn = QtWidgets.QPushButton()
        prev_icon_path = os.path.join(os.path.dirname(__file__), '..', 'resources', 'icons', 'previous.svg')
        if os.path.exists(prev_icon_path):
            self.prev_frame_btn.setIcon(QtGui.QIcon(prev_icon_path))
        self.prev_frame_btn.setIconSize(QtCore.QSize(16, 16))
        self.prev_frame_btn.setMaximumWidth(40)
        self.prev_frame_btn.setToolTip("Previous Frame")
        self.prev_frame_btn.clicked.connect(lambda: self.step_frame(-1))
        self.prev_frame_btn.setEnabled(False)
        controls_layout.addWidget(self.prev_frame_btn)

        # Next frame button (SVG)
        self.next_frame_btn = QtWidgets.QPushButton()
        next_icon_path = os.path.join(os.path.dirname(__file__), '..', 'resources', 'icons', 'next.svg')
        if os.path.exists(next_icon_path):
            self.next_frame_btn.setIcon(QtGui.QIcon(next_icon_path))
        self.next_frame_btn.setIconSize(QtCore.QSize(16, 16))
        self.next_frame_btn.setMaximumWidth(40)
        self.next_frame_btn.setToolTip("Next Frame")
        self.next_frame_btn.clicked.connect(lambda: self.step_frame(1))
        self.next_frame_btn.setEnabled(False)
        controls_layout.addWidget(self.next_frame_btn)
        
        controls_layout.addStretch()
        
        # Frame counter
        self.frame_label = QtWidgets.QLabel("Frame: 0 / 0")
        self.frame_label.setStyleSheet("color: #888; font-family: monospace;")
        controls_layout.addWidget(self.frame_label)
        
        layout.addLayout(controls_layout)
        
        # Metadata section
        metadata_group = QtWidgets.QGroupBox("Metadata")
        metadata_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                color: #16c6b0;
                border: 1px solid #16c6b0;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        metadata_layout = QtWidgets.QVBoxLayout(metadata_group)
        
        # Metadata display (read-only text area)
        self.metadata_text = QtWidgets.QTextEdit()
        self.metadata_text.setReadOnly(True)
        self.metadata_text.setMaximumHeight(200)
        self.metadata_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #ddd;
                border: 1px solid #444;
                border-radius: 3px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
            }
        """)
        metadata_layout.addWidget(self.metadata_text)
        
        layout.addWidget(metadata_group)
        
        layout.addStretch()

    def _set_controls_enabled(self, enabled):
        """Enable or disable playback-related controls."""
        self.play_pause_btn.setEnabled(enabled)
        self.stop_btn.setEnabled(enabled)
        self.timeline_slider.setEnabled(enabled)
        self.prev_frame_btn.setEnabled(enabled)
        self.next_frame_btn.setEnabled(enabled)

    def _set_play_button_state(self, is_playing):
        """Update the play button's icon and tooltip based on state."""
        icon_path = self._pause_icon_path if is_playing else self._play_icon_path
        if icon_path and os.path.exists(icon_path):
            self.play_pause_btn.setIcon(QtGui.QIcon(icon_path))
        tooltip = "Pause" if is_playing else "Play"
        self.play_pause_btn.setToolTip(tooltip)

    def _shutdown_player(self, clear_element_state=False):
        """Completely stop playback and reset the UI state."""
        self.player_controller.stop()
        self._set_play_button_state(False)
        self._set_controls_enabled(False)
        self.timeline_slider.setValue(0)
        self.timeline_slider.setMaximum(0)
        self._duration_known = False
        self._resume_after_scrub = False
        self.current_time_label.setText("00:00:00")
        self.total_time_label.setText("00:00:00")
        self.frame_label.setText("Frame: 0 / 0")
        self.video_widget.clear_frame("No media loaded")
        if clear_element_state:
            self.current_element = None

    def _get_config_player(self):
        """Retrieve configured external player path from the provided config or prompt the user."""
        try:
            cfg_path = None
            if hasattr(self, 'config') and isinstance(self.config, dict):
                player = self.config.get('external_player')
                if player:
                    return player
        except Exception:
            pass

        # Ask user to pick an executable
        dlg = QtWidgets.QFileDialog(self, 'Select external player executable')
        dlg.setFileMode(QtWidgets.QFileDialog.ExistingFile)
        if dlg.exec_():
            files = dlg.selectedFiles()
            if files:
                player_path = files[0]
                # store (best-effort) back to config if possible
                try:
                    if hasattr(self, 'config') and isinstance(self.config, dict):
                        self.config['external_player'] = player_path
                        # try to write to disk to the project's config if present
                        cfg_file = getattr(self, '_config_file_path', None)
                        if not cfg_file:
                            # look for common project config location
                            possible = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'config.json'))
                            if os.path.exists(os.path.dirname(possible)):
                                cfg_file = possible
                        if cfg_file:
                            try:
                                with open(cfg_file, 'w') as f:
                                    json.dump(self.config, f, indent=2)
                                # remember where we stored it
                                self._config_file_path = cfg_file
                            except Exception:
                                pass
                except Exception:
                    pass
                return player_path
        return None

    def open_in_external_player(self):
        """Open the current element in an external player chosen by the user."""
        if not self.current_element:
            return

        filepath = self.current_element.get('filepath_hard') or self.current_element.get('filepath_soft')
        if not filepath or not os.path.exists(filepath):
            QtWidgets.QMessageBox.warning(self, 'File not found', 'Media file not available for external playback')
            return

        player = self._get_config_player()
        if not player:
            return

        try:
            # On Windows, use shell execute when user provides command like "C:\Program Files\..." or a URL
            if sys.platform == 'win32':
                # Use subprocess.Popen to preserve non-blocking UI
                subprocess.Popen([player, filepath], shell=False)
            else:
                subprocess.Popen([player, filepath])
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Launch Error', 'Failed to start external player:\n{}'.format(e))
    
    def load_element(self, element_id):
        """Load element data and prepare for playback."""
        element = self.db.get_element_by_id(element_id)
        if not element:
            self._shutdown_player(clear_element_state=True)
            return

        self.current_element = element
        self._shutdown_player()
        self._duration_known = False
        self.timeline_slider.setMaximum(0)

        # Update metadata display with the newly selected element
        self.update_metadata_display()
        
        # Get file path
        filepath = self.current_element.get('filepath_hard') or self.current_element.get('filepath_soft')
        
        # Check for image sequences (not supported by ffpyplayer MediaPlayer)
        if filepath and '%' in filepath:
            self.video_widget.clear_frame("Image sequences not supported")
            QtWidgets.QMessageBox.warning(
                self,
                "Format Not Supported",
                "Image sequences are not supported in the embedded video player.\n\n"
                "ffpyplayer can only play video files (mp4, mov, avi, mkv, etc.).\n\n"
                "File: {}".format(filepath)
            )
            return
        
        if not filepath:
            QtWidgets.QMessageBox.warning(
                self,
                "No File Path",
                "Element has no file path associated with it."
            )
            return
        
        if not os.path.exists(filepath):
            QtWidgets.QMessageBox.warning(
                self,
                "File Not Found",
                "Cannot load media: File does not exist\n\n{}".format(filepath)
            )
            return
        
        # Check if ffpyplayer is available
        if FFMediaPlayer is None:
            QtWidgets.QMessageBox.critical(
                self,
                "ffpyplayer Not Available",
                "The ffpyplayer library is required for video playback.\n\n"
                "Please install it with:\n"
                "pip install ffpyplayer"
            )
            return
        
        # Try to open the media file with ffpyplayer
        try:
            self.video_widget.clear_frame("Loading preview…")
            self.player_controller.open(filepath)
            self._set_controls_enabled(True)
            self._set_play_button_state(self.player_controller.is_playing())
            self.stop_btn.setEnabled(True)
            self.external_btn.setEnabled(True)
            self.video_widget.clear_frame("Ready to play")
            print("Media loaded with ffpyplayer: {}".format(filepath))
        except Exception as e:
            self._shutdown_player()
            QtWidgets.QMessageBox.critical(
                self,
                "Playback Error",
                "Failed to load media file:\n\n{}".format(str(e))
            )
            print("Failed to load media: {}".format(e))
    
    def on_frame_ready(self, data, width, height):
        """Handle frame ready signal from player controller."""
        try:
            self.video_widget.show_frame_rgb24(data, width, height)
        except Exception as e:
            print("Failed to show frame: {}".format(e))
    
    def on_playback_finished(self):
        """Handle playback finished signal."""
        print("Playback finished")
        self._set_play_button_state(False)
        self.timeline_slider.setValue(self.timeline_slider.maximum())
        self.current_time_label.setText(self.total_time_label.text())
    
    def play_with_ffplay(self, filepath):
        """Deprecated - no longer needed with ffpyplayer."""
        pass
    
    def update_metadata_display(self):
        """Update the metadata text display."""
        if not self.current_element:
            return
        
        metadata_lines = []
        metadata_lines.append("<b style='color: #16c6b0;'>Element Information</b>")
        metadata_lines.append("")
        metadata_lines.append("<b>Name:</b> {}".format(self.current_element.get('name', 'N/A')))
        metadata_lines.append("<b>Type:</b> {}".format(self.current_element.get('type', 'N/A')))
        metadata_lines.append("<b>Format:</b> {}".format(self.current_element.get('format', 'N/A')))
        
        # Frame range
        frame_range = self.current_element.get('frame_range', '')
        if frame_range:
            metadata_lines.append("<b>Frame Range:</b> {}".format(frame_range))
        
        # File size
        file_size = self.current_element.get('file_size', 0)
        if file_size:
            size_mb = file_size / (1024.0 * 1024.0)
            metadata_lines.append("<b>File Size:</b> {:.2f} MB".format(size_mb))
        
        # File path
        filepath = self.current_element.get('filepath_hard') or self.current_element.get('filepath_soft')
        if filepath:
            metadata_lines.append("<b>Path:</b> {}".format(filepath))
        
        # Tags
        tags = self.current_element.get('tags', '')
        if tags:
            metadata_lines.append("")
            metadata_lines.append("<b style='color: #ffd93d;'>Tags:</b>")
            tag_list = [t.strip() for t in tags.split(',') if t.strip()]
            for tag in tag_list:
                metadata_lines.append("  • {}".format(tag))
        
        # Comment
        comment = self.current_element.get('comment', '')
        if comment:
            metadata_lines.append("")
            metadata_lines.append("<b>Comment:</b>")
            metadata_lines.append(comment)
        
        # Deprecated status
        if self.current_element.get('is_deprecated'):
            metadata_lines.append("")
            metadata_lines.append("<span style='color: #ff5555;'><b>⚠ DEPRECATED</b></span>")
        
        self.metadata_text.setHtml("<br>".join(metadata_lines))
    
    def toggle_playback(self):
        """Toggle play/pause state."""
        if not self.player_controller.player:
            return

        if self.player_controller.is_playing():
            self.player_controller.pause()
            self._set_play_button_state(False)
        else:
            self.player_controller.play()
            self._set_play_button_state(True)
        self.stop_btn.setEnabled(True)
    
    def stop_playback(self):
        """Stop video playback and reset."""
        if not self.player_controller.player:
            return

        self.player_controller.pause()
        self.player_controller.seek(0.0, relative=False)
        self._set_play_button_state(False)
        self.timeline_slider.setValue(0)
        self.current_time_label.setText("00:00:00")
        duration = self.player_controller.get_duration()
        total_frames = int(duration * 24.0) if duration > 0 else "?"
        self.frame_label.setText("Frame: 0 / {}".format(total_frames))
        self.stop_btn.setEnabled(True)
    
    def on_state_changed(self, state):
        """Deprecated - not used with ffpyplayer."""
        pass
    
    def on_position_changed(self, position_seconds):
        """Handle playback position changes from player controller."""
        position_seconds = max(0.0, position_seconds)
        position_ms = int(position_seconds * 1000)

        if not self._duration_known and position_ms > self.timeline_slider.maximum():
            self.timeline_slider.setMaximum(position_ms)

        if not self.timeline_slider.isSliderDown():
            slider_max = self.timeline_slider.maximum()
            if slider_max > 0:
                self.timeline_slider.setValue(min(position_ms, slider_max))
            else:
                self.timeline_slider.setValue(position_ms)

        # Update time label
        self.current_time_label.setText(self.format_time(position_seconds))

        duration = self.player_controller.get_duration()
        if duration > 0:
            total_frames = int(duration * 24.0)  # Assume 24 fps
            current_frame = int(min(position_seconds, duration) * 24.0)
            self.frame_label.setText("Frame: {} / {}".format(current_frame, total_frames))
        else:
            current_frame = int(position_seconds * 24.0)
            self.frame_label.setText("Frame: {} / ?".format(current_frame))
    
    def on_duration_changed(self, duration_seconds):
        """Handle duration changes from player controller."""
        # Set timeline slider maximum (convert seconds to milliseconds)
        duration_seconds = max(0.0, duration_seconds)
        duration_ms = int(duration_seconds * 1000)
        self.timeline_slider.setMaximum(duration_ms)
        self._duration_known = duration_seconds > 0
        
        # Update total time label
        self.total_time_label.setText(self.format_time(duration_seconds))
        
        # Update frame counter
        total_frames = int(duration_seconds * 24.0) if duration_seconds > 0 else "?"
        self.frame_label.setText("Frame: 0 / {}".format(total_frames))
    
    def on_player_error(self):
        """Deprecated - not used with ffpyplayer."""
        pass
    
    def on_slider_pressed(self):
        """Handle slider press - pause during scrubbing."""
        if not self.player_controller.player:
            return

        self._resume_after_scrub = self.player_controller.is_playing()
        if self._resume_after_scrub:
            self.player_controller.pause()
    
    def on_slider_released(self):
        """Handle slider release - seek to position."""
        if not self.player_controller.player:
            return

        position_ms = self.timeline_slider.value()
        position_seconds = position_ms / 1000.0
        self.player_controller.seek(position_seconds, relative=False)

        if self._resume_after_scrub:
            self.player_controller.play()
        self._resume_after_scrub = False
    
    def on_timeline_scrub(self, position_ms):
        """Handle timeline scrubbing."""
        # Update time label while scrubbing
        seconds = position_ms / 1000.0
        self.current_time_label.setText(self.format_time(seconds))
    
    def step_frame(self, direction):
        """Step forward or backward by one frame."""
        if not self.player_controller.player:
            return

        current_pos = self.player_controller.get_position()
        frame_duration = 1.0 / 24.0  # ~0.0417 seconds for 24fps
        new_pos = current_pos + (direction * frame_duration)
        
        # Clamp to valid range
        duration = self.player_controller.get_duration()
        if duration > 0:
            new_pos = max(0.0, min(new_pos, duration))
        else:
            new_pos = max(0.0, new_pos)
        self.player_controller.seek(new_pos, relative=False)
    
    def format_time(self, seconds):
        """Format seconds as HH:MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return "{:02d}:{:02d}:{:02d}".format(hours, minutes, secs)
    
    def close_panel(self):
        """Close the preview panel."""
        self._shutdown_player(clear_element_state=True)
        self.closed.emit()
        self.hide()
    
    def clear(self):
        """Clear the panel and stop playback."""
        self._shutdown_player(clear_element_state=True)
        self.metadata_text.clear()
        self.video_widget.clear_frame("No preview available")
    
    def closeEvent(self, event):
        """Handle widget close event."""
        self._shutdown_player()
        super(VideoPlayerWidget, self).closeEvent(event)
