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


# Кандидаты реального прогона 17 сентября: четыре верных и шесть ложных.
@pytest.mark.parametrize("feature_id,quote,expected_violation", [
    ("GRA_103", "дааа", False),
    ("GRA_103", "чё", False),
    ("LEX_201", "база", False),
    ("LEX_201", "огонь", False),
    ("GRA_103", "ЗЫ: завтра пришлю исходный файл.", True),
    ("GRA_103", "Ну и что!!!", True),
    ("LEX_201", "ghbdtn", True),
    ("LEX_201", "дааа", True),
    # Опечатка и разговорная форма записаны обычными русскими буквами одним
    # словом, поэтому машинно неотличимы и остаются эксперту.
    ("LEX_201", "првиет", False),
    ("LEX_201", "чё", False),
])
def test_machine_checks_match_the_real_run(feature_id, quote, expected_violation):
    assert bool(exclusion_violations(feature_id, quote)) is expected_violation


def test_machine_checks_never_touch_a_correct_candidate():
    for feature_id, quote in [("GRA_103", "дааа"), ("GRA_103", "чё"),
                              ("LEX_201", "база"), ("LEX_201", "огонь")]:
        assert exclusion_violations(feature_id, quote) == ()


def test_same_quote_is_judged_per_feature():
    """`дааа` допустимо для графики и запрещено для лексики."""
    assert exclusion_violations("GRA_103", "дааа") == ()
    assert exclusion_violations("LEX_201", "дааа")


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
        ("CASE_001/TEXT_A.txt", "Ну что, дааа, договорились."),
        ("CASE_001/TEXT_B.txt", "Он написал ghbdtn в неверной раскладке."),
    ]
    # Первый документ: верный кандидат. Второй: ложный, ловится машинно.
    provider = ScriptedProvider([
        detected("GRA_103", "дааа"), ABSTAINED,
        ABSTAINED, detected("LEX_201", "ghbdtn"),
    ])
    service = QwenShadowService(provider, registry=registry)

    report, rows = evaluate_blind(
        service, documents, ("phonetic_imitation", "internet_lexicon"),
    )

    assert report["documents"] == 2 and report["runs"] == 4
    assert report["candidates"] == 2
    assert report["per_feature"] == {
        "GRA_103": {"candidates": 1, "violations": 0},
        "LEX_201": {"candidates": 1, "violations": 1},
    }
    # Инструмент измеряет, а не отсекает: нарушивший кандидат остаётся в листе.
    flagged = next(row for row in rows if row["feature_id"] == "LEX_201")
    assert "латиница" in flagged["machine_violations"]
    assert next(row for row in rows if row["feature_id"] == "GRA_103")["machine_violations"] == ""


def test_review_sheet_carries_context_and_an_empty_expert_column(tmp_path):
    documents = [("CASE_001/TEXT_A.txt", "Ну что, дааа, договорились о встрече.")]
    provider = ScriptedProvider([detected("GRA_103", "дааа"), ABSTAINED])
    service = QwenShadowService(provider, registry=FeatureRegistry.load(DEFAULT_SHADOW_REGISTRY))
    _, rows = evaluate_blind(service, documents, ("phonetic_imitation", "internet_lexicon"))

    path = tmp_path / "review.csv"
    _write_review_sheet(path, rows)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        written = list(csv.DictReader(handle))

    assert len(written) == 1
    assert written[0]["quote"] == "дааа"
    assert "[дааа]" in written[0]["context"]
    assert written[0]["expert_verdict"] == ""
