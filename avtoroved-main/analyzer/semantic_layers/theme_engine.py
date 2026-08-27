"""Тонкий адаптер над текущим TF-IDF тематическим анализатором."""
from __future__ import annotations

from typing import Optional

from analyzer import thematic_engine as legacy_theme
from analyzer.semantic_layers.contracts import (
    ThemeAnalysisResult,
    ThemeEvidence,
    ThemeScore,
)

THEME_ENGINE_VERSION = "v1"


class ThemeEngine:
    """Версионированный facade; ``analyze`` возвращает legacy-результат без изменений."""

    version = THEME_ENGINE_VERSION

    def __init__(self, legacy_engine=None):
        self._legacy = legacy_engine or legacy_theme.get()

    def analyze(self, lemmas: list[str]):
        return self._legacy.analyze(lemmas)

    def analyze_structured(self, lemmas: list[str]) -> ThemeAnalysisResult:
        """Представить тот же результат через будущий контракт, без нового scoring."""
        legacy_result = self.analyze(lemmas)
        themes = tuple(self._to_score(score) for score in legacy_result.scores)
        top_ids = {score.key for score in legacy_result.top_domains}
        dominant = next((score for score in themes if score.theme_id in top_ids), None)
        return ThemeAnalysisResult(
            themes=themes,
            dominant_theme=dominant,
            engine_version=self.version,
        )

    @staticmethod
    def _to_score(score) -> ThemeScore:
        evidence = tuple(
            ThemeEvidence(
                label=word,
                fragment=word,
                start=None,
                end=None,
                source="legacy_thematic_dictionary",
                score=score.cosine,
            )
            for word in score.examples
        )
        return ThemeScore(
            theme_id=score.key,
            label=score.label,
            score=score.cosine,
            evidence=evidence,
            metadata={
                "color": score.color,
                "tf_idf_sum": score.tf_idf_sum,
                "match_count": score.match_count,
            },
        )

    def invalidate(self) -> None:
        self._legacy.invalidate()


_instance: Optional[ThemeEngine] = None


def get() -> ThemeEngine:
    global _instance
    if _instance is None:
        _instance = ThemeEngine()
    return _instance
