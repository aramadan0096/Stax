# -*- coding: utf-8 -*-
"""main() read resources/style.qss with the platform-default codec (cp1252 on
Windows), which fails on the UTF-8 box-drawing characters in the QSS comments
('charmap' codec can't decode byte 0x90) -- so on Windows the whole stylesheet
silently fails to load and the app runs unstyled. It must be read as UTF-8.
"""

import os

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_QSS = os.path.join(_REPO, "resources", "style.qss")


@pytest.mark.gui
def test_stylesheet_requires_utf8_not_cp1252():
    raw = open(_QSS, "rb").read()
    with pytest.raises(UnicodeDecodeError):
        raw.decode("cp1252")        # the bug: Windows default codec chokes on it
    assert raw.decode("utf-8")      # ...but it is valid UTF-8


@pytest.mark.gui
def test_read_stylesheet_helper_reads_utf8():
    from main import _read_stylesheet

    text = _read_stylesheet(_QSS)
    assert text
    assert "═" in text         # the box-drawing char that broke cp1252
