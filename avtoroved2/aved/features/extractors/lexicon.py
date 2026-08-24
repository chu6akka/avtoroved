"""Экстрактор совпадений со словарём-маркером (lexicon_match, thematic).

Покрывает множество признаков НС/НСВ, опирающихся на закрытые классы слов и штампы
(вводные слова, субституты, сокращения, тематическая лексика и т. п.).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from aved.core.models import Evidence, Feature, FeatureValue
from aved.features.extractors.base import (
    ExtractorContext,
    absent,
    rate_per_1000,
    register,
)


@lru_cache(maxsize=256)
def _load_lexicon(path_str: str) -> tuple[frozenset[str], tuple[str, ...]]:
    """Вернуть (однословные_алфавитные, фразы_и_сокращения) из файла словаря."""
    p = Path(path_str)
    if not p.exists():
        return frozenset(), tuple()
    alpha: set[str] = set()
    other: list[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        term = line.strip().lower()
        if not term or term.startswith("#"):
            continue
        if term.isalpha():
            alpha.add(term)
        else:
            other.append(term)
    return frozenset(alpha), tuple(other)


def count_matches(
    ctx: ExtractorContext, alpha: frozenset[str], phrases: tuple[str, ...]
) -> tuple[int, list[Evidence]]:
    doc = ctx.doc
    hits = 0
    evidence: list[Evidence] = []
    for tok in doc.words:
        if tok.lemma in alpha or tok.text.lower() in alpha:
            hits += 1
            if len(evidence) < 6:
                evidence.append(Evidence(tok.text, tok.start, tok.stop))
    if phrases:
        low = doc.text.lower()
        for phrase in phrases:
            start = 0
            while (idx := low.find(phrase, start)) >= 0:
                hits += 1
                if len(evidence) < 6:
                    evidence.append(Evidence(doc.text[idx:idx + len(phrase)], idx, idx + len(phrase)))
                start = idx + len(phrase)
    return hits, evidence


def _lexicon_value(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    if not feature.lexicon:
        return absent(feature, note="словарь не задан")
    path = ctx.data_dir / feature.lexicon
    alpha, phrases = _load_lexicon(str(path))
    if not alpha and not phrases:
        return absent(feature, note=f"словарь недоступен: {feature.lexicon}")
    hits, evidence = count_matches(ctx, alpha, phrases)
    return FeatureValue(
        feature_id=feature.id,
        present=hits > 0,
        value=rate_per_1000(hits, ctx.doc.word_count()),
        evidence=evidence,
        source_kind="auto",
        note=f"совпадений: {hits}",
    )


@register("lexicon_match")
def lexicon_match(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    return _lexicon_value(feature, ctx)


_THEME_THRESHOLD = 0.35


@register("thematic")
def thematic(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    """Тематика: точное совпадение по словарю + семантическая близость (Navec)."""
    base = _lexicon_value(feature, ctx)
    if not feature.lexicon:
        return base
    try:
        from aved.nlp.semantic import theme_score

        sim = theme_score(ctx, str(ctx.data_dir / feature.lexicon))
    except Exception:
        return base  # семантика недоступна — остаётся точное совпадение
    present = base.present or sim >= _THEME_THRESHOLD
    return FeatureValue(
        feature_id=feature.id,
        present=present,
        value=round(sim, 3),
        evidence=base.evidence,
        source_kind="auto",
        note=f"{base.note}; семант. близость {sim:.2f}",
    )
