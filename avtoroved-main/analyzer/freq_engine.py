"""
analyzer/freq_engine.py — Анализ лексической частоты по НКРЯ.

Словарь: Ляшевская О.Н., Шаров С.А. «Частотный словарь современного
русского языка (на материалах НКРЯ)». М.: Азбуковник, 2009.

Частотные диапазоны:
  nucleus   — ранг 1-300     (>300 ipm)  ядерная лексика, служебные слова
  high      — ранг 301-1500  (30-300 ipm) высокочастотная общеупотребительная
  medium    — ранг 1501-7000 (3-30 ipm)  среднечастотная
  low       — ранг 7001-30000 (0.2-3 ipm) низкочастотная
  rare      — ранг >30000    (<0.2 ipm)  редкая (присутствует в НКРЯ)
  absent    — отсутствует в корпусе
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Путь к словарю
_DICT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data", "freq", "freqrnc.json"
)

# Порядок и метаданные диапазонов
BANDS: Dict[str, dict] = {
    "nucleus": {
        "label": "Ядерная (топ 300)",
        "desc":  "Служебные слова, местоимения, союзы — ранг 1–300",
        "color": "#89b4fa",
        "rank_max": 300,
    },
    "high": {
        "label": "Высокочастотная",
        "desc":  "Общеупотребительная лексика — ранг 301–1 500",
        "color": "#a6e3a1",
        "rank_max": 1_500,
    },
    "medium": {
        "label": "Среднечастотная",
        "desc":  "Нейтральная книжная лексика — ранг 1 501–7 000",
        "color": "#f9e2af",
        "rank_max": 7_000,
    },
    "low": {
        "label": "Низкочастотная",
        "desc":  "Специальная, редко употребляемая — ранг 7 001–30 000",
        "color": "#fab387",
        "rank_max": 30_000,
    },
    "rare": {
        "label": "Раритетная (есть в НКРЯ)",
        "desc":  "Очень редкая лексика — ранг >30 000",
        "color": "#f38ba8",
        "rank_max": 10_000_000,
    },
    "absent": {
        "label": "Отсутствует в НКРЯ",
        "desc":  "Неологизмы, узкоспециальные термины, авторские слова",
        "color": "#cba6f7",
        "rank_max": None,
    },
}

# Функциональные PoS, которые исключаем при расчёте «авторского словаря»
# (предлоги, союзы, частицы, местоимения — слишком зависят от жанра)
_FUNCTION_POS = {"conj", "prep", "pron", "part", "interj", "num", "adv.pron"}


@dataclass
class WordEntry:
    form:   str       # исходная форма из текста
    lemma:  str       # лемма (pymorphy3)
    rank:   int       # ранг в НКРЯ (0 = отсутствует)
    ipm:    float     # частота (ipm)
    pos:    str       # PoS из словаря
    band:   str       # ключ диапазона
    count:  int = 1   # сколько раз встретилась в тексте


@dataclass
class FreqResult:
    total_tokens:    int   # всего слов (включая служебные)
    content_tokens:  int   # знаменательных слов
    bands:           Dict[str, int]         = field(default_factory=dict)
    avg_rank:        float                  = 0.0
    avg_ipm:         float                  = 0.0
    content_avg_ipm: float                  = 0.0    # без ядерной лексики
    words:           List[WordEntry]        = field(default_factory=list)
    # Топ-N редких слов (не считая «absent»)
    rarest:          List[WordEntry]        = field(default_factory=list)
    # Слова, отсутствующие в НКРЯ
    absent_words:    List[WordEntry]        = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return self.total_tokens == 0


# ─────────────────────────────────────────────────────────────────────────────

class FreqEngine:
    """Движок частотного анализа по словарю НКРЯ."""

    def __init__(self):
        self._data: Dict[str, Tuple[int, float, str]] = {}  # lemma -> (rank, ipm, pos)
        self._loaded = False
        self._load_error: Optional[str] = None

    # ── Загрузка ──────────────────────────────────────────────────────────

    def load(self, path: str = _DICT_PATH) -> bool:
        if self._loaded:
            return True
        if not os.path.exists(path):
            self._load_error = (
                f"Словарь не найден: {path}\n"
                "Запустите: python scripts/download_freq_dict.py"
            )
            return False
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            # raw: { lemma: [rank, ipm, pos], ... }
            self._data = {k: tuple(v) for k, v in raw.items()}  # type: ignore[assignment]
            self._loaded = True
            self._load_error = None
            return True
        except Exception as e:
            self._load_error = f"Ошибка загрузки словаря: {e}"
            return False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    @property
    def dict_size(self) -> int:
        return len(self._data)

    # ── Поиск слова ───────────────────────────────────────────────────────

    def lookup(self, lemma: str) -> Optional[Tuple[int, float, str]]:
        """Вернуть (rank, ipm, pos) для леммы или None."""
        return self._data.get(lemma.lower())

    def _band_for(self, rank: int) -> str:
        if rank == 0:
            return "absent"
        for key, meta in BANDS.items():
            if key == "absent":
                continue
            if rank <= meta["rank_max"]:
                return key
        return "rare"

    # ── Анализ текста ─────────────────────────────────────────────────────

    def analyze(
        self,
        text: str,
        lemmas: Optional[Dict[str, str]] = None,
    ) -> FreqResult:
        """
        Проанализировать текст.

        lemmas: словарь {словоформа -> лемма} (из Stanza/spaCy).
                Если None — используем простое приведение к lower.
        """
        # Токенизация: только слова (русские + латинские)
        tokens = re.findall(r"[А-Яа-яЁёA-Za-z]+", text)
        if not tokens:
            return FreqResult(total_tokens=0, content_tokens=0)

        # Агрегировать по уникальным формам
        form_count: Dict[str, int] = {}
        for t in tokens:
            form_count[t.lower()] = form_count.get(t.lower(), 0) + 1

        entries: List[WordEntry] = []
        bands: Dict[str, int] = {k: 0 for k in BANDS}
        rank_sum = 0.0
        ipm_sum  = 0.0
        content_ipm_sum = 0.0
        n_for_rank = 0
        content_n  = 0

        for form, cnt in form_count.items():
            # Получить лемму
            if lemmas and form in lemmas:
                lemma = lemmas[form].lower()
            else:
                lemma = form  # fallback — form == lemma

            # Попробовать lookup: сначала по лемме, потом по форме
            entry = self.lookup(lemma) or self.lookup(form)

            if entry:
                rank, ipm, pos = entry
            else:
                rank, ipm, pos = 0, 0.0, ""

            band = self._band_for(rank)
            bands[band] += cnt

            if rank > 0:
                rank_sum += rank * cnt
                ipm_sum  += ipm  * cnt
                n_for_rank += cnt
                # Контентный avg (без ядерной лексики и служебных)
                if band != "nucleus" and pos.lower() not in _FUNCTION_POS:
                    content_ipm_sum += ipm * cnt
                    content_n += cnt

            entries.append(WordEntry(
                form=form, lemma=lemma,
                rank=rank, ipm=ipm, pos=pos,
                band=band, count=cnt,
            ))

        total = sum(form_count.values())
        content_tokens = total - bands.get("nucleus", 0)

        avg_rank = rank_sum / n_for_rank if n_for_rank else 0.0
        avg_ipm  = ipm_sum  / n_for_rank if n_for_rank else 0.0
        content_avg = content_ipm_sum / content_n if content_n else 0.0

        # Топ-20 редких (из НКРЯ, но с высоким рангом)
        in_corpus = [e for e in entries if e.rank > 0]
        rarest = sorted(in_corpus, key=lambda e: -e.rank)[:20]

        # Absent words (отсутствуют в НКРЯ), отсортировать по убыванию count
        absent = sorted(
            [e for e in entries if e.band == "absent"],
            key=lambda e: -e.count
        )

        return FreqResult(
            total_tokens=total,
            content_tokens=content_tokens,
            bands=bands,
            avg_rank=round(avg_rank, 1),
            avg_ipm=round(avg_ipm, 3),
            content_avg_ipm=round(content_avg, 3),
            words=sorted(entries, key=lambda e: e.rank if e.rank > 0 else 10_000_000),
            rarest=rarest,
            absent_words=absent,
        )


# ── Singleton ──────────────────────────────────────────────────────────────

_instance = FreqEngine()


def get() -> FreqEngine:
    return _instance
