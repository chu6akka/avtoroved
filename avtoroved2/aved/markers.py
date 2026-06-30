"""Высокоточные лексические маркеры пластов лексики.

Маркер показывается ТОЛЬКО при реальном наличии в тексте и сопровождается примерами
(найденными словами) — это верифицируемо. Никаких вероятностных «качественных» оценок.
"""
from __future__ import annotations

import re

from aved.features.extractors.base import ExtractorContext
from aved.features.extractors.lexicon import _load_lexicon, count_matches
from aved.nlp.backend import Document

# (название, путь к словарю относительно data/, ссылка на методику)
_LEXICON_MARKERS = [
    ("Обсценная лексика", "lexicons/lex/obscene.txt", "с. 104"),
    ("Диалектизмы", "lexicons/lex/dialectisms.txt", "с. 89, 96"),
    ("Профессионализмы", "lexicons/lex/professionalisms.txt", "с. 89, 96"),
    ("Арготизмы", "lexicons/lex/argotisms.txt", "с. 96"),
    ("Штампы официально-делового стиля", "lexicons/style/ob_stamps.txt", "с. 98"),
    ("Канцелярские субституты", "lexicons/style/ob_substitutes.txt", "с. 98"),
    ("Вводные слова психологического давления", "lexicons/style/orat_pressure.txt", "с. 100"),
    ("Маркеры логики изложения", "lexicons/lex/logic_markers.txt", "с. 95"),
    ("Средства субъективной модальности", "lexicons/synt/modality_subjective.txt", "с. 101"),
]
_INITIAL_ABBR = re.compile(r"\b[А-ЯЁ]{2,}\b")


def scan(doc: Document, data_dir=None) -> list[dict]:
    """Список найденных маркеров: {name, count, rate, examples, source}. Только count>0."""
    ctx = ExtractorContext(doc, data_dir)
    nw = doc.word_count() or 1
    found: list[dict] = []

    for name, rel, src in _LEXICON_MARKERS:
        alpha, phrases = _load_lexicon(str(ctx.data_dir / rel))
        if not alpha and not phrases:
            continue
        hits, ev = count_matches(ctx, alpha, phrases)
        if hits > 0:
            examples = list(dict.fromkeys(e.quote for e in ev))[:5]
            found.append({
                "name": name, "count": hits, "rate": round(hits / nw * 1000, 1),
                "examples": examples, "source": src,
            })

    ab = _INITIAL_ABBR.findall(doc.text)
    if ab:
        found.append({
            "name": "Инициальные аббревиатуры", "count": len(ab),
            "rate": round(len(ab) / nw * 1000, 1),
            "examples": list(dict.fromkeys(ab))[:5], "source": "с. 99",
        })
    return found
