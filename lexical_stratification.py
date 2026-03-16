# -*- coding: utf-8 -*-
"""
lexical_stratification.py — Модуль лексической стратификации текста
====================================================================
Определяет принадлежность лексики исследуемого текста к стилистическим
пластам русского языка для целей автороведческой экспертизы.

Методическая основа:
  — Назарова Л.С., Маняни В.А., Громова А.Н. (ЭКЦ МВД России, 2021)
    «Методика производства автороведческой экспертизы»
  — Химик В.В. «Большой словарь русской разговорной экспрессивной речи» (2004)
  — Буй В. «Русская заветная идиоматика» (2005)
  — Словарь арготизмов семантического поля «Наркотики» (2014)

Словарная база: 12 251 лемма, 8 стилистических слоёв.
Поиск идиом: n-граммный поиск для фразеологизмов (≥2 токенов).
"""

from __future__ import annotations
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

# ── Метки слоёв ─────────────────────────────────────────────────────────────

LAYER_LABELS: Dict[str, str] = {
    "colloquial_reduced":  "Разговорно-сниженная",
    "vernacular":          "Просторечная",
    "folk_speech":         "Народно-разговорная",
    "general_jargon":      "Общий жаргон",
    "criminal_jargon":     "Уголовный жаргон",
    "youth_jargon":        "Молодёжный жаргон",
    "military_jargon":     "Военный жаргон",
    "drug_jargon":         "Наркожаргон",
    "obscene":             "Обсценная лексика",
    "euphemistic":         "Эвфемистическая",
    "extremist":           "Экстремистская",
    "religious_radical":   "Религиозно-радикальная",
    "nationalist":         "Националистическая",
}

# Порядок отображения в отчёте
LAYER_ORDER = [
    "colloquial_reduced", "vernacular", "folk_speech",
    "general_jargon", "criminal_jargon", "youth_jargon",
    "military_jargon", "drug_jargon",
    "obscene", "euphemistic",
    "extremist", "religious_radical", "nationalist",
]

# Цвета для GUI (hex)
LAYER_COLORS: Dict[str, str] = {
    "colloquial_reduced":  "#4a90d9",
    "vernacular":          "#7b68ee",
    "folk_speech":         "#9acd32",
    "general_jargon":      "#ff8c00",
    "criminal_jargon":     "#dc143c",
    "youth_jargon":        "#20b2aa",
    "military_jargon":     "#556b2f",
    "drug_jargon":         "#8b0000",
    "obscene":             "#b22222",
    "euphemistic":         "#daa520",
    "extremist":           "#800000",
    "religious_radical":   "#483d8b",
    "nationalist":         "#8b4513",
}

# ── Датаклассы ───────────────────────────────────────────────────────────────

@dataclass
class StratifiedToken:
    """Токен с установленным стилистическим слоем."""
    word: str          # словоформа в тексте
    lemma: str         # лемма (от Stanza или простая нормализация)
    layer: str         # идентификатор слоя
    layer_label: str   # русское название слоя
    match_key: str     # ключ, по которому произошло совпадение
    is_phrase: bool = False  # True — найден как часть идиомы/фразеологизма


@dataclass
class StratificationResult:
    """Результат стратификационного анализа текста."""
    # Список всех найденных маркированных единиц
    found: List[StratifiedToken] = field(default_factory=list)

    # Подсчёты по слоям: layer → список (слово, лемма, ключ)
    by_layer: Dict[str, List[StratifiedToken]] = field(
        default_factory=lambda: defaultdict(list))

    # Общая статистика
    total_words: int = 0
    marked_words: int = 0
    layer_counts: Dict[str, int] = field(default_factory=Counter)
    layer_ratios: Dict[str, float] = field(default_factory=dict)

    # Флаг: хватает ли слов для надёжного вывода
    sufficient_volume: bool = True


# ── Загрузка словаря ─────────────────────────────────────────────────────────

