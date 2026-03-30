"""
analyzer/senti_engine.py — Анализ тональности текста по RuSentiLex 2017.

Источник: Loukachevitch N., Levchik A. (2016)
  «Creating a General Sentiment Lexicon for Russian»
  LREC-2016. Portorož, Slovenia.

Лексикон: data/senti/rusentilex.json
  lemma -> [sentiment, type, pos]
  sentiment: positive | negative | neutral
  type:      fact | opinion | feeling
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

_DICT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data", "senti", "rusentilex.json"
)

# ─── Метаданные ──────────────────────────────────────────────────────────────

SENTIMENTS = {
    "positive": {"label": "Позитивная",  "color": "#a6e3a1", "emoji": "😊"},
    "negative": {"label": "Негативная",  "color": "#f38ba8", "emoji": "😟"},
    "neutral":  {"label": "Нейтральная", "color": "#89b4fa", "emoji": "😐"},
}

TYPES = {
    "fact":    "Факт",
    "opinion": "Мнение",
    "feeling": "Чувство/эмоция",
    "":        "—",
}

# PoS из лексикона → читаемое название
_POS_NAMES = {
    "Noun": "существительное", "Adj": "прилагательное",
    "Verb": "глагол", "Adv": "наречие",
    "NG":   "именная группа",  "VG": "глагольная группа",
    "PG":   "предложная группа",
}


@dataclass
class SentiWord:
    form:      str   # словоформа из текста
    lemma:     str   # лемма
    sentiment: str   # positive / negative / neutral
    stype:     str   # fact / opinion / feeling
    pos:       str   # PoS из лексикона
    count:     int = 1


@dataclass
class SentiResult:
    total_words:    int
    scored_words:   int          # слов, найденных в лексиконе
    positive_count: int
    negative_count: int
    neutral_count:  int
    # Нормированный баланс: >0 = позитивный, <0 = негативный
    balance:        float        # (pos - neg) / scored
    # Индекс эмоциональности: (pos + neg) / total
    emotionality:   float
    # Доминирующая тональность
    dominant:       str
    # Слова по категориям
    positive_words: List[SentiWord] = field(default_factory=list)
    negative_words: List[SentiWord] = field(default_factory=list)
    neutral_words:  List[SentiWord] = field(default_factory=list)
    # Топ-10 самых частотных тональных слов
    top_positive:   List[SentiWord] = field(default_factory=list)
    top_negative:   List[SentiWord] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return self.total_words == 0

    @property
    def coverage_pct(self) -> float:
        return round(self.scored_words / self.total_words * 100, 1) if self.total_words else 0


# ─── Движок ──────────────────────────────────────────────────────────────────

class SentiEngine:
    """Движок анализа тональности по RuSentiLex."""

    def __init__(self):
        self._data: Dict[str, Tuple[str, str, str]] = {}
        self._loaded = False
        self._load_error: Optional[str] = None

    def load(self, path: str = _DICT_PATH) -> bool:
        if self._loaded:
            return True
        if not os.path.exists(path):
            self._load_error = f"Лексикон не найден: {path}"
            return False
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            self._data = {k: tuple(v) for k, v in raw.items()}
            self._loaded = True
            return True
        except Exception as e:
            self._load_error = str(e)
            return False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def size(self) -> int:
        return len(self._data)

    def lookup(self, lemma: str) -> Optional[Tuple[str, str, str]]:
        """Вернуть (sentiment, type, pos) или None."""
        return self._data.get(lemma.lower())

    def analyze(
        self,
        text: str,
        lemma_map: Optional[Dict[str, str]] = None,
    ) -> SentiResult:
        """
        lemma_map: {словоформа.lower() -> лемма.lower()} из Stanza/pymorphy3.
        Если None — используем форму как лемму (менее точно).
        """
        tokens = re.findall(r"[А-Яа-яЁё]+", text)
        if not tokens:
            return SentiResult(0, 0, 0, 0, 0, 0.0, 0.0, "neutral")

        # Агрегировать по словоформам
        form_count: Dict[str, int] = {}
        for t in tokens:
            tl = t.lower()
            form_count[tl] = form_count.get(tl, 0) + 1

        # Ищем по леммам
        found: Dict[str, SentiWord] = {}  # lemma -> SentiWord (агрегация по лемме)
        for form, cnt in form_count.items():
            lemma = (lemma_map or {}).get(form, form)
            entry = self.lookup(lemma) or self.lookup(form)
            if entry:
                sent, stype, pos = entry
                if lemma in found:
                    found[lemma].count += cnt
                else:
                    found[lemma] = SentiWord(
                        form=form, lemma=lemma,
                        sentiment=sent, stype=stype, pos=pos,
                        count=cnt,
                    )

        total = len(tokens)
        all_words = list(found.values())
        scored = sum(w.count for w in all_words)

        pos_words = [w for w in all_words if w.sentiment == "positive"]
        neg_words = [w for w in all_words if w.sentiment == "negative"]
        neu_words = [w for w in all_words if w.sentiment == "neutral"]

        pos_cnt = sum(w.count for w in pos_words)
        neg_cnt = sum(w.count for w in neg_words)
        neu_cnt = sum(w.count for w in neu_words)

        balance = (pos_cnt - neg_cnt) / scored if scored else 0.0
        emotionality = (pos_cnt + neg_cnt) / total if total else 0.0

        if pos_cnt > neg_cnt:
            dominant = "positive"
        elif neg_cnt > pos_cnt:
            dominant = "negative"
        else:
            dominant = "neutral"

        top_pos = sorted(pos_words, key=lambda w: -w.count)[:10]
        top_neg = sorted(neg_words, key=lambda w: -w.count)[:10]

        return SentiResult(
            total_words=total,
            scored_words=scored,
            positive_count=pos_cnt,
            negative_count=neg_cnt,
            neutral_count=neu_cnt,
            balance=round(balance, 3),
            emotionality=round(emotionality, 3),
            dominant=dominant,
            positive_words=sorted(pos_words, key=lambda w: -w.count),
            negative_words=sorted(neg_words, key=lambda w: -w.count),
            neutral_words=sorted(neu_words, key=lambda w: -w.count),
            top_positive=top_pos,
            top_negative=top_neg,
        )


# ─── Singleton ───────────────────────────────────────────────────────────────

_instance = SentiEngine()

def get() -> SentiEngine:
    return _instance
