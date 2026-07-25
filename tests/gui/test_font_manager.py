# -*- coding: utf-8 -*-
"""The app shipped no bundled UI font, so it inherited Qt's platform default
(Arial/Segoe on Windows). font_manager bundles a font under resources/fonts/,
registers every font there with Qt, and applies a configurable family as the
app-wide UI font. Swapping the font later is a drop-in: add a .ttf/.otf to
resources/fonts/ and/or set the `ui_font_family` config key.
"""

import os

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FONT_DIR = os.path.join(_REPO, "resources", "fonts")


def test_bundled_font_asset_and_license_present():
    assert os.path.isfile(os.path.join(_FONT_DIR, "Inter-Variable.ttf")), \
        "bundled UI font missing"
    assert os.path.isfile(os.path.join(_FONT_DIR, "OFL.txt")), \
        "OFL license for the bundled font must ship alongside it"


@pytest.mark.gui
def test_register_bundled_fonts_registers_inter(qtbot):
    from font_manager import register_bundled_fonts
    families = register_bundled_fonts()
    assert "Inter" in families


def test_resolve_ui_family_honors_config_override():
    from font_manager import resolve_ui_family
    fam = resolve_ui_family({"ui_font_family": "Roboto"}, registered={"Inter"})
    assert fam == "Roboto"


def test_resolve_ui_family_defaults_to_bundled():
    from font_manager import resolve_ui_family, DEFAULT_UI_FONT
    assert resolve_ui_family(None, registered={DEFAULT_UI_FONT}) == DEFAULT_UI_FONT


def test_resolve_ui_family_none_when_nothing_available():
    from font_manager import resolve_ui_family
    assert resolve_ui_family(None, registered=set()) is None


@pytest.mark.gui
def test_apply_ui_font_replaces_default_family(qtbot):
    from PySide2 import QtWidgets
    from font_manager import apply_ui_font

    app = QtWidgets.QApplication.instance()
    applied = apply_ui_font(app, config=None)

    assert applied == "Inter"
    assert app.font().family() == "Inter"
    assert app.font().family().lower() != "arial"
