"""
analyzer/thematic_engine.py — Тематическая атрибуция текста.

Методология: TF-IDF + косинусное сходство с эталонными центроидами доменов.
  — Manning C.D., Raghavan P., Schütze H. «Introduction to Information Retrieval» (2008)
  — Salton G., McGill M.J. «Introduction to Modern Information Retrieval» (1983)

Алгоритм:
  1. Загружаются JSON-словари для каждого домена (data/thematic/*.json).
  2. Вычисляется IDF(w) = log((N+1) / (df(w)+1)) по коллекции доменов.
  3. Для входного текста строится TF-IDF вектор: TF(w) * IDF(w).
  4. Для каждого домена строится единичный центроид — нормированный вектор
     из IDF-весов слов домена.
  5. Косинусное сходство text_vector · domain_centroid определяет
     степень принадлежности к домену.

Использование:
    from analyzer.thematic_engine import get as get_thematic
    engine = get_thematic()
    result = engine.analyze(lemmas)   # lemmas: List[str]
"""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ── Метаданные доменов ──────────────────────────────────────────────────────

DOMAIN_META: Dict[str, dict] = {
    "law":        {"label": "Юридическая / правовая",          "color": "#1565c0"},
    "medicine":   {"label": "Медицинская / фармацевтика",       "color": "#c62828"},
    "it":         {"label": "IT / цифровые технологии",        "color": "#00695c"},
    "economics":  {"label": "Экономика / финансы",              "color": "#f57f17"},
    "military":   {"label": "Военная / силовые структуры",      "color": "#4e342e"},
    "science":    {"label": "Научная / академическая",          "color": "#6a1b9a"},
    "religion":   {"label": "Религиозная / духовная",           "color": "#880e4f"},
    "politics":   {"label": "Политическая / государственная",   "color": "#1a237e"},
    "sports":     {"label": "Спортивная / физкультура",         "color": "#2e7d32"},
    "everyday":   {"label": "Бытовая / разговорная",            "color": "#37474f"},
}

_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "thematic",
)

# Порог косинусного сходства для включения домена в «топ».
# Значение подобрано экспериментально на типичных русских текстах.
_COS_THRESHOLD = 0.02
_MAX_TOP = 3


# ── Датакласс результата ────────────────────────────────────────────────────

@dataclass
class DomainScore:
    key:        str    # "law", "medicine", …
    label:      str
    color:      str
    cosine:     float  # косинусное сходство [0..1]
    tf_idf_sum: float  # сырая сумма TF-IDF (для отладки)
    match_count: int   # уникальных совпадающих лемм
    examples:   List[str] = field(default_factory=list)


@dataclass
class ThematicResult:
    scores:      List[DomainScore]   # все домены, отсортированы по убыванию cosine
    top_domains: List[DomainScore]   # домены выше порога (max 3)
    total_words: int = 0
    matched_words: int = 0           # слов с совпадением хотя бы в 1 домене


# ── Движок ─────────────────────────────────────────────────────────────────

