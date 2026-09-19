"""Замер подсказки по эталону; настоящая модель не запускается."""
import json

import pytest

from authoroved_core.core.qwen_classification import QwenClassificationService
from authoroved_core.core.qwen_shadow import ProviderCompletion
from authoroved_core.tools.measure_hint_accuracy import (
    candidate_from_gold, evidence_from_gold, gold_items, measure, text_and_span,
)


class ScriptedProvider:
    """Отвечает заранее заданной меткой на каждый вопрос."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.index = 0

    def complete(self, **kwargs):
        value = self.answers[self.index % len(self.answers)]
        self.index += 1
        raw = value if isinstance(value, str) else json.dumps(
            {"classification": value[0], "reason": value[1]}, ensure_ascii=False,
        )
        return ProviderCompletion(raw, {"model": "frozen-test-model"})


def item(word, gold, context=None, **extra):
    return {
        "word": word, "gold_label": gold,
        "context": context or f"…начало строки [{word}] продолжение строки…",
        "documents": 1, "repeats_in_document": 1, "corpus_ipm": None,
        "nearest_correction": "", "edits": None, "flags": "", "note": "",
        **extra,
    }


def test_context_restores_the_word_and_its_coordinates():
    text, span = text_and_span(item("пикабушник", "neologism"))

    assert text[span.start:span.end] == "пикабушник"
    assert "[" not in text and "…" not in text


def test_every_gold_record_restores_its_own_coordinates():
    for value in gold_items():
        text, span = text_and_span(value)
        assert text[span.start:span.end] == value["word"]


def test_numbers_come_from_the_gold_record_not_recomputed():
    """Замер обязан повторять то, что программа показывала эксперту."""
    value = item("тимбилдинг", "neologism", repeats_in_document=3,
                 corpus_ipm=12.5, nearest_correction="тимбилдинге", edits=1,
                 flags="латиница")

    evidence = evidence_from_gold(value)

    assert evidence.repeats_in_text == 3 and evidence.frequency_ipm == 12.5
    assert evidence.nearest_replacement == "тимбилдинге" and evidence.edit_distance == 1
    assert evidence.has_latin


def test_candidate_carries_the_languagetool_correction():
    value = item("пришол", "spelling_error", nearest_correction="пришёл", edits=1)
    _, span = text_and_span(value)

    candidate = candidate_from_gold(value, span)

    assert candidate.fragment == "пришол"
    assert candidate.replacements == ("пришёл",)
    assert candidate.rule_id == "MORFOLOGIK_RULE_RU_RU"


def test_accuracy_counts_only_answered_cases():
    """Воздержание — не ошибка, а размен полноты на точность."""
    values = [item("первое", "colloquial"), item("второе", "colloquial"),
              item("третье", "name")]
    service = QwenClassificationService(ScriptedProvider([
        ("colloquial", "разговорная форма"),
        ("name", "имя собственное"),
        ("unclear", "окружения не хватает"),
    ]))

    report = measure(service, values)

    assert report["measured"] == 3
    assert report["answered"] == 2 and report["correct"] == 1
    assert report["unclear"] == 1
    assert report["precision_when_answered"] == 0.5
    assert report["share_of_all_items"] == round(1 / 3, 3)


def test_items_without_an_expert_label_are_skipped_and_named():
    """Растяжения написания списком классификаций не покрываются."""
    values = [item("Слууууушай", ""), item("пикабушник", "neologism")]
    service = QwenClassificationService(
        ScriptedProvider([("neologism", "новое слово")]),
    )

    report = measure(service, values)

    assert report["measured"] == 1
    assert report["skipped_without_label"] == ["Слууууушай"]


def test_report_names_what_the_model_confuses():
    values = [item("первое", "authorial"), item("второе", "authorial")]
    service = QwenClassificationService(ScriptedProvider([("name", "имя")]))

    report = measure(service, values)

    assert report["confusions"] == [{"gold": "authorial", "answer": "name", "count": 2}]
    assert report["by_label"]["authorial"] == {"total": 2, "correct": 0, "unclear": 0}


def test_broken_answer_is_counted_as_rejected_not_as_a_mistake():
    values = [item("первое", "authorial")]
    service = QwenClassificationService(ScriptedProvider(['{"classification":"выдумка"}']))

    report = measure(service, values)

    assert report["system_rejected"] == 1
    assert report["answered"] == 0 and report["precision_when_answered"] is None
