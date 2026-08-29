"""Patch C.1: methodological registry is separate from style engineering."""
from __future__ import annotations

import inspect

from analyzer import stratification_engine as legacy_style
from analyzer.semantic_layers import config_loader
from analyzer.semantic_layers.style_engine import StyleEngine
from analyzer.semantic_layers.style_engine_v2 import (
    STYLE_ENGINE_V2_VERSION,
    StyleEngineV2,
)
from analyzer.semantic_layers.style_selection import (
    CALIBRATED_STYLE_SELECTION_PARAMETERS,
    LEGACY_STYLE_SELECTION_PARAMETERS,
)
from analyzer.semantic_layers.style_scoring import (
    STYLE_MIN_FAMILIES,
    STYLE_SELECTION_FLOOR,
)
from expert_core.style_method_registry import (
    legacy_style_method_mapping_by_id,
    load_style_method_registry,
)
from protocol import feature_model, profile
from protocol.methodological_guard import MethodologicalGuard
from scripts.evaluate_style_engines import evaluate


def _candidate(result, method_feature_id):
    return next(row for row in result.method_feature_candidates
                if row.method_feature_id == method_feature_id)


def test_01_canonical_method_style_registry_exists():
    rows = load_style_method_registry()
    assert len(rows) == 62
    assert len({row["method_feature_id"] for row in rows}) == len(rows)


def test_02_all_method_rows_have_complete_source_traceability():
    rows = load_style_method_registry()
    assert all(row["source_kind"] == "METHOD" for row in rows)
    assert all(row["method_reference"] and row["source_registry"]
               and row["source_wording"] for row in rows)


def test_03_all_method_rows_have_functional_style():
    assert all(row["functional_style"] in {
        "official_business", "scientific", "publicistic", "oratorical",
        "conversational",
    } for row in load_style_method_registry())


def test_04_all_method_rows_have_automation_status():
    assert all(row["automation_status"] in {
        "AUTO", "CANDIDATE_ONLY", "EXPERT_ONLY",
    } for row in load_style_method_registry())


def test_05_canonical_ids_are_separate_from_legacy_metric_ids():
    canonical = {row["method_feature_id"] for row in load_style_method_registry()}
    legacy = {row["id"] for row in config_loader.load_style_features()}
    mappings = config_loader.load_style_legacy_method_mappings()
    assert canonical.isdisjoint(legacy)
    assert len(mappings) == 32
    assert {row["legacy_feature_id"] for row in mappings} == legacy
    assert all(row["method_feature_id"] is None
               for row in config_loader.load_style_features())


def test_06_raw_particle_metric_remains_aux_or_unresolved():
    row = next(row for row in config_loader.load_style_features()
               if row["id"] == "metrics.particles.01")
    assert row["method_status"] == "UNRESOLVED"
    assert row["method_feature_id"] is None
    assert "AUX_METRIC" in row["data_roles"]


def test_07_plain_question_is_not_rhetorical_method_feature():
    result = StyleEngineV2().analyze("Когда открывается библиотека?")
    assert not any("rhetorical" in row.method_feature_id
                   for row in result.method_feature_candidates)


def test_08_vernacular_evidence_may_support_conversational_method_feature():
    mapping = legacy_style_method_mapping_by_id()
    assert "nn.lang.style_colloquial" in mapping["strat.layer.vernacular"]
    registry = feature_model.registered_method_feature("nn.lang.style_colloquial")
    assert registry and registry["canonical_style_method_feature"] is True


def test_09_detected_method_candidate_defaults_unaccepted():
    result = StyleEngineV2().analyze(
        "В соответствии с порядком осуществляется рассмотрение заявления.")
    assert result.method_feature_candidates
    assert all(row.role == "METHOD_FEATURE" and row.accepted is False
               for row in result.method_feature_candidates)


def test_10_unaccepted_candidate_does_not_enter_methodological_count():
    result = StyleEngineV2().analyze(
        "В соответствии с порядком осуществляется рассмотрение заявления.")
    candidate = result.method_feature_candidates[0]
    row = {
        "role": candidate.role,
        "status": candidate.status,
        "source_kind": candidate.source_kind,
        "method_feature_id": candidate.method_feature_id,
    }
    assert MethodologicalGuard.is_countable(None, row) is False


def test_11_expert_identification_value_is_never_assigned():
    result = StyleEngineV2().analyze(
        "В соответствии с порядком осуществляется рассмотрение заявления.")
    assert all(row.expert_identification_value is None
               for row in result.method_feature_candidates)
    assert all("expert_identification_value" not in row
               for row in load_style_method_registry())


def test_12_candidate_only_requires_expert_confirmation():
    result = StyleEngineV2().analyze(
        "На основании решения производится регистрация и направление документов.")
    candidate = _candidate(result, "nn.lang.style_official_business")
    assert candidate.automation_status == "CANDIDATE_ONLY"
    assert candidate.accepted is False and candidate.status == "detected_candidate"


def test_13_expert_only_is_never_auto_detected():
    expert_only = {row["method_feature_id"] for row in load_style_method_registry()
                   if row["automation_status"] == "EXPERT_ONLY"}
    result = StyleEngineV2().analyze(
        "Город расправил каменные плечи, а улицы проглотили тишину.")
    detected = {row.method_feature_id for row in result.method_feature_candidates}
    assert detected.isdisjoint(expert_only)


def test_14_shared_detector_does_not_force_one_style():
    result = StyleEngineV2().analyze("Осуществление.")
    candidates = {row.method_feature_id for row in result.method_feature_candidates}
    assert {"nsv.style.ob.verbal_nouns", "nsv.style.sci.deverbal_nouns"} <= candidates
    assert result.selected_styles == ()


def test_15_methodology_and_style_thresholds_unchanged():
    assert STYLE_SELECTION_FLOOR == 0.12
    assert STYLE_MIN_FAMILIES == 2


def test_16_production_style_engine_remains_v1():
    text = "Чувак, это движуха и тусовка."
    assert StyleEngine().analyze(text) == legacy_style.StratificationEngine().analyze(text)
    assert "style_engine_v2" not in inspect.getsource(profile)


def test_17_v2_stays_shadow_only():
    assert STYLE_ENGINE_V2_VERSION == "v2-shadow"
    assert StyleEngineV2().analyze("Текст.").engine_version == "v2-shadow"


def test_18_development_metrics_are_unchanged():
    metrics = evaluate(
        selection_parameters=LEGACY_STYLE_SELECTION_PARAMETERS)["v2"]
    assert metrics["top1_accuracy"] == 0.8
    assert metrics["micro_precision"] == 0.882353
    assert metrics["micro_recall"] == 0.882353
    assert metrics["micro_f1"] == 0.882353
    assert metrics["macro_f1"] == 0.87


def test_19_calibrated_shadow_metrics_are_explicit():
    metrics = evaluate(
        selection_parameters=CALIBRATED_STYLE_SELECTION_PARAMETERS)["v2"]
    assert metrics["micro_f1"] == 0.923077
