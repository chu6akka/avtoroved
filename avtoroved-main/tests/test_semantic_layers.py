"""Patch A: новые facade/config сохраняют фактическое поведение legacy v1."""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from analyzer import corpus_manager
from analyzer import metrics as metrics_module
from analyzer import stratification_engine as legacy_style
from analyzer import thematic_engine as legacy_theme
from analyzer.semantic_layers import config_loader
from analyzer.semantic_layers.style_engine import STYLE_ENGINE_VERSION, StyleEngine
from analyzer.semantic_layers.theme_engine import THEME_ENGINE_VERSION, ThemeEngine
from analyzer.stanza_backend import TokenInfo
from protocol import feature_map
from protocol import profile


THEME_FIXTURES = {
    "empty": ([], [], 0, 0),
    "politics": (
        ["государство", "правительство", "президент", "парламент", "партия",
         "выборы", "голосование", "депутат", "министр", "реформа", "политика",
         "оппозиция", "власть", "суверенитет", "конституция"],
        [("politics", 0.197912, 15)], 15, 15),
    "military": (
        ["армия", "солдат", "офицер", "командир", "боевой", "приказ", "оружие",
         "операция", "оборона", "штаб", "батальон", "дивизия", "полк", "рота",
         "взвод"],
        [("military", 0.172781, 15), ("sports", 0.062556, 6)], 15, 15),
    "everyday": (
        ["дом", "семья", "ребёнок", "работа", "деньги", "еда", "одежда",
         "магазин", "транспорт", "город", "квартира", "машина", "муж", "жена",
         "мать"],
        [("everyday", 0.163103, 15)], 15, 15),
    "it": (
        ["программа", "компьютер", "сервер", "база", "данные", "алгоритм",
         "интерфейс", "сеть", "протокол", "разработчик", "код", "функция",
         "переменная", "класс", "объект"],
        [("it", 0.182734, 15), ("science", 0.059834, 6)], 15, 15),
    "law": (
        ["суд", "иск", "обвинение", "кодекс", "статья", "гражданин", "договор",
         "обязательство", "права", "закон", "приговор", "следователь", "прокурор",
         "адвокат", "обвиняемый"],
        [("law", 0.194729, 15)], 15, 15),
}

STYLE_FIXTURES = {
    "Это обычный нейтральный текст.": ({}, 4, 0.0),
    "Чувак, это движуха и тусовка.": ({"youth_jargon": 2}, 4, 0.5),
    "Сей град и оный государь.": ({"archaic": 2}, 4, 0.5),
    "Баской парень говорил давеча.": ({"dialectal": 2}, 4, 0.5),
    "Чувак сказал: сей град — полный абзац.": (
        {"youth_jargon": 1, "archaic": 1,
         "colloquial_reduced": 1, "general_jargon": 1}, 6, 2 / 3),
}


@pytest.fixture(autouse=True)
def no_user_theme_words(monkeypatch):
    """Снимки описывают поставляемые словари, а не локальные правки corpus.db."""
    monkeypatch.setattr(corpus_manager, "get_user_domain_words", lambda: {})


def _theme_summary(result):
    return [(row.key, row.cosine, row.match_count) for row in result.top_domains]


@pytest.mark.parametrize("_name,fixture", THEME_FIXTURES.items())
def test_current_thematic_snapshots(_name, fixture):
    lemmas, expected_top, total, matched = fixture
    result = legacy_theme.ThematicEngine().analyze(lemmas)
    assert _theme_summary(result) == expected_top
    assert (result.total_words, result.matched_words) == (total, matched)


@pytest.mark.parametrize("text,expected", STYLE_FIXTURES.items())
def test_current_stratification_snapshots(text, expected):
    counts, total, ratio = expected
    result = legacy_style.StratificationEngine().analyze(text)
    assert result.layer_counts == counts
    assert result.total_words == total
    assert result.marked_ratio == pytest.approx(ratio)


def test_theme_facade_returns_exact_legacy_result():
    lemmas = THEME_FIXTURES["politics"][0]
    legacy = legacy_theme.ThematicEngine()
    facade = ThemeEngine(legacy_theme.ThematicEngine())
    assert facade.analyze(lemmas) == legacy.analyze(lemmas)
    assert facade.version == THEME_ENGINE_VERSION == "v1"


def test_style_facade_returns_exact_legacy_result():
    text = "Чувак, это движуха и тусовка."
    legacy = legacy_style.StratificationEngine().analyze(text)
    adapted = StyleEngine(legacy_style.StratificationEngine()).analyze(text)
    assert adapted == legacy
    assert STYLE_ENGINE_VERSION == "v1"


def test_structured_theme_is_only_an_adapter():
    result = ThemeEngine(legacy_theme.ThematicEngine()).analyze_structured(
        THEME_FIXTURES["military"][0])
    assert result.engine_version == "v1"
    assert result.dominant_theme.theme_id == "military"
    assert result.dominant_theme.score == 0.172781


def test_current_candidate_feature_keys_are_frozen():
    expected = {
        "politics": "91564b01657c31de",
        "military": "3e2a3d80623a5d09",
        "everyday": "542f5ae9cc43d895",
        "it": "c69d774d39cc821c",
        "law": "e6452a70ec057eba",
    }
    engine = ThemeEngine(legacy_theme.ThematicEngine())
    for name, key in expected.items():
        candidates = profile.semantic_candidates(engine.analyze(THEME_FIXTURES[name][0]))
        assert [feature_map.candidate_key(row) for row in candidates] == [key]


