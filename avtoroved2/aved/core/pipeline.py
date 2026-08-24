"""Оркестрация стадий идентификационного исследования.

Текст каждого объекта разбирается один раз, затем последовательно проходят стадии:
S1 (пригодность) → S2 (раздельное) → S3 (сравнительное) → S4 (вывод).
S3/S4 подключаются в фазе 5.
"""
from __future__ import annotations

from dataclasses import dataclass

from aved.core.models import Comparison, NavykModel, ObjectText, Role, Verdict
from aved.core.registry import Registry
from aved.nlp.backend import Document, analyze
from aved.stages import s1_suitability, s2_separate, s3_comparison, s4_verdict


def analyze_objects(objects: list[ObjectText]) -> dict[str, Document]:
    """Разобрать тексты всех объектов (один раз на объект)."""
    return {obj.id: analyze(obj.text) for obj in objects}


def run_suitability(
    objects: list[ObjectText], docs: dict[str, Document], data_dir=None
) -> s1_suitability.SuitabilityReport:
    return s1_suitability.assess(objects, docs, data_dir=data_dir)


def run_separate(
    objects: list[ObjectText],
    docs: dict[str, Document],
    registry: Registry,
    assessor: s2_separate.Assessor | None = None,
    data_dir=None,
    only_suitable: bool = True,
) -> dict[str, NavykModel]:
    """Построить модель навыка для каждого пригодного объекта."""
    models: dict[str, NavykModel] = {}
    for obj in objects:
        if only_suitable and obj.suitable is False:
            continue
        if obj.id not in docs:  # защита от рассинхрона объектов и разбора
            continue
        models[obj.id] = s2_separate.build_model(
            obj.id, docs[obj.id], registry, assessor=assessor, data_dir=data_dir
        )
    return models


@dataclass
class IdentificationResult:
    suitability: s1_suitability.SuitabilityReport
    models: dict[str, NavykModel]
    comparison: Comparison | None
    verdict: Verdict | None


def identify(
    objects: list[ObjectText],
    registry: Registry,
    assessor: s2_separate.Assessor | None = None,
    data_dir=None,
) -> IdentificationResult:
    """Полный цикл идентификации: S1 → S2 → S3 → S4."""
    docs = analyze_objects(objects)
    suitability = run_suitability(objects, docs, data_dir=data_dir)
    models = run_separate(objects, docs, registry, assessor=assessor, data_dir=data_dir)

    disputed = [models[o.id] for o in objects if o.role is Role.DISPUTED and o.id in models]
    samples = [models[o.id] for o in objects if o.role is Role.SAMPLE and o.id in models]
    if not disputed or not samples:
        return IdentificationResult(suitability, models, None, None)

    disputed_agg = s3_comparison.aggregate_samples(disputed)
    disputed_agg.object_id = "disputed"
    sample_agg = s3_comparison.aggregate_samples(samples)
    comparison = s3_comparison.compare(disputed_agg, sample_agg, registry)
    verdict = s4_verdict.decide(comparison)
    return IdentificationResult(suitability, models, comparison, verdict)
