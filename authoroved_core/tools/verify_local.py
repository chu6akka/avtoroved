"""Реальные офлайн-проверки и снимок собственного окна, не макет результата."""
import argparse
import json
import os
import socket
import time
from dataclasses import asdict
from pathlib import Path

from authoroved_core.core.analysis import AnalysisService
from authoroved_core.core.document import load_document
from authoroved_core.nlp.settings import LocalSettings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("document", type=Path)
    parser.add_argument("--output", type=Path, default=Path("authoroved_core/artifacts"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    settings = LocalSettings.load()
    service = AnalysisService(settings)
    document = load_document(args.document)
    attempted = []
    def forbid_network(sock, address):
        attempted.append(str(address))
        raise RuntimeError("Сетевые соединения запрещены во время офлайн-проверки")
    socket.socket.connect = forbid_network
    socket.socket.connect_ex = forbid_network
    print("Real analysis, network blocked", flush=True)
    first = service.analyze(document, lambda s: print(s, flush=True))
    assert not first.errors, first.errors
    assert first.tokens
    print("Reproducibility check", flush=True)
    second = service.analyze(document)
    assert not second.errors
    assert first.tokens == second.tokens and first.metrics == second.metrics
    assert first.candidates == second.candidates
    assert not attempted, attempted
    for newline in ["\n", "\r\n", "\r"]:
        text = "😀😀 Он пришол домой." + newline + "Он пришол снова."
        candidates, _ = service.lt.analyze("offset-test", text)
        spelling = [c for c in candidates if c.rule_id == "MORFOLOGIK_RULE_RU_RU"]
        assert len(spelling) == 2 and all(c.fragment == "пришол" for c in spelling), spelling

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFontDatabase
    from authoroved_core.ui.main_window import MainWindow
    from authoroved_core.core.models import ReviewStatus
    app = QApplication([])
    # Offscreen-платформа Qt на Windows не перечисляет системные шрифты сама.
    if os.name == "nt":
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ["segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "seguiemj.ttf", "georgia.ttf"]:
            assert QFontDatabase.addApplicationFont(str(fonts / name)) != -1
    window = MainWindow(settings, service)
    window.load_path(args.document)
    # Повторная загрузка даёт новый id документа, используем исходную сущность.
    window.material = document
    window.show()
    window.splitter.setSizes([720, 460])
    window.start_analysis()
    deadline = time.monotonic() + 180
    while window.worker.isRunning() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert not window.worker.isRunning(), "Фоновый анализ не завершился за 180 секунд"
    app.processEvents()
    assert window.result is not None and not window.result.errors
    assert window.result.tokens == first.tokens and window.result.metrics == first.metrics
    assert window.result.candidates == first.candidates
    assert not attempted, attempted
    window.grab().save(str(args.output / "stage_b_analysis.png"))
    window.show_stage(2)
    app.processEvents()
    if window.result.candidates:
        window.candidate_list.setCurrentRow(0)
        assert window.current_candidate is window.result.candidates[0]
        candidate = window.current_candidate
        display_fragment = candidate.fragment.replace("\r\n", "\n").replace("\r", "\n")
        actual = window.text_view.extraSelections()[0].cursor.selectedText().replace("\u2029", "\n")
        assert actual == display_fragment, (actual, display_fragment)
        window.comment.setPlainText("Проверено в приёмочном сценарии этапа B")
        window.accept_button.click()
        assert candidate.status == ReviewStatus.ACCEPTED
        window.reject_button.click()
        assert candidate.status == ReviewStatus.REJECTED
        window.reset_button.click()
        assert candidate.status == ReviewStatus.NEW
        window.comment.clear()
    app.processEvents()
    window.grab().save(str(args.output / "stage_b_review.png"))
    window.resize(1060, 760)
    app.processEvents()
    window.grab().save(str(args.output / "stage_b_review_compact.png"))
    report = {"document": document.name, "metadata": first.metadata,
              "tokens": len(first.tokens), "candidates": len(first.candidates),
              "metrics": len(first.metrics), "reproducible": True, "python_network_attempts": attempted,
              "offset_cases": "emoji + LF/CRLF/CR", "ui_review_actions": "passed",
              "limitations": ["Java subprocess is not covered by Python socket interception; CLI has no remote rules configured.",
                              "Session-only decisions; persistence and export are stage D."]}
    (args.output / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["tokens", "candidates", "metrics", "reproducible"]}), flush=True)
    window.result = None
    window.close()


if __name__ == "__main__":
    main()
