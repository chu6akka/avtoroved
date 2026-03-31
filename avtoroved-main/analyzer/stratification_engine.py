"""
analyzer/stratification_engine.py — Лексическая стратификация с точным
морфологическим разбором через pymorphy3.

Методология:
  — Виноградов В.В. «Русский язык» (1947): теория стилистических пластов
  — Химик В.В. «Поэтика сниженной речи» (2000): классификация сниженной лексики
  — Ожегов С.И. «Словарь русского языка»: маркировка разговорной/просторечной лексики

Алгоритм:
  1. При загрузке словаря каждый ключ лемматизируется через pymorphy3
     (normal_form) → строится таблица «лемма → слой».
  2. При анализе текста каждый токен лемматизируется и ищется в таблице.
  3. Если лемма встречается в нескольких слоях — применяется приоритет слоёв.
  4. Фразовые совпадения (n-граммы) проверяются отдельным проходом.
"""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

try:
    import pymorphy3
    _MORPH = pymorphy3.MorphAnalyzer()
    _MORPHY_AVAILABLE = True
except ImportError:
    _MORPH = None
    _MORPHY_AVAILABLE = False

from analyzer.strat_filter import LITERARY_WHITELIST, FILTERABLE_LAYERS, COLLOQUIAL_KEEPLIST


# ── Метаданные слоёв ────────────────────────────────────────────────────────

LAYER_META: Dict[str, dict] = {
    "obscene": {
        "label":    "Обсценная лексика",
        "color":    "#f38ba8",
        "priority": 10,
        "desc":     "Матерные и грубо-бранные слова и выражения",
    },
    "criminal_jargon": {
        "label":    "Криминальный жаргон",
        "color":    "#fab387",
        "priority": 9,
        "desc":     "Лексика криминальной субкультуры и уголовного арго",
    },
    "drug_jargon": {
        "label":    "Наркотический жаргон",
        "color":    "#eba0ac",
        "priority": 8,
        "desc":     "Жаргон наркопотребителей и наркоторговцев",
    },
    "youth_jargon": {
        "label":    "Молодёжный жаргон",
        "color":    "#cba6f7",
        "priority": 7,
        "desc":     "Сленг молодёжных субкультур и интернет-коммуникации",
    },
    "general_jargon": {
        "label":    "Общий жаргон",
        "color":    "#89b4fa",
        "priority": 6,
        "desc":     "Межсубкультурный жаргон, социолектизмы",
    },
    "vernacular": {
        "label":    "Просторечие",
        "color":    "#a6e3a1",
        "priority": 5,
        "desc":     "Грубо-разговорные и просторечные слова (Ожегов: «прост.»)",
    },
    "colloquial_reduced": {
        "label":    "Разговорно-сниженная",
        "color":    "#94e2d5",
        "priority": 4,
        "desc":     "Разговорные слова со сниженной стилистической окраской",
    },
    "literary_standard": {
        "label":    "Книжная / нейтральная",
        "color":    "#89dceb",
        "priority": 1,
        "desc":     "Книжно-письменный пласт, терминология, официальный стиль",
    },
    "archaic": {
        "label":    "Архаизмы",
        "color":    "#f9e2af",
        "priority": 2,
        "desc":     "Устаревшая лексика, архаизмы и историзмы",
    },
    "dialectal": {
        "label":    "Диалектизмы",
        "color":    "#b5e8b0",
        "priority": 3,
        "desc":     "Территориальная диалектная лексика",
    },
    "euphemistic": {
        "label":    "Эвфемизмы",
        "color":    "#f5c2e7",
        "priority": 4,
        "desc":     "Смягчённые обозначения запретных или нежелательных понятий",
    },
}

_LEXICON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "lexicon_stratified.json",
)

_WORD_RE = re.compile(r"[А-Яа-яЁё]{2,}", re.UNICODE)


# ── Датакласс результата ────────────────────────────────────────────────────

@dataclass
class StratToken:
    """Токен, попавший в нелитературный слой."""
    surface: str          # форма в тексте
    lemma:   str          # нормальная форма
    layer:   str          # ключ слоя (obscene, vernacular, …)
    start:   int          # позиция начала в тексте
    end:     int          # позиция конца в тексте
    context: str = ""     # фрагмент контекста


