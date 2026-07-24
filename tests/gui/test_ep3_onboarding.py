import pytest


class _Cfg:
    def __init__(self): self.d = {}
    def get(self, k, default=None): return self.d.get(k, default)
    def set(self, k, v): self.d[k] = v


@pytest.mark.gui
def test_step_states_reflect_db(qtbot, stax_db):
    from ui.onboarding_checklist import OnboardingChecklist
    cfg = _Cfg()
    oc = OnboardingChecklist(stax_db, cfg)
    qtbot.addWidget(oc)
    states = oc.step_states()
    assert states["Create a stack"] is False
    stax_db.create_stack("S", "/tmp/S")
    assert oc.step_states()["Create a stack"] is True


@pytest.mark.gui
def test_dismiss_persists(qtbot, stax_db):
    from ui.onboarding_checklist import OnboardingChecklist
    cfg = _Cfg()
    oc = OnboardingChecklist(stax_db, cfg)
    qtbot.addWidget(oc)
    oc.dismiss()
    assert cfg.get("onboarding_dismissed") is True


@pytest.mark.gui
def test_ingest_files_step_flips_when_element_exists(qtbot, stax_db):
    """'Ingest files' is derived from element existence, not a config flag."""
    from ui.onboarding_checklist import OnboardingChecklist
    cfg = _Cfg()
    oc = OnboardingChecklist(stax_db, cfg)
    qtbot.addWidget(oc)
    assert oc.step_states()["Ingest files"] is False

    stack_id = stax_db.create_stack("S", "/tmp/S")
    list_id = stax_db.create_list(stack_id, "L")
    assert oc.step_states()["Ingest files"] is False  # list exists, but no elements yet

    stax_db.create_element(list_id, "Elem1", "2D")
    assert oc.step_states()["Ingest files"] is True


@pytest.mark.gui
def test_insert_into_nuke_step_derived_from_insertion_log(qtbot, stax_db):
    """'Insert into Nuke' must be derived from db.get_total_insertions(), not a config flag."""
    from ui.onboarding_checklist import OnboardingChecklist
    cfg = _Cfg()
    oc = OnboardingChecklist(stax_db, cfg)
    qtbot.addWidget(oc)
    assert oc.step_states()["Insert into Nuke"] is False

    # Setting a config flag must NOT flip the step (that would be the wrong,
    # brief-as-written behavior this task explicitly corrects).
    cfg.set("onboarding_inserted", True)
    assert oc.step_states()["Insert into Nuke"] is False

    stack_id = stax_db.create_stack("S", "/tmp/S")
    list_id = stax_db.create_list(stack_id, "L")
    element_id = stax_db.create_element(list_id, "Elem1", "2D")

    from ui.analytics_panel import log_insertion
    log_insertion(stax_db, element_id)

    assert stax_db.get_total_insertions() == 1
    assert oc.step_states()["Insert into Nuke"] is True


@pytest.mark.gui
def test_step_states_not_cached_across_calls(qtbot, stax_db):
    """step_states() must be recomputed live on every call, nothing cached on the instance."""
    from ui.onboarding_checklist import OnboardingChecklist
    cfg = _Cfg()
    oc = OnboardingChecklist(stax_db, cfg)
    qtbot.addWidget(oc)

    assert oc.step_states() == {
        "Create a stack": False,
        "Ingest files": False,
        "Insert into Nuke": False,
    }

    stack_id = stax_db.create_stack("S", "/tmp/S")
    list_id = stax_db.create_list(stack_id, "L")
    element_id = stax_db.create_element(list_id, "Elem1", "2D")

    from ui.analytics_panel import log_insertion
    log_insertion(stax_db, element_id)

    assert oc.step_states() == {
        "Create a stack": True,
        "Ingest files": True,
        "Insert into Nuke": True,
    }


@pytest.mark.gui
def test_action_requested_signal_fires_for_actionable_steps(qtbot, stax_db):
    """Clicking a step's action button emits action_requested(step_name); the widget
    does not reach into MainWindow itself -- the host is expected to connect and
    perform the real action."""
    from PySide2.QtTest import QTest
    from PySide2 import QtCore
    from ui.onboarding_checklist import OnboardingChecklist

    cfg = _Cfg()
    oc = OnboardingChecklist(stax_db, cfg)
    qtbot.addWidget(oc)

    seen = []
    oc.action_requested.connect(seen.append)

    assert "Create a stack" in oc.action_buttons
    assert "Ingest files" in oc.action_buttons
    QTest.mouseClick(oc.action_buttons["Create a stack"], QtCore.Qt.LeftButton)
    QTest.mouseClick(oc.action_buttons["Ingest files"], QtCore.Qt.LeftButton)

    assert seen == ["Create a stack", "Ingest files"]


@pytest.mark.gui
def test_insert_into_nuke_step_has_no_dead_action_button(qtbot, stax_db):
    """'Insert into Nuke' needs a selected element and has no generic one-click
    entry point, so it must not get a fake/dead action button."""
    from ui.onboarding_checklist import OnboardingChecklist
    cfg = _Cfg()
    oc = OnboardingChecklist(stax_db, cfg)
    qtbot.addWidget(oc)
    assert "Insert into Nuke" not in oc.action_buttons
