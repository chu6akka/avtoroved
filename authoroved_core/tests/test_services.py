import subprocess
from types import SimpleNamespace

from authoroved_core.core.analysis import AnalysisService
from authoroved_core.core.document import load_document
from authoroved_core.nlp.languagetool_adapter import LanguageToolAdapter
from authoroved_core.nlp.settings import LocalSettings


def test_failed_engines_never_report_no_errors(tmp_path, monkeypatch):
    path = tmp_path / "a.txt"
    path.write_text("Пример текста.", encoding="utf-8")
    service = AnalysisService(LocalSettings())
    def fail(*args):
        raise RuntimeError("Недоступно")
    monkeypatch.setattr(service.stanza, "analyze", fail)
    monkeypatch.setattr(service.lt, "analyze", fail)
    result = service.analyze(load_document(path))
    assert len(result.errors) == 2
    assert "languagetool" not in result.metadata and "stanza" not in result.metadata
    assert result.metrics and not result.candidates


def test_cli_transmits_exact_utf8_bytes_without_newline_translation(tmp_path, monkeypatch):
    (tmp_path / "languagetool-commandline.jar").write_bytes(b"jar")
    java = tmp_path / "java.exe"
    java.write_bytes(b"java")
    adapter = LanguageToolAdapter(LocalSettings("", str(tmp_path), str(java)))
    text = "😀 Текст\r\nДалее\n"
    def run(command, **kwargs):
        assert kwargs["input"] == text.encode("utf-8")
        assert not kwargs.get("text")
        assert kwargs["timeout"] == 120
        assert "--remoterules" not in command
        return SimpleNamespace(stdout=b'{"matches": [], "software": {"version": "test"}}')
    monkeypatch.setattr(subprocess, "run", run)
    candidates, metadata = adapter.analyze("d", text)
    assert not candidates and metadata["mode"] == "local-cli"
