# -*- coding: utf-8 -*-
"""
setup_freeze.py  —  cx_Freeze build configuration for StaX
===========================================================
Usage (from repo root, inside the uv venv):

    python setup_freeze.py build_exe

Or via build.ps1 (recommended):

    .\\tools\\build.ps1

Environment variables
---------------------
STAX_BUILD_OUT   Absolute path for the output directory.
                 Defaults to  .\\build\\StaX-<version>
                 Set by build.ps1 automatically.
"""

import os
import re
import sys
import shutil

# ---------------------------------------------------------------------------
# cx_Freeze must be imported BEFORE anything from setuptools so that
# cx_Freeze's setup() takes precedence over the one in setuptools.
# The _MissingDynamic warning was caused by passing `author=` to setup()
# while setuptools was also reading pyproject.toml — those fields are now
# removed from the setup() call entirely.
# ---------------------------------------------------------------------------
from cx_Freeze import setup, Executable

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.abspath(__file__))


def _read_version():
    """Read __version__ from main.py, src/version.py, or pyproject.toml."""
    for candidate in ("main.py", os.path.join("src", "version.py")):
        p = os.path.join(ROOT, candidate)
        if os.path.isfile(p):
            with open(p, encoding="utf-8", errors="replace") as fh:
                m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', fh.read())
                if m:
                    return m.group(1)
    pyproject = os.path.join(ROOT, "pyproject.toml")
    if os.path.isfile(pyproject):
        with open(pyproject, encoding="utf-8") as fh:
            m = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', fh.read(), re.MULTILINE)
            if m:
                return m.group(1)
    return "0.0.0"


STAX_VERSION = _read_version()

BUILD_OUT = os.environ.get(
    "STAX_BUILD_OUT",
    os.path.join(ROOT, "build", "StaX-{}".format(STAX_VERSION)),
)

# ---------------------------------------------------------------------------
# Pre-clean the output directory BEFORE cx_Freeze tries to.
# cx_Freeze calls shutil.rmtree() internally and raises
#   "error: the build_exe directory cannot be cleaned"
# when any file inside is locked.  We do it here with error handling so
# we can give a clear message instead of a cryptic cx_Freeze traceback.
# ---------------------------------------------------------------------------
if os.path.isdir(BUILD_OUT):
    print("--- Removing previous build output: {}".format(BUILD_OUT))
    try:
        shutil.rmtree(BUILD_OUT)
    except OSError as exc:
        print(
            "\nERROR: Cannot remove previous build directory:\n"
            "  {}\n\n"
            "  Close any Explorer windows, terminals, or processes that\n"
            "  have files open inside that folder, then try again.\n".format(exc)
        )
        sys.exit(1)

os.makedirs(BUILD_OUT, exist_ok=True)

# ---------------------------------------------------------------------------
# Packages cx_Freeze misses via automatic discovery
# ---------------------------------------------------------------------------
PACKAGES = [
    # Qt / PySide2
    "PySide2",
    "PySide2.QtCore",
    "PySide2.QtGui",
    "PySide2.QtWidgets",
    "PySide2.QtWebEngineWidgets",
    "PySide2.QtMultimedia",
    "PySide2.QtMultimediaWidgets",
    "PySide2.QtNetwork",
    "PySide2.QtOpenGL",
    # StaX — core
    "src",
    "src.ui",
    "src.db_manager",
    "src.ingestion_core",
    "src.nuke_bridge",
    "src.extensibility_hooks",
    "src.config",
    "src.icon_loader",
    "src.video_player_widget",
    "src.dark_palette",
    "src.debug_manager",
    "src.db_migrations",
    # StaX — new features
    "src.preview_worker",
    "src.api_server",
    "src.duplicate_detection",
    "src.ui.analytics_panel",
    "src.ui.batch_edit_dialog",
    "src.ui.lazy_gallery_view",
    # Image processing
    "PIL",
    "PIL.Image",
    # Database
    "sqlite3",
    "_sqlite3",
    # Standard library extras
    "logging",
    "threading",
    "queue",
    "encodings",
    "email",
]

