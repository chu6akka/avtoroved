"""Patch C.2: honest selection calibration for shadow StyleEngineV2."""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from analyzer import stratification_engine as legacy_style
from analyzer.semantic_layers.style_calibration import (
    CALIBRATION_PARTITION,
    HOLDOUT_PARTITION,
    StyleCalibrationRecord,
    build_deterministic_split,
    optimize_style_selection,
)
from analyzer.semantic_layers.style_engine import StyleEngine
from analyzer.semantic_layers.style_engine_v2 import StyleEngineV2
from analyzer.semantic_layers.style_selection import (
    CALIBRATED_STYLE_SELECTION_PARAMETERS,
    LEGACY_STYLE_SELECTION_PARAMETERS,
    StyleSelectionParameters,
    select_style_scores,
)
from analyzer.semantic_layers.theme_engine_v2 import ThemeEngineV2
from expert_core.style_method_registry import load_style_method_registry
from protocol import profile
from scripts.evaluate_style_engines import analyze_fixtures, load_fixtures


_SPLIT = Path(__file__).parent / "fixtures" / "style_v2" / "split.json"


def _selected(result) -> set[str]:
    return {row.style_id for row in result.selected_styles}


def test_01_style_engine_v1_is_unchanged():
    text = "Чувак, это движуха и тусовка."
    assert StyleEngine().analyze(text) == legacy_style.StratificationEngine().analyze(text)


def test_02_v2_remains_shadow_only():
    assert "StyleEngineV2" not in inspect.getsource(profile)
    assert StyleEngineV2().version == "v2-shadow"


def test_03_ranking_is_separate_from_selection():
    result = StyleEngineV2().analyze("Решение принято.")
    assert result.leading_style is not None
    assert result.selected_styles == ()


def test_04_selected_styles_can_be_empty():
    assert StyleEngineV2().analyze("Молоко; хлеб; чай.").selected_styles == ()


def test_05_leading_style_survives_abstention():
    result = StyleEngineV2().analyze("Нейтральный текст.")
    assert result.leading_style is not None
    assert result.selected_styles == ()


def test_06_weak_conversational_candidates_do_not_force_selection():
    text = ("Уважаемые граждане, разве можно мириться с опасным бездействием? "
            "Нет! Давайте потребуем честного ответа и защитим наш общий город.")
    result = StyleEngineV2().analyze(text)
    conversational = next(row for row in result.styles
                          if row.style_id == "conversational")
    assert "conversational" not in _selected(result)
    assert conversational.selection_reason["weak_evidence_only"] is True
    assert conversational.selection_reason["weak_style_gate_passed"] is False


def test_07_one_quotation_cannot_force_publicistic():
    assert "publicistic" not in _selected(
        StyleEngineV2().analyze("Он сказал: «встреча завтра»."))


def test_08_one_exclamation_cannot_force_publicistic():
    assert "publicistic" not in _selected(StyleEngineV2().analyze("Встреча завтра!"))


def test_09_one_question_cannot_force_oratorical():
    assert "oratorical" not in _selected(StyleEngineV2().analyze("Когда встреча?"))


def test_10_independent_families_can_support_selection():
    result = StyleEngineV2().analyze(
        "Уважаемые коллеги, давайте сохраним нашу общую работу.")
    row = next(row for row in result.styles if row.style_id == "oratorical")
    assert row.selection_reason["supporting_family_count"] >= 2
    assert row.selection_reason["selected"] is True


def test_11_relative_margin_rejects_distant_secondary_style():
    scored = {
        "publicistic": {"support_score": 0.4, "active_families": 3},
        "conversational": {"support_score": 0.2, "active_families": 2},
    }
    features = {"publicistic": (), "conversational": ()}
    baseline = select_style_scores(
        scored, features, LEGACY_STYLE_SELECTION_PARAMETERS)
    calibrated = select_style_scores(
        scored, features, CALIBRATED_STYLE_SELECTION_PARAMETERS)
    assert baseline["conversational"]["selected"] is True
    assert calibrated["conversational"]["selected"] is False
    assert calibrated["conversational"]["relative_margin_passed"] is False


