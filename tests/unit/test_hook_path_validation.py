import os
import pytest

from extensibility_hooks import resolve_trusted_script


@pytest.mark.unit
def test_accepts_file_inside_trusted_dir(tmp_path):
    trusted = tmp_path / "processors"
    trusted.mkdir()
    script = trusted / "validate.py"
    script.write_text("result = {'continue': True}\n")
    resolved = resolve_trusted_script(str(script), str(trusted))
    assert resolved == os.path.realpath(str(script))


@pytest.mark.unit
def test_rejects_none_trusted_dir_fail_closed(tmp_path):
    script = tmp_path / "x.py"
    script.write_text("result = {}\n")
    assert resolve_trusted_script(str(script), None) is None


@pytest.mark.unit
def test_rejects_dotdot_escape(tmp_path):
    trusted = tmp_path / "processors"
    trusted.mkdir()
    outside = tmp_path / "evil.py"
    outside.write_text("result = {}\n")
    sneaky = os.path.join(str(trusted), "..", "evil.py")
    assert resolve_trusted_script(sneaky, str(trusted)) is None


@pytest.mark.unit
def test_rejects_absolute_path_outside(tmp_path):
    trusted = tmp_path / "processors"
    trusted.mkdir()
    outside = tmp_path / "evil.py"
    outside.write_text("result = {}\n")
    assert resolve_trusted_script(str(outside), str(trusted)) is None


@pytest.mark.unit
def test_rejects_nonexistent_file(tmp_path):
    trusted = tmp_path / "processors"
    trusted.mkdir()
    assert resolve_trusted_script(str(trusted / "missing.py"), str(trusted)) is None
