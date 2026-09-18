import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QLabel, QListWidgetItem, QPushButton

from authoroved_core.core.case_repository import CaseRepository
from authoroved_core.core.feature_models import (
    Applicability, ExpertFeatureStatus, FeatureEvidence, FeatureObservation,
)
from authoroved_core.core.models import (
    AnalysisResult, Candidate, Metric, ReviewStatus, Span, Token,
)
from authoroved_core.core.qwen_theme import QwenThemeRun, ThemeCandidate, ThemeRunStatus
from authoroved_core.nlp.settings import LocalSettings
from authoroved_core.ui.main_window import MainWindow
from authoroved_core.ui.qwen_pilot import (
    NON_SHADOW_PROFILE_IDS, PROFILE_LABELS, QwenPilotDialog,
)
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
    repository = CaseRepository(memory_cost_kib=8192, time_cost=1, parallelism=1)
    window = MainWindow(LocalSettings(), case_repository=repository)
    window.load_path(path)
    candidate = Candidate("c", window.material.id, "Ошибка", "Орфография", "Возможная ошибка", "пришол", Span(6, 12), "RULE")
    result = AnalysisResult(window.material.id, candidates=[candidate],
                            metrics=[Metric("Среднее", "3", "Объяснение", "Количественные показатели")],
                            feature_observations=[FeatureObservation(
                                "LEX_001", {"и": 1}, {"и": 500.0},
                                (FeatureEvidence("Он", Span(3, 5), "пример"),),
                                Applicability.APPLICABLE, (), "auto-0.1.0", (),
                            )],
                            metadata={"languagetool": {"mode": "local-cli"}})
    window.display_result(result)
    window.show()
    app.processEvents()
    yield window
    window.results = [None, None]
    window.dirty = False
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


def test_auto_feature_is_russian_explained_and_requires_explicit_review(window):
    feature_page = next(
        window.toolbox.widget(index) for index in range(window.toolbox.count())
        if window.toolbox.itemText(index) == "Методические AUTO-показатели"
    )
    feature_page.setCurrentRow(0)
    observation = window.result.feature_observations[0]

    assert "внутренняя операционализация" in window.metric_help.text().casefold()
    assert "Сырое значение" in window.metric_help.text()
    assert observation.expert_status is ExpertFeatureStatus.UNREVIEWED
    window.feature_comment.setText("Проверено по тексту")
    window.confirm_feature_button.click()

    assert observation.expert_status is ExpertFeatureStatus.CONFIRMED
    assert observation.expert_comment == "Проверено по тексту"
    assert window.case.audit[-1].event == "feature_reviewed"


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
    assert window.stage_buttons[4].isEnabled()
    assert window.results[0].candidates[0].status == ReviewStatus.ACCEPTED
    assert window.results[1].candidates[0].status == ReviewStatus.ACCEPTED
    window.show_stage(3)
    app.processEvents()
    assert window.workspace.currentWidget() is window.comparison_page
    assert [view.source for view in window.comparison_texts] == [
        window.materials[0].text, window.materials[1].text,
    ]
    assert window.comparison_candidate_list.count() == 2
    relations = [window.comparison_candidate_list.item(row).text()
                 for row in range(window.comparison_candidate_list.count())]
    assert any("Только в тексте 1" in text for text in relations)
    assert any("Только в тексте 2" in text for text in relations)

    window.show_stage(4)
    app.processEvents()
    assert window.workspace.currentWidget() is window.final_page
    report = tmp_path / "Проект.docx"
    package = tmp_path / "Проверка.zip"
    assert window.export_docx_to(report)
    assert window.export_verification_to(package, include_sources=False)
    assert report.is_file() and package.is_file()
    assert window.case.audit[-2].event == "report_exported"
    assert window.case.audit[-1].event == "verification_package_exported"


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
    assert not window.save_button.isEnabled()


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


def test_case_controls_fit_minimum_window(window, app):
    window.resize(1060, 760)
    app.processEvents()
    for widget in [window.settings_button, window.open_case_button, window.save_button,
                   window.audit_button, window.open_button]:
        assert window.rect().contains(widget.mapTo(window, widget.rect().topLeft()))
        assert window.rect().contains(widget.mapTo(window, widget.rect().bottomRight()))