def test_12_absolute_floor_is_enforced():
    parameters = StyleSelectionParameters(0.12, None, 1, None)
    decisions = select_style_scores(
        {"x": {"support_score": 0.1, "active_families": 2}}, {"x": ()},
        parameters)
    assert decisions["x"]["selected"] is False
    assert decisions["x"]["absolute_floor_passed"] is False


def test_13_holdout_records_are_inaccessible_to_optimizer():
    result = StyleEngineV2().analyze("Уважаемые коллеги, давайте действовать.")
    record = StyleCalibrationRecord(
        "forbidden", ("oratorical",), result.styles, HOLDOUT_PARTITION)
    with pytest.raises(ValueError, match="CALIBRATION records only"):
        optimize_style_selection((record,))


def test_14_split_is_deterministic_and_complete():
    fixtures = load_fixtures()
    split = json.loads(_SPLIT.read_text("utf-8"))
    generated = build_deterministic_split(
        fixtures, seed=split["seed"], holdout_size=split["holdout_count"])
    assert generated == {key: split[key]
                         for key in ("calibration_ids", "holdout_ids")}
    assert not set(split["calibration_ids"]) & set(split["holdout_ids"])


def test_15_mixed_styles_are_preserved():
    text = ("На основании решения комиссии утверждается методология исследования. "
            "Под показателем понимается отношение числа совпадений к объёму выборки; "
            "таким образом, расчёт подлежит документированию.")
    assert {"official_business", "scientific"} <= _selected(
        StyleEngineV2().analyze(text))


def test_16_short_ambiguous_fragment_may_abstain():
    result = StyleEngineV2().analyze("Решение принято.")
    assert result.selected_styles == ()


def test_17_method_candidates_remain_unaccepted():
    result = StyleEngineV2().analyze(
        "В соответствии с порядком производится регистрация документов.")
    assert result.method_feature_candidates
    assert all(row.accepted is False for row in result.method_feature_candidates)


def test_18_expert_identification_value_remains_null():
    result = StyleEngineV2().analyze(
        "Уважаемые коллеги, давайте сохраним общую работу.")
    assert all(row.expert_identification_value is None for row in result.styles)
    assert all(row.expert_identification_value is None
               for row in result.method_feature_candidates)


def test_19_methodological_counts_are_unchanged():
    rows = load_style_method_registry()
    assert len(rows) == 62
    assert sum(row["implementation_status"] == "IMPLEMENTED" for row in rows) == 12
    assert sum(row["implementation_status"] == "PARTIAL" for row in rows) == 2
    assert sum(row["implementation_status"] == "NOT_IMPLEMENTED" for row in rows) == 30
    assert sum(row["implementation_status"] == "NOT_APPLICABLE" for row in rows) == 18


def test_20_canonical_registry_has_no_calibration_metadata():
    rows = load_style_method_registry()
    assert all("selection_threshold" not in row for row in rows)
    assert all("relative_margin" not in row for row in rows)


def test_21_theme_engine_is_untouched_by_style_calibration():
    assert "style_selection" not in inspect.getsource(ThemeEngineV2)
    assert "style_calibration" not in inspect.getsource(ThemeEngineV2)


def test_22_selection_reason_is_debug_not_expert_justification():
    row = StyleEngineV2().analyze(
        "Уважаемые коллеги, давайте действовать вместе.").styles[0]
    assert row.selection_reason["semantics"] == \
        "engineering_debug_not_expert_justification"
    assert "threshold_used" in row.selection_reason
    assert "strongest_evidence" in row.selection_reason


def test_23_optimizer_uses_calibration_records_and_freezes_expected_winner():
    fixtures = load_fixtures()
    split = json.loads(_SPLIT.read_text("utf-8"))
    calibration_ids = set(split["calibration_ids"])
    calibration = [fixture for fixture in fixtures
                   if fixture["id"] in calibration_ids]
    analysis = analyze_fixtures(
        calibration, LEGACY_STYLE_SELECTION_PARAMETERS)
    records = tuple(StyleCalibrationRecord(
        fixture["id"], tuple(fixture["expected_styles"]), result.styles,
        CALIBRATION_PARTITION)
        for fixture, result in zip(calibration, analysis["v2_results"]))
    winner, _ = optimize_style_selection(records)
    assert winner.strategy == "F_HYBRID"
    assert winner.parameters == CALIBRATED_STYLE_SELECTION_PARAMETERS
