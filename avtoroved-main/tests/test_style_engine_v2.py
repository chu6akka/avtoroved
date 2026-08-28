"""Patch C: StyleEngineV2 is evidence-first and shadow-only."""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

from analyzer import comparison_engine, stratification_engine as legacy_style
from analyzer.semantic_layers import config_loader
from analyzer.semantic_layers.style_detectors import (
    AUTOMATION_STATUSES,
    SPECS,
    STYLE_DETECTOR_SPECS,
    STYLE_LABELS,
)
from analyzer.semantic_layers.style_engine import StyleEngine
from analyzer.semantic_layers.style_engine_v2 import (
    STYLE_ENGINE_V2_VERSION,
    StyleEngineV2,
)
from protocol import profile, report
from protocol.conclusion import methodological_checks


def _selected(result) -> set[str]:
    return {row.style_id for row in result.selected_styles}


def _feature(result, feature_id: str):
    return next(feature for row in result.styles for feature in row.detected_features
                if feature.feature_id == feature_id)


def test_01_v1_output_unchanged():
    text = "Чувак, это движуха и тусовка."
    legacy = legacy_style.StratificationEngine().analyze(text)
    assert StyleEngine(legacy_style.StratificationEngine()).analyze(text) == legacy


def test_02_production_analyze_still_delegates_to_v1():
    sentinel = object()
    fake = type("Fake", (), {"analyze": lambda _self, _text: sentinel})()
    assert StyleEngine(fake).analyze("text") is sentinel


def test_03_v2_is_shadow_only():
    assert STYLE_ENGINE_V2_VERSION == "v2-shadow"
    assert "StyleEngineV2" not in inspect.getsource(profile)


def test_04_exactly_five_functional_styles():
    assert set(STYLE_LABELS) == {
        "official_business", "scientific", "publicistic", "oratorical",
        "conversational",
    }


def test_05_config_schema_is_explicit_and_valid():
    config_loader.load_style_features.cache_clear()
    rows = config_loader.load_style_features()
    required = {
        "id", "label", "style", "method_status", "method_feature_id",
        "automation_status", "producer", "metric_type", "normalization",
        "active", "description", "limitations",
    }
    assert len(rows) == 32
    assert all(required <= set(row) for row in rows)
    assert all(row["automation_status"] in AUTOMATION_STATUSES for row in rows)


def test_06_resolution_table_covers_all_32_features():
    rows = config_loader.load_style_features()
    document = (Path(__file__).parents[1] / "docs" / "style_feature_resolution.md").read_text("utf-8")
    assert all(f"`{row['id']}`" in document for row in rows)
    assert document.count("| `") >= 32


def test_07_auto_detector_has_reproducible_evidence():
    text = "В соответствии с регламентом документы подлежат регистрации."
    first = StyleEngineV2().analyze(text)
    second = StyleEngineV2().analyze(text)
    one = _feature(first, "v2.official.cliche")
    two = _feature(second, "v2.official.cliche")
    assert one == two
    assert one.automation_status == "AUTO"
    assert one.evidence and one.evidence[0].fragment == "В соответствии с"


def test_08_candidate_only_is_never_accepted_automatically():
    result = StyleEngineV2().analyze("Это важно. Очень важно. Для каждого.")
    candidates = [feature for row in result.styles for feature in row.detected_features
                  if feature.automation_status == "CANDIDATE_ONLY"]
    assert candidates
    assert all(feature.accepted is False for feature in candidates)


def test_09_expert_only_is_not_asserted():
    asserted_ids = {
        feature.feature_id for row in StyleEngineV2().analyze(
            "Город проснулся и расправил каменные плечи.").styles
        for feature in row.detected_features
    }
    expert_ids = {spec.feature_id for spec in STYLE_DETECTOR_SPECS.values()
                  if spec.automation_status == "EXPERT_ONLY"}
    assert SPECS["metaphor"].feature_id in expert_ids
    assert asserted_ids.isdisjoint(expert_ids)


def test_10_support_score_is_not_probability():
    result = StyleEngineV2().analyze("На основании решения проводится регистрация.")
    assert result.parameters["score_semantics"] == \
        "engineering_style_support_not_probability"
    assert "probability" not in {field.name for field in
                                 __import__("dataclasses").fields(result.styles[0])}


def test_11_no_expert_identification_value_assignment():
    result = StyleEngineV2().analyze(
        "Уважаемые коллеги, давайте сохраним нашу общую работу.")
    assert all(row.expert_identification_value is None for row in result.styles)
    assert all(feature.expert_identification_value is None for row in result.styles
               for feature in row.detected_features)


def test_12_punctuation_alone_cannot_force_publicistic_style():
    result = StyleEngineV2().analyze("Вот это да!!!")
    assert "publicistic" not in _selected(result)


def test_13_plain_question_cannot_force_oratorical_style():
    result = StyleEngineV2().analyze("Во сколько отправляется поезд?")
    assert "oratorical" not in _selected(result)


def test_14_one_abbreviation_cannot_force_official_style():
    result = StyleEngineV2().analyze("На полке лежал старый ГОСТ.")
    assert "official_business" not in _selected(result)


