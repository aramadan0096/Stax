# -*- coding: utf-8 -*-
"""Stylesheet loading / icon-URL resolution (no Qt required).

main.py and nuke_launcher.py used to hard-code the rewrite for exactly two
icon URLs (`checked.svg`, `unchecked.svg`), so any *other* `url(:/icons/...)`
in style.qss silently rendered as nothing -- the failure mode that left the
dock float/close buttons and the combo/spin arrows blank.
"""

import os

import pytest

from qss_loader import icons_dir, read_stylesheet, resolve_icon_urls

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STYLE_QSS = os.path.join(PROJECT_ROOT, "resources", "style.qss")


def test_resolves_a_known_icon_to_an_absolute_path():
    out = resolve_icon_urls("QComboBox::down-arrow { image: url(:/icons/chevron_down.svg); }")
    assert ":/icons/" not in out
    assert os.path.exists(out.split("url(")[1].split(")")[0])


def test_unknown_icon_is_left_untouched_rather_than_raising():
    src = "QX { image: url(:/icons/does_not_exist.svg); }"
    assert resolve_icon_urls(src) == src


def test_every_icon_referenced_by_the_stylesheet_ships_with_the_app():
    import re

    with open(STYLE_QSS, "r", encoding="utf-8") as handle:
        raw = handle.read()
    referenced = set(re.findall(r"url\(\s*:/icons/([A-Za-z0-9_.\-]+)\s*\)", raw))
    assert referenced, "style.qss should reference its icons via :/icons/"
    missing = sorted(n for n in referenced if not os.path.exists(os.path.join(icons_dir(), n)))
    assert not missing, "style.qss references missing icons: {}".format(missing)


def test_read_stylesheet_resolves_everything_and_decodes_utf8():
    qss = read_stylesheet(STYLE_QSS)
    # style.qss's section comments are UTF-8 box drawing; a cp1252 read raises.
    assert "─" in qss or "═" in qss
    assert ":/icons/" not in qss


@pytest.mark.parametrize(
    "icon",
    [
        "chevron_down.svg", "chevron_up.svg",
        "chevron_down_accent.svg", "chevron_up_accent.svg",
        "chevron_left.svg", "chevron_right.svg",
        "dock_close.svg", "dock_float.svg",
    ],
)
def test_new_chrome_icons_exist(icon):
    assert os.path.exists(os.path.join(icons_dir(), icon))
