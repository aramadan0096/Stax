#!/usr/bin/env python3
"""
PySide2 video player using ffpyplayer (recommended over embedding ffplay).

Features:
- Uses ffpyplayer.MediaPlayer to decode video frames (no external ffplay binary needed).
- Displays decoded frames inside a PySide2 widget.
- Basic play/pause/stop/open controls.

Requirements:
    pip install PySide2 ffpyplayer

Notes:
- ffpyplayer includes FFmpeg binaries in many wheels; on some platforms licensing/packaging may apply.
- This implementation requests rgb24 output from ffpyplayer for simple QImage creation.

"""

import sys
import os
import time
from PySide2 import QtWidgets, QtCore, QtGui

try:
    from ffpyplayer.player import MediaPlayer
except Exception as e:
    MediaPlayer = None
    _IMPORT_ERROR = e


class FFpyVideoWidget(QtWidgets.QLabel):
    """Simple QLabel-based widget that shows QPixmap frames from raw RGB byte data."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setMinimumSize(320, 240)
        self._pix = None

    def show_frame_rgb24(self, data, width, height):
        # data: bytes or bytearray in RGB24 (R,G,B per pixel)
        # create QImage from buffer (no copy if possible)
        bytes_per_line = width * 3
        image = QtGui.QImage(data, width, height, bytes_per_line, QtGui.QImage.Format_RGB888)
        pix = QtGui.QPixmap.fromImage(image)
        self.setPixmap(pix.scaled(self.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # if we already have a pixmap, rescale it to fit
        if self.pixmap():
            self.setPixmap(self.pixmap().scaled(self.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))


class PlayerController(QtCore.QObject):
    """Controller that wraps ffpyplayer.MediaPlayer and emits frames as Qt signals."""

    frame_ready = QtCore.Signal(bytes, int, int)  # data, width, height
    finished = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = None
        self._timer = QtCore.QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timer)
        self._playing = False

    def open(self, filename):
        if MediaPlayer is None:
            raise RuntimeError(f"ffpyplayer not available: {_IMPORT_ERROR}")
        self.close()
        # Request rgb24 output to simplify conversion to QImage
        self.player = MediaPlayer(filename, ff_opts={'out_fmt': 'rgb24'})
        self._playing = True
        # start polling loop
        QtCore.QTimer.singleShot(0, self._on_timer)

    def play(self):
        if not self.player:
            return
        # unpause
        try:
            self.player.set_pause(False)
        except Exception:
            pass
        self._playing = True
        QtCore.QTimer.singleShot(0, self._on_timer)

    def pause(self):
        if not self.player:
            return
        try:
            self.player.set_pause(True)
        except Exception:
            pass
        self._playing = False

    def stop(self):
        self.close()

    def close(self):
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

    def _on_timer(self):
        if not self.player or not self._playing:
            return
        # get_frame returns (frame, val) where frame is (img, pts) or None
        try:
            frame, val = self.player.get_frame()
        except Exception as e:
            print("Error reading frame:", e)
            return

        if val == 'eof':
            self.finished.emit()
            self._playing = False
            return

        if frame is None:
            # not ready yet — poll soon
            self._timer.start(10)
            return

        # frame is a tuple (ffpyplayer.pic.Image, pts)
        img, pts = frame
        # Expected output pix_fmt is rgb24; extract byte data
        try:
            # img.to_bytearray() returns a list of planes; for rgb24 expect a single plane
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
            # emit frame for Qt UI
            self.frame_ready.emit(data, width, height)
            # schedule next frame according to val (val is seconds to wait)
            ms = max(1, int(val * 1000)) if isinstance(val, (float, int)) and val > 0 else 10
            self._timer.start(ms)
        except Exception as e:
            print("Failed to convert ffpyplayer image:", e)
            # fallback small delay
            self._timer.start(10)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ffpyplayer + PySide2 Player")
        self.resize(900, 600)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        # video widget
        self.video = FFpyVideoWidget(self)
        layout.addWidget(self.video, 1)

        # controls
        h = QtWidgets.QHBoxLayout()
        self.open_btn = QtWidgets.QPushButton("Open")
        self.play_btn = QtWidgets.QPushButton("Play")
        self.pause_btn = QtWidgets.QPushButton("Pause")
        self.stop_btn = QtWidgets.QPushButton("Stop")
        h.addWidget(self.open_btn)
        h.addWidget(self.play_btn)
        h.addWidget(self.pause_btn)
        h.addWidget(self.stop_btn)
        layout.addLayout(h)

        # controller
        self.controller = PlayerController(self)
        self.controller.frame_ready.connect(self.on_frame_ready)
        self.controller.finished.connect(self.on_finished)

        # connections
        self.open_btn.clicked.connect(self.open_file)
        self.play_btn.clicked.connect(self.controller.play)
        self.pause_btn.clicked.connect(self.controller.pause)
        self.stop_btn.clicked.connect(self.controller.stop)

    def open_file(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open video", os.path.expanduser("~"))
        if not fn:
            return
        try:
            self.controller.open(fn)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to open file: {e}")

    @QtCore.Slot(bytes, int, int)
    def on_frame_ready(self, data, w, h):
        try:
            self.video.show_frame_rgb24(data, w, h)
        except Exception as e:
            print("Failed to show frame:", e)

    def on_finished(self):
        print("Playback finished")

    def closeEvent(self, event):
        self.controller.close()
        super().closeEvent(event)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    if MediaPlayer is None:
        QtWidgets.QMessageBox.critical(None, "Missing dependency",
                                       f"""ffpyplayer import failed: {_IMPORT_ERROR}

Install with:
    pip install ffpyplayer""")
        sys.exit(1)
    sys.exit(app.exec_())