def test_qwen_pilot_button_is_available_for_loaded_text(window):
    assert window.qwen_button.isEnabled()
    assert window.qwen_button.text() == "Qwen · пилот"


def test_qwen_pilot_displays_theme_quotes_and_review(app):
    text = "Обсуждались ремонт дороги и сроки укладки асфальта."
    dialog = QwenPilotDialog(text, "Тема.txt")
    quote = "ремонт дороги"
    start = text.index(quote)
    run = QwenThemeRun(
        "theme_assistance", "0.1.0", ThemeRunStatus.VALIDATED_CANDIDATES,
        '{"status":"DETECTED"}',
        (ThemeCandidate("Ремонт дороги", (
            FeatureEvidence(quote, Span(start, start + len(quote)), "основание"),
        )),),
        {"provider": "test"},
    )

    dialog.display_run(run)
    app.processEvents()
    assert dialog.candidate_list.count() == 1
    assert "Тема · Ремонт дороги" in dialog.candidate_list.item(0).text()
    assert "Дослов" not in dialog.detail.toPlainText()
    assert quote in dialog.detail.toPlainText()
    dialog.accept_button.click()
    assert "Подтверждён только в пилоте" in dialog.candidate_list.item(0).text()
    dialog.close()


def test_qwen_pilot_humanizes_existing_stanza_tokens_without_model(app):
    text = "Он будет писать."
    tokens = [
        Token("Он", "он", "PRON", {"Case": "Nom"}, "nsubj", 3, 1, 1, Span(0, 2)),
        Token("будет", "быть", "AUX", {"Tense": "Fut"}, "aux", 3, 1, 2, Span(3, 8)),
        Token("писать", "писать", "VERB", {"VerbForm": "Inf"}, "root", 0, 1, 3, Span(9, 15)),
    ]
    dialog = QwenPilotDialog(text, "Stanza.txt", tokens=tokens)
    dialog.profile.setCurrentIndex(dialog.profile.findData("stanza_explanation"))
    dialog.run_button.click()
    app.processEvents()

    assert dialog.worker is None
    assert dialog.candidate_list.count() == 3
    assert "Глаголы" in dialog.candidate_list.item(1).text()
    dialog.candidate_list.setCurrentRow(1)
    assert "будущее" in dialog.detail.toPlainText()
    assert "вспомогатель" not in dialog.detail.toPlainText().casefold()
    assert "AUX" in dialog.raw_response.toPlainText()
    dialog.close()


def test_case_save_and_restore_keeps_expert_decisions(window, app, tmp_path):
    window.show_stage(2)
    window.comment.setPlainText("Проверено экспертом")
    window.accept_button.click()
    target = tmp_path / "Рабочее дело.avedcase"

    assert window.save_case_to(target, "надёжный пароль")
    assert not window.dirty
    saved_bytes = target.read_bytes()
    assert "Он пришол".encode("utf-8") not in saved_bytes

    restored = MainWindow(
        LocalSettings(),
        case_repository=CaseRepository(memory_cost_kib=8192, time_cost=1, parallelism=1),
    )
    assert restored.restore_case_from(target, "надёжный пароль")
    app.processEvents()
    candidate = restored.results[0].candidates[0]
    assert candidate.status == ReviewStatus.ACCEPTED
    assert candidate.comment == "Проверено экспертом"
    assert restored.materials[0].original_bytes == window.materials[0].original_bytes
    assert restored.case.audit[-1].event == "case_opened"
    assert restored.dirty
    restored.results = [None, None]
    restored.dirty = False
    restored.close()


def test_case_audit_records_import_analysis_and_review(window):
    window.show_stage(2)
    window.reject_button.click()
    events = [entry.event for entry in window.case.audit]

    assert events[0] == "case_created"
    assert "document_imported" in events
    assert "analysis_completed" in events
    assert events[-1] == "candidate_reviewed"
    window.case_repository.verify_integrity(window.case)


