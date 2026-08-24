"""Экстракторы уровня НН: функциональный стиль, уровень языка, эмоциональность."""
from __future__ import annotations

import re

from aved.core.models import Feature, FeatureValue
from aved.features.extractors.base import ExtractorContext, absent, register
from aved.features.extractors.lexicon import _load_lexicon, count_matches

_DOUBLE_S = re.compile(r"\b[а-яё]+сс\b", re.IGNORECASE)
_SUPERLATIVE_DIALECT = re.compile(r"\b[а-яё]+ейше\b", re.IGNORECASE)


def _lex_rate(ctx: ExtractorContext, rel: str) -> float:
    alpha, phrases = _load_lexicon(str(ctx.data_dir / rel))
    hits, _ = count_matches(ctx, alpha, phrases)
    return hits / (ctx.doc.word_count() or 1) * 1000


def _verbal_noun_rate(ctx: ExtractorContext) -> float:
    n = sum(1 for t in ctx.doc.words
            if t.pos == "NOUN" and t.lemma.endswith(("ние", "нье", "тие", "ция")))
    return n / (ctx.doc.word_count() or 1) * 1000


def _style_scores(ctx: ExtractorContext) -> dict[str, float]:
    def compute() -> dict[str, float]:
        return {
            "official_business": _lex_rate(ctx, "lexicons/style/ob_stamps.txt")
            + _lex_rate(ctx, "lexicons/style/ob_substitutes.txt") + _verbal_noun_rate(ctx),
            "scientific": _lex_rate(ctx, "lexicons/thematic/science.txt") + _verbal_noun_rate(ctx),
            "publicistic": _lex_rate(ctx, "lexicons/style/pub_metaphor_stamps.txt")
            + _lex_rate(ctx, "lexicons/style/linking_verbs.txt"),
            "oratorical": _lex_rate(ctx, "lexicons/style/orat_pressure.txt")
            + _lex_rate(ctx, "lexicons/style/orat_generic.txt"),
            "colloquial": _lex_rate(ctx, "lexicons/style/coll_broad.txt"),
        }

    return ctx.cached("style_scores", compute)  # type: ignore[return-value]


def dominant_style(ctx: ExtractorContext) -> str | None:
    """Преобладающий функциональный стиль текста (или None, если индексы нулевые)."""
    scores = _style_scores(ctx)
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else None


@register("style_profile")
def style_profile(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    scores = _style_scores(ctx)
    key = feature.id.rsplit("_", 1)[-1]  # ...style_official_business -> business? нет
    mapping = {
        "nn.lang.style_official_business": "official_business",
        "nn.lang.style_scientific": "scientific",
        "nn.lang.style_publicistic": "publicistic",
        "nn.lang.style_oratorical": "oratorical",
        "nn.lang.style_colloquial": "colloquial",
    }
    style = mapping.get(feature.id)
    if style is None:
        return absent(feature, note="style_profile: неизвестный признак")
    score = round(scores[style], 2)
    dominant = scores[style] == max(scores.values()) and score > 0
    return FeatureValue(feature_id=feature.id, present=score >= 2.0, value=score,
                        source_kind="auto",
                        note=f"индекс стиля: {score}" + (" (преобладает)" if dominant else ""))


def _ttr(ctx: ExtractorContext) -> float:
    words = ctx.doc.words
    if not words:
        return 0.0
    return round(len({t.lemma for t in words}) / len(words), 3)


def _subord_ratio(ctx: ExtractorContext) -> float:
    sents = ctx.doc.sentences
    if not sents:
        return 0.0
    sub = sum(1 for s in sents if any(t.pos == "SCONJ" for t in s.tokens))
    return sub / len(sents)


def _avg_len(ctx: ExtractorContext) -> float:
    sents = ctx.doc.sentences
    return ctx.doc.word_count() / len(sents) if sents else 0.0


@register("language_level")
def language_level(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    avg, sub, ttr = _avg_len(ctx), _subord_ratio(ctx), _ttr(ctx)
    fid = feature.id
    if fid.endswith("school_level"):
        present, val, note = (avg < 12 and sub < 0.25), round(avg, 1), \
            f"ср. длина {avg:.1f}, доля СПП {sub:.2f}"
    elif fid.endswith("high_literacy"):
        present, val, note = ttr >= 0.55, ttr, f"лексическое разнообразие (TTR) {ttr}"
    elif fid.endswith("higher_humanities"):
        present, val, note = (avg >= 14 and sub >= 0.3), round(avg, 1), \
            f"ср. длина {avg:.1f}, доля СПП {sub:.2f}"
    else:
        return absent(feature, note="language_level: неизвестный признак")
    return FeatureValue(feature_id=fid, present=present, value=val,
                        source_kind="auto", note=note)


@register("emotionality")
def emotionality(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    marks = ctx.doc.text.count("!") + ctx.doc.text.count("?")
    emo = _lex_rate(ctx, "lexicons/lex/emotion.txt")
    rate = round(marks / (ctx.doc.word_count() or 1) * 1000 + emo, 2)
    return FeatureValue(feature_id=feature.id, present=rate >= 1.0, value=rate,
                        source_kind="auto", note=f"восклицаний/вопросов: {marks}; эмо-индекс: {rate}")


@register("foreign_interference")
def foreign_interference(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    hits = _DOUBLE_S.findall(ctx.doc.text)
    return FeatureValue(feature_id=feature.id, present=len(hits) > 0, value=len(hits),
                        source_kind="auto", note=f"подозрительных удвоений «сс»: {len(hits)}")


@register("dialect_markers")
def dialect_markers(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    hits = _SUPERLATIVE_DIALECT.findall(ctx.doc.text)
    return FeatureValue(feature_id=feature.id, present=len(hits) > 0, value=len(hits),
                        source_kind="auto", note=f"диалектных форм «-ейше-»: {len(hits)}")
