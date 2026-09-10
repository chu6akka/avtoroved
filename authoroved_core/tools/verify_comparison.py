"""Реальная офлайн-проверка этапа C на двух документах."""
import argparse
import json
import os
from pathlib import Path
import socket
import tempfile

from authoroved_core.core.analysis import AnalysisService
from authoroved_core.core.case_repository import CaseRepository
from authoroved_core.core.document import load_document
from authoroved_core.core.models import ReviewStatus
from authoroved_core.nlp.settings import LocalSettings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    parser.add_argument("--output", type=Path, default=Path("authoroved_core/artifacts"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    attempts = []
    def forbid_network(sock, address):
        attempts.append(str(address))
        raise RuntimeError("Сетевые соединения запрещены во время офлайн-проверки")
    socket.socket.connect = forbid_network
    socket.socket.connect_ex = forbid_network

    settings = LocalSettings.load()
    service = AnalysisService(settings)
    documents = [load_document(args.first), load_document(args.second)]
    results = [service.analyze(document, print) for document in documents]
    assert all(not result.errors for result in results), [result.errors for result in results]
    assert not attempts, attempts
    for result in results:
        if result.candidates:
            result.candidates[0].review(ReviewStatus.ACCEPTED, "Принято для проверки экрана сравнения")

    repository = CaseRepository()
    case = repository.create()
    case.materials = documents
    case.results = results
    for slot, document in enumerate(documents, 1):
        repository.record(case, "document_imported", {
            "slot": slot, "name": document.name, "file_sha256": document.file_sha256,
        })
        repository.record(case, "analysis_completed", {
            "slot": slot, "document_id": document.id,
            "metrics": len(results[slot - 1].metrics),
            "candidates": len(results[slot - 1].candidates), "errors": 0,
        })
    with tempfile.TemporaryDirectory() as directory:
        case_path = Path(directory) / "verification.avedcase"
        repository.save(case_path, case, "Проверочный пароль D1")
        restored = repository.open(case_path, "Проверочный пароль D1")
        assert restored.materials == case.materials
        assert restored.results == case.results
        repository.verify_integrity(restored)

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFontDatabase
    from PyQt6.QtWidgets import QApplication
    from authoroved_core.ui.main_window import MainWindow

    app = QApplication([])
    if os.name == "nt":
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ["segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "seguiemj.ttf", "georgia.ttf"]:
            assert QFontDatabase.addApplicationFont(str(fonts / name)) != -1
    window = MainWindow(settings, service)
    window.case = restored
    window.materials = restored.materials
    window.results = restored.results
    window.current_slot = 1
    window.case_path = Path("Проверочное дело.avedcase")
    window.dirty = False
    window.audited_comments = {
        (candidate.document_id, candidate.id): candidate.comment
        for result in window.results if result for candidate in result.candidates
    }
    window.update_material_selector()
    window.update_case_controls()
    window.render_current_material()
    window.stage_buttons[3].setEnabled(True)
    window.resize(1280, 900)
    window.show()
    window.show_stage(2)
    unknown = next((candidate for candidate in results[1].candidates
                    if candidate.rule_id == "MORFOLOGIK_RULE_RU_RU"), None)
    if unknown:
        for row in range(window.candidate_list.count()):
            if window.candidate_list.item(row).data(Qt.ItemDataRole.UserRole) == unknown.id:
                window.candidate_list.setCurrentRow(row)
                break
        app.processEvents()
        assert window.grab().save(str(args.output / "stage_c_unknown_word.png"))
    window.show_stage(1)
    ud_group = next((index for index in range(window.toolbox.count())
                     if window.toolbox.itemText(index) == "Служебная синтаксическая разметка Stanza"), None)
    if ud_group is not None:
        window.toolbox.setCurrentIndex(ud_group)
        window.toolbox.widget(ud_group).setCurrentRow(0)
        app.processEvents()
        assert window.grab().save(str(args.output / "stage_c_ud_explanation.png"))
    window.show_stage(3)
    app.processEvents()
    assert window.workspace.currentWidget() is window.comparison_page
    assert [view.source for view in window.comparison_texts] == [document.text for document in documents]
    screenshot = args.output / "stage_c_comparison.png"
    assert window.grab().save(str(screenshot))
    window.show_stage(4)
    app.processEvents()
    final_screenshot = args.output / "stage_d4_export.png"
    assert window.grab().save(str(final_screenshot))
    docx = args.output / "stage_d4_project.docx"
    package = args.output / "stage_d4_verification.zip"
    assert window.export_docx_to(docx)
    assert window.export_verification_to(package, include_sources=False)
    report = {
        "documents": [document.name for document in documents],
        "metrics": len(window.comparison.metrics),
        "accepted_groups": len(window.comparison.accepted_groups),
        "python_network_attempts": attempts,
        "authorship_score": None,
        "case_roundtrip": True,
        "audit_entries": len(restored.audit),
        "screenshot": str(screenshot),
        "export_screenshot": str(final_screenshot),
        "docx": str(docx),
        "verification_package": str(package),
    }
    (args.output / "stage_c_verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False), flush=True)
    window.results = [None, None]
    window.dirty = False
    window.close()


if __name__ == "__main__":
    main()