def _dummy_metrics(text: str) -> dict:
    words = re.findall(r"[A-Za-zА-Яа-яЁё]+", text)
    tokens = [TokenInfo(word, word.lower(), "NOUN", "Существительное", "")
              for word in words]
    return metrics_module.calculate_metrics(tokens, text)


def test_current_style_markers_and_feature_keys_are_frozen():
    text = "Ну вот, на самом деле это так, потому что поэтому и однако."
    metrics = _dummy_metrics(text)
    assert StyleEngine.service_word_markers(metrics) == metrics["профиль_служебных_слов"]
    candidates = profile.stylistic_candidates(metrics, None)
    assert [(row["label"], row["value"], feature_map.candidate_key(row))
            for row in candidates] == [
        ("Стилевые маркеры: частицы", "2", "e407445ef6e1b7f8"),
        ("Стилевые маркеры: связки", "1", "a76fa1d12ff71c27"),
        ("Стилевые маркеры: союзы", "3", "0a84c0a0d86144d3"),
    ]


def test_current_leading_style_thresholds_are_frozen():
    reduced = SimpleNamespace(
        marked_ratio=0.04, layer_counts={"colloquial_reduced": 2})
    assert StyleEngine.leading_style({}, reduced) == "разговорно-сниженный"
    assert StyleEngine.leading_style(
        {"дополнительно": {"Средняя длина предложения (слов)": 18}}, None
    ) == "книжно-письменный"
    assert StyleEngine.leading_style({}, None) == "нейтральный / смешанный"


def test_theme_ontology_loads_and_ids_are_unique():
    config_loader.load_theme_ontology.cache_clear()
    ontology = config_loader.load_theme_ontology()
    assert len(ontology) == 10
    assert len({row["id"] for row in ontology.values()}) == len(ontology)


def test_all_prototypes_refer_to_known_themes():
    config_loader.load_theme_prototypes.cache_clear()
    prototypes = config_loader.load_theme_prototypes()
    assert set(prototypes) <= set(config_loader.load_theme_ontology())
    assert all(values == [] for values in prototypes.values())


def test_style_features_load_and_ids_are_unique():
    config_loader.load_style_features.cache_clear()
    features = config_loader.load_style_features()
    assert len(features) == 32
    assert len({row["id"] for row in features}) == len(features)


def test_theme_config_is_exact_legacy_dictionary_snapshot():
    ontology = config_loader.load_theme_ontology()
    assert set(ontology) == set(legacy_theme.DOMAIN_META)
    for theme_id, row in ontology.items():
        legacy_keywords = json.loads(
            (Path(legacy_theme._DATA_DIR) / f"{theme_id}.json").read_text("utf-8"))
        assert row["keywords"] == legacy_keywords
        assert row["label"] == legacy_theme.DOMAIN_META[theme_id]["label"]
        assert row["legacy_color"] == legacy_theme.DOMAIN_META[theme_id]["color"]
        assert row["legacy_threshold"] == legacy_theme._COS_THRESHOLD


def test_style_config_is_exact_legacy_indicator_snapshot():
    features = config_loader.load_style_features()
    metric_rows = [row for row in features
                   if row["source"] == "analyzer.metrics.STYLE_MARKERS"]
    expected_markers = [marker for markers in metrics_module.STYLE_MARKERS.values()
                        for marker in markers]
    assert [row["label"] for row in metric_rows] == expected_markers
    layer_rows = {row["id"].removeprefix("strat.layer."): row for row in features
                  if row["source"] == "analyzer.stratification_engine.LAYER_META"}
    assert set(layer_rows) == set(legacy_style.LAYER_META)
    assert all(layer_rows[key]["legacy_priority"] == meta["priority"]
               for key, meta in legacy_style.LAYER_META.items())


def test_unresolved_entries_are_valid_configuration():
    ontology = config_loader.load_theme_ontology()
    features = config_loader.load_style_features()
    assert all(row["method_status"] in {"METHOD", "AUXILIARY"}
               for row in ontology.values())
    assert any(row["style"] == "unresolved" for row in features)


def test_unknown_theme_with_unresolved_status_is_accepted(tmp_path, monkeypatch):
    payload = {
        "future_unknown": {
            "id": "future_unknown", "label": "Не установлено",
            "method_status": "UNRESOLVED", "method_feature_id": None,
            "keywords": [], "legacy_threshold": None, "active": False,
        }
    }
    (tmp_path / "theme_ontology.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(config_loader, "_data_dir", lambda: tmp_path)
    config_loader.load_theme_ontology.cache_clear()
    try:
        assert config_loader.load_theme_ontology()["future_unknown"]["method_status"] == \
            "UNRESOLVED"
    finally:
        config_loader.load_theme_ontology.cache_clear()


def test_missing_required_field_has_clear_error(tmp_path, monkeypatch):
    (tmp_path / "theme_ontology.json").write_text(
        json.dumps({"broken": {"id": "broken"}}), encoding="utf-8")
    monkeypatch.setattr(config_loader, "_data_dir", lambda: tmp_path)
    config_loader.load_theme_ontology.cache_clear()
    try:
        with pytest.raises(config_loader.SemanticConfigError,
                           match="отсутствуют обязательные поля"):
            config_loader.load_theme_ontology()
    finally:
        config_loader.load_theme_ontology.cache_clear()