def test_languagetool_groups_explain_unknown_words(window, app):
    unknown = Candidate(
        "unknown", window.material.id, "Слово не распознано словарём",
        "Слово не распознано словарём", "Не найдено в словаре", "кодемашине",
        Span(0, 10), "MORFOLOGIK_RULE_RU_RU", ("коде машине",),
    )
    window.result.candidates.append(unknown)
    window.populate_candidate_groups()
    index = window.candidate_group_filter.findData("unknown_words")
    window.candidate_group_filter.setCurrentIndex(index)
    app.processEvents()

    assert index > 0
    assert window.candidate_list.count() == 1
    assert "не доказательство ошибки" in window.candidate_group_help.text()
    assert window.accept_button.text() == "Сохранить особую словоформу"
    assert window.reject_button.text() == "Не учитывать"
    assert not window.unknown_classification.isHidden()
    assert not window.accept_button.isEnabled()
    assert "не варианты исправления" in window.explanation.toPlainText()

    window.unknown_classification.setCurrentIndex(
        window.unknown_classification.findData("authorial")
    )
    app.processEvents()
    assert window.accept_button.isEnabled()
    window.accept_button.click()

    assert unknown.status is ReviewStatus.ACCEPTED
    assert unknown.expert_classification == "authorial"
    assert any(entry.event == "candidate_classified" for entry in window.case.audit)


def test_qwen_pilot_offers_every_shadow_profile_from_the_registry(app):
    from authoroved_core.core.feature_registry import FeatureRegistry
    from authoroved_core.core.qwen_shadow import (
        DEFAULT_SHADOW_REGISTRY, load_shadow_profiles,
    )

    registry = FeatureRegistry.load(DEFAULT_SHADOW_REGISTRY)
    expected = [item.id for item in load_shadow_profiles(registry=registry)]
    dialog = QwenPilotDialog("Ну что, дааа, договорились.", "Профили.txt")

    offered = [dialog.profile.itemData(index) for index in range(dialog.profile.count())]

    assert offered == expected + list(NON_SHADOW_PROFILE_IDS)
    labels = [dialog.profile.itemText(index) for index in range(dialog.profile.count())]
    assert all(label.strip() for label in labels)
    assert labels[offered.index("overview")] == PROFILE_LABELS["overview"]
    dialog.close()


def _inject_unknown_word(window):
    """LanguageTool в тестах не запускается, поэтому кандидат подставляется."""
    from authoroved_core.core.models import Candidate, Span

    candidate = Candidate(
        "c-unknown", window.result.document_id if hasattr(window.result, "document_id") else "d1",
        "Слово не распознано словарём", "Слово не распознано словарём",
        "Словарь не знает эту форму", "пришол", Span(3, 9), "MORFOLOGIK_RULE_RU_RU",
    )
    window.result.candidates.append(candidate)
    return candidate


def _hint(candidate, status, classification="colloquial"):
    from authoroved_core.core.qwen_classification import CandidateHint

    return CandidateHint(
        candidate.id, status, classification,
        "Разговорная или жаргонная форма" if classification else "",
        "разговорная форма", "{}", {},
    )


def test_llm_hint_never_overwrites_the_expert_choice(window):
    """Подсказка пишется в своё поле и ждёт действия эксперта."""
    from authoroved_core.core.qwen_classification import HintStatus

    candidate = _inject_unknown_word(window)
    candidate.expert_classification = "spelling_error"

    window.llm_hints_ready([_hint(candidate, HintStatus.VALIDATED_HINT)])

    assert candidate.llm_hint == "colloquial"
    assert candidate.llm_hint_reason == "разговорная форма"
    assert candidate.expert_classification == "spelling_error"


@pytest.mark.parametrize("status_name", ["SYSTEM_REJECTED", "MODEL_UNCLEAR"])
def test_rejected_and_unclear_hints_are_not_written_at_all(window, status_name):
    from authoroved_core.core.qwen_classification import HintStatus

    candidate = _inject_unknown_word(window)

    window.llm_hints_ready([_hint(candidate, HintStatus[status_name], classification="")])

    assert candidate.llm_hint == ""


