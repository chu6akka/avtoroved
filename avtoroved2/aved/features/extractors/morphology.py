"""Морфологические экстракторы (по pos/feats/леммам)."""
from __future__ import annotations

from aved.core.models import Evidence, Feature, FeatureValue
from aved.features.extractors.base import ExtractorContext, rate_per_1000, register

_VERBAL_NOUN_SUFFIXES = ("ние", "нье", "тие", "ция")
_NEG_VERBAL_NOUN_SUFFIXES = ("ние", "нье", "тие", "ция", "ка")
_EVAL_SUFFIXES = ("енький", "онький", "оватый", "еватый", "ишка", "ушка", "юшка", "ёшка")


def _collect(ctx: ExtractorContext, predicate) -> tuple[int, list[Evidence]]:
    hits, evidence = 0, []
    for tok in ctx.doc.words:
        if predicate(tok):
            hits += 1
            if len(evidence) < 6:
                evidence.append(Evidence(tok.text, tok.start, tok.stop))
    return hits, evidence


def _value(feature: Feature, ctx: ExtractorContext, predicate, label: str) -> FeatureValue:
    hits, evidence = _collect(ctx, predicate)
    return FeatureValue(
        feature_id=feature.id,
        present=hits > 0,
        value=rate_per_1000(hits, ctx.doc.word_count()),
        evidence=evidence,
        source_kind="auto",
        note=f"{label}: {hits}",
    )


@register("verbal_nouns")
def verbal_nouns(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    pred = lambda t: t.pos == "NOUN" and t.lemma.endswith(_VERBAL_NOUN_SUFFIXES)
    return _value(feature, ctx, pred, "отглагольных сущ.")


@register("neg_verbal_nouns")
def neg_verbal_nouns(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    pred = lambda t: (
        t.pos == "NOUN"
        and t.lemma.startswith("не")
        and t.lemma.endswith(_NEG_VERBAL_NOUN_SUFFIXES)
    )
    return _value(feature, ctx, pred, "сущ. с «не-»")


@register("reflexive_verbs")
def reflexive_verbs(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    pred = lambda t: t.pos == "VERB" and t.lemma.endswith(("ся", "сь"))
    return _value(feature, ctx, pred, "глаголов на «-ся»")


@register("short_form_predicate")
def short_form_predicate(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    pred = lambda t: t.feats.get("Variant") == "Short" or "ADJS" in t.pm_tag or "PRTS" in t.pm_tag
    return _value(feature, ctx, pred, "кратких форм")


@register("subjective_eval_suffixes")
def subjective_eval_suffixes(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    pred = lambda t: t.pos in ("NOUN", "ADJ") and t.lemma.endswith(_EVAL_SUFFIXES)
    return _value(feature, ctx, pred, "слов с оценочными суффиксами")
