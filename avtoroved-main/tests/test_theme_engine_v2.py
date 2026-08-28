"""Patch B: ThemeEngineV2 существует только в управляемом shadow mode."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from analyzer import thematic_engine as legacy_theme
from analyzer.semantic_layers import config_loader
from analyzer.semantic_layers.embedding_backend import (
    DeterministicEmbeddingBackend,
    SentenceTransformerEmbeddingBackend,
    UnavailableEmbeddingBackend,
)
from analyzer.semantic_layers.lexical_theme_evidence import (
    LexicalThemeEvidenceExtractor,
)
from analyzer.semantic_layers.theme_engine import ThemeEngine
from analyzer.semantic_layers.theme_engine_v2 import (
    THEME_ENGINE_V2_VERSION,
    ThemeEngineV2,
    clear_prototype_embedding_cache,
)
from analyzer.semantic_layers.theme_segmenter import (
    SegmentationParameters,
    segment_text,
)
from protocol import profile
from scripts.evaluate_theme_engines import evaluate, load_fixtures


@pytest.fixture(scope="module")
def deterministic_engine():
    return ThemeEngineV2(DeterministicEmbeddingBackend())


def test_01_v1_behavior_unchanged():
    lemmas = ["государство", "правительство", "президент", "парламент"]
    legacy = legacy_theme.ThematicEngine().analyze(lemmas)
    facade = ThemeEngine(legacy_theme.ThematicEngine()).analyze(lemmas)
    assert facade == legacy


def test_02_production_analyze_still_uses_v1():
    expected = object()
    fake_legacy = SimpleNamespace(analyze=lambda lemmas: expected)
    assert ThemeEngine(fake_legacy).analyze(["текст"]) is expected


def test_03_v2_does_not_affect_profile_result(monkeypatch):
    def forbidden(_self, _text):
        raise AssertionError("V2 не должен вызываться production profile")

    monkeypatch.setattr(ThemeEngineV2, "analyze", forbidden)
    result = profile.semantic_candidates(
        legacy_theme.ThematicEngine().analyze(["суд", "иск", "кодекс"] * 5))
    assert isinstance(result, list)


def test_04_v2_segments_text():
    segments = segment_text(
        "Первый достаточно подробный абзац описывает одну часть материала. "
        "В нем есть несколько связанных предложений.\n\n"
        "Второй содержательный абзац посвящен другой части материала и тоже "
        "содержит достаточно слов для отдельного сегмента.")
    assert len(segments) == 2


def test_05_segment_offsets_are_valid():
    text = "Начальный абзац содержит восемь разных слов для надежной проверки.\n\n" \
           "Следующий абзац также содержит достаточно слов для проверки смещений."
    for segment in segment_text(text):
        assert 0 <= segment.start < segment.end <= len(text)
        assert text[segment.start:segment.end] == segment.text


def test_06_empty_paragraphs_are_ignored():
    text = "Первый непустой абзац содержит достаточно слов для теста.\n\n \n\n" \
           "Второй непустой абзац тоже содержит достаточно слов для теста."
    segments = segment_text(text)
    assert segments
    assert all(segment.text.strip() for segment in segments)


def test_07_long_paragraph_is_split_safely():
    sentence = "Это длинное предложение содержит десять обычных слов для проверки алгоритма. "
    text = sentence * 60
    parameters = SegmentationParameters(min_tokens=8, target_tokens=40, max_tokens=55)
    segments = segment_text(text, parameters)
    assert len(segments) > 1
    assert all(segment.token_count <= 55 for segment in segments)
    assert all(text[segment.start:segment.end] == segment.text for segment in segments)


def test_08_prototypes_load():
    prototypes = config_loader.load_theme_prototypes()
    assert sum(len(row["prototypes"]) for row in prototypes.values()) == 200


def test_09_all_active_themes_have_prototypes():
    ontology = config_loader.load_theme_ontology()
    prototypes = config_loader.load_theme_prototypes()
    active = {key for key, row in ontology.items() if row["active"]}
    assert active == set(prototypes)
    assert all(prototypes[key]["prototypes"] for key in active)


def test_10_prototype_ids_map_to_ontology():
    assert set(config_loader.load_theme_prototypes()) == set(
        config_loader.load_theme_ontology())


def test_11_embedding_backend_is_lazy():
    backend = SentenceTransformerEmbeddingBackend()
    assert backend.loaded is False
    assert backend.model_info["loaded"] is False


def test_12_missing_backend_does_not_crash_app():
    result = ThemeEngineV2(UnavailableEmbeddingBackend()).analyze(
        "Достаточно длинный текст для контролируемой проверки недоступного backend.")
    assert result.status == "unavailable"
    assert result.reason == "embedding backend not installed"
    assert result.engine_version == "v2-shadow"


def test_13_lexical_evidence_returns_lemmas_and_fragments():
    ontology = config_loader.load_theme_ontology()
    extractor = LexicalThemeEvidenceExtractor(
        ontology, lemmatizer=lambda word: word.lower().replace("ё", "е"))
    text = "Суд рассмотрел иск и вынес приговор."
    evidence = extractor.analyze("law", text, base_offset=12)
    assert {"суд", "иск", "приговор"} <= set(evidence.matched_lemmas)
    assert evidence.fragments
    assert all(fragment.start >= 12 for fragment in evidence.fragments)


def test_14_one_keyword_does_not_force_dominant_theme(deterministic_engine):
    result = deterministic_engine.analyze("На столе лежал старый кодекс.")
    assert result.dominant_theme is None
    assert all(row.segment_support_count == 0 for row in result.themes)


def test_15_v2_supports_multiple_themes(deterministic_engine):
    text = (
        "Суд рассмотрел иск, изучил договор, доказательства и вынес приговор. "
        "Адвокат подготовил апелляционную жалобу.\n\n"
        "Компания получила прибыль от продажи товаров, пересмотрела бюджет, "
        "расходы, инвестиции и банковский кредит.")
    result = deterministic_engine.analyze(text)
    supported = {row.theme_id for row in result.themes
                 if row.segment_support_count > 0}
    assert {"law", "economics"} <= supported


def test_16_coverage_is_bounded(deterministic_engine):
    result = deterministic_engine.analyze(
        "Команда выиграла матч и забила гол на стадионе. "
        "Тренер похвалил игроков после финала.")
    assert all(0.0 <= row.coverage <= 1.0 for row in result.themes)


def test_17_semantic_score_is_not_named_probability(deterministic_engine):
    result = deterministic_engine.analyze(
        "Программа отправила данные на сервер через сетевой протокол.")
    field_names = {field.name for field in dataclasses.fields(result.themes[0])}
    assert "probability" not in field_names
    assert result.parameters["score_semantics"] == \
        "similarity_and_ranking_not_probability"


def test_18_expert_value_is_never_assigned(deterministic_engine):
    result = deterministic_engine.analyze(
        "Президент и парламент обсуждали выборы, власть и государственную реформу.")
    assert all(row.expert_identification_value is None for row in result.themes)


def test_19_experimental_theme_not_accepted_method_feature():
    ontology = {
        "experimental": {
            "id": "experimental", "label": "Экспериментальная",
            "method_status": "EXPERIMENTAL", "method_feature_id": None,
            "keywords": ["маркер", "сигнал"], "active": True,
        }
    }
    prototypes = {
        "experimental": {
            "provenance": "engineered_for_v2",
            "prototypes": ["описание экспериментального сигнала"] * 1,
        }
    }
    result = ThemeEngineV2(
        DeterministicEmbeddingBackend(), ontology=ontology,
        prototype_config=prototypes,
        lemmatizer=lambda word: word.lower()).analyze(
            "Маркер и сигнал появились в наблюдаемом тексте.")
    assert result.themes[0].method_status == "EXPERIMENTAL"
    assert result.themes[0].method_feature_id is None
    assert result.themes[0].expert_identification_value is None


def test_20_v2_result_contains_evidence(deterministic_engine):
    result = deterministic_engine.analyze(
        "Команда выиграла матч, игрок забил гол, а тренер изменил тактику.")
    sports = next(row for row in result.themes if row.theme_id == "sports")
    assert sports.evidence
    assert sports.evidence[0].prototype_matches
    assert sports.evidence[0].prototype_max >= sports.evidence[0].prototype_top3_mean
    assert sports.evidence[0].prototype_top3_mean >= sports.evidence[0].prototype_top5_mean
    assert sports.evidence[0].lexical_match_count >= 1
    assert sports.evidence[0].start < sports.evidence[0].end


def test_21_dominant_theme_is_first_supported_rank(deterministic_engine):
    result = deterministic_engine.analyze(
        "Команда выиграла матч, игрок забил гол на стадионе, тренер праздновал финал.")
    expected = next(row for row in result.themes if row.segment_support_count > 0)
    assert result.dominant_theme == expected


def test_22_shadow_comparison_works(deterministic_engine):
    text = "Команда выиграла матч, игрок забил гол на стадионе."
    lemmas = ["команда", "выиграть", "матч", "игрок", "забить", "гол", "стадион"]
    shadow = ThemeEngine(legacy_theme.ThematicEngine()).analyze_shadow(
        text, lemmas, v2_engine=deterministic_engine)
    assert set(shadow) == {"v1", "v2", "v2_error", "comparison"}
    assert "agreement" in shadow["comparison"]
    assert shadow["v1"] is not None


def test_23_development_evaluator_runs():
    report = evaluate(load_fixtures(include_hard=False)[:4],
                      backend=DeterministicEmbeddingBackend())
    assert report["fixture_count"] == 4
    assert report["v1"] is not None
    assert report["v2"] is not None
    assert "VALIDATION" not in report["v2_label"]


def test_24_hard_cases_do_not_crash(deterministic_engine):
    hard_cases = json.loads((
        Path(__file__).parent / "fixtures" / "theme_v2" / "hard_cases.json"
    ).read_text(encoding="utf-8"))
    results = [deterministic_engine.analyze(row["text"]) for row in hard_cases]
    assert len(results) >= 10
    assert all(result.status == "ok" for result in results)


def test_25_empty_text_returns_controlled_result(deterministic_engine):
    result = deterministic_engine.analyze(" \n\n ")
    assert result.status == "empty"
    assert result.themes == ()
    assert result.dominant_theme is None


def test_26_very_short_text_returns_controlled_result(deterministic_engine):
    result = deterministic_engine.analyze("Матч закончился.")
    assert result.status == "ok"
    assert result.segment_count == 1


def test_27_deterministic_backend_is_stable():
    first = DeterministicEmbeddingBackend().encode(["одинаковый текст"])
    second = DeterministicEmbeddingBackend().encode(["одинаковый текст"])
    assert first == second


def test_28_model_metadata_is_recorded(deterministic_engine):
    result = deterministic_engine.analyze(
        "Сервер обработал данные, программа выполнила алгоритм и сохранила результат.")
    required = {
        "model_name", "model_revision", "tokenizer_revision",
        "library_version", "device", "normalization", "pooling",
        "inference_parameters",
    }
    assert required <= set(result.model_info)


def test_29_prototype_embeddings_are_cached():
    clear_prototype_embedding_cache()
    backend = DeterministicEmbeddingBackend()
    engine = ThemeEngineV2(backend)
    engine.analyze("Команда выиграла матч, игрок забил гол на стадионе.")
    calls_after_first = backend.encode_calls
    engine.analyze("Суд рассмотрел иск, договор и доказательства по делу.")
    # Второй вызов кодирует только новый segment; 10 банков prototypes берутся из cache.
    assert backend.encode_calls == calls_after_first + 1


def test_30_v2_version_is_shadow():
    assert THEME_ENGINE_V2_VERSION == "v2-shadow"
