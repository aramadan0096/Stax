# -*- coding: utf-8 -*-
"""EP2 Task 12: "did you mean", synonym expansion, and a recent-query
completer wired into MediaDisplayWidget's search box.

Constructed with the real MediaDisplayWidget signature
(db_manager, config, nuke_bridge) -- the brief's `MediaDisplayWidget(stax_db)`
is stale; see the task-12 report for the reconciliation.
"""
import pytest

from ui.media_display_widget import MediaDisplayWidget
from nuke_bridge import NukeBridge


def _seed(stax_db):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type,tags) VALUES (1,'x','2D','fire')")


def _widget(qtbot, stax_db, stax_config):
    w = MediaDisplayWidget(stax_db, stax_config, NukeBridge(mock_mode=True))
    qtbot.addWidget(w)
    # QWidget.isVisible() reflects the whole ancestor chain, including the
    # top-level window itself -- without an explicit show() here, a freshly
    # constructed (never-shown) top-level widget makes isVisible() report
    # False for every child regardless of its own setVisible() calls. Shown
    # so the did_you_mean_label visibility assertions below are meaningful.
    w.show()
    return w


@pytest.mark.gui
def test_did_you_mean_appears_on_typo(qtbot, stax_db, stax_config):
    _seed(stax_db)
    w = _widget(qtbot, stax_db, stax_config)

    w.run_text_search("frie")  # no exact hits -> suggestion

    assert "fire" in w.did_you_mean_label.text().lower()
    assert w.did_you_mean_label.isVisible()


@pytest.mark.gui
def test_no_suggestion_when_results_found(qtbot, stax_db, stax_config):
    _seed(stax_db)
    w = _widget(qtbot, stax_db, stax_config)

    w.run_text_search("fire")

    assert not w.did_you_mean_label.isVisible()
