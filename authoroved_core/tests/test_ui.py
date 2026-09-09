import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

from authoroved_core.core.models import AnalysisResult, Candidate, Metric, ReviewStatus, Span
from authoroved_core.nlp.settings import LocalSettings
from authoroved_core.ui.main_window import MainWindow
from authoroved_core.ui.text_view import SourceTextView


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    if os.name == "nt":
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ["segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "georgia.ttf"]:
            assert QFontDatabase.addApplicationFont(str(fonts / name)) != -1
    return application


@pytest.fixture
def window(app, tmp_path):
    path = tmp_path / "Текст.txt"
    path.write_bytes("😀\r\nОн пришол домой.".encode())
    window = MainWindow(LocalSettings())
    window.load_path(path)
    candidate = Candidate("c", window.material.id, "Ошибка", "Орфография", "Возможная ошибка", "пришол", Span(6, 12), "RULE")
    result = AnalysisResult(window.material.id, candidates=[candidate],
                            metrics=[Metric("Среднее", "3", "Объяснение", "Количественные показатели")],
                            metadata={"languagetool": {"mode": "local-cli"}})
    window.display_result(result)
    window.show()
    app.processEvents()
    yield window
    window.results = [None, None]
    window.close()
    window.deleteLater()


def test_review_and_comment_survive_navigation(window):
    window.show_stage(2)
    window.comment.setPlainText("Моё замечание")
    window.accept_button.click()
    candidate = window.result.candidates[0]
    assert candidate.status == ReviewStatus.ACCEPTED
    window.show_stage(1)
    window.show_stage(2)
    assert window.comment.toPlainText() == "Моё замечание"
    window.reject_button.click()
    assert candidate.status == ReviewStatus.REJECTED
    window.reset_button.click()
    assert candidate.status == ReviewStatus.NEW


def test_exact_highlight_on_crlf_and_emoji(window):
    window.show_stage(2)
    selection = window.text_view.extraSelections()[0]
    assert selection.cursor.selectedText() == "пришол"


def test_aggregate_clears_highlight(window):
    window.show_stage(2)
    window.show_stage(1)
    window.toolbox.widget(0).setCurrentRow(0)
    assert not window.text_view.extraSelections()
    assert "не имеет одного конкретного фрагмента" in window.highlight_note.text()


def test_rejected_filter_and_next_unreviewed(window):
    window.show_stage(2)
    window.filter.setCurrentIndex(1)
    window.accept_button.click()
    assert window.candidate_list.count() == 0
    assert not window.accept_button.isEnabled()
    window.filter.setCurrentIndex(0)
    window.reset_button.click()
    window.next_candidate()
    assert window.current_candidate.status == ReviewStatus.NEW


def test_no_english_statuses_or_active_future_stages(window):
    texts = [widget.text() for widget in window.findChildren(QLabel)]
    texts += [widget.text() for widget in window.findChildren(QPushButton)]
    assert all(word not in " ".join(texts) for word in ["ACCEPTED", "REJECTED", "NOT_REVIEWED", "HIGH", "METHOD_FEATURE"])
    assert all(not b.isEnabled() for b in window.stage_buttons[3:])


def test_second_text_has_separate_analysis_and_opens_comparison(window, app, tmp_path):
    window.result.candidates[0].review(ReviewStatus.ACCEPTED)
    second_path = tmp_path / "Второй текст.txt"
    second_path.write_text("Она пришла домой!", encoding="utf-8")
    window.load_path(second_path, slot=1)
    second_candidate = Candidate(
        "c2", window.material.id, "Ошибка", "Орфография", "Возможная ошибка",
        "пришла", Span(4, 10), "RULE",
    )
    second_candidate.review(ReviewStatus.ACCEPTED)
    second_result = AnalysisResult(
        window.material.id,
        candidates=[second_candidate],
        metrics=[Metric("Среднее", "5", "Объяснение", "Количественные показатели")],
        metadata={"languagetool": {"mode": "local-cli"}},
    )
    window.display_result(second_result)
    app.processEvents()

    assert window.stage_buttons[3].isEnabled()
    assert window.results[0].candidates[0].status == ReviewStatus.ACCEPTED
    assert window.results[1].candidates[0].status == ReviewStatus.ACCEPTED
    window.show_stage(3)
    app.processEvents()
    assert window.workspace.currentWidget() is window.comparison_page
    assert [view.source for view in window.comparison_texts] == [
        window.materials[0].text, window.materials[1].text,
    ]
    assert window.comparison_candidate_list.count() == 1
    assert "В обоих текстах" in window.comparison_candidate_list.item(0).text()


def test_switching_text_restores_its_review_state(window, app, tmp_path):
    window.result.candidates[0].review(ReviewStatus.REJECTED, "Решение по первому")
    second_path = tmp_path / "Другой.txt"
    second_path.write_text("Второй материал.", encoding="utf-8")
    window.load_path(second_path, slot=1)
    window.material_selector.setCurrentIndex(0)
    window.show_stage(2)
    app.processEvents()

    assert window.current_slot == 0
    assert window.current_candidate.status == ReviewStatus.REJECTED
    assert window.comment.toPlainText() == "Решение по первому"


def test_busy_disables_new_analysis_and_settings(window):
    window.set_busy(True)
    assert not window.open_button.isEnabled()
    assert not window.settings_button.isEnabled()
    assert not window.analyze_button.isEnabled()


def test_empty_span_does_not_highlight_neighbour(app):
    text = SourceTextView()
    text.set_source("Текст")
    text.highlight((Span(2, 2),))
    assert text.extraSelections()[0].cursor.selectedText() == ""


def test_document_typography_preserves_content_and_coordinates(app):
    view = SourceTextView()
    view.set_source("😀 Первая строка.\r\nВторая строка.")
    assert view.toPlainText() == "😀 Первая строка.\nВторая строка."
    assert view.document().firstBlock().blockFormat().lineHeight() == 140
    start = view.source.index("Вторая")
    view.highlight((Span(start, start + len("Вторая")),))
    assert view.extraSelections()[0].cursor.selectedText() == "Вторая"


def test_review_controls_are_accessible_in_compact_window(window, app):
    window.show_stage(2)
    window.resize(1060, 760)
    app.processEvents()
    assert window.width() == 1060 and window.height() == 760
    for widget in [window.accept_button, window.reject_button, window.comment, window.next_button]:
        window.review_scroll.ensureWidgetVisible(widget)
        app.processEvents()
        top_left = widget.mapTo(window, widget.rect().topLeft())
        bottom_right = widget.mapTo(window, widget.rect().bottomRight())
        assert window.rect().contains(top_left) and window.rect().contains(bottom_right)
        viewport = window.review_scroll.viewport()
        assert viewport.rect().contains(widget.mapTo(viewport, widget.rect().center()))
    card = window.candidate_detail.parentWidget()
    for widget in [window.candidate_detail, window.explanation]:
        assert card.rect().contains(widget.geometry())


def test_main_review_actions_visible_without_scrolling_at_default_size(window, app):
    window.show_stage(2)
    window.resize(1280, 900)
    app.processEvents()
    viewport = window.review_scroll.viewport()
    for widget in [window.accept_button, window.reject_button, window.next_button]:
        assert viewport.rect().contains(widget.mapTo(viewport, widget.rect().bottomRight()))
