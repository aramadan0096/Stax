# -*- coding: utf-8 -*-
"""Bundled UI-font loader.

The app used to inherit Qt's platform-default UI font (Arial/Segoe on Windows).
This module bundles a font as a repo asset, registers every font file under
``resources/fonts/`` with Qt at startup, and applies a chosen family as the
application-wide UI font.

**Swapping the font later is a drop-in, no code change required:**

- Drop a new ``.ttf``/``.otf`` into ``resources/fonts/`` — it is auto-registered.
- Set the ``ui_font_family`` config key to the family you want active
  (e.g. ``"Roboto"``). With no key set, the bundled default (``DEFAULT_UI_FONT``)
  is used; if that isn't present either, Qt's default is left untouched.

``resources/fonts/`` is the single source of truth for bundled fonts; keep each
font's license file (e.g. ``OFL.txt``) alongside it.
"""

import logging
import os

from PySide2 import QtGui

log = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(_PROJECT_ROOT, "resources", "fonts")

# Family bundled by default (resources/fonts/Inter-Variable.ttf). Change this
# only if you replace the default bundled asset with a different family.
DEFAULT_UI_FONT = "Inter"

_FONT_EXTS = (".ttf", ".otf", ".ttc")


def register_bundled_fonts(font_dir=None):
    """Register every bundled font file with Qt.

    Requires a live ``QApplication``. Returns the set of font families that were
    successfully registered. Never raises (a bad/locked font file is logged and
    skipped so it can't block startup).
    """
    directory = font_dir or FONT_DIR
    families = set()
    if not os.path.isdir(directory):
        log.warning("Font directory not found: %s", directory)
        return families
    for name in sorted(os.listdir(directory)):
        if not name.lower().endswith(_FONT_EXTS):
            continue
        path = os.path.join(directory, name)
        try:
            font_id = QtGui.QFontDatabase.addApplicationFont(path)
        except Exception:
            log.exception("Failed to register font: %s", path)
            continue
        if font_id == -1:
            log.warning("Qt rejected font file: %s", path)
            continue
        for family in QtGui.QFontDatabase.applicationFontFamilies(font_id):
            families.add(family)
    return families


def resolve_ui_family(config=None, registered=None):
    """Decide which family to use for the UI font.

    Priority: an explicit ``ui_font_family`` config value (honored even if it is
    a system font outside our bundle — Qt substitutes if it's missing) → the
    bundled ``DEFAULT_UI_FONT`` when registered → ``None`` (leave Qt's default).
    """
    available = set(registered or ())
    requested = None
    if config is not None:
        try:
            requested = config.get("ui_font_family")
        except AttributeError:
            requested = getattr(config, "ui_font_family", None)
    if requested:
        return requested
    if DEFAULT_UI_FONT in available:
        return DEFAULT_UI_FONT
    return None


def apply_ui_font(app, config=None):
    """Register bundled fonts and set the app-wide UI font family.

    The current point size is preserved (only the family changes), so QSS
    ``font-size`` rules and the accessibility text-scale still apply on top.
    Returns the family applied, or ``None`` if the font was left unchanged.
    Safe to call once, early, right after the ``QApplication`` is created.
    """
    if app is None:
        return None
    registered = register_bundled_fonts()
    family = resolve_ui_family(config, registered)
    if not family:
        return None
    font = app.font()
    font.setFamily(family)
    app.setFont(font)
    log.info("UI font applied: %s", family)
    return family
