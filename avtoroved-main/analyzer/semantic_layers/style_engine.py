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

    def analyze_shadow(self, text: str, *, parsed_tokens=None, v2_engine=None) -> dict:
        """Явно запустить V1 и V2; production ``analyze`` остаётся V1."""
        from analyzer import senti_engine
        from analyzer.semantic_layers.style_engine_v2 import (
            StyleEngineV2,
            compare_style_v1_v2,
        )

        v1_result = self.analyze(text)
        sentiment = senti_engine.get()
        sentiment.load()
        lemma_map = {
            token.text.lower(): token.lemma.lower()
            for token in (parsed_tokens or ())
            if getattr(token, "text", None) and getattr(token, "lemma", None)
        }
        sentiment_result = sentiment.analyze(text, lemma_map=lemma_map)
        engine = v2_engine or StyleEngineV2()
        v2_result = engine.analyze(
            text, parsed_tokens=parsed_tokens,
            stratification_result=v1_result,
            sentiment_result=sentiment_result)
        return {
            "v1": v1_result,
            "v2": v2_result,
            "comparison": compare_style_v1_v2(v1_result, v2_result),
        }


_instance: Optional[StyleEngine] = None


def get() -> StyleEngine:
    global _instance
    if _instance is None:
        _instance = StyleEngine()
    return _instance
