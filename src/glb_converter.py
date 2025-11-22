# -*- coding: utf-8 -*-
"""Utility helpers for converting geometry assets to GLB and previewing them."""

import os
import sys
import shutil
import subprocess
import traceback
import time

MAX_BLENDER_TIMEOUT = 300
BLENDER_ONLY_EXTS = set(['.abc'])
SUPPORTED_GEOMETRY_EXTS = set(['.obj', '.fbx', '.abc', '.gltf', '.glb', '.ply', '.stl', '.dae'])

BLENDER_SCRIPT_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src', 'convert_to_glb.py')
)

try:
    import numpy as _np  # pylint: disable=import-error
except Exception:  # pragma: no cover
    _np = None  # type: ignore
else:
    if _np is not None and not hasattr(_np, 'infty'):
        try:
            _np.infty = _np.inf  # type: ignore[attr-defined]
        except Exception:
            pass

try:
    import trimesh  # type: ignore
except Exception as _trimesh_error:  # pragma: no cover
    trimesh = None  # type: ignore
    TRIMESH_IMPORT_ERROR = _trimesh_error
else:
    TRIMESH_IMPORT_ERROR = None

try:
    import pygltflib  # type: ignore
    from pygltflib import BufferFormat  # type: ignore
except Exception as _pygltflib_error:  # pragma: no cover
    pygltflib = None  # type: ignore
    BufferFormat = None  # type: ignore
    PYGLTFLIB_IMPORT_ERROR = _pygltflib_error
else:
    PYGLTFLIB_IMPORT_ERROR = None

try:
    import pyrender  # type: ignore
except Exception:  # pragma: no cover
    pyrender = None  # type: ignore

try:
    from distutils.spawn import find_executable  # pylint: disable=import-error,no-name-in-module
except Exception:  # pragma: no cover
    find_executable = None  # type: ignore


def _which(executable):
    """Portable find executable for Python 2.7."""
    if hasattr(shutil, 'which'):
        path = shutil.which(executable)  # type: ignore[attr-defined]
        if path:
            return path
    if find_executable:
        path = find_executable(executable)
        if path:
            return path
    paths = os.environ.get('PATH', '').split(os.pathsep)
    for directory in paths:
        candidate = os.path.join(directory.strip('"'), executable)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def find_blender_executable(blender_override=None):
    """Return path to blender executable (or None)."""
    if blender_override:
        candidate = os.path.abspath(blender_override)
        if os.path.isfile(candidate):
            return candidate
    names = ['blender']
    if sys.platform.startswith('win'):
        names = ['blender.exe', 'blender']
    for name in names:
        path = _which(name)
        if path:
            return path
    return None


def ensure_directory(path):
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.exists(directory):
        os.makedirs(directory)


def write_bytes(path_obj, data):
    ensure_directory(path_obj)
    handle = open(path_obj, 'wb')
    try:
        handle.write(data)
    finally:
        handle.close()


def convert_obj_with_trimesh(in_path, out_path):
    """Use trimesh to export supported mesh formats to GLB."""
    if trimesh is None:
        return False, "trimesh library is not available: {0}".format(TRIMESH_IMPORT_ERROR)
    try:
        mesh_or_scene = trimesh.load(in_path, force='mesh')  # type: ignore[attr-defined]
        if isinstance(mesh_or_scene, getattr(trimesh, 'Trimesh', object)):
            scene = trimesh.Scene(mesh_or_scene)
        else:
            scene = mesh_or_scene
        try:
            exported = scene.export(file_type='glb')
            if isinstance(exported, (bytes, bytearray)):
                write_bytes(out_path, exported)
                return True, 'Exported with trimesh.Scene.export'
        except Exception:
            pass
        try:
            from trimesh.exchange import gltf as trimesh_gltf  # type: ignore
        except Exception as exc:
            return False, 'trimesh GLB exporter unavailable: {0}'.format(exc)
        glb_bytes = trimesh_gltf.export_glb(scene)  # type: ignore[attr-defined]
        write_bytes(out_path, glb_bytes)
        return True, 'Exported with trimesh.exchange.gltf.export_glb'
    except Exception as exc:
        return False, 'trimesh export failed: {0}\n{1}'.format(exc, traceback.format_exc())


def _communicate_with_timeout(proc, timeout):
    """Communicate with timeout support for Python 2.7."""
    start_time = time.time()
    stdout = ''
    stderr = ''
    while True:
        retcode = proc.poll()
        if retcode is not None:
            stdout, stderr = proc.communicate()
            return retcode, stdout, stderr
        if timeout and (time.time() - start_time) > timeout:
            try:
                proc.terminate()
            except Exception:
                pass
            stdout, stderr = proc.communicate()
            return None, stdout, stderr
        time.sleep(1)


def convert_with_blender(in_path, out_path, blender_path=None):
    """Run Blender headless using the bundled conversion script."""
    blender_exec = blender_path or find_blender_executable()
    if not blender_exec:
        return False, 'Blender not found on PATH; install Blender or set Blender Path in settings.'

    if not BLENDER_SCRIPT_PATH or not os.path.exists(BLENDER_SCRIPT_PATH):
        return False, 'Blender conversion script missing: {0}'.format(BLENDER_SCRIPT_PATH)

    ensure_directory(out_path)

    cmd = [
        blender_exec,
        '--background',
        '--python', BLENDER_SCRIPT_PATH,
        '--',
        os.path.abspath(in_path),
        os.path.abspath(out_path)
    ]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    except Exception as exc:
        return False, 'Failed to launch Blender: {0}'.format(exc)

    retcode, stdout, stderr = _communicate_with_timeout(proc, MAX_BLENDER_TIMEOUT)
    stdout = stdout or ''
    stderr = stderr or ''

    if retcode is None:
        return False, 'Blender timed out after {0} seconds.'.format(MAX_BLENDER_TIMEOUT)
    if retcode == 0 and os.path.exists(out_path):
        return True, 'Converted with Blender script ({0}).'.format(blender_exec)
    return False, 'Blender returned code {0}. stdout:\n{1}\nstderr:\n{2}'.format(retcode, stdout, stderr)


