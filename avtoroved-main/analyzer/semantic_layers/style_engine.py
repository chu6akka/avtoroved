"""Facade над независимыми legacy-producers стилевого блока."""
from __future__ import annotations

from typing import Optional

from analyzer import stratification_engine as legacy_stratification

STYLE_ENGINE_VERSION = "v1"


class StyleEngine:
    """Не объединяет legacy-оценки и не изменяет их веса или пороги."""

    version = STYLE_ENGINE_VERSION

    def __init__(self, stratification_engine=None):
        self._stratification = stratification_engine or legacy_stratification.get()

    def analyze(self, text: str):
        """Совместимый alias текущего ``StratificationEngine.analyze``."""
        return self._stratification.analyze(text)

    @staticmethod
    def service_word_markers(metrics: dict) -> dict:
        """Вернуть существующий metrics-профиль без пересчёта и преобразований."""
        return (metrics or {}).get("профиль_служебных_слов", {})

    @staticmethod
    def leading_style(metrics: dict, stratification_result) -> str:
        """Делегировать неизменённой legacy-эвристике comparison engine."""
        from analyzer.comparison_engine import _leading_style
        return _leading_style(metrics or {}, stratification_result)

    def reload(self) -> None:
        self._stratification.reload()


_instance: Optional[StyleEngine] = None


def get() -> StyleEngine:
    global _instance
    if _instance is None:
        _instance = StyleEngine()
    return _instance