def _find_lexicon_path() -> str:
    """Ищет файл lexicon_stratified.json рядом с модулем."""
    candidates = [
        os.path.join(os.path.dirname(__file__), "lexicon_stratified.json"),
        os.path.join(os.path.dirname(__file__), "analyzer", "lexicon_stratified.json"),
        "lexicon_stratified.json",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    raise FileNotFoundError(
        "Файл lexicon_stratified.json не найден. "
        "Поместите его в директорию с программой."
    )


def _load_lexicon(path: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Загружает словарь. Возвращает два словаря:
      single: lemma → layer        (для однословного поиска)
      phrases: phrase → layer      (для n-граммного поиска)
    """
    with open(path, "r", encoding="utf-8") as f:
        raw: Dict = json.load(f)

    single: Dict[str, str] = {}
    phrases: Dict[str, str] = {}

    for key, value in raw.items():
        layer = value if isinstance(value, str) else value[0]
        key_clean = key.strip().lower()
        if not key_clean:
            continue
        if " " in key_clean:
            phrases[key_clean] = layer
        else:
            single[key_clean] = layer

    return single, phrases


# Глобальный кэш (загружается один раз при первом вызове)
_LEXICON_SINGLE: Optional[Dict[str, str]] = None
_LEXICON_PHRASES: Optional[Dict[str, str]] = None
_LEXICON_PATH: Optional[str] = None


def get_lexicon() -> Tuple[Dict[str, str], Dict[str, str]]:
    global _LEXICON_SINGLE, _LEXICON_PHRASES, _LEXICON_PATH
    if _LEXICON_SINGLE is None:
        path = _find_lexicon_path()
        _LEXICON_PATH = path
        _LEXICON_SINGLE, _LEXICON_PHRASES = _load_lexicon(path)
    return _LEXICON_SINGLE, _LEXICON_PHRASES


def reload_lexicon(path: str) -> None:
    """Принудительная перезагрузка словаря из указанного файла."""
    global _LEXICON_SINGLE, _LEXICON_PHRASES, _LEXICON_PATH
    _LEXICON_SINGLE, _LEXICON_PHRASES = _load_lexicon(path)
    _LEXICON_PATH = path


# ── Вспомогательные функции ──────────────────────────────────────────────────

_WORD_RE = re.compile(r"[А-Яа-яЁё]{2,}", re.UNICODE)


def _normalize(word: str) -> str:
    """Приводим слово к нижнему регистру, убираем окружающие знаки."""
    return word.strip(" .,;:!?«»\"'()[]").lower()


def _simple_lemmatize(word: str) -> str:
    """
    Простое «огрубление» для поиска в словаре без Stanza.
    Обрезает типичные окончания — не заменяет морфологический анализ,
    но позволяет найти словарную форму в ~60% случаев.
    Используется только если леммы от Stanza недоступны.
    """
    w = word.lower()
    for suffix in ("ющими", "ующими", "ющего", "ующего", "ющей", "ующей",
                   "ющем", "ующем", "ющие", "ующие", "ющий", "ующий",
                   "ющих", "ующих", "ющим", "ующим", "ющую", "ующую",
                   "овавших", "овавшим", "овавшей", "овавшем", "овавший",
                   "ившись", "авшись", "евшись",
                   "ишься", "ешься", "ться",
                   "ового", "евого", "ового",
                   "овый", "евый", "ового",
                   "ными", "ыми", "ими",
                   "ного", "него", "ной", "ней",
                   "ному", "нему", "ных", "них", "ным", "ним",
                   "ами", "ями", "ем", "ом", "ою", "ею",
                   "ой", "ей", "ую", "юю",
                   "ых", "их", "ый", "ий", "ая", "яя",
                   "ов", "ев", "ёв",
                   "ам", "ям", "ах", "ях",
                   "ть", "ти", "чь",
                   "шь", "ит", "ат", "ят", "ет", "ют", "ут",
                   "ла", "ло", "ли", "ал", "ял", "ил", "ул",
                   "ся", "сь",
                   "ы", "и", "а", "я", "е", "у", "ю", "ё"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[: len(w) - len(suffix)]
    return w


# ── Основная функция анализа ─────────────────────────────────────────────────

def analyze_stratification(
    text: str,
    lemmas: Optional[List[Tuple[str, str]]] = None,
) -> StratificationResult:
    """
    Анализирует стилистическую стратификацию текста.

    Параметры
    ----------
    text : str
        Исходный текст.
    lemmas : list of (wordform, lemma), optional
        Пары (словоформа, лемма) от Stanza. Если не переданы —
        используется упрощённая нормализация.

    Возвращает
    ----------
    StratificationResult
    """
    single, phrases = get_lexicon()
    result = StratificationResult()

    # ── 1. Подготовка списка токенов ─────────────────────────────────────────
    words_raw = _WORD_RE.findall(text)
    result.total_words = len(words_raw)
    if result.total_words < 50:
        result.sufficient_volume = False

    # Строим список (словоформа, лемма) для каждого слова
    if lemmas:
        token_pairs: List[Tuple[str, str]] = lemmas
    else:
        token_pairs = [(w, _simple_lemmatize(w)) for w in words_raw]

    # ── 2. N-граммный поиск идиом (Буй и фразеологизмы Арготизмов) ───────────
    # Строим строку из лемм для поиска подстрок
    lemma_sequence = [pair[1].lower() for pair in token_pairs]
    lemma_str = " ".join(lemma_sequence)

    phrase_hits: Dict[int, Tuple[str, str, int]] = {}  # start_idx → (phrase, layer, length)

    for phrase, layer in phrases.items():
        phrase_words = phrase.split()
        phrase_str = " ".join(phrase_words)
        # Ищем в строке лемм
        pos = 0
        while True:
            idx = lemma_str.find(phrase_str, pos)
            if idx == -1:
                break
            # Вычисляем индекс первого токена
            prefix = lemma_str[:idx]
            tok_start = prefix.count(" ") if prefix else 0
            phrase_len = len(phrase_words)
            # Записываем только если ещё не покрыто более длинной фразой
            covered = any(
                tok_start >= s and tok_start < s + phrase_hits[s][2]
                for s in phrase_hits
            )
            if not covered:
                phrase_hits[tok_start] = (phrase, layer, phrase_len)
            pos = idx + 1

    # ── 3. Однословный поиск ─────────────────────────────────────────────────
    covered_indices = set()
    for start, (phrase, layer, length) in phrase_hits.items():
        for i in range(start, min(start + length, len(token_pairs))):
            covered_indices.add(i)

    found_set: Dict[int, StratifiedToken] = {}  # idx → StratifiedToken

    # Сначала вносим найденные идиомы
    for start, (phrase, layer, length) in phrase_hits.items():
        for i in range(start, min(start + length, len(token_pairs))):
            if i < len(token_pairs):
                wf, lm = token_pairs[i]
                st = StratifiedToken(
                    word=wf, lemma=lm,
                    layer=layer,
                    layer_label=LAYER_LABELS.get(layer, layer),
                    match_key=phrase,
                    is_phrase=True,
                )
                found_set[i] = st

    # Однословный поиск для непокрытых токенов
    for i, (wf, lm) in enumerate(token_pairs):
        if i in covered_indices:
            continue
        # Пробуем лемму, потом словоформу
        for key in (lm.lower(), _normalize(wf)):
            if key in single:
                layer = single[key]
                st = StratifiedToken(
                    word=wf, lemma=lm,
                    layer=layer,
                    layer_label=LAYER_LABELS.get(layer, layer),
                    match_key=key,
                    is_phrase=False,
                )
                found_set[i] = st
                break

    # ── 4. Сборка результата ─────────────────────────────────────────────────
    result.found = [found_set[i] for i in sorted(found_set.keys())]
    result.marked_words = len(result.found)

    for st in result.found:
        result.by_layer[st.layer].append(st)
        result.layer_counts[st.layer] += 1

    # Доли от общего числа слов
    if result.total_words > 0:
        result.layer_ratios = {
            layer: count / result.total_words
            for layer, count in result.layer_counts.items()
        }

    return result


# ── Форматирование отчёта ─────────────────────────────────────────────────────

def format_stratification_report(result: StratificationResult) -> str:
    """Текстовый отчёт о стратификации для вкладки GUI."""
    lines: List[str] = []
    lines.append("=" * 65)
    lines.append("ЛЕКСИЧЕСКАЯ СТРАТИФИКАЦИЯ ТЕКСТА")
    lines.append("Методическая основа: ЭКЦ МВД России (Назарова и др., 2021)")
    lines.append("=" * 65)
    lines.append(f"\n  Всего слов в тексте:       {result.total_words}")
    lines.append(f"  Маркированных единиц:      {result.marked_words}")
    if result.total_words:
        pct = result.marked_words / result.total_words * 100
        lines.append(f"  Доля маркированной лекс.:  {pct:.1f}%")

    if not result.sufficient_volume:
        lines.append("\n  ⚠  Объём текста мал (<50 слов) — результаты ориентировочны.")

    lines.append("\n" + "-" * 65)
    lines.append(f"  {'Пласт':<35} {'Ед.':>5}  {'%':>6}  Примеры")
    lines.append("-" * 65)

    for layer in LAYER_ORDER:
        count = result.layer_counts.get(layer, 0)
        if count == 0:
            continue
        ratio = result.layer_ratios.get(layer, 0.0)
        label = LAYER_LABELS.get(layer, layer)
        tokens = result.by_layer.get(layer, [])
        # Уникальные примеры (до 5 слов)
        seen: Dict[str, int] = {}
        for t in tokens:
            k = t.match_key if t.is_phrase else t.lemma
            seen[k] = seen.get(k, 0) + 1
        top = sorted(seen, key=lambda x: -seen[x])[:5]
        examples = ", ".join(top)
        lines.append(f"  {label:<35} {count:>5}  {ratio:>5.1%}  {examples}")

    # Вывод
    lines.append("\n" + "=" * 65)
    lines.append("АНАЛИТИЧЕСКИЙ ВЫВОД")
    lines.append("-" * 65)
    lines.append(_make_conclusion(result))

    return "\n".join(lines)


def _make_conclusion(result: StratificationResult) -> str:
    """Автоматический вывод для экспертного заключения."""
    parts: List[str] = []
    tw = result.total_words
    if tw == 0:
        return "  Нет данных."

    def pct(layer: str) -> float:
        return result.layer_ratios.get(layer, 0.0) * 100

    # Разговорно-сниженная лексика
    coll = pct("colloquial_reduced")
    if coll >= 15:
        parts.append(
            f"  Высокая доля разговорно-сниженной лексики ({coll:.1f}%) "
            f"свидетельствует о преимущественно разговорном стиле изложения."
        )
    elif coll >= 5:
        parts.append(
            f"  Наличие разговорно-сниженной лексики ({coll:.1f}%) "
            f"указывает на смешение стилей."
        )

    # Жаргонные пласты
    jargon_total = sum(
        pct(l) for l in ("general_jargon", "criminal_jargon",
                          "youth_jargon", "military_jargon", "drug_jargon")
    )
    if jargon_total >= 5:
        dominant_jargon = max(
            ("general_jargon", "criminal_jargon", "youth_jargon",
             "military_jargon", "drug_jargon"),
            key=lambda l: pct(l)
        )
        parts.append(
            f"  Присутствие жаргонной лексики ({jargon_total:.1f}%), "
            f"в том числе {LAYER_LABELS.get(dominant_jargon,'').lower()} "
            f"({pct(dominant_jargon):.1f}%), может указывать "
            f"на специфическую социальную среду автора."
        )

    # Обсценная лексика
    obs = pct("obscene")
    if obs >= 3:
        parts.append(
            f"  Значительная доля обсценной лексики ({obs:.1f}%) "
            f"является маркером субкультурной принадлежности или "
            f"сниженной речевой культуры автора."
        )
    elif obs > 0:
        parts.append(
            f"  Единичные обсценные единицы ({pct('obscene'):.1f}%) "
            f"зафиксированы, что может быть ситуативным."
        )

    # Наркожаргон
    drug = pct("drug_jargon")
    if drug >= 2:
        parts.append(
            f"  Наличие наркожаргонной лексики ({drug:.1f}%) "
            f"указывает на осведомлённость автора о наркотической субкультуре."
        )

    # Эвфемизмы
    euph = pct("euphemistic")
    if euph >= 2:
        parts.append(
            f"  Использование эвфемизмов ({euph:.1f}%) указывает "
            f"на стремление автора к завуалированному выражению."
        )

    if not parts:
        total_marked = result.marked_words / tw * 100 if tw else 0
        if total_marked < 1:
            parts.append(
                "  Стилистически маркированная лексика в тексте практически "
                "отсутствует, что характерно для нейтрального или книжного стиля."
            )
        else:
            parts.append(
                f"  Маркированная лексика составляет {total_marked:.1f}% — "
                f"стилистическая окраска незначительна."
            )

    return "\n".join(parts)
