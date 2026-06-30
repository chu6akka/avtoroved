"""Сухие верифицируемые лингвистические показатели текста (без интерпретаций).

Только объективные, воспроизводимые величины: объёмы, длины, доли частей речи,
пунктуация, лексическое разнообразие. Никаких выводов и оценок — это делает эксперт.
"""
from __future__ import annotations

from collections import Counter

from aved.nlp.backend import Document


def _pct(n: int, total: int) -> float:
    return round(n / total * 100, 1) if total else 0.0


def _rate(n: int, total: int) -> float:
    return round(n / total * 1000, 1) if total else 0.0


def compute(doc: Document) -> dict[str, float | int]:
    words = doc.words
    sents = doc.sentences
    nw = len(words)
    ns = len(sents)
    toks = doc.tokens

    lemma_counts = Counter(t.lemma for t in words)
    uniq = len(lemma_counts)
    hapax = sum(1 for c in lemma_counts.values() if c == 1)
    pos = Counter(t.pos for t in words)
    punct = Counter(t.text for t in toks if not t.is_word)
    complex_sents = sum(1 for s in sents if any(t.pos == "SCONJ" for t in s.tokens))
    participles = sum(1 for t in words if t.feats.get("VerbForm") in ("Part", "Conv"))

    return {
        "Слов (знаменательных)": nw,
        "Предложений": ns,
        "Уникальных лемм": uniq,
        "Средняя длина предложения, слов": round(nw / ns, 1) if ns else 0.0,
        "Средняя длина слова, букв": round(sum(len(t.text) for t in words) / nw, 1) if nw else 0.0,
        "Лексическое разнообразие (TTR)": round(uniq / nw, 3) if nw else 0.0,
        "Доля hapax legomena, %": _pct(hapax, nw),
        "Существительные, %": _pct(pos.get("NOUN", 0) + pos.get("PROPN", 0), nw),
        "Глаголы, %": _pct(pos.get("VERB", 0), nw),
        "Прилагательные, %": _pct(pos.get("ADJ", 0), nw),
        "Наречия, %": _pct(pos.get("ADV", 0), nw),
        "Местоимения, %": _pct(pos.get("PRON", 0) + pos.get("DET", 0), nw),
        "Предлоги, %": _pct(pos.get("ADP", 0), nw),
        "Союзы, %": _pct(pos.get("CCONJ", 0) + pos.get("SCONJ", 0), nw),
        "Частицы, %": _pct(pos.get("PART", 0), nw),
        "Сложноподчинённые предложения, %": _pct(complex_sents, ns),
        "Причастия и деепричастия на 1000 слов": _rate(participles, nw),
        "Запятых на 1000 слов": _rate(punct.get(",", 0), nw),
        "Тире на 1000 слов": _rate(punct.get("—", 0) + punct.get("–", 0), nw),
        "Двоеточий на 1000 слов": _rate(punct.get(":", 0), nw),
        "Точек с запятой на 1000 слов": _rate(punct.get(";", 0), nw),
        "Восклицательных знаков": punct.get("!", 0),
        "Вопросительных знаков": punct.get("?", 0),
    }
