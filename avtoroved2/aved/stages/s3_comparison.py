"""Стадия S3 — сравнительное исследование (методика, с. 84).

Модели навыка спорного текста и образцов сопоставляются по каждому уровню
индивидуализации. Результат — два комплекса признаков: совпадающие и различающиеся.
Образцы агрегируются (признак относится к проверяемому лицу, если устойчиво
проявляется в образцах).
"""
from __future__ import annotations

import math

from aved.core.models import (
    Comparison,
    Feature,
    FeatureValue,
    Level,
    LevelComparison,
    NavykModel,
)
from aved.core.registry import Registry

_STYLE_KEYS = ("official_business", "scientific", "publicistic", "oratorical", "colloquial")


def aggregate_samples(models: list[NavykModel], min_fraction: float = 0.5) -> NavykModel:
    """Свести образцы к одной модели: признак присутствует, если устойчиво в образцах."""
    if not models:
        return NavykModel(object_id="samples")
    if len(models) == 1:
        m = models[0]
        return NavykModel(object_id="samples", values=dict(m.values))

    threshold = max(1, math.ceil(len(models) * min_fraction))
    all_ids = {fid for m in models for fid in m.values}
    agg = NavykModel(object_id="samples")
    for fid in all_ids:
        present_vals = [m.values[fid] for m in models if fid in m.values and m.values[fid].present]
        present = len(present_vals) >= threshold
        nums = [v.value for v in present_vals if isinstance(v.value, (int, float))]
        value = round(sum(nums) / len(nums), 3) if nums else None
        evidence = list(present_vals[0].evidence) if present_vals else []
        agg.values[fid] = FeatureValue(
            feature_id=fid, present=present, value=value, source_kind="aggregate",
            evidence=evidence,
            # устойчивость на уровне образцов = проявление в большинстве из них
            stable=present,
            note=f"в образцах: {len(present_vals)}/{len(models)}",
        )
    return agg


def dominant_style(model: NavykModel) -> str | None:
    best, best_val = None, -1.0
    for key in _STYLE_KEYS:
        v = model.values.get(f"nn.lang.style_{key}")
        if v and v.present and isinstance(v.value, (int, float)) and v.value > best_val:
            best, best_val = key, float(v.value)
    return best


def _thinking_conflict(disputed: NavykModel, sample: NavykModel) -> bool:
    def present(m, fid):
        v = m.values.get(fid)
        return bool(v and v.present)
    d_cat = present(disputed, "nn.psy.categorical_thinking")
    d_sit = present(disputed, "nn.psy.situational_thinking")
    s_cat = present(sample, "nn.psy.categorical_thinking")
    s_sit = present(sample, "nn.psy.situational_thinking")
    return (d_cat and s_sit and not s_cat) or (d_sit and s_cat and not d_cat)


def compare(disputed: NavykModel, sample: NavykModel, registry: Registry) -> Comparison:
    levels = {lv: LevelComparison(level=lv) for lv in Level}

    for feature in registry:
        d = disputed.values.get(feature.id)
        s = sample.values.get(feature.id)
        dp = bool(d and d.present)
        sp = bool(s and s.present)
        # различие засчитываем только по устойчиво проявленному признаку (методика
        # требует устойчивости): одиночное (неустойчивое) употребление — не сигнал
        d_stable = bool(d and d.present and d.stable)
        s_stable = bool(s and s.present and s.stable)

        lc = levels[feature.level]
        if dp and sp:
            lc.matching.append(feature.id)
            if feature.high_info:
                lc.matching_high += 1
        elif (d_stable and not sp) or (s_stable and not dp):
            lc.differing.append(feature.id)
            if feature.high_info:
                lc.differing_high += 1
        # иначе (оба отсутствуют, либо одностороннее неустойчивое проявление) — пропуск

    # конфликт на уровне НН (разные наборы норм)
    ds, ss = dominant_style(disputed), dominant_style(sample)
    reason = ""
    conflict = False
    if ds and ss and ds != ss:
        conflict = True
        reason = f"преобладающий стиль различается: спорный — {ds}, образцы — {ss}"
    elif _thinking_conflict(disputed, sample):
        conflict = True
        reason = "различается тип мышления (категориальный/ситуативный)"

    return Comparison(
        disputed_id=disputed.object_id,
        sample_id=sample.object_id,
        levels=levels,
        nn_norm_conflict=conflict,
        nn_conflict_reason=reason,
    )
