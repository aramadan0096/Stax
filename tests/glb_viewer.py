"""
converter_gui.py

Single-file PySide2 app that:
 - converts .obj/.fbx/.abc -> .glb
 - uses trimesh for OBJ (and FBX if trimesh can)
 - falls back to Blender (headless) for FBX and Alembic (.abc)
 - offers a pyrender-powered view button that keeps the Qt event loop responsive

Dependencies:
  pip install PySide2 trimesh pygltflib pyrender

Notes:
 - Blender must be installed & on PATH (command 'blender') for the Blender fallback to work.
 - .fpx is usually an image format (FlashPix) — not FBX. If you meant FBX, use .fbx.
"""

import sys
import os
import json
import subprocess
import shutil
import traceback
import time
from pathlib import Path

from PySide2 import QtWidgets, QtCore

try:
    import numpy as _np  # type: ignore
except Exception:
    _np = None  # type: ignore
else:
    if _np is not None and not hasattr(_np, "infty"):  # pragma: no cover - compatibility shim
        _np.infty = _np.inf  # type: ignore[attr-defined]

try:
    import trimesh  # type: ignore
except Exception as _trimesh_error:  # pragma: no cover - optional dependency guard
    trimesh = None  # type: ignore
    TRIMESH_IMPORT_ERROR = _trimesh_error
else:
    TRIMESH_IMPORT_ERROR = None

try:
    import pygltflib  # type: ignore
    from pygltflib import BufferFormat  # type: ignore
except Exception as _pygltflib_error:  # pragma: no cover - optional dependency guard
    pygltflib = None  # type: ignore
    BufferFormat = None  # type: ignore
    PYGLTFLIB_IMPORT_ERROR = _pygltflib_error
else:
    PYGLTFLIB_IMPORT_ERROR = None

try:
    import pyrender  # type: ignore  # noqa: F401
except Exception:
    pyrender = None

APP_TITLE = "3D → GLB Converter (PySide2 + trimesh/pyrender + pygltflib)"

BLENDER_ONLY_EXTS = set([".abc"])
MAX_BLENDER_TIMEOUT = 300  # seconds


# ---------- Utilities ----------

def find_blender_executable():
    """Return path to blender executable (or None)."""
    names = ["blender"]
    if sys.platform.startswith("win"):
        names = ["blender.exe", "blender"]
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def ensure_directory(path):
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.exists(directory):
        os.makedirs(directory)


def write_bytes(path_obj, data):
    ensure_directory(str(path_obj))
    with open(path_obj, "wb") as handle:
        handle.write(data)


# ---------- Conversion helpers ----------

def convert_obj_with_trimesh(in_path, out_path):
    """Use trimesh to export supported mesh formats to GLB."""
    if trimesh is None:
        return False, "trimesh library is not available: {0}".format(TRIMESH_IMPORT_ERROR)
    try:
        mesh_or_scene = trimesh.load(in_path, force="mesh")
        if isinstance(mesh_or_scene, trimesh.Trimesh):
            scene = trimesh.Scene(mesh_or_scene)
        else:
            scene = mesh_or_scene

        try:
            exported = scene.export(file_type="glb")
            if isinstance(exported, (bytes, bytearray)):
                write_bytes(Path(out_path), exported)
                return True, "Exported with trimesh.Scene.export"
        except Exception:
            pass

        try:
            from trimesh.exchange import gltf as trimesh_gltf  # type: ignore
        except Exception as exc:
            return False, "trimesh GLB exporter unavailable: {0}".format(exc)

        glb_bytes = trimesh_gltf.export_glb(scene)
        write_bytes(Path(out_path), glb_bytes)
        return True, "Exported with trimesh.exchange.gltf.export_glb"
    except Exception as exc:
        return False, "trimesh export failed: {0}\n{1}".format(exc, traceback.format_exc())


