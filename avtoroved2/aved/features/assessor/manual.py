"""Ручной оценщик-заглушка: качественные признаки отмечает эксперт сам.

Используется, когда LLM недоступна или нежелательна. Возвращает None — признак
остаётся неоценённым и предъявляется эксперту в интерфейсе для ручной отметки.
"""
from __future__ import annotations

from aved.core.models import Feature, FeatureValue
from aved.features.extractors.base import ExtractorContext


class ManualAssessor:
    def assess(self, feature: Feature, ctx: ExtractorContext) -> FeatureValue | None:
        return None

    def assess_batch(
        self, features: list[Feature], ctx: ExtractorContext
    ) -> dict[str, FeatureValue]:
        return {}
