"""Каркас авто-экстракторов признаков.

Экстрактор — функция ``(Feature, ExtractorContext) -> FeatureValue``, зарегистрированная
под именем (поле ``extractor`` в реестре). Несколько признаков могут использовать один
экстрактор: внутри он различает их по ``feature.id``. Тяжёлые вычисления по документу
кэшируются в контексте (один раз на текст).
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from aved.core.models import Feature, FeatureValue
from aved.core.registry import find_data_dir
from aved.nlp.backend import Document

ExtractorFn = Callable[[Feature, "ExtractorContext"], FeatureValue]

_REGISTRY: dict[str, ExtractorFn] = {}


def register(name: str) -> Callable[[ExtractorFn], ExtractorFn]:
    def deco(fn: ExtractorFn) -> ExtractorFn:
        if name in _REGISTRY:
            raise ValueError(f"экстрактор {name!r} уже зарегистрирован")
        _REGISTRY[name] = fn
        return fn
    return deco


def get_extractor(name: str) -> ExtractorFn | None:
    return _REGISTRY.get(name)


def registered_names() -> set[str]:
    return set(_REGISTRY)


class ExtractorContext:
    """Контекст разбора одного текста: документ, каталог данных, кэш вычислений."""

    def __init__(self, doc: Document, data_dir: Path | None = None) -> None:
        self.doc = doc
        self.data_dir = data_dir or find_data_dir()
        self._cache: dict[str, object] = {}

    def cached(self, key: str, factory: Callable[[], object]) -> object:
        if key not in self._cache:
            self._cache[key] = factory()
        return self._cache[key]


def run(feature: Feature, ctx: ExtractorContext) -> FeatureValue | None:
    """Запустить экстрактор признака. None — если экстрактор не реализован/не задан."""
    if not feature.extractor:
        return None
    fn = _REGISTRY.get(feature.extractor)
    if fn is None:
        return None
    return fn(feature, ctx)


# --------------------------------------------------------------------------- #
#  Вспомогательные конструкторы FeatureValue
# --------------------------------------------------------------------------- #

def absent(feature: Feature, note: str = "") -> FeatureValue:
    return FeatureValue(feature_id=feature.id, present=False, source_kind="auto", note=note)


def rate_per_1000(count: int, word_count: int) -> float:
    return round(count / word_count * 1000, 2) if word_count else 0.0
