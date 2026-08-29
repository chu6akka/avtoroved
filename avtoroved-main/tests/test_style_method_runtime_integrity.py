"""Patch C.1.1: honest runtime status for all canonical style features."""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from analyzer import stratification_engine as legacy_style
from analyzer.semantic_layers.style_engine import StyleEngine
from analyzer.semantic_layers.style_engine_v2 import StyleEngineV2
from analyzer.semantic_layers.style_runtime_integrity import (
    assert_style_method_runtime_integrity,
    audit_style_method_runtime,
)
from analyzer.semantic_layers.style_scoring import (
    STYLE_MIN_FAMILIES,
    STYLE_SELECTION_FLOOR,
)
from expert_core.style_method_registry import (
    IMPLEMENTATION_STATUSES,
    load_style_method_registry,
)
from protocol import profile
from protocol.methodological_guard import MethodologicalGuard
from scripts.evaluate_style_engines import evaluate, load_fixtures


def _method_ids(result):
    return {row.method_feature_id for row in result.method_feature_candidates}


def _candidate(result, feature_id):
    return next(row for row in result.method_feature_candidates
                if row.method_feature_id == feature_id)


def test_01_all_62_features_have_implementation_status():
    rows = load_style_method_registry()
    assert len(rows) == 62
    assert all("implementation_status" in row for row in rows)


def test_02_implementation_status_enum_is_valid():
    assert {row["implementation_status"] for row in load_style_method_registry()} \
        <= IMPLEMENTATION_STATUSES


def test_03_implemented_features_have_real_registered_detectors():
    implemented = [row for row in audit_style_method_runtime()
                   if row.implementation_status == "IMPLEMENTED"]
    assert len(implemented) == 12
    assert all(row.detectors and row.detector_registered for row in implemented)


def test_04_implemented_detectors_are_runtime_reachable():
    assert_style_method_runtime_integrity()
    assert not [row.method_feature_id for row in audit_style_method_runtime()
                if row.implementation_status == "IMPLEMENTED"
                and not row.runtime_reachable]


def test_05_not_implemented_features_are_never_detected():
    unavailable = {row["method_feature_id"] for row in load_style_method_registry()
                   if row["implementation_status"] == "NOT_IMPLEMENTED"}
    detected = set()
    for fixture in load_fixtures():
        detected.update(_method_ids(StyleEngineV2().analyze(fixture["text"])))
    assert detected.isdisjoint(unavailable)


def test_06_not_applicable_features_are_never_detected():
    unavailable = {row["method_feature_id"] for row in load_style_method_registry()
                   if row["implementation_status"] == "NOT_APPLICABLE"}
    detected = set()
    for fixture in load_fixtures():
        detected.update(_method_ids(StyleEngineV2().analyze(fixture["text"])))
    assert detected.isdisjoint(unavailable)


def test_07_partial_features_have_real_documented_legacy_producers():
    partial = [row for row in audit_style_method_runtime()
               if row.implementation_status == "PARTIAL"]
    assert len(partial) == 2
    assert all(row.producer == "analyzer.metrics.STYLE_MARKERS"
               and row.evidence_type == "legacy_exact_marker_count"
               and row.detector_registered and row.runtime_route == "legacy_evidence_only"
               for row in partial)


def test_08_auto_does_not_imply_implemented():
    rows = load_style_method_registry()
    assert any(row["automation_status"] == "AUTO"
               and row["implementation_status"] == "NOT_IMPLEMENTED"
               for row in rows)


def test_09_expert_only_features_are_not_applicable_to_automation():
    rows = [row for row in load_style_method_registry()
            if row["automation_status"] == "EXPERT_ONLY"]
    assert len(rows) == 18
    assert all(row["implementation_status"] == "NOT_APPLICABLE"
               and not row["detectors"] for row in rows)


def test_10_selected_scientific_style_does_not_cascade_private_features():
    text = ("Под величиной понимается число данных. Таким образом, показатель "
            "определяется как отношение частей [1].")
    result = StyleEngineV2().analyze(text)
    assert "scientific" in {row.style_id for row in result.selected_styles}
    ids = _method_ids(result)
    assert "nn.lang.style_scientific" in ids
    assert "nsv.style.sci.identity_constructs" not in ids
    assert "nsv.style.sci.specific_adjectives" not in ids


