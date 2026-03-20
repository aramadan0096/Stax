# -*- coding: utf-8 -*-
"""
StaX — Local REST API Server  (Feature 4)
==========================================
Exposes a lightweight HTTP/JSON API so external pipeline tools (Deadline
callbacks, project management scripts, CI triggers) can interact with the
StaX library without going through the GUI.

Architecture
------------
  APIServer       – QThread that runs a WSGI server (Flask if available,
                    falling back to the stdlib http.server).
  get_api_server()– Singleton factory.

Endpoints
---------
  GET  /api/v1/health
  GET  /api/v1/stacks                  list all stacks
  GET  /api/v1/stacks/{id}/lists       lists in a stack
  GET  /api/v1/lists/{id}/elements     elements in a list (supports ?page=&per_page=)
  GET  /api/v1/elements/{id}           single element
  POST /api/v1/elements/ingest         queue a file for ingestion
  PATCH /api/v1/elements/{id}          update tags/comment/name
  GET  /api/v1/analytics/top           top N most-inserted elements
  GET  /api/v1/search?q=&property=&match=  search elements

Authentication
--------------
All requests must include the header:

    X-StaX-Token: <token>

The token is stored as plaintext in the StaX config under key 'api_token'.
If not set, the API generates and saves one on first start.

Enable in Settings → API → "Enable local REST API".
Config keys: api_enabled (bool), api_port (int, default 17171),
             api_token (str).

Integration
-----------
In MainWindow.__init__ (after self.config is ready):

    from src.api_server import get_api_server
    if self.config.get('api_enabled', False):
        srv = get_api_server()
        srv.configure(self.db, self.config)
        srv.start()

In MainWindow.closeEvent():

    from src.api_server import shutdown_api_server
    shutdown_api_server()
"""

from __future__ import absolute_import, unicode_literals, print_function

import os
import json
import logging
import threading
import secrets
import socket

from PySide2 import QtCore

log = logging.getLogger(__name__)

_GLOBAL_SERVER = None   # type: APIServer | None


# ---------------------------------------------------------------------------
# Flask app factory (used when Flask is available)
# ---------------------------------------------------------------------------

def _build_flask_app(db, config):
    """Build and return a configured Flask application."""
    from flask import Flask, request, jsonify, abort

    app = Flask("stax_api")
    app.config["JSON_SORT_KEYS"] = False

    token = config.get("api_token", "")

    # ---- Auth decorator ---------------------------------------------------
    def require_auth(f):
        from functools import wraps
        @wraps(f)
        def wrapper(*args, **kwargs):
            provided = request.headers.get("X-StaX-Token", "")
            if not provided or provided != token:
                abort(401)
            return f(*args, **kwargs)
        return wrapper

    # ---- /health ----------------------------------------------------------
    @app.route("/api/v1/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "version": "1.0"})

    # ---- Stacks -----------------------------------------------------------
    @app.route("/api/v1/stacks", methods=["GET"])
    @require_auth
    def list_stacks():
        stacks = db.get_all_stacks()
        return jsonify([dict(s) for s in stacks])

    @app.route("/api/v1/stacks/<int:stack_id>/lists", methods=["GET"])
    @require_auth
    def list_lists(stack_id):
        lists = db.get_lists_by_stack(stack_id)
        return jsonify([dict(l) for l in lists])

    # ---- Lists / Elements -------------------------------------------------
    @app.route("/api/v1/lists/<int:list_id>/elements", methods=["GET"])
    @require_auth
    def list_elements(list_id):
        page     = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 100))
        offset   = (page - 1) * per_page
        elements = db.get_elements_by_list(
            list_id, limit=per_page, offset=offset
        )
        total = db.count_elements_by_list(list_id)
        return jsonify({
            "total": total,
            "page": page,
            "per_page": per_page,
            "elements": [dict(e) for e in elements],
        })

    @app.route("/api/v1/elements/<int:element_id>", methods=["GET"])
    @require_auth
    def get_element(element_id):
        elem = db.get_element_by_id(element_id)
        if elem is None:
            abort(404)
        return jsonify(dict(elem))

    @app.route("/api/v1/elements/<int:element_id>", methods=["PATCH"])
    @require_auth
    def patch_element(element_id):
        data = request.get_json(silent=True) or {}
        allowed = {"name", "tags", "comment", "is_deprecated"}
        updates = {k: v for k, v in data.items() if k in allowed}
        if not updates:
            abort(400)
        db.update_element_metadata(element_id, **updates)
        return jsonify({"updated": element_id})

    # ---- Ingest -----------------------------------------------------------
    @app.route("/api/v1/elements/ingest", methods=["POST"])
    @require_auth
    def ingest():
        data = request.get_json(silent=True) or {}
        filepath = data.get("filepath")
        list_id  = data.get("list_id")
        if not filepath or not list_id:
            abort(400)
        if not os.path.isfile(filepath):
            return jsonify({"error": "file not found"}), 404

        try:
            from src.ingestion_core import IngestionCore
            core   = IngestionCore(db, config.get_all())
            result = core.ingest_file(
                filepath,
                list_id,
                copy_policy=data.get("copy_policy",
                                     config.get("default_copy_policy")),
            )
            return jsonify(result), (200 if result.get("success") else 422)
        except Exception as exc:
            log.error("API ingest failed: %s", exc)
            return jsonify({"error": str(exc)}), 500

    # ---- Search -----------------------------------------------------------
    @app.route("/api/v1/search", methods=["GET"])
    @require_auth
    def search():
        q        = request.args.get("q", "")
        prop     = request.args.get("property", "name")
        match    = request.args.get("match", "loose")
        results  = db.search_elements(q, prop, match)
        return jsonify([dict(e) for e in results])

    # ---- Analytics --------------------------------------------------------
    @app.route("/api/v1/analytics/top", methods=["GET"])
    @require_auth
    def analytics_top():
        n       = int(request.args.get("n", 20))
        results = db.get_top_inserted_elements(n)
        return jsonify(results)

    return app