def test_15_one_terminology_hit_cannot_force_scientific_style():
    result = StyleEngineV2().analyze("Корреляция удивила читателя.")
    assert "scientific" not in _selected(result)


def test_16_metaphor_is_never_auto_asserted():
    result = StyleEngineV2().analyze("Море огней проглотило ночной город.")
    assert all(feature.feature_id != SPECS["metaphor"].feature_id
               for row in result.styles for feature in row.detected_features)


def test_17_question_mark_is_not_rhetorical_question():
    result = StyleEngineV2().analyze("Когда открывается библиотека?")
    assert all(feature.feature_id != SPECS["rhetorical_question"].feature_id
               for row in result.styles for feature in row.detected_features)


def test_18_internet_marker_is_experimental_not_method():
    result = StyleEngineV2().analyze("Ну да))) #вечер")
    feature = _feature(result, "v2.experimental.internet_marker")
    assert feature.method_status == "EXPERIMENTAL"
    assert feature.role == "AUX_METRIC"
    assert feature.method_feature_id is None


def test_19_segment_offsets_are_source_offsets():
    text = ("В соответствии с установленным регламентом проводится обязательная "
            "регистрация всех представленных документов и последующее направление "
            "материалов ответственному подразделению.\n\n"
            "Уважаемые коллеги, давайте сегодня подробно обсудим нашу общую задачу, "
            "сохраним взаимное доверие и вместе завершим начатую важную работу.")
    result = StyleEngineV2().analyze(text)
    assert len(result.segments) == 2
    assert all(text[row.start:row.end] == row.text for row in result.segments)
    assert all(text[e.start:e.end] == e.fragment for row in result.styles
               for e in row.evidence)


def test_20_mixed_styles_can_be_selected():
    text = (
        "На основании решения утверждается методология исследования. "
        "Под показателем понимается отношение числа совпадений к объёму выборки; "
        "таким образом, расчёт подлежит документированию.")
    result = StyleEngineV2().analyze(text)
    assert {"official_business", "scientific"} <= _selected(result)


def test_21_abstention_is_supported():
    result = StyleEngineV2().analyze("Решение принято.")
    assert result.selected_styles == ()
    assert result.leading_style is not None  # debug rank remains available


def test_22_short_text_is_controlled():
    result = StyleEngineV2().analyze("Текст.")
    assert result.status == "ok"
    assert result.segment_count == 1


def test_23_empty_text_is_controlled():
    result = StyleEngineV2().analyze(" \n ")
    assert result.status == "empty"
    assert result.selected_styles == ()
    assert result.leading_style is None


def test_24_aux_metric_is_not_method_feature():
    result = StyleEngineV2().analyze(
        "В соответствии с регламентом проводится регистрация документов.")
    assert all(feature.role == "AUX_METRIC" for row in result.styles
               for feature in row.detected_features)
    assert not any(feature.method_status == "METHOD" for row in result.styles
                   for feature in row.detected_features)


def test_25_experimental_evidence_is_excluded_from_style_score():
    plain = StyleEngineV2().analyze("Нейтральный фрагмент")
    internet = StyleEngineV2().analyze("Нейтральный фрагмент)))")
    plain_score = next(row.support_score for row in plain.styles
                       if row.style_id == "conversational")
    internet_score = next(row.support_score for row in internet.styles
                          if row.style_id == "conversational")
    assert internet_score == plain_score


def test_26_shadow_api_returns_both_versions():
    result = StyleEngine().analyze_shadow(
        "На основании решения проводится регистрация документов.")
    assert set(result) == {"v1", "v2", "comparison"}
    assert result["v2"].engine_version == "v2-shadow"


def test_27_profile_behavior_has_no_v2_import():
    assert "style_engine_v2" not in inspect.getsource(profile)


def test_28_report_behavior_has_no_v2_import():
    assert "style_engine_v2" not in inspect.getsource(report)


def test_29_comparison_behavior_has_no_v2_import():
    source = inspect.getsource(comparison_engine)
    assert "style_engine_v2" not in source
    assert "marked >= 0.04" in source


def test_30_methodological_checks_are_unchanged():
    digest = hashlib.sha256(
        inspect.getsource(methodological_checks).encode()).hexdigest()
    assert digest == "bb319926e1c4c0ba51a3cbf4f3d4ad9889bddcb3184edd13e433c9f32b9e3ab4"


def test_31_feature_resolution_totals_are_conservative():
    rows = config_loader.load_style_features()
    automation = {status: sum(row["automation_status"] == status for row in rows)
                  for status in AUTOMATION_STATUSES}
    method = {status: sum(row["method_status"] == status for row in rows)
              for status in {"METHOD", "AUXILIARY", "EXPERIMENTAL", "UNRESOLVED"}}
    assert automation == {"AUTO": 26, "CANDIDATE_ONLY": 4, "EXPERT_ONLY": 2}
    assert method == {"METHOD": 0, "AUXILIARY": 21,
                      "EXPERIMENTAL": 0, "UNRESOLVED": 11}
