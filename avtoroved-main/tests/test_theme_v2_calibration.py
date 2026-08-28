"""Patch B.2: ranking/selection separation and frozen development calibration."""
from __future__ import annotations

import hashlib
import inspect
from pathlib import Path
from types import SimpleNamespace

from analyzer import thematic_engine as legacy_theme
from analyzer.semantic_layers.contracts import ThemeV2Score
from analyzer.semantic_layers.embedding_backend import DeterministicEmbeddingBackend
from analyzer.semantic_layers.theme_engine import ThemeEngine
from analyzer.semantic_layers.theme_engine_v2 import ThemeEngineV2
from analyzer.semantic_layers.theme_selection import (
    DEFAULT_THEME_SELECTION_PARAMETERS,
    ThemeSelectionParameters,
    select_themes,
)
from protocol.conclusion import methodological_checks
from scripts.calibrate_theme_v2 import (
    SPLIT_SEED,
    create_split_manifest,
    tune_selection,
)
from scripts.evaluate_theme_engines import load_fixtures


def _score(theme_id: str, combined: float, *, semantic: float | None = None,
           lexical: float = 0.0, coverage: float = 1.0,
           supports: int = 1) -> ThemeV2Score:
    return ThemeV2Score(
        theme_id=theme_id,
        label=theme_id,
        semantic_score=semantic if semantic is not None else combined,
        lexical_score=lexical,
        combined_score=combined,
        coverage=coverage,
        segment_support_count=supports,
        segment_count=1,
        expert_identification_value=None,
    )


def test_01_production_v1_unchanged():
    lemmas = ["суд", "иск", "договор", "кодекс", "приговор"]
    legacy = legacy_theme.ThematicEngine().analyze(lemmas)
    assert ThemeEngine(legacy_theme.ThematicEngine()).analyze(lemmas) == legacy


def test_02_v2_remains_explicit_shadow_only():
    from protocol import profile
    assert "ThemeEngineV2" not in inspect.getsource(profile)
    assert ThemeEngineV2.version == "v2-shadow"


def test_03_ranking_is_separate_from_selection():
    ranked = (_score("science", 0.61), _score("medicine", 0.54),
              _score("sports", 0.33))
    before = tuple((row.theme_id, row.combined_score) for row in ranked)
    selected = select_themes(ranked, ThemeSelectionParameters(
        absolute_floor=0.44, relative_margin=0.08))
    assert [row.theme_id for row in selected] == ["science", "medicine"]
    assert tuple((row.theme_id, row.combined_score) for row in ranked) == before


def test_04_dominant_can_exist_with_empty_selected_themes():
    engine = ThemeEngineV2(
        DeterministicEmbeddingBackend(),
        selection_parameters=ThemeSelectionParameters(
            strategy="absolute", absolute_floor=1.0,
            relative_margin=None, relative_ratio=None),
    )
    result = engine.analyze(
        "Команда выиграла матч, игрок забил гол, тренер праздновал финал.")
    assert result.dominant_theme is not None
    assert result.selected_themes == ()


def test_05_relative_margin_selection_works():
    ranked = (_score("law", 0.60), _score("politics", 0.55),
              _score("economics", 0.49))
    parameters = ThemeSelectionParameters(
        strategy="relative_margin", absolute_floor=0.0,
        relative_margin=0.06, relative_ratio=None)
    assert [row.theme_id for row in select_themes(ranked, parameters)] == [
        "law", "politics"]


def test_06_absolute_floor_works():
    ranked = (_score("science", 0.47), _score("it", 0.43))
    parameters = ThemeSelectionParameters(
        strategy="absolute", absolute_floor=0.44,
        relative_margin=None, relative_ratio=None)
    assert [row.theme_id for row in select_themes(ranked, parameters)] == ["science"]


def test_07_weak_unrelated_themes_are_rejected():
    ranked = (_score("sports", 0.62), _score("religion", 0.38),
              _score("military", 0.34))
    assert [row.theme_id for row in select_themes(
        ranked, DEFAULT_THEME_SELECTION_PARAMETERS)] == ["sports"]


def test_08_close_second_survives_for_mixed_text():
    ranked = (_score("it", 0.63), _score("science", 0.57),
              _score("everyday", 0.41))
    assert [row.theme_id for row in select_themes(
        ranked, DEFAULT_THEME_SELECTION_PARAMETERS)] == ["it", "science"]


def test_09_semantic_only_theme_does_not_require_lexical_match():
    semantic_only = _score("science", 0.58, semantic=0.773333, lexical=0.0)
    selected = select_themes(
        (semantic_only, _score("medicine", 0.42)),
        DEFAULT_THEME_SELECTION_PARAMETERS)
    assert selected == (semantic_only,)


def test_10_calibration_parameters_are_deterministic():
    first = DEFAULT_THEME_SELECTION_PARAMETERS.as_dict()
    second = ThemeSelectionParameters(**first).as_dict()
    assert first == second


def test_11_tuning_api_cannot_receive_holdout():
    parameter_names = tuple(inspect.signature(tune_selection).parameters)
    assert parameter_names == ("calibration_fixtures", "calibration_results")
    assert all("holdout" not in name for name in parameter_names)


def test_12_fixed_split_is_reproducible():
    fixtures = load_fixtures(include_hard=True)
    first = create_split_manifest(fixtures, seed=SPLIT_SEED)
    second = create_split_manifest(fixtures, seed=SPLIT_SEED)
    assert first == second
    frozen = Path(__file__).parent / "fixtures" / "theme_v2" / "split.json"
    import json
    assert first == json.loads(frozen.read_text(encoding="utf-8"))


def test_13_selected_count_is_substantially_lower_on_fixture_corpus():
    engine = ThemeEngineV2(DeterministicEmbeddingBackend())
    results = [engine.analyze(row["text"])
               for row in load_fixtures(include_hard=True)]
    baseline = sum(
        score.segment_support_count > 0
        for result in results for score in result.themes)
    calibrated = sum(len(result.selected_themes) for result in results)
    assert calibrated <= baseline * 0.50


def test_14_expert_identification_value_remains_null():
    result = ThemeEngineV2(DeterministicEmbeddingBackend()).analyze(
        "Президент и парламент обсуждали выборы и государственную реформу.")
    assert all(row.expert_identification_value is None for row in result.themes)
    assert all(row.expert_identification_value is None
               for row in result.selected_themes)


def test_15_methodological_checks_implementation_is_unchanged():
    source_hash = hashlib.sha256(
        inspect.getsource(methodological_checks).encode()).hexdigest()
    assert source_hash == "bb319926e1c4c0ba51a3cbf4f3d4ad9889bddcb3184edd13e433c9f32b9e3ab4"


def test_16_previous_v2_contract_fields_are_preserved():
    result = ThemeEngineV2(DeterministicEmbeddingBackend()).analyze(
        "Исследователь провел эксперимент и опубликовал научную статью.")
    assert result.status == "ok"
    assert result.themes
    assert result.dominant_theme is None or result.dominant_theme in result.themes
    assert all(row in result.themes for row in result.selected_themes)
    assert result.parameters["score_semantics"] == \
        "similarity_and_ranking_not_probability"
