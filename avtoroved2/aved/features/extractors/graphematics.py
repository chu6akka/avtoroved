"""Графематические экстракторы (регулярные выражения по тексту)."""
from __future__ import annotations

import re

from aved.core.models import Evidence, Feature, FeatureValue
from aved.features.extractors.base import ExtractorContext, rate_per_1000, register
from aved.features.extractors.lexicon import _load_lexicon, count_matches

_INITIAL_ABBR = re.compile(r"\b[А-ЯЁ]{2,}\b")
# Сокращения: составные с точками («т. е.», «г.г.») или с дефисом («р-н», «м-ц»).
# Одиночное «слово.» намеренно не ловим — это чаще конец предложения (ловится словарём).
_GRAPHIC_ABBR = re.compile(r"\b[а-яё]{1,4}\.\s?[а-яё]{1,4}\.|\b[а-яё]{1,4}-[а-яё]{1,3}\b")


def _regex_value(feature: Feature, ctx: ExtractorContext, pattern: re.Pattern, label: str) -> FeatureValue:
    matches = list(pattern.finditer(ctx.doc.text))
    ev = [Evidence(m.group(), m.start(), m.end()) for m in matches[:6]]
    return FeatureValue(
        feature_id=feature.id, present=len(matches) > 0,
        value=rate_per_1000(len(matches), ctx.doc.word_count()),
        evidence=ev, source_kind="auto", note=f"{label}: {len(matches)}",
    )


@register("initial_abbr")
def initial_abbr(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    return _regex_value(feature, ctx, _INITIAL_ABBR, "инициальных аббревиатур")


@register("graphic_abbr")
def graphic_abbr(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    """Графические сокращения: словарь (если задан) + общий шаблон сокращений."""
    matches = list(_GRAPHIC_ABBR.finditer(ctx.doc.text))
    hits = len(matches)
    evidence = [Evidence(m.group(), m.start(), m.end()) for m in matches[:6]]
    if feature.lexicon:
        alpha, phrases = _load_lexicon(str(ctx.data_dir / feature.lexicon))
        lex_hits, lex_ev = count_matches(ctx, alpha, phrases)
        hits += lex_hits
        evidence = (lex_ev + evidence)[:6]
    return FeatureValue(
        feature_id=feature.id, present=hits > 0,
        value=rate_per_1000(hits, ctx.doc.word_count()),
        evidence=evidence, source_kind="auto", note=f"сокращений: {hits}",
    )


@register("sentence_initial_marker")
def sentence_initial_marker(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    """Слово-связка в начале предложения: «поэтому» / «вот» как средство связи."""
    target = "поэтому" if feature.id.endswith("poetomu_link") else "вот"
    hits = 0
    evidence: list[Evidence] = []
    for sent in ctx.doc.sentences:
        words = sent.words
        if words and (words[0].lemma == target or words[0].text.lower() == target):
            hits += 1
            if len(evidence) < 6:
                evidence.append(Evidence(sent.text.strip()[:80], sent.start, sent.stop))
    return FeatureValue(feature_id=feature.id, present=hits > 0, value=hits,
                        evidence=evidence, source_kind="auto",
                        note=f"предложений, начатых с «{target}»: {hits}")


@register("punctuation_logic")
def punctuation_logic(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    """Двоеточие и тире как средство выражения логических отношений."""
    text = ctx.doc.text
    hits = text.count(":") + text.count("—") + text.count(" - ")
    return FeatureValue(feature_id=feature.id, present=hits > 0,
                        value=rate_per_1000(hits, ctx.doc.word_count()),
                        source_kind="auto", note=f"двоеточий/тире: {hits}")


@register("double_by")
def double_by(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    """Повторение частицы «бы» в пределах одного предложения."""
    flagged = 0
    evidence: list[Evidence] = []
    for sent in ctx.doc.sentences:
        by = [t for t in sent.tokens if t.text.lower() in ("бы", "б")]
        if len(by) >= 2:
            flagged += 1
            if len(evidence) < 6:
                evidence.append(Evidence(sent.text.strip()[:80], sent.start, sent.stop))
    return FeatureValue(
        feature_id=feature.id, present=flagged > 0, value=flagged,
        evidence=evidence, source_kind="auto", note=f"предложений с двойным «бы»: {flagged}",
    )
