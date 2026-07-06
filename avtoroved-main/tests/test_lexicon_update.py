"""Тесты обновления словарных баз (protocol/lexicon_update.py). Без сети."""
import json
import os

import pytest

from protocol import lexicon_update as lu


_SAMPLE = """! комментарий RuSentiLex
! ещё комментарий
хороший, Adj, хороший, positive, opinion
аборт, Noun, аборт, negative, fact
до лампочки, Idiom, до лампочки, negative, opinion
битая, строка
"""


def test_parse_rusentilex():
    d = lu.parse_rusentilex(_SAMPLE)
    assert d["хороший"] == ["positive", "opinion", "Adj"]
    assert d["аборт"] == ["negative", "fact", "Noun"]
    assert d["до лампочки"] == ["negative", "opinion", "Idiom"]   # фразы тоже
    assert len(d) == 3            # комментарии и битые строки пропущены


def _fake_source(tmp_path, min_entries=2):
    """Временный источник в реестре, целящий во временный файл."""
    target = tmp_path / "dict.json"
    target.write_text(json.dumps({"старый": ["negative", "fact", "Noun"]}),
                      encoding="utf-8")
    lu.SOURCES["_test"] = {
        "name": "Тестовый", "url": "http://example.invalid/dict.txt",
        "target": str(target), "converter": lu.parse_rusentilex,
        "min_entries": min_entries, "encoding": "utf-8",
    }
    return target


@pytest.fixture(autouse=True)
def _cleanup_registry(tmp_path, monkeypatch):
    # Метаданные — во временный файл, чтобы не трогать репозиторий.
    monkeypatch.setattr(lu, "_META_PATH", str(tmp_path / "meta.json"))
    yield
    lu.SOURCES.pop("_test", None)


def test_update_source_writes_backup_meta(tmp_path):
    target = _fake_source(tmp_path)
    summary = lu.update_source(
        "_test", fetcher=lambda url, enc: _SAMPLE, log_to_db=False)
    assert summary["entries"] == 3
    # Новая база записана.
    data = json.loads(target.read_text(encoding="utf-8"))
    assert "хороший" in data and "старый" not in data
    # Бэкап создан и содержит старую версию.
    assert summary["backup"] and os.path.exists(summary["backup"])
    old = json.loads(open(summary["backup"], encoding="utf-8").read())
    assert "старый" in old
    # Метаданные зафиксированы.
    meta = lu.read_meta()
    assert meta["_test"]["entries"] == 3
    assert meta["_test"]["sha256"] == summary["sha256"]


def test_update_source_validation_keeps_target(tmp_path):
    target = _fake_source(tmp_path, min_entries=100)
    before = target.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="мал"):
        lu.update_source("_test", fetcher=lambda url, enc: _SAMPLE,
                         log_to_db=False)
    # Целевой файл не изменён.
    assert target.read_text(encoding="utf-8") == before
    assert lu.read_meta() == {}


def test_unknown_source():
    with pytest.raises(ValueError):
        lu.update_source("нет-такого", log_to_db=False)


def test_registry_has_rusentilex():
    assert "rusentilex" in lu.SOURCES
    assert lu.SOURCES["rusentilex"]["min_entries"] >= 1000
