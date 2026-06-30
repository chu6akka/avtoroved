"""Проверки целостности реестра признаков (НН/НС/НСВ)."""

from collections import Counter

import pytest

from aved.core.models import Level, Method, Significance
from aved.core.registry import Registry


@pytest.fixture(scope="module")
def reg() -> Registry:
    return Registry.load()


def test_registry_loads_and_is_large(reg):
    # реестр воспроизводит полную систему признаков методики
    assert len(reg) >= 200


def test_all_three_levels_present(reg):
    by_level = Counter(f.level for f in reg)
    assert by_level[Level.NN] >= 15
    assert by_level[Level.NS] >= 90
    assert by_level[Level.NSV] >= 90


def test_significance_grows_with_level(reg):
    # НН — низкая значимость, НСВ — высокая (методика: НН < НС < НСВ)
    assert all(f.significance is Significance.LOW for f in reg.by_level(Level.NN))
    assert all(f.significance is Significance.HIGH for f in reg.by_level(Level.NSV))


def test_high_info_are_nsv(reg):
    # высокоинформативные признаки — это уровень НСВ (порог ≥20 опирается на них)
    assert len(reg.high_info()) >= 90
    assert all(f.level is Level.NSV for f in reg.high_info())


def test_auto_features_have_extractor(reg):
    missing = [f.id for f in reg.by_method(Method.AUTO) if not f.extractor]
    assert not missing, f"auto-признаки без extractor: {missing}"


def test_every_feature_has_source(reg):
    missing = [f.id for f in reg if not f.source]
    assert not missing, f"признаки без ссылки на источник: {missing}"


def test_methods_distribution(reg):
    # должны быть представлены все способы установления признаков
    methods = {f.method for f in reg}
    assert methods == {Method.AUTO, Method.HYBRID, Method.LLM, Method.MANUAL}
