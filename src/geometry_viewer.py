# -*- coding: utf-8 -*-
"""Shared HTTP server and PySide2 widget for geometry previews.

This refactors the previous pyrender-based preview to a WebGL pipeline that
reuses the bundled js-3d-model-viewer dependency. The HTTP server mirrors the
reference implementation from tests/glb_converter but is written to work with
Python 2.7, which StaX targets for Nuke compatibility.
"""

from __future__ import absolute_import

import os
import sys
import threading
import socket
import base64
import traceback

try:  # Python 3 names
    from http.server import SimpleHTTPRequestHandler, HTTPServer
    from socketserver import ThreadingMixIn
    from urllib.parse import urlparse, unquote, quote
except Exception:  # Python 2 fallback
    from SimpleHTTPServer import SimpleHTTPRequestHandler  # type: ignore
    from BaseHTTPServer import HTTPServer  # type: ignore
    from SocketServer import ThreadingMixIn  # type: ignore
    import urlparse  # type: ignore
    import urllib  # type: ignore

    def urlparse(url):  # type: ignore
        return urlparse.urlparse(url)

    def unquote(value):  # type: ignore
        return urllib.unquote(value)

    def quote(value):  # type: ignore
        return urllib.quote(value)

try:
    from PySide2 import QtWidgets, QtCore
    from PySide2.QtWebEngineWidgets import QWebEngineView  # type: ignore
except Exception:  # pragma: no cover - QtWebEngine is optional
    QtWidgets = None
    QtCore = None
    QWebEngineView = None


def _norm(path):
    return os.path.normpath(os.path.abspath(path))


def _find_free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def _make_handler(viewer_dir, dependencies_root, project_root):
    viewer_dir = _norm(viewer_dir)
    dependencies_root = _norm(dependencies_root)
    project_root = _norm(project_root)

    class GeometryRequestHandler(SimpleHTTPRequestHandler):
        server_version = "StaXGeometryHTTP/0.1"

        def log_message(self, fmt, *args):  # pylint: disable=arguments-differ
            sys.stdout.write("[GeometryHTTP] " + (fmt % args) + "\n")

        def translate_path(self, path):  # pylint: disable=arguments-differ
            parsed = urlparse(path)
            resource = parsed.path or '/'
            if resource in ('/', '/viewer'):
                resource = '/viewer/index.html'
            if resource.startswith('/viewer/'):
                rel = unquote(resource[len('/viewer/'):])
                target = os.path.join(viewer_dir, rel)
                return _norm(target)
            if resource.startswith('/dependencies/'):
                rel = unquote(resource[len('/dependencies/'):])
                target = os.path.join(dependencies_root, rel)
                return _norm(target)
            rel = unquote(resource.lstrip('/'))
            target = os.path.join(project_root, rel)
            return _norm(target)

        def do_GET(self):  # pylint: disable=invalid-name
            parsed = urlparse(self.path)
            resource = parsed.path or '/'

            if resource.startswith('/model/'):
                token = resource[len('/model/'):] or ''
                try:
                    padded = token.encode('utf-8')
                    # Pad base64 manually for Python 2 compatibility
                    missing = (-len(padded)) % 4
                    if missing:
                        padded += b'=' * missing
                    raw = base64.urlsafe_b64decode(padded)
                    model_path = raw.decode('utf-8')
                except Exception as exc:  # pylint: disable=broad-except
                    self.send_error(400, "Invalid model token: {0}".format(exc))
                    return

                model_path = _norm(model_path)
                if not os.path.exists(model_path) or not os.path.isfile(model_path):
                    self.send_error(404, "Model not found")
                    return

                ext = os.path.splitext(model_path)[1].lower()
                if ext == '.glb':
                    mime = 'model/gltf-binary'
                elif ext == '.gltf':
                    mime = 'model/gltf+json'
                else:
                    mime = 'application/octet-stream'

                try:
                    self.send_response(200)
                    self.send_header('Content-Type', mime)
                    self.send_header('Content-Length', str(os.path.getsize(model_path)))
                    self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                    self.end_headers()
                    chunk = 64 * 1024
                    handle = open(model_path, 'rb')
                    try:
                        while True:
                            data = handle.read(chunk)
                            if not data:
                                break
                            self.wfile.write(data)
                    finally:
                        handle.close()
                    return
                except Exception as exc:  # pylint: disable=broad-except
                    traceback.print_exc()
                    self.send_error(500, "Failed to stream model: {0}".format(exc))
                    return

            if resource in ('/', '/viewer'):
                self.path = '/viewer/index.html'

            return SimpleHTTPRequestHandler.do_GET(self)

    return GeometryRequestHandler