# ---------------------------------------------------------------------------
# Stdlib fallback WSGI handler (when Flask is not installed)
# ---------------------------------------------------------------------------

class _SimpleHandler(object):
    """
    Minimal JSON router for when Flask is unavailable.
    Only implements /api/v1/health and a helpful "install Flask" message
    for all other routes.
    """

    def __init__(self, db, config):
        self.db     = db
        self.config = config

    def __call__(self, environ, start_response):
        path   = environ.get("PATH_INFO", "")
        token  = environ.get("HTTP_X_STAX_TOKEN", "")
        method = environ.get("REQUEST_METHOD", "GET")

        def respond(status, body):
            data = json.dumps(body).encode("utf-8")
            start_response(status, [
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(data))),
            ])
            return [data]

        if path == "/api/v1/health":
            return respond("200 OK", {"status": "ok"})

        if token != self.config.get("api_token", ""):
            return respond("401 Unauthorized", {"error": "invalid token"})

        return respond(
            "501 Not Implemented",
            {
                "error": (
                    "Full API requires Flask. "
                    "Install with: pip install flask"
                )
            },
        )


# ---------------------------------------------------------------------------
# APIServer QThread
# ---------------------------------------------------------------------------

class APIServer(QtCore.QThread):
    """
    Background QThread hosting the HTTP server.

    Signals
    -------
    server_started(int port)
    server_stopped()
    server_error(str message)
    """

    server_started = QtCore.Signal(int)
    server_stopped = QtCore.Signal()
    server_error   = QtCore.Signal(str)

    def __init__(self, parent=None):
        super(APIServer, self).__init__(parent)
        self._db       = None
        self._config   = None
        self._server   = None
        self._stop_evt = threading.Event()
        self.setObjectName("StaX-APIServer")
        self.daemon = True

    def configure(self, db, config):
        self._db     = db
        self._config = config
        # Generate a token if none exists
        if not config.get("api_token"):
            config.set("api_token", secrets.token_hex(24))
            config.save()

    def get_token(self):
        return self._config.get("api_token", "") if self._config else ""

    def get_port(self):
        return int(self._config.get("api_port", 17171)) if self._config else 17171

    def stop(self):
        self._stop_evt.set()
        if self._server:
            try:
                self._server.shutdown()
            except Exception:
                pass

    def run(self):
        if self._db is None or self._config is None:
            self.server_error.emit("APIServer not configured.")
            return

        port = self.get_port()

        try:
            flask_available = False
            try:
                import flask as _f
                flask_available = True
            except ImportError:
                pass

            if flask_available:
                from flask import Flask
                import werkzeug.serving
                app = _build_flask_app(self._db, self._config)
                self._server = werkzeug.serving.make_server(
                    "127.0.0.1", port, app
                )
            else:
                from wsgiref.simple_server import make_server
                app = _SimpleHandler(self._db, self._config)
                self._server = make_server("127.0.0.1", port, app)

            self._server.socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_REUSEADDR, 1
            )
            log.info("StaX API server listening on http://127.0.0.1:%d", port)
            self.server_started.emit(port)
            self._server.serve_forever()

        except OSError as exc:
            msg = "API server could not start on port {}: {}".format(port, exc)
            log.error(msg)
            self.server_error.emit(msg)
        except Exception as exc:
            log.error("API server crashed: %s", exc)
            self.server_error.emit(str(exc))
        finally:
            self.server_stopped.emit()
            log.debug("APIServer thread exited.")


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------

def get_api_server():
    """Return (and create if needed) the global APIServer instance."""
    global _GLOBAL_SERVER
    if _GLOBAL_SERVER is None:
        _GLOBAL_SERVER = APIServer()
    return _GLOBAL_SERVER


def shutdown_api_server():
    global _GLOBAL_SERVER
    if _GLOBAL_SERVER is not None and _GLOBAL_SERVER.isRunning():
        _GLOBAL_SERVER.stop()
        _GLOBAL_SERVER.wait(3000)
    _GLOBAL_SERVER = None
