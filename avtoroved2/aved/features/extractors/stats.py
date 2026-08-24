"""Статистические экстракторы (длина предложений, объём изложения)."""
from __future__ import annotations

from aved.core.models import Feature, FeatureValue
from aved.features.extractors.base import ExtractorContext, absent, register

# Пороги средней длины предложения (в словах) для лаконичности/многословности.
_LACONIC_MAX = 9.0
_VERBOSE_MIN = 22.0


def _avg_sentence_len(ctx: ExtractorContext) -> float:
    def compute() -> float:
        sents = ctx.doc.sentences
        if not sents:
            return 0.0
        return round(ctx.doc.word_count() / len(sents), 2)

    return ctx.cached("avg_sentence_len", compute)  # type: ignore[return-value]


@register("brevity")
def brevity(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    avg = _avg_sentence_len(ctx)
    fid = feature.id
    if fid.endswith("laconic"):
        present, note = 0 < avg <= _LACONIC_MAX, f"средняя длина предложения: {avg} слов"
    elif fid.endswith("verbose"):
        present, note = avg >= _VERBOSE_MIN, f"средняя длина предложения: {avg} слов"
    else:
        return absent(feature, note="brevity: неизвестный признак")
    return FeatureValue(feature_id=fid, present=present, value=avg,
                        source_kind="auto", note=note)
