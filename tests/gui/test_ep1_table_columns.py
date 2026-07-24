import pytest

from ui.media_display_widget import MediaDisplayWidget
from nuke_bridge import NukeBridge


def _widget(qtbot, stax_db, stax_config):
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True))
    qtbot.addWidget(w)
    return w


@pytest.mark.gui
def test_table_has_rating_and_label_columns(qtbot, stax_db, stax_config):
    w = _widget(qtbot, stax_db, stax_config)
    assert w.table_view.columnCount() == 8
    headers = [w.table_view.horizontalHeaderItem(i).text()
               for i in range(w.table_view.columnCount())]
    assert headers[-2:] == ["Rating", "Label"]


@pytest.mark.gui
def test_rating_cell_text(qtbot, stax_db, stax_config):
    w = _widget(qtbot, stax_db, stax_config)
    assert w._rating_cell_text(3) == "★★★"
    assert w._rating_cell_text(0) == ""
