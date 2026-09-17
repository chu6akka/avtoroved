"""Замер теневых признаков по неразмеченному корпусу; модель не запускается."""
import csv
import json

import pytest

from authoroved_core.core.feature_registry import FeatureRegistry
from authoroved_core.core.qwen_shadow import (
    DEFAULT_SHADOW_REGISTRY, ProviderCompletion, QwenShadowService,
)
from authoroved_core.tools.evaluate_qwen_shadow_blind import (
    evaluate_blind,
    exclusion_violations,
    iter_corpus_documents,
    _write_review_sheet,
)


class ScriptedProvider:
    """Отдаёт заранее заданный ответ на каждый вызов профиля."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.index = 0

    def complete(self, **kwargs):
        raw = self.responses[self.index % len(self.responses)]
        self.index += 1
        return ProviderCompletion(raw, {"model": "frozen-test-model"})


def detected(feature_id, quote):
    return json.dumps(
        {"status": "DETECTED", "observations": [{"feature_id": feature_id, "quote": quote}]},
        ensure_ascii=False,
    )


ABSTAINED = '{"status":"INSUFFICIENT_DATA","observations":[]}'


# Главный отказ замера: цитата длиннее одного слова в 20 случаях из 25.
@pytest.mark.parametrize("quote,expected_violation", [
    ("дааа", False),
    ("ЗЫ", False),
    ("ЗЫ: завтра пришлю исходный файл.", True),
    ("Ну и что!!!", True),
])
def test_multiword_quote_is_the_violation_that_survived(quote, expected_violation):
    assert bool(exclusion_violations("GRA_101", quote)) is expected_violation


def test_corpus_reader_walks_blind_cases_in_stable_order(tmp_path):
    for case, text in [("CASE_002", "второй"), ("CASE_001", "первый")]:
        case_dir = tmp_path / "blind" / case
        case_dir.mkdir(parents=True)
        (case_dir / "TEXT_A.txt").write_text(text + " A", encoding="utf-8")
        (case_dir / "TEXT_B.txt").write_text(text + " B", encoding="utf-8")

    documents = iter_corpus_documents(tmp_path)

    assert [item[0] for item in documents] == [
        "CASE_001/TEXT_A.txt", "CASE_001/TEXT_B.txt",
        "CASE_002/TEXT_A.txt", "CASE_002/TEXT_B.txt",
    ]
    assert documents[0][1] == "первый A"


def test_corpus_reader_reports_a_missing_corpus_clearly(tmp_path):
    with pytest.raises(FileNotFoundError, match="Не найден каталог"):
        iter_corpus_documents(tmp_path)


def test_blind_measurement_counts_violations_and_keeps_every_candidate(tmp_path):
    registry = FeatureRegistry.load(DEFAULT_SHADOW_REGISTRY)
    documents = [
        ("CASE_001/TEXT_A.txt", "Основное сообщение. ЗЫ: завтра пришлю файл."),
        ("CASE_001/TEXT_B.txt", "Он написал ghbdtn в неверной раскладке."),
    ]
    # Первый документ: верный кандидат. Второй: ложный, ловится машинно.
    provider = ScriptedProvider([
        detected("GRA_101", "ЗЫ"), ABSTAINED,
        ABSTAINED, detected("GRA_102", "ghbdtn"),
    ])
    service = QwenShadowService(provider, registry=registry)

    report, rows = evaluate_blind(
        service, documents, ("overview", "internet_communication"),
    )

    assert report["documents"] == 2 and report["runs"] == 4
    assert report["candidates"] == 2
    assert report["per_feature"] == {
        "GRA_101": {"candidates": 1, "violations": 0},
        "GRA_102": {"candidates": 1, "violations": 0},
    }
    # Инструмент измеряет, а не отсекает: все кандидаты остаются в листе.
    assert {row["feature_id"] for row in rows} == {"GRA_101", "GRA_102"}


def test_review_sheet_carries_context_and_an_empty_expert_column(tmp_path):
    documents = [("CASE_001/TEXT_A.txt", "Основное сообщение. ЗЫ: завтра пришлю файл.")]
    provider = ScriptedProvider([detected("GRA_101", "ЗЫ"), ABSTAINED])
    service = QwenShadowService(provider, registry=FeatureRegistry.load(DEFAULT_SHADOW_REGISTRY))
    _, rows = evaluate_blind(service, documents, ("overview", "internet_communication"))

    path = tmp_path / "review.csv"
    _write_review_sheet(path, rows)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        written = list(csv.DictReader(handle))

    assert len(written) == 1
    assert written[0]["quote"] == "ЗЫ"
    assert "[ЗЫ]" in written[0]["context"]
    assert written[0]["expert_verdict"] == ""