def convert_with_blender(in_path, out_path, blender_path=None):
    """Run Blender headless to import and export to GLB."""
    ext = Path(in_path).suffix.lower()
    blender_exec = blender_path or find_blender_executable()
    if not blender_exec:
        return False, "Blender not found on PATH; install Blender or add it to PATH."

    ensure_directory(out_path)

    in_literal = json.dumps(os.path.abspath(in_path))
    out_literal = json.dumps(os.path.abspath(out_path))

    if ext == ".fbx":
        import_cmd = "bpy.ops.import_scene.fbx(filepath={0})".format(in_literal)
    elif ext == ".abc":
        import_cmd = "bpy.ops.wm.alembic_import(filepath={0})".format(in_literal)
    elif ext == ".obj":
        import_cmd = "bpy.ops.import_scene.obj(filepath={0})".format(in_literal)
    else:
        import_cmd = "# unsupported extension for automatic import"

    export_cmd = "bpy.ops.export_scene.gltf(filepath={0}, export_format='GLB')".format(out_literal)

    python_expr = (
        "import bpy,sys,time;"
        "bpy.ops.wm.read_homefile(use_empty=True);"
        "{0};".format(import_cmd) +
        "time.sleep(0.1);"
        "{0};".format(export_cmd) +
        "print('EXPORT_DONE')"
    )

    cmd = [blender_exec, "-b", "--python-expr", python_expr]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=MAX_BLENDER_TIMEOUT,
        )
        stdout = proc.stdout
        stderr = proc.stderr
        if proc.returncode == 0:
            if "EXPORT_DONE" in stdout or os.path.exists(out_path):
                return True, "Converted with Blender ({0}).".format(blender_exec)
            return False, "Blender finished but export not detected. stdout:\n{0}\nstderr:\n{1}".format(stdout, stderr)
        return False, "Blender returned code {0}. stdout:\n{1}\nstderr:\n{2}".format(proc.returncode, stdout, stderr)
    except Exception as exc:
        return False, "Running Blender failed: {0}\n{1}".format(exc, traceback.format_exc())


def validate_glb_with_pygltflib(glb_path):
    """Validate produced GLB by loading and re-saving with pygltflib."""
    if pygltflib is None or BufferFormat is None:
        return False, "pygltflib not available: {0}".format(PYGLTFLIB_IMPORT_ERROR)
    try:
        gltf = pygltflib.GLTF2().load(glb_path)
        gltf.convert_buffers(BufferFormat.BINARYBLOB)
        gltf.save(glb_path)
        return True, "Validated with pygltflib.GLTF2().load/save cycle."
    except Exception as exc:
        return False, "pygltflib validation failed: {0}".format(exc)


def convert_to_glb(in_path, out_path, blender_path=None, reporter=None):
    """High-level conversion controller with status callbacks."""
    if reporter is None:
        reporter = lambda message: None  # noqa: E731

    if not os.path.isfile(in_path):
        return False, "Input file not found."

    reporter("Preparing conversion for {0}".format(in_path))

    ext = Path(in_path).suffix.lower()
    ensure_directory(out_path)

    success = False
    message = "Unsupported format"

    if ext == ".gltf":
        if pygltflib is None or BufferFormat is None:
            return False, "pygltflib is required to convert .gltf to .glb ({0}).".format(PYGLTFLIB_IMPORT_ERROR)
        try:
            reporter("Detected .gltf; repacking via pygltflib per project quickstart.")
            gltf = pygltflib.GLTF2().load(in_path)
            gltf.convert_buffers(BufferFormat.BINARYBLOB)
            gltf.save(out_path)
            success = True
            message = "Converted .gltf to .glb with pygltflib"
        except Exception as exc:
            return False, "pygltflib conversion failed: {0}".format(exc)

    elif ext == ".glb":
        shutil.copy2(in_path, out_path)
        reporter("Input already .glb; copied file before validation.")
        success = True
        message = "Copied .glb"

    elif ext in [".obj", ".ply", ".stl", ".dae"]:
        if trimesh is None:
            return False, "trimesh is required for {0} conversion ({1}).".format(ext, TRIMESH_IMPORT_ERROR)
        reporter("Attempting trimesh export for {0}.".format(ext))
        success, message = convert_obj_with_trimesh(in_path, out_path)
        reporter("trimesh: {0}".format(message))

    elif ext == ".fbx":
        if trimesh is not None:
            reporter("Trying trimesh fast-path for FBX before Blender fallback.")
            success, message = convert_obj_with_trimesh(in_path, out_path)
            reporter("trimesh: {0}".format(message))
        else:
            success = False
            message = "trimesh unavailable for FBX fast-path"

        if not success:
            reporter("Falling back to Blender import/export for FBX.")
            success, message = convert_with_blender(in_path, out_path, blender_path)
            reporter("blender: {0}".format(message))

    elif ext in BLENDER_ONLY_EXTS:
        reporter("Alembic detected; delegating to Blender headless pipeline.")
        success, message = convert_with_blender(in_path, out_path, blender_path)
        reporter("blender: {0}".format(message))

    else:
        reporter("Extension {0} not explicitly supported; attempting trimesh then Blender.".format(ext))
        if trimesh is not None:
            success, message = convert_obj_with_trimesh(in_path, out_path)
            reporter("trimesh: {0}".format(message))
        else:
            success = False
            message = "trimesh unavailable for format {0}".format(ext)

        if not success:
            reporter("Attempting Blender fallback.")
            success, message = convert_with_blender(in_path, out_path, blender_path)
            reporter("blender: {0}".format(message))

    if not success:
        return False, message

    if pygltflib is not None and BufferFormat is not None:
        ok, validation_message = validate_glb_with_pygltflib(out_path)
        reporter("pygltflib validation: {0}".format(validation_message))
        if not ok:
            return False, validation_message
    else:
        reporter("pygltflib not available; skipping validation step.")

    return True, message


