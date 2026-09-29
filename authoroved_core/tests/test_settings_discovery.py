import json

from authoroved_core.nlp import settings


def _installation(root):
    lt = root / "Programs" / "LanguageTool-6.6"
    lt.mkdir(parents=True)
    (lt / settings.LT_JAR).write_bytes(b"jar")
    stanza = root / "stanza_resources"
    (stanza / "ru").mkdir(parents=True)
    (stanza / settings.STANZA_MARKER).write_text("{}", encoding="utf-8")
    java = root / "jdk" / "bin" / "java.exe"
    java.parent.mkdir(parents=True)
    java.write_bytes(b"exe")
    return lt, stanza, java


def test_stale_paths_after_moving_are_replaced_by_found_ones(tmp_path, monkeypatch):
    lt, stanza, java = _installation(tmp_path)
    settings_file = tmp_path / ".local" / "settings.json"
    settings_file.parent.mkdir()
    settings_file.write_text(json.dumps({
        "stanza_dir": "F:/moved/stanza", "languagetool_dir": "F:/moved/lt",
        "java_executable": "F:/moved/java.exe",
    }), encoding="utf-8")
    monkeypatch.setattr(settings, "SETTINGS_PATH", settings_file)
    monkeypatch.setattr(settings, "CORE_ROOT", tmp_path / "missing")
    monkeypatch.setattr(settings, "_search_bases", lambda: [tmp_path])
    monkeypatch.setattr(settings, "find_java", lambda: str(java))
    monkeypatch.setattr(settings.Path, "home", classmethod(lambda cls: tmp_path / "home"))

    loaded = settings.LocalSettings.load()

    assert loaded.languagetool_dir == str(lt)
    assert loaded.stanza_dir == str(stanza)
    assert loaded.java_executable == str(java)
    assert json.loads(settings_file.read_text(encoding="utf-8"))["languagetool_dir"] == str(lt)


def test_valid_saved_paths_are_kept(tmp_path, monkeypatch):
    lt, stanza, java = _installation(tmp_path)
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "stanza_dir": str(stanza), "languagetool_dir": str(lt), "java_executable": str(java),
    }), encoding="utf-8")
    monkeypatch.setattr(settings, "SETTINGS_PATH", settings_file)
    monkeypatch.setattr(settings, "_search_bases", lambda: (_ for _ in ()).throw(AssertionError("поиск не нужен")))

    loaded = settings.LocalSettings.load()

    assert (loaded.stanza_dir, loaded.languagetool_dir, loaded.java_executable) == (str(stanza), str(lt), str(java))