class GeometryViewerServer(object):
    """Singleton HTTP server that feeds the embedded geometry viewer."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self, project_root):  # pylint: disable=too-many-statements
        self._project_root = _norm(project_root)
        self._viewer_dir = os.path.join(self._project_root, 'resources', 'geometry_viewer')
        self._dependencies_root = os.path.join(self._project_root, 'dependencies')

        handler_cls = _make_handler(self._viewer_dir, self._dependencies_root, self._project_root)
        self._port = _find_free_port()
        self._httpd = _ThreadingHTTPServer(('127.0.0.1', self._port), handler_cls)

        self._thread = threading.Thread(target=self._httpd.serve_forever)
        self._thread.daemon = True
        self._thread.start()

    @classmethod
    def instance(cls, project_root):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(project_root)
            return cls._instance

    def viewer_base_url(self):
        return 'http://127.0.0.1:{0}/viewer/index.html'.format(self._port)

    def model_endpoint(self, model_path):
        if not model_path:
            return None
        try:
            token = base64.urlsafe_b64encode(model_path.encode('utf-8')).rstrip(b'=')
            quoted = quote(token.decode('ascii'))
            return 'http://127.0.0.1:{0}/model/{1}'.format(self._port, quoted)
        except Exception:
            return None

    def viewer_url_for_model(self, model_path):
        if not model_path:
            return self.viewer_base_url()
        endpoint = self.model_endpoint(model_path)
        if not endpoint:
            return self.viewer_base_url()
        return '{0}?model={1}'.format(self.viewer_base_url(), quote(endpoint, safe=':/?=&'))


class GeometryViewerWidget(QtWidgets.QWidget):
    """Widget that hosts the WebGL-based viewer or a fallback message."""

    def __init__(self, project_root, parent=None):
        super(GeometryViewerWidget, self).__init__(parent)
        self._project_root = _norm(project_root)
        self._server = None
        self._current_model = None
        self._web_available = QWebEngineView is not None and QtWidgets is not None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._stack = QtWidgets.QStackedWidget()
        self._stack.setContentsMargins(0, 0, 0, 0)

        self._placeholder = QtWidgets.QLabel()
        self._placeholder.setAlignment(QtCore.Qt.AlignCenter)
        self._placeholder.setMinimumHeight(240)
        self._placeholder.setStyleSheet(
            "background-color: #111; border: 2px solid #16c6b0; border-radius: 6px; color: #888;"
        )
        self._placeholder.setText("3D preview unavailable")
        self._stack.addWidget(self._placeholder)

        if self._web_available:
            self._webview = QWebEngineView()
            self._webview.setMinimumHeight(240)
            self._stack.addWidget(self._webview)
        else:
            self._webview = None

        layout.addWidget(self._stack, 1)

        self._status = QtWidgets.QLabel()
        self._status.setAlignment(QtCore.Qt.AlignCenter)
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._status)

        self._set_placeholder()

    def _ensure_server(self):
        if not self._web_available:
            return None
        if self._server is None:
            self._server = GeometryViewerServer.instance(self._project_root)
        return self._server

    def _set_placeholder(self):
        self._stack.setCurrentIndex(0)
        self._status.setText("Drop or ingest geometry to generate a WebGL preview.")

    def show_placeholder(self):
        self._set_placeholder()

    def set_placeholder_pixmap(self, pixmap):
        if pixmap is not None and not pixmap.isNull():
            scaled = pixmap.scaled(180, 180, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            self._placeholder.setPixmap(scaled)
        else:
            self._placeholder.clear()

    def show_message(self, text):
        self._status.setText(text or "")

    def clear_geometry(self):
        self._current_model = None
        if self._web_available and self._webview is not None:
            self._webview.setHtml("<html><body style='background:#111;'></body></html>")
        self._set_placeholder()

    def load_geometry(self, glb_path):
        if not glb_path or not os.path.exists(glb_path):
            self.show_message("GLB preview not found on disk.")
            self._set_placeholder()
            return False, "GLB preview missing"

        if not self._web_available or self._webview is None:
            self.show_message("QtWebEngine is not available; install PySide2 with QtWebEngine.")
            self._set_placeholder()
            return False, "QtWebEngine missing"

        server = self._ensure_server()
        if server is None:
            self.show_message("Failed to start geometry viewer server.")
            self._set_placeholder()
            return False, "Server unavailable"

        url = server.viewer_url_for_model(glb_path)
        if not url:
            self.show_message("Could not generate viewer URL.")
            self._set_placeholder()
            return False, "Invalid URL"

        try:
            self._webview.load(QtCore.QUrl(url))
            self._stack.setCurrentWidget(self._webview)
            self._status.setText("Loading WebGL preview...")
            self._current_model = glb_path
            return True, "GLB preview loading"
        except Exception as exc:  # pylint: disable=broad-except
            traceback.print_exc()
            self.show_message("Failed to load WebGL preview: {0}".format(exc))
            self._set_placeholder()
            return False, str(exc)