# ---------- Viewer helpers ----------

def launch_viewer_thread(glb_path):
    """Launch pyrender.Viewer in a background thread using documented options."""
    if pyrender is None:
        return False, "pyrender is not installed; install it to enable viewing.", None
    if trimesh is None:
        return False, "trimesh is required to build pyrender scene: {0}".format(TRIMESH_IMPORT_ERROR), None

    try:
        mesh_or_scene = trimesh.load(glb_path, force="scene")
        if isinstance(mesh_or_scene, trimesh.Trimesh):
            mesh_or_scene = trimesh.Scene(mesh_or_scene)

        try:
            scene = pyrender.Scene.from_trimesh_scene(mesh_or_scene)
        except Exception:
            scene = pyrender.Scene()
            geometry_items = getattr(mesh_or_scene, "geometry", {})
            for geometry in geometry_items.values():
                mesh = pyrender.Mesh.from_trimesh(geometry, smooth=False)
                scene.add(mesh)

        viewer = pyrender.Viewer(
            scene,
            use_raymond_lighting=True,
            run_in_thread=True,
        )
        return True, "Viewer started with pyrender.Viewer(..., run_in_thread=True).", viewer
    except Exception as exc:
        return False, "Failed to launch pyrender viewer: {0}".format(exc), None


# ---------- Qt worker ----------

class ConversionWorker(QtCore.QObject):
    finished = QtCore.Signal(bool, str)
    progress = QtCore.Signal(str)

    def __init__(self, in_path, out_path, blender_path=None):
        super(ConversionWorker, self).__init__()
        self._in_path = in_path
        self._out_path = out_path
        self._blender_path = blender_path

    @QtCore.Slot()
    def run(self):
        def _report(message):
            self.progress.emit(message)

        try:
            success, message = convert_to_glb(
                self._in_path,
                self._out_path,
                blender_path=self._blender_path,
                reporter=_report,
            )
        except Exception as exc:  # pragma: no cover - defensive
            message = "Unexpected error: {0}\n{1}".format(exc, traceback.format_exc())
            success = False
            self.progress.emit(message)

        self.finished.emit(success, message)


# ---------- GUI ----------