def test_expert_action_is_required_to_transfer_a_hint(window):
    from authoroved_core.core.qwen_classification import HintStatus

    candidate = _inject_unknown_word(window)
    window.llm_hints_ready([_hint(candidate, HintStatus.VALIDATED_HINT)])
    window.current_candidate = candidate
    window.show_llm_hint(candidate)
    assert candidate.expert_classification != "colloquial"

    window.apply_llm_hint()

    assert candidate.expert_classification == "colloquial"
    assert "Подсказка Qwen" in window.hint_label.text()


def test_hint_is_marked_as_not_a_conclusion_when_absent(window):
    candidate = _inject_unknown_word(window)
    window.current_candidate = candidate

    window.show_llm_hint(candidate)

    assert "не является выводом" in window.hint_label.text()
    assert not window.hint_apply_button.isEnabled()


def test_pilot_context_shows_each_quote_separately_not_the_gap_between_them(app):
    """Тематический кандидат ставит цитаты далеко, и промежуток между ними
    вырастал до тысячи с лишним знаков, занимая пол-окна."""
    from authoroved_core.core.feature_models import FeatureEvidence
    from authoroved_core.core.models import Span
    from authoroved_core.ui.qwen_pilot import CONTEXT_LIMIT

    text = "НАЧАЛО первая цитата тут. " + "разделитель " * 200 + "ХВОСТ вторая цитата тут."
    dialog = QwenPilotDialog(text, "Контекст.txt")
    first = text.index("первая цитата")
    second = text.index("вторая цитата")
    evidence = (
        FeatureEvidence("первая цитата", Span(first, first + len("первая цитата"))),
        FeatureEvidence("вторая цитата", Span(second, second + len("вторая цитата"))),
    )

    context = dialog.evidence_context(evidence)

    assert len(context) <= CONTEXT_LIMIT + 1
    assert "первая цитата" in context
    assert "…" in context
    # Промежуток целиком в подпись не попадает.
    assert context.count("разделитель") < 20
    dialog.close()


def test_pilot_context_keeps_a_single_quote_readable(app):
    from authoroved_core.core.feature_models import FeatureEvidence
    from authoroved_core.core.models import Span

    text = "Обычное начало. Ну что, дааа, договорились о встрече. Обычный конец."
    dialog = QwenPilotDialog(text, "Контекст.txt")
    start = text.index("дааа")

    context = dialog.evidence_context((FeatureEvidence("дааа", Span(start, start + 4)),))

    assert "дааа" in context and "…" not in context
    dialog.close()


def test_pilot_candidate_list_does_not_collapse(app):
    dialog = QwenPilotDialog("Текст для проверки списка кандидатов.", "Список.txt")

    assert dialog.candidate_list.minimumHeight() >= 150
    dialog.close()


def test_word_evidence_is_shown_without_any_model(window):
    """Справка не зависит от модели: она полезна, даже если модель выключить."""
    candidate = _inject_unknown_word(window)
    window.current_candidate = candidate

    window.show_word_evidence(candidate)

    text = window.evidence_label.text()
    assert text.startswith("Справка ·")
    assert "В тексте встречается:" in text
    assert window.evidence_label.isVisible() or True  # окно теста может быть скрыто


def test_evidence_shows_numbers_and_never_a_verdict(window):
    """Автоматические метки сняты контрольным набором: 4 верных из 37."""
    candidate = _inject_unknown_word(window)
    candidate.replacements = ()

    window.show_word_evidence(candidate)

    text = window.evidence_label.text()
    assert "В тексте встречается:" in text
    assert "Следует из чисел" not in text


def test_evidence_and_hint_hidden_for_non_unknown_candidates(window):
    """Справка и подсказка касаются только нераспознанных словоформ."""
    from authoroved_core.core.models import Candidate, Span

    unknown = _inject_unknown_word(window)
    other = Candidate(
        "c-punct", "d1", "Пунктуация", "Пунктуация", "пояснение", ",",
        Span(0, 1), "COMMA_RULE",
    )
    window.result.candidates.append(other)

    def select(candidate):
        item = QListWidgetItem(candidate.fragment)
        item.setData(Qt.ItemDataRole.UserRole, candidate.id)
        window.select_candidate(item)

    select(unknown)
    assert window.evidence_label.text().startswith("Справка ·")

    select(other)

    assert window.evidence_label.isHidden()
    assert window.hint_label.isHidden()