class ThematicEngine:
    """
    TF-IDF косинусный анализатор тематической принадлежности.

    Центроид домена D = нормированный вектор IDF-весов его слов:
        centroid[w] = IDF(w) / ||domain_idf_vector||

    TF-IDF вектор текста T:
        text_vec[w] = TF(w, T) * IDF(w)

    Косинусное сходство:
        cos(T, D) = (text_vec · centroid) / ||text_vec||
    """

    def __init__(self):
        # word → set of domain keys containing this word
        self._word_domains: Dict[str, set] = {}
        # domain key → frozenset of lemmas
        self._domain_vocab: Dict[str, frozenset] = {}
        # domain key → centroid vector (word → idf_normalized_weight)
        self._centroids: Dict[str, Dict[str, float]] = {}
        self._loaded = False

    # ── Загрузка ──────────────────────────────────────────────────────────

    def load(self) -> None:
        if self._loaded:
            return

        raw: Dict[str, List[str]] = {}
        for domain in DOMAIN_META:
            path = os.path.join(_DATA_DIR, f"{domain}.json")
            if not os.path.exists(path):
                raw[domain] = []
                continue
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                raw[domain] = [w.lower().strip() for w in data if isinstance(w, str)]
            else:
                raw[domain] = [w.lower().strip() for w in data.keys()]

        # Заморозить словари доменов
        self._domain_vocab = {d: frozenset(words) for d, words in raw.items()}

        # Подсчёт df(w): сколько доменов содержат слово
        for domain, words in raw.items():
            for w in words:
                if w not in self._word_domains:
                    self._word_domains[w] = set()
                self._word_domains[w].add(domain)

        # Вычислить IDF и построить центроиды
        N = len(DOMAIN_META)
        for domain, words in raw.items():
            if not words:
                self._centroids[domain] = {}
                continue
            vec: Dict[str, float] = {}
            for w in words:
                df = len(self._word_domains.get(w, {1}))
                idf = math.log((N + 1) / (df + 1)) + 1.0  # smooth IDF
                vec[w] = idf
            # Нормировать центроид до единичного вектора
            norm = math.sqrt(sum(v * v for v in vec.values()))
            if norm > 0:
                self._centroids[domain] = {w: v / norm for w, v in vec.items()}
            else:
                self._centroids[domain] = {}

        self._loaded = True

    # ── Анализ ────────────────────────────────────────────────────────────

    def analyze(self, lemmas: List[str]) -> ThematicResult:
        """
        Args:
            lemmas: список лемм (нижний регистр), полученных из
                    StanzaBackend или spaCy токенизатора.
        """
        if not self._loaded:
            self.load()

        lemmas_lower = [l.lower() for l in lemmas if l.strip()]
        total = len(lemmas_lower)
        if total == 0:
            return ThematicResult(scores=[], top_domains=[], total_words=0)

        N = len(DOMAIN_META)

        # ── TF-IDF вектор текста ──────────────────────────────────────
        tf_counts = Counter(lemmas_lower)
        text_vec: Dict[str, float] = {}
        for w, cnt in tf_counts.items():
            if w not in self._word_domains:
                continue  # слово не в ни одном домене — пропустить
            tf = cnt / total
            df = len(self._word_domains[w])
            idf = math.log((N + 1) / (df + 1)) + 1.0
            text_vec[w] = tf * idf

        text_norm = math.sqrt(sum(v * v for v in text_vec.values()))

        # Слов, найденных хотя бы в одном домене
        matched_words = len(set(text_vec.keys()))

        # ── Косинусное сходство с каждым центроидом ───────────────────
        scores: List[DomainScore] = []
        for domain, meta in DOMAIN_META.items():
            centroid = self._centroids.get(domain, {})
            if not centroid:
                scores.append(DomainScore(
                    key=domain, label=meta["label"], color=meta["color"],
                    cosine=0.0, tf_idf_sum=0.0, match_count=0))
                continue

            # Скалярное произведение text_vec · centroid
            dot = sum(text_vec.get(w, 0.0) * c for w, c in centroid.items())
            cosine = dot / text_norm if text_norm > 0 else 0.0

            # Сырая сумма TF-IDF для отладки
            tf_idf_sum = sum(text_vec.get(w, 0.0) for w in centroid)

            # Примеры совпадений (слова из текста в словаре домена)
            vocab = self._domain_vocab.get(domain, frozenset())
            examples = [w for w in tf_counts if w in vocab]
            # Сортировать примеры по TF-IDF весу (самые значимые первыми)
            examples.sort(key=lambda w: -text_vec.get(w, 0.0))

            scores.append(DomainScore(
                key=domain,
                label=meta["label"],
                color=meta["color"],
                cosine=round(cosine, 6),
                tf_idf_sum=round(tf_idf_sum, 4),
                match_count=len(examples),
                examples=examples[:8],
            ))

        scores.sort(key=lambda s: -s.cosine)

        # ── Топ-домены выше порога ────────────────────────────────────
        if scores:
            best = scores[0].cosine
            threshold = max(_COS_THRESHOLD, best * 0.25)
            top = [s for s in scores if s.cosine >= threshold][:_MAX_TOP]
        else:
            top = []

        return ThematicResult(
            scores=scores,
            top_domains=top,
            total_words=total,
            matched_words=matched_words,
        )

    def invalidate(self) -> None:
        """Сбросить кэш (например, после обновления словарей)."""
        self._word_domains.clear()
        self._domain_vocab.clear()
        self._centroids.clear()
        self._loaded = False


# ── Синглтон ───────────────────────────────────────────────────────────────

_instance: Optional[ThematicEngine] = None


def get() -> ThematicEngine:
    global _instance
    if _instance is None:
        _instance = ThematicEngine()
    return _instance
