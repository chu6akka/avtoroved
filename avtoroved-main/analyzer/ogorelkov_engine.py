"""
analyzer/ogorelkov_engine.py — частотный анализ служебной лексики.

Методическое основание: Огорелков И.В. «Диагностика пола автора текста
политического дискурса» (монография), гл. 3, п. 3.2–3.4. Метод: относительная
частота ipm (instances per million words) закрытого перечня служебных
лексико-грамматических классов слов, сравнение с нормой НКРЯ по частотному
словарю Ляшевской–Шарова (analyzer/freq_engine.py, уже в проекте).

Модуль выдаёт ТОЛЬКО наблюдаемые факты (карточку признаков) — никаких
выводов об авторстве или поле автора не формулирует.

Снятие омонимии — по POS-тегу Stanza: лемма засчитывается в категорию только
при совпадении части речи («что» как SCONJ — союз, как PRON — не союз;
«да» CCONJ vs PART; «так/точно» PART vs ADV). Для «несмотря на» — детект
биграммы по соседним токенам. Вводные слова не имеют собственного POS —
считаются по лемме с исключением знаменательных омонимов (NOUN/ADJ/PROPN/NUM);
допущение зафиксировано здесь и в docs.

Пайплайн NLP переиспользуется (леммы/POS из уже полученных токенов Stanza) —
второй пайплайн не создаётся.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Optional

DICT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                         "data", "ogorelkov_function_words.json")

# Допустимые UPOS по категориям (снятие омонимии). None = правило-исключение
# для вводных слов (см. _INTRO_EXCLUDED).
CATEGORY_POS: dict[str, Optional[set]] = {
    "личные_местоимения": {"PRON"},
    "притяжательные_местоимения": {"DET", "PRON"},
    "указательные_местоимения": {"DET", "PRON"},
    "неопределённые_местоимения": {"PRON", "DET", "ADV"},
    "отрицательные_местоимения": {"PRON", "DET", "ADV"},
    "сочинительные_союзы": {"CCONJ"},
    "подчинительные_союзы": {"SCONJ"},
    "простые_предлоги": {"ADP"},
    "производные_предлоги": {"ADP", "SCONJ"},   # «благодаря/несмотря» размечаются по-разному
    "частицы": {"PART"},
    "вводные_слова": None,
}
# Для вводных: лемма засчитывается, если POS НЕ знаменательный омоним.
_INTRO_EXCLUDED = {"NOUN", "ADJ", "PROPN", "NUM"}

# Биграммы (единственная в перечне — «несмотря на»).
_BIGRAMS = {"несмотря на": ("несмотря", "на")}


def load_marker_dict(path: str = DICT_PATH) -> tuple[dict[str, list[str]], str]:
    """Словарь маркеров + sha256 файла (версия словаря — в аудит)."""
    with open(path, "rb") as f:
        raw = f.read()
    data = json.loads(raw.decode("utf-8"))
    markers = {k: v for k, v in data.items() if not k.startswith("_")}
    return markers, hashlib.sha256(raw).hexdigest()


def analyze(tokens: list, freq_lookup=None,
            dict_path: str = DICT_PATH) -> dict:
    """
    Частотный анализ служебной лексики по токенам Stanza.

    tokens — список TokenInfo (text, lemma, pos, sent_id); freq_lookup —
    callable(lemma) -> (rank, ipm, pos) | None (словарь Ляшевской–Шарова).

    Возвращает:
      {"total_words": int, "dict_sha256": str,
       "categories": {категория: {
           "lemmas": {лемма: {"count", "ipm_text", "ipm_rnc"|None, "ratio"|None}},
           "total_count", "total_ipm", "share_pct", "used", "total_lemmas"}}}
    """
    markers, dict_sha = load_marker_dict(dict_path)

    # Словоупотребления = все токены-слова (не пунктуация).
    words = [t for t in tokens if getattr(t, "pos", "") != "PUNCT"]
    total_words = len(words)

    # Счётчики: (категория, лемма) -> вхождения.
    counts: dict[tuple[str, str], int] = {}

    def _hit(category: str, lemma: str):
        counts[(category, lemma)] = counts.get((category, lemma), 0) + 1

    # Одиночные леммы со снятием омонимии по POS.
    single_lemmas: dict[str, list[str]] = {}   # лемма -> [категории]
    for cat, lemmas in markers.items():
        for lem in lemmas:
            if lem in _BIGRAMS:
                continue
            single_lemmas.setdefault(lem, []).append(cat)

    for t in words:
        lem = (getattr(t, "lemma", "") or "").lower()
        pos = getattr(t, "pos", "") or ""
        for cat in single_lemmas.get(lem, []):
            allowed = CATEGORY_POS.get(cat)
            if allowed is None:                       # вводные: исключение
                if pos not in _INTRO_EXCLUDED:
                    _hit(cat, lem)
            elif pos in allowed:
                _hit(cat, lem)

    # Биграммы («несмотря на»): соседние токены одного предложения.
    for bigram, (w1, w2) in _BIGRAMS.items():
        bigram_cats = [cat for cat, lemmas in markers.items() if bigram in lemmas]
        for i in range(len(words) - 1):
            a, b = words[i], words[i + 1]
            if (a.lemma or "").lower() == w1 and (b.lemma or "").lower() == w2 \
                    and getattr(a, "sent_id", 0) == getattr(b, "sent_id", 0):
                for cat in bigram_cats:
                    _hit(cat, bigram)

    # Сборка результата.
    def _ipm(n: int) -> float:
        return round(n / total_words * 1_000_000, 1) if total_words else 0.0

    categories: dict[str, dict] = {}
    for cat, lemmas in markers.items():
        detail: dict[str, dict] = {}
        cat_total = 0
        for lem in lemmas:
            n = counts.get((cat, lem), 0)
            cat_total += n
            if n == 0:
                continue      # нулевые в детальную таблицу не включаются
            ipm_text = _ipm(n)
            ipm_rnc = None
            ratio = None
            if freq_lookup is not None:
                try:
                    hit = freq_lookup(lem)
                    if hit:
                        ipm_rnc = round(float(hit[1]), 1)
                        if ipm_rnc:
                            ratio = round(ipm_text / ipm_rnc, 2)
                except Exception:
                    pass
            detail[lem] = {"count": n, "ipm_text": ipm_text,
                           "ipm_rnc": ipm_rnc, "ratio": ratio}
        categories[cat] = {
            "lemmas": dict(sorted(detail.items(),
                                  key=lambda kv: -kv[1]["ipm_text"])),
            "total_count": cat_total,
            "total_ipm": _ipm(cat_total),
            "share_pct": round(cat_total / total_words * 100, 2) if total_words else 0.0,
            "used": len(detail),
            "total_lemmas": len(lemmas),
        }

    return {"total_words": total_words, "dict_sha256": dict_sha,
            "categories": categories}