class ConverterWindow(QtWidgets.QWidget):
    def __init__(self):
        super(ConverterWindow, self).__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(760, 380)

        self.input_path = QtWidgets.QLineEdit()
        self.input_btn = QtWidgets.QPushButton("Browse…")
        self.out_path = QtWidgets.QLineEdit()
        self.blender_path = QtWidgets.QLineEdit()
        self.blender_btn = QtWidgets.QPushButton("Locate Blender…")
        self.convert_btn = QtWidgets.QPushButton("Convert to .glb")
        self.view_btn = QtWidgets.QPushButton("View .glb")
        self.view_btn.setEnabled(False)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Conversion log output…")

        self._conversion_thread = None
        self._worker = None
        self._viewer = None
        self._pending_output = None
        self._last_export = None

        form = QtWidgets.QFormLayout()
        input_row = QtWidgets.QHBoxLayout()
        input_row.addWidget(self.input_path)
        input_row.addWidget(self.input_btn)
        form.addRow("Input", input_row)

        form.addRow("Output", self.out_path)

        blender_row = QtWidgets.QHBoxLayout()
        blender_row.addWidget(self.blender_path)
        blender_row.addWidget(self.blender_btn)
        form.addRow("Blender (optional)", blender_row)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addWidget(self.convert_btn)
        button_row.addWidget(self.view_btn)
        button_row.addStretch(1)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(button_row)
        layout.addWidget(self.log)

        self.input_btn.clicked.connect(self.browse_input)
        self.input_path.textChanged.connect(self.suggest_output)
        self.blender_btn.clicked.connect(self.browse_blender)
        self.convert_btn.clicked.connect(self.on_convert)
        self.view_btn.clicked.connect(self.on_view)

        self.update_view_button_state()

    def browse_input(self):
        filters = "3D files (*.obj *.fbx *.abc *.gltf *.glb);;All files (*.*)"
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Choose 3D file", "", filters)
        if path:
            self.input_path.setText(path)
            self.update_view_button_state()

    def browse_blender(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Locate blender executable", "", "Executable (*.exe);;All files (*.*)")
        if path:
            self.blender_path.setText(path)

    def suggest_output(self):
        in_path = self.input_path.text().strip()
        if in_path:
            base = Path(in_path).stem
            self.out_path.setText(str(Path(in_path).parent / (base + ".glb")))
        self.update_view_button_state()

    def update_view_button_state(self):
        glb_path = self._last_export or self.out_path.text().strip()
        can_view = bool(
            glb_path
            and glb_path.lower().endswith(".glb")
            and os.path.isfile(glb_path)
        )
        if self._conversion_thread is not None and self._conversion_thread.isRunning():
            can_view = False
        self.view_btn.setEnabled(can_view)

    def log_msg(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.log.appendPlainText("[{0}] {1}".format(timestamp, message))

    def on_convert(self):
        in_path = self.input_path.text().strip()
        out_path = self.out_path.text().strip()
        blender_override = self.blender_path.text().strip() or None

        if not in_path or not out_path:
            QtWidgets.QMessageBox.warning(self, "Missing", "Please choose input and output paths.")
            return

        self.convert_btn.setEnabled(False)
        self.convert_btn.setText("Converting…")
        self.view_btn.setEnabled(False)
        self.log.clear()
        self.log_msg("Starting conversion job…")

        self._pending_output = out_path

        self._conversion_thread = QtCore.QThread(self)
        self._worker = ConversionWorker(in_path, out_path, blender_override)
        self._worker.moveToThread(self._conversion_thread)

        self._conversion_thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.log_msg)
        self._worker.finished.connect(self.on_conversion_finished)
        self._worker.finished.connect(self._conversion_thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._conversion_thread.finished.connect(self._conversion_thread.deleteLater)

        self._conversion_thread.start()

    @QtCore.Slot(bool, str)
    def on_conversion_finished(self, success, message):
        self.convert_btn.setEnabled(True)
        self.convert_btn.setText("Convert to .glb")

        if success:
            self.log_msg("Conversion succeeded: {0}".format(message))
            self._last_export = self._pending_output
        else:
            self.log_msg("Conversion failed: {0}".format(message))
            QtWidgets.QMessageBox.critical(self, "Conversion failed", message)

        self._worker = None
        self._conversion_thread = None
        self.update_view_button_state()

    def on_view(self):
        glb_path = self._last_export or self.out_path.text().strip()
        if not glb_path or not os.path.isfile(glb_path):
            QtWidgets.QMessageBox.warning(self, "Missing", "Please convert the file first or select an existing .glb.")
            return

        ok, message, viewer = launch_viewer_thread(glb_path)
        self.log_msg(message)
        if ok and viewer is not None:
            self._install_viewer(viewer)

    def _install_viewer(self, viewer):
        if self._viewer is not None and getattr(self._viewer, "is_active", False):
            self._viewer.close_external()
            start = time.time()
            while self._viewer.is_active and time.time() - start < 3:
                QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)
                time.sleep(0.05)
        self._viewer = viewer

    def closeEvent(self, event):  # noqa: N802 - Qt signature
        if self._viewer is not None and getattr(self._viewer, "is_active", False):
            self._viewer.close_external()
            start = time.time()
            while self._viewer.is_active and time.time() - start < 3:
                QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)
                time.sleep(0.05)
        super(ConverterWindow, self).closeEvent(event)


def main():
    app = QtWidgets.QApplication.instance()  # type: ignore
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    window = ConverterWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
