import pytest

from ui.empty_state_widget import EmptyStateWidget


@pytest.mark.gui
def test_renders_headline_and_fires_primary(qtbot):
    fired = {"n": 0}
    w = EmptyStateWidget(
        "No assets yet",
        "Ingest footage to get started.",
        primary_action=("Ingest files…", lambda: fired.__setitem__("n", fired["n"] + 1)),
        kind="action",
    )
    qtbot.addWidget(w)
    assert "No assets yet" in w.headline_label.text()
    w.primary_button.click()
    assert fired["n"] == 1


@pytest.mark.gui
def test_secondary_optional(qtbot):
    w = EmptyStateWidget("Nothing here", "…", primary_action=("Browse", lambda: None))
    qtbot.addWidget(w)
    assert w.secondary_button is None