def validate_glb_with_pygltflib(glb_path):
    """Validate produced GLB by loading and re-saving with pygltflib."""
    if pygltflib is None or BufferFormat is None:
        return False, 'pygltflib not available: {0}'.format(PYGLTFLIB_IMPORT_ERROR)
    try:
        gltf = pygltflib.GLTF2().load(glb_path)  # type: ignore[attr-defined]
        gltf.convert_buffers(BufferFormat.BINARYBLOB)  # type: ignore[attr-defined]
        gltf.save(glb_path)
        return True, 'Validated with pygltflib.GLTF2().load/save cycle.'
    except Exception as exc:
        return False, 'pygltflib validation failed: {0}'.format(exc)


def convert_to_glb(in_path, out_path, blender_path=None, reporter=None):
    """High-level conversion controller with status callbacks."""
    if reporter is None:
        reporter = lambda message: None  # noqa: E731

    if not os.path.isfile(in_path):
        return False, 'Input file not found.'

    reporter('Preparing conversion for {0}'.format(in_path))

    ext = os.path.splitext(in_path)[1].lower()
    ensure_directory(out_path)

    success = False
    message = 'Unsupported format'

    if ext == '.gltf':
        if pygltflib is None or BufferFormat is None:
            return False, 'pygltflib is required to convert .gltf to .glb ({0}).'.format(PYGLTFLIB_IMPORT_ERROR)
        try:
            reporter('Detected .gltf; repacking via pygltflib per project quickstart.')
            gltf = pygltflib.GLTF2().load(in_path)  # type: ignore[attr-defined]
            gltf.convert_buffers(BufferFormat.BINARYBLOB)  # type: ignore[attr-defined]
            gltf.save(out_path)
            success = True
            message = 'Converted .gltf to .glb with pygltflib'
        except Exception as exc:
            return False, 'pygltflib conversion failed: {0}'.format(exc)

    elif ext == '.glb':
        shutil.copy2(in_path, out_path)
        reporter('Input already .glb; copied file before validation.')
        success = True
        message = 'Copied .glb'

    elif ext in ['.obj', '.ply', '.stl', '.dae', '.fbx']:
        reporter('Delegating geometry conversion to Blender script for {0}.'.format(ext))
        success, message = convert_with_blender(in_path, out_path, blender_path)
        reporter('blender: {0}'.format(message))

        if not success and trimesh is not None and ext in ['.obj', '.ply', '.stl', '.dae']:
            reporter('Blender conversion failed; attempting trimesh fallback.')
            success, message = convert_obj_with_trimesh(in_path, out_path)
            reporter('trimesh: {0}'.format(message))

    elif ext in BLENDER_ONLY_EXTS:
        reporter('Alembic detected; using Blender conversion script.')
        success, message = convert_with_blender(in_path, out_path, blender_path)
        reporter('blender: {0}'.format(message))

    else:
        reporter('Extension {0} not explicitly supported; attempting Blender first.'.format(ext))
        success, message = convert_with_blender(in_path, out_path, blender_path)
        reporter('blender: {0}'.format(message))

        if not success and trimesh is not None:
            reporter('Blender conversion failed; attempting trimesh fallback.')
            success, message = convert_obj_with_trimesh(in_path, out_path)
            reporter('trimesh: {0}'.format(message))

    if not success:
        return False, message

    if pygltflib is not None and BufferFormat is not None:
        ok, validation_message = validate_glb_with_pygltflib(out_path)
        reporter('pygltflib validation: {0}'.format(validation_message))
        if not ok:
            return False, validation_message
    else:
        reporter('pygltflib not available; skipping validation step.')

    return True, message


def launch_viewer_thread(glb_path):
    """Launch pyrender.Viewer in a background thread using documented options."""
    if pyrender is None:
        return False, 'pyrender is not installed; install it to enable viewing.', None
    if trimesh is None:
        return False, 'trimesh is required to build pyrender scene: {0}'.format(TRIMESH_IMPORT_ERROR), None

    try:
        mesh_or_scene = trimesh.load(glb_path, force='scene')  # type: ignore[attr-defined]
        if isinstance(mesh_or_scene, getattr(trimesh, 'Trimesh', object)):
            mesh_or_scene = trimesh.Scene(mesh_or_scene)

        try:
            scene = pyrender.Scene.from_trimesh_scene(mesh_or_scene)  # type: ignore[attr-defined]
        except Exception:
            scene = pyrender.Scene()
            geometry_items = getattr(mesh_or_scene, 'geometry', {})
            if hasattr(geometry_items, 'values'):
                geometry_iterable = geometry_items.values()
            else:
                geometry_iterable = geometry_items
            for geometry in geometry_iterable:
                mesh = pyrender.Mesh.from_trimesh(geometry, smooth=False)  # type: ignore[attr-defined]
                scene.add(mesh)

        viewer = pyrender.Viewer(
            scene,
            use_raymond_lighting=True,
            run_in_thread=True,
        )
        return True, 'Viewer started with pyrender.Viewer(..., run_in_thread=True).', viewer
    except Exception as exc:
        return False, 'Failed to launch pyrender viewer: {0}'.format(exc), None


def has_geometry_support():
    """Return True if at least one conversion path is available."""
    return bool(trimesh or find_blender_executable())
