"""Стадия S2 — раздельное исследование (методика, с. 83–84).

Для каждого текста строится модель речемыслительного навыка: по реестру признаков
запускаются авто-экстракторы, а качественные признаки (при наличии оценщика) —
оценщик. Проверяется устойчивость признака (повторяемость в тексте).
"""
from __future__ import annotations

from typing import Protocol

from aved.core.models import FeatureValue, Method, NavykModel
from aved.core.registry import Registry
from aved.features.extractors import ExtractorContext, run
from aved.nlp.backend import Document


class Assessor(Protocol):
    """Оценщик качественных признаков (LLM/ручной)."""

    def assess(self, feature, ctx: ExtractorContext) -> FeatureValue | None: ...

    def assess_batch(self, features, ctx: ExtractorContext) -> dict[str, FeatureValue]: ...


def _mark_stability(fv: FeatureValue) -> None:
    """Устойчивость = повторяемость признака по тексту (эвристика для одного текста).

    Для оценок LLM повторяемость в тексте недоступна — используем уверенность модели.
    """
    if fv.source_kind == "llm":
        fv.stable = bool(fv.present and fv.confidence >= 0.7)
        return
    numeric = fv.value if isinstance(fv.value, (int, float)) else 0
    fv.stable = bool(fv.present and (len(fv.evidence) >= 2 or numeric >= 2))


def build_model(
    obj_id: str,
    doc: Document,
    registry: Registry,
    assessor: Assessor | None = None,
    data_dir=None,
) -> NavykModel:
    ctx = ExtractorContext(doc, data_dir)
    model = NavykModel(object_id=obj_id)
    pending: list = []  # качественные признаки для оценщика

    for feature in registry:
        fv: FeatureValue | None = None
        if feature.method in (Method.AUTO, Method.HYBRID):
            fv = run(feature, ctx)
        if fv is None:
            if assessor is not None and feature.method in (Method.LLM, Method.HYBRID):
                pending.append(feature)
            continue
        _mark_stability(fv)
        model.values[feature.id] = fv

    if pending and assessor is not None:
        assessed = assessor.assess_batch(pending, ctx)
        for fid, fv in assessed.items():
            if fv is None:
                continue
            _mark_stability(fv)
            model.values[fid] = fv

    return model
