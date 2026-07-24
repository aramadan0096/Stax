import pytest
from PySide2 import QtCore, QtGui

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


@pytest.mark.gui
def test_row_population_renders_rating_and_label_cells(qtbot, stax_db, stax_config):
    # Seeded palette label: sort_order 0 is "Reject" / "#E5484D" (see db_migrations.DEFAULT_LABELS).
    labels = stax_db.get_labels()
    assert labels, "expected default labels to be seeded"
    label = labels[0]
    assert (label["name"], label["color_hex"]) == ("Reject", "#E5484D")

    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1,'L')")
        conn.execute(
            "INSERT INTO elements (list_fk, name, type, rating, label_fk) "
            "VALUES (1,'a_labeled','2D',3,?)",
            (label["label_id"],),
        )

    w = _widget(qtbot, stax_db, stax_config)
    w.load_elements(1)  # real entry point: populates both views via _update_views_with_elements

    assert w.table_view.rowCount() == 1

    rating_item = w.table_view.item(0, 6)
    assert rating_item.text() == "★★★"

    label_item = w.table_view.item(0, 7)
    assert label_item.toolTip() == "Reject"
    assert label_item.data(QtCore.Qt.AccessibleTextRole) == "Reject"
    assert label_item.background().color() == QtGui.QColor("#E5484D")

    flags = label_item.flags()
    assert not (flags & QtCore.Qt.ItemIsEditable)
    assert flags & QtCore.Qt.ItemIsSelectable
    assert flags & QtCore.Qt.ItemIsEnabled


@pytest.mark.gui
def test_row_population_degrades_cleanly_without_rating_or_label(qtbot, stax_db, stax_config):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk, name) VALUES (1,'L')")
        conn.execute(
            "INSERT INTO elements (list_fk, name, type, rating, label_fk) "
            "VALUES (1,'b_plain','2D',0,NULL)"
        )

    w = _widget(qtbot, stax_db, stax_config)
    w.load_elements(1)

    assert w.table_view.rowCount() == 1

    rating_item = w.table_view.item(0, 6)
    assert rating_item.text() == ""

    label_item = w.table_view.item(0, 7)
    assert label_item.toolTip() == ""
    assert not label_item.data(QtCore.Qt.AccessibleTextRole)