@dataclass
class StratResult:
    """Результат стратификации текста."""
    tokens:       List[StratToken]              = field(default_factory=list)
    layer_counts: Dict[str, int]               = field(default_factory=dict)
    layer_words:  Dict[str, List[str]]         = field(default_factory=dict)
    total_words:  int                          = 0
    marked_ratio: float                        = 0.0   # доля нелитературной лексики


# ── Движок ─────────────────────────────────────────────────────────────────

class StratificationEngine:
    """
    Движок лексической стратификации.

    Принцип «нереально точного парсинга»:
      — при инициализации словаря каждый ключ приводится к нормальной форме
        через pymorphy3 (словарная статья → лемма);
      — при анализе текста каждое слово тоже приводится к лемме через pymorphy3,
        после чего производится поиск в лемматизированном словаре;
      — таким образом «идёт», «шли», «пошедший» все правильно сопоставляются
        с леммой «идти» из словаря.
    """

    def __init__(self):
        self._lemma_to_layer: Dict[str, str] = {}     # лемма → слой
        self._phrase_to_layer: Dict[str, str] = {}    # фраза → слой (n-граммы)
        self._loaded = False

    # ── Загрузка ──────────────────────────────────────────────────────────

    def load(self) -> None:
        if self._loaded:
            return
        if not os.path.exists(_LEXICON_PATH):
            self._loaded = True
            return

        with open(_LEXICON_PATH, encoding="utf-8") as f:
            raw: Dict[str, str] = json.load(f)

        for surface_key, layer_val in raw.items():
            # Значение может быть строкой или списком строк
            if isinstance(layer_val, list):
                valid = [l for l in layer_val if l in LAYER_META]
                if not valid:
                    continue
                layer = max(valid, key=lambda l: LAYER_META[l]["priority"])
            else:
                layer = layer_val
            if layer not in LAYER_META:
                continue

            words = surface_key.strip().split()
            if len(words) == 1:
                surface = words[0]
                lemma   = self._lemmatize(surface)

                # ── Фильтрация ложных срабатываний ───────────────────────
                # Вайтлист применяется КО ВСЕМ слоям: нейтральное слово
                # не должно появляться ни в каком «нелитературном» слое,
                # даже если оно ошибочно занесено в drug_jargon / criminal_jargon.
                # pymorphy3-фильтр — только для «слабых» слоёв.
                if self._is_false_positive(surface, lemma,
                                           check_morph=(layer in FILTERABLE_LAYERS)):
                    continue

                if lemma not in self._lemma_to_layer or (
                    LAYER_META[layer]["priority"]
                    > LAYER_META[self._lemma_to_layer[lemma]]["priority"]
                ):
                    self._lemma_to_layer[lemma] = layer
            else:
                # Фраза: хранить как нормализованную строку
                norm_phrase = " ".join(self._lemmatize(w) for w in words if _WORD_RE.fullmatch(w))
                if norm_phrase:
                    if norm_phrase not in self._phrase_to_layer or (
                        LAYER_META[layer]["priority"]
                        > LAYER_META[self._phrase_to_layer[norm_phrase]]["priority"]
                    ):
                        self._phrase_to_layer[norm_phrase] = layer

        self._loaded = True

    @staticmethod
    def _is_false_positive(surface: str, lemma: str, check_morph: bool = True) -> bool:
        """
        Определить, является ли слово ложным срабатыванием.

        Двухступенчатый фильтр:
          1. Статический вайтлист (strat_filter.LITERARY_WHITELIST) — применяется
             ко ВСЕМ слоям: если нейтральное слово попало в drug_jargon / criminal_jargon
             из-за ошибки в исходном словаре — оно всё равно исключается.
          2. pymorphy3 (только для «слабых» слоёв, check_morph=True): если слово
             есть в словаре OpenCorpora и не помечено как неформальное (Infr, Slng, Dist)
             — оно считается литературной нормой.

        Возвращает True → слово следует исключить.
        """
        lm = lemma.lower()

        # Шаг 1: универсальный вайтлист (все слои)
        if lm in LITERARY_WHITELIST:
            return True

        # Шаг 2: подлинно разговорные слова, которые pymorphy3 не помечает Infr/Slng
        # (OpenCorpora не охватывает всю неформальную лексику — защищаем от ложной фильтрации)
        if lm in COLLOQUIAL_KEEPLIST:
            return False

        # Шаг 3: pymorphy3 — только для слабых слоёв
        if check_morph and _MORPHY_AVAILABLE and _MORPH:
            try:
                if _MORPH.word_is_known(surface):
                    parses = _MORPH.parse(surface)
                    _INFORMAL = {'Infr', 'Slng', 'Dist', 'Erro'}
                    has_informal = any(
                        bool(p.tag.grammemes & _INFORMAL)
                        for p in parses
                    )
                    if not has_informal:
                        return True   # словарное слово без пометок → литературная норма
            except Exception:
                pass

        return False

    # ── Лемматизация ──────────────────────────────────────────────────────

    @staticmethod
    def _lemmatize(word: str) -> str:
        """Получить нормальную форму слова через pymorphy3."""
        if not _MORPHY_AVAILABLE or not _MORPH:
            return word.lower()
        w = word.lower()
        parses = _MORPH.parse(w)
        if not parses:
            return w
        # Берём разбор с наибольшим скором (наиболее вероятный)
        best = max(parses, key=lambda p: p.score)
        return best.normal_form

    # ── Анализ текста ─────────────────────────────────────────────────────

    def analyze(self, text: str) -> StratResult:
        if not self._loaded:
            self.load()

        result = StratResult()
        word_tokens = list(_WORD_RE.finditer(text))
        result.total_words = len(word_tokens)

        layer_counts: Dict[str, int]       = defaultdict(int)
        layer_words:  Dict[str, List[str]] = defaultdict(list)
        found_tokens: List[StratToken]     = []
        used_positions: Set[int]           = set()

        # ── Проход 1: одиночные слова ──────────────────────────────────
        for m in word_tokens:
            surface = m.group()
            lemma   = self._lemmatize(surface)
            layer   = self._lemma_to_layer.get(lemma)
            if layer is None:
                continue

            start, end = m.start(), m.end()
            ctx = _make_context(text, start, end)

            st = StratToken(
                surface=surface,
                lemma=lemma,
                layer=layer,
                start=start,
                end=end,
                context=ctx,
            )
            found_tokens.append(st)
            layer_counts[layer] += 1
            if surface.lower() not in layer_words[layer]:
                layer_words[layer].append(surface.lower())
            used_positions.add(start)

        # ── Проход 2: фразы (n-граммы) ────────────────────────────────
        if self._phrase_to_layer:
            lemma_sequence = [(m.group(), self._lemmatize(m.group()), m.start(), m.end())
                              for m in word_tokens]
            n = len(lemma_sequence)
            for size in range(2, min(6, n + 1)):
                for i in range(n - size + 1):
                    chunk = lemma_sequence[i:i + size]
                    phrase_key = " ".join(tok[1] for tok in chunk)
                    layer = self._phrase_to_layer.get(phrase_key)
                    if layer is None:
                        continue
                    # Проверяем, не перекрывается ли с уже найденными
                    positions = {tok[2] for tok in chunk}
                    if positions & used_positions:
                        continue
                    surface = " ".join(tok[0] for tok in chunk)
                    start   = chunk[0][2]
                    end     = chunk[-1][3]
                    ctx     = _make_context(text, start, end)
                    st = StratToken(
                        surface=surface,
                        lemma=phrase_key,
                        layer=layer,
                        start=start,
                        end=end,
                        context=ctx,
                    )
                    found_tokens.append(st)
                    layer_counts[layer] += 1
                    if surface.lower() not in layer_words[layer]:
                        layer_words[layer].append(surface.lower())
                    used_positions.update(positions)

        found_tokens.sort(key=lambda t: t.start)
        result.tokens       = found_tokens
        result.layer_counts = dict(layer_counts)
        result.layer_words  = dict(layer_words)
        if result.total_words > 0:
            result.marked_ratio = len(found_tokens) / result.total_words

        return result


# ── Утилиты ────────────────────────────────────────────────────────────────

def _make_context(text: str, start: int, end: int, window: int = 45) -> str:
    cs = max(0, start - window)
    ce = min(len(text), end + window)
    snippet = text[cs:ce].replace("\n", " ").strip()
    if cs > 0:
        snippet = "…" + snippet
    if ce < len(text):
        snippet = snippet + "…"
    return snippet


# ── Синглтон ───────────────────────────────────────────────────────────────

_instance: Optional[StratificationEngine] = None


def get() -> StratificationEngine:
    global _instance
    if _instance is None:
        _instance = StratificationEngine()
    return _instance
