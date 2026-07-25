# -*- coding: utf-8 -*-
"""GUI icon buttons must use bundled SVG icons (via icon_loader.get_icon), not
emoji/text glyphs. Two call sites previously used glyphs: the color-search
button ("\U0001F3A8" palette emoji) and the filter chip remove affordance
("… ✕"). Both now carry real SVG icons (resources/icons/palette.svg,
resources/icons/close.svg).
"""

import os

import pytest
from PySide2 import QtWidgets

from nuke_bridge import NukeBridge

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ICONS = os.path.join(_REPO, "resources", "icons")


@pytest.mark.gui
@pytest.mark.parametrize("name", ["palette", "close"])
def test_new_svg_icon_exists_and_loads(name, qtbot):
    # qtbot ensures a QApplication exists for QSvgRenderer/QPainter rendering.
    assert os.path.isfile(os.path.join(_ICONS, name + ".svg")), \
        "missing resources/icons/{}.svg".format(name)
    from src.icon_loader import get_icon
    icon = get_icon(name, size=16)
    assert not icon.isNull(), "{} icon failed to render".format(name)


def _chip_buttons(bar):
    out = []
    for i in range(bar._row.count()):
        w = bar._row.itemAt(i).widget()
        if w is not None and w not in (bar.count_label, bar.clear_button):
            out.append(w)
    return out


@pytest.mark.gui
def test_filter_chip_uses_svg_not_emoji(qtbot):
    from ui.filter_chip_bar import FilterChipBar

    bar = FilterChipBar()
    qtbot.addWidget(bar)
    bar.set_filter({"types": ["2D"]}, result_count=1)

    chips = _chip_buttons(bar)
    assert len(chips) == 1
    chip = chips[0]
    assert "✕" not in chip.text()          # no ✕ glyph
    assert not chip.icon().isNull()             # carries the SVG close icon


@pytest.mark.gui
def test_color_search_button_uses_svg_not_emoji(qtbot, stax_db, stax_config):
    from ui.media_display_widget import MediaDisplayWidget

    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True))
    qtbot.addWidget(w)

    assert "\U0001F3A8" not in w.color_search_btn.text()   # no 🎨 glyph
    assert not w.color_search_btn.icon().isNull()          # carries the SVG palette icon