def test_11_selected_conversational_style_does_not_cascade_private_features():
    text = ("Ну вот, выходные закончились... В общем, посидели дома, потом "
            "сходили в кино. Нормально так.")
    result = StyleEngineV2().analyze(text)
    assert "conversational" in {row.style_id for row in result.selected_styles}
    ids = _method_ids(result)
    assert "nn.lang.style_colloquial" in ids
    assert "ns.style.coll.ellipsis_action" not in ids
    assert "nsv.style.coll.contextual_metaphors" not in ids


@pytest.mark.parametrize(("text", "feature_id"), [
    ("Документ соответствует ГОСТ.", "nsv.style.ob.initial_abbr"),
    ("В соответствии с порядком направлен документ.", "nsv.style.ob.stamps"),
    ("Заявление регистрируется.", "nsv.style.ob.sya_verbs"),
    ("Проводится документирование решения.", "nsv.style.ob.verbal_nouns"),
    ("Проводится документирование решения.", "nsv.style.sci.deverbal_nouns"),
    ("Методология проверяет гипотезу.", "nsv.style.sci.terms"),
])
def test_12_implemented_detectors_return_evidence(text, feature_id):
    candidate = _candidate(StyleEngineV2().analyze(text), feature_id)
    assert candidate.evidence and candidate.accepted is False
    assert candidate.expert_identification_value is None
    assert all(text[row.start:row.end] == row.fragment for row in candidate.evidence)


def test_13_genitive_detector_is_reachable_with_parsed_tokens():
    text = "оценка изменения концентрации"
    tokens = (
        SimpleNamespace(char_start=7, char_end=16, feats="Case=Gen"),
        SimpleNamespace(char_start=17, char_end=29, feats="Case=Gen"),
    )
    candidate = _candidate(
        StyleEngineV2().analyze(text, parsed_tokens=tokens),
        "nsv.style.sci.genitive_chains")
    assert candidate.evidence and candidate.accepted is False
    assert text[candidate.evidence[0].start:candidate.evidence[0].end] == \
        candidate.evidence[0].fragment


@pytest.mark.parametrize(("style_id", "method_id", "text"), [
    ("official_business", "nn.lang.style_official_business",
     "В соответствии с регламентом ООО уведомляет: документы подлежат регистрации."),
    ("scientific", "nn.lang.style_scientific",
     "Под показателем понимается отношение величин. Таким образом, результат определяется как число [1]."),
    ("publicistic", "nn.lang.style_publicistic",
     "«Город достоин лучшего». Город меняется. Город должен жить!"),
    ("oratorical", "nn.lang.style_oratorical",
     "Уважаемые коллеги, перед нами общая задача. Давайте сохраним доверие и завершим работу."),
    ("conversational", "nn.lang.style_colloquial",
     "Ну вот, приехали поздно... В общем, посидели дома. Нормально так."),
])
def test_14_aggregate_detectors_create_only_unaccepted_candidate(
        style_id, method_id, text):
    result = StyleEngineV2().analyze(text)
    assert style_id in {row.style_id for row in result.selected_styles}
    candidate = _candidate(result, method_id)
    assert candidate.accepted is False
    assert candidate.expert_identification_value is None
    assert candidate.evidence


def test_15_candidate_does_not_enter_methodological_count():
    result = StyleEngineV2().analyze(
        "В соответствии с порядком производится регистрация документов.")
    candidate = result.method_feature_candidates[0]
    row = {"role": candidate.role, "status": candidate.status,
           "source_kind": candidate.source_kind,
           "method_feature_id": candidate.method_feature_id}
    assert MethodologicalGuard.is_countable(None, row) is False


def test_16_scoring_and_development_metrics_are_frozen():
    assert (STYLE_SELECTION_FLOOR, STYLE_MIN_FAMILIES) == (0.12, 2)
    metrics = evaluate()["v2"]
    assert metrics == {
        "top1_accuracy": 0.8,
        "micro_precision": 0.882353,
        "micro_recall": 0.882353,
        "micro_f1": 0.882353,
        "macro_f1": 0.87,
        "average_selected_styles": 0.971429,
        "abstention_count": 6,
        "mixed_case_recall": 0.75,
    }


def test_17_production_remains_v1():
    text = "Чувак, это движуха и тусовка."
    assert StyleEngine().analyze(text) == legacy_style.StratificationEngine().analyze(text)
    assert "style_engine_v2" not in inspect.getsource(profile)


def test_18_status_totals_match_audit():
    rows = audit_style_method_runtime()
    assert {status: sum(row.implementation_status == status for row in rows)
            for status in IMPLEMENTATION_STATUSES} == {
                "IMPLEMENTED": 12,
                "PARTIAL": 2,
                "NOT_IMPLEMENTED": 30,
                "NOT_APPLICABLE": 18,
            }
