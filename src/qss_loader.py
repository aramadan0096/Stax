# -*- coding: utf-8 -*-
"""Stylesheet loading + icon-URL resolution.

`resources/style.qss` references its icons through Qt-resource-style URLs
(``url(:/icons/chevron_down.svg)``) even though the project ships no compiled
``.qrc``: the icons live as plain files under ``resources/icons/``. Every
entry point that applies the stylesheet therefore has to rewrite those URLs to
absolute filesystem paths before handing the QSS to Qt.

main.py and nuke_launcher.py each used to hard-code that rewrite for the two
checkbox icons, which meant any *new* QSS icon silently rendered as nothing.
`resolve_icon_urls` rewrites them all generically, so adding an icon to the
stylesheet needs no Python change.

Unknown icon names are left untouched (Qt then draws nothing, exactly as
before) rather than raising -- a missing decoration must never take the whole
theme down with it.
"""

import os
import re

_ICON_URL_RE = re.compile(r"url\(\s*:/icons/([A-Za-z0-9_.\-]+)\s*\)")

_ICONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resources", "icons",
)


def icons_dir():
    """Absolute path of the shipped SVG icon directory."""
    return _ICONS_DIR


def resolve_icon_urls(qss, directory=None):
    """Rewrite every ``url(:/icons/<name>)`` in *qss* to an absolute path."""
    directory = directory or _ICONS_DIR

    def _sub(match):
        path = os.path.join(directory, match.group(1))
        if not os.path.exists(path):
            return match.group(0)
        return "url({})".format(path.replace("\\", "/"))

    return _ICON_URL_RE.sub(_sub, qss)


def read_stylesheet(path):
    """Read a QSS file as UTF-8 and resolve its icon URLs.

    style.qss contains UTF-8 box-drawing characters in its section comments;
    the platform-default codec (cp1252 on Windows) can't decode them
    ('charmap' codec can't decode byte 0x90), which silently drops the whole
    stylesheet and leaves the app unstyled. Always decode as UTF-8.
    """
    with open(path, "r", encoding="utf-8") as handle:
        return resolve_icon_urls(handle.read())