# ---------------------------------------------------------------------------
# Modules to exclude (reduces bundle size by ~15-20 MB)
# ---------------------------------------------------------------------------
EXCLUDES = [
    "tkinter",
    "tkinter.ttk",
    "unittest",
    "pydoc",
    "doctest",
    "argparse",
    "difflib",
    "distutils",
    "lib2to3",
    "xmlrpc",
    "ftplib",
    "telnetlib",
    "imaplib",
    "smtplib",
    "poplib",
    "nntplib",
]

# ---------------------------------------------------------------------------
# Data files that must be copied into the build directory
# ---------------------------------------------------------------------------
def _include_files():
    pairs = [
        # (source relative to ROOT,  destination name in build)
        ("resources",    "resources"),
        ("src",          "src"),
        ("dependencies", "dependencies"),
    ]

    # Optional bundled-libs folder
    if os.path.isdir(os.path.join(ROOT, "lib")):
        pairs.append(("lib", "lib"))

    # Nuke plugin files at repo root
    for nuke_file in ("nuke_launcher.py", "menu.py"):
        p = os.path.join(ROOT, nuke_file)
        if os.path.isfile(p):
            pairs.append((p, nuke_file))

    # nuke_plugin\ subdirectory (whole tree)
    nuke_plugin_dir = os.path.join(ROOT, "nuke_plugin")
    if os.path.isdir(nuke_plugin_dir):
        pairs.append((nuke_plugin_dir, "nuke_plugin"))

    return pairs


# ---------------------------------------------------------------------------
# cx_Freeze build options
# ---------------------------------------------------------------------------
BUILD_OPTIONS = {
    "packages":             PACKAGES,
    "excludes":             EXCLUDES,
    "include_files":        _include_files(),
    "build_exe":            BUILD_OUT,
    # PySide2 must NOT be zipped — Qt's plugin loader needs real file paths
    "zip_include_packages": ["*"],
    "zip_exclude_packages": ["PySide2", "src"],
    "optimize":             1,
    "silent":               False,
}

# ---------------------------------------------------------------------------
# Executables
# ---------------------------------------------------------------------------
_WIN_GUI     = "Win32GUI" if sys.platform == "win32" else None
_WIN_CONSOLE = "Console"  if sys.platform == "win32" else None
_ICON        = os.path.join(ROOT, "resources", "logo.png")
_ICON        = _ICON if os.path.isfile(_ICON) else None

EXECUTABLES = [
    # Main GUI — no console window on Windows
    Executable(
        script      = os.path.join(ROOT, "main.py"),
        base        = _WIN_GUI,
        target_name = "StaX.exe",
        icon        = _ICON,
        copyright   = "Copyright (c) 2025 Ahmed Ramadan",
    ),
    # Nuke launcher — console, called from Nuke's init.py
    Executable(
        script      = os.path.join(ROOT, "nuke_launcher.py"),
        base        = _WIN_CONSOLE,
        target_name = "StaX_nuke_launcher.exe",
        icon        = _ICON,
        copyright   = "Copyright (c) 2025 Ahmed Ramadan",
    ),
]

# ---------------------------------------------------------------------------
# setup()
#
# Only pass fields that cx_Freeze itself uses.  Do NOT pass author=,
# author_email=, or url= — setuptools reads pyproject.toml at the same
# time and those fields conflict with PEP 621, producing the
# "_MissingDynamic" warning (and potentially erroring on strict setups).
# ---------------------------------------------------------------------------
setup(
    name        = "StaX",
    version     = STAX_VERSION,
    description = "Professional stock footage and asset management for VFX pipelines",
    options     = {"build_exe": BUILD_OPTIONS},
    executables = EXECUTABLES,
)
