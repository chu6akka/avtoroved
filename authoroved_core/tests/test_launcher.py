from pathlib import Path


def test_launcher_does_not_hide_qt_window():
    script = Path("authoroved_core/launch.ps1").read_text(encoding="utf-8-sig")
    assert "-WindowStyle Hidden" not in script
    assert "pythonw.exe" in script
    assert "-PassThru" in script
    assert "HasExited" in script


def test_root_launcher_targets_core_only():
    script = Path("Запустить_Авторовед_Core.cmd").read_text(encoding="utf-8-sig")
    assert "authoroved_core\\launch.ps1" in script
    assert "app2.py" not in script
    assert "avtoroved-main" not in script
