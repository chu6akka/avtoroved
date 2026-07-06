"""
protocol/token_card.py — обогащённая карточка токена (инспектор токенов).

Собирает по одному токену документа всё, что знают ЛОКАЛЬНЫЕ словарные базы
проекта (частотность НКРЯ, регистровая стратификация, тональность RuSentiLex,
морфология из БД протокола), плюс СПРАВОЧНЫЕ ссылки на внешние словари
(Викисловарь, Грамота.ру, КартаСлов, Академик).

Конфиденциальность: анализ полностью офлайн; в интернет уходит только клик
эксперта по ссылке для конкретного слова — сами тексты никуда не передаются.
"""
from __future__ import annotations

import urllib.parse
from typing import Any, Callable, Optional

# ── Внешние словари (открываются в браузере по клику) ────────────────────────
def dictionary_links(word: str, lemma: str) -> list[tuple[str, str]]:
    """Справочные ссылки для слова: (название, URL)."""
    lem = urllib.parse.quote(lemma or word)
    wrd = urllib.parse.quote(word)
    return [
        ("Викисловарь", f"https://ru.wiktionary.org/wiki/{lem}"),
        ("Грамота.ру", f"https://gramota.ru/poisk?query={wrd}&mode=slovari"),
        ("КартаСлов", f"https://kartaslov.ru/значение-слова/{lem}"),
        ("Академик", f"https://dic.academic.ru/searchall.php?SWord={lem}"),
    ]


# ── Частотность (НКРЯ, локальный словарь freq_engine) ────────────────────────
def frequency_info(freq_engine: Any, lemma: str) -> dict:
    """{rank, ipm, band, band_label} или band='absent', если слова нет в НКРЯ."""
    out = {"rank": 0, "ipm": 0.0, "band": "absent",
           "band_label": "Отсутствует в НКРЯ"}
    if freq_engine is None:
        return out
    try:
        from analyzer.freq_engine import BANDS
        hit = freq_engine.lookup(lemma)
        if hit:
            rank, ipm, _pos = hit
            band = freq_engine._band_for(rank)
            out.update(rank=rank, ipm=ipm, band=band,
                       band_label=BANDS.get(band, {}).get("label", band))
    except Exception:
        pass
    return out


def strat_info(strat_lookup: Optional[Callable[[str], Optional[str]]],
               lemma: str) -> dict:
    """{layer, layer_label} по регистровой стратификации (или нейтральный)."""
    out = {"layer": "", "layer_label": "нейтральная / вне словаря"}
    if strat_lookup is None:
        return out
    try:
        from analyzer.stratification_engine import LAYER_META
        layer = strat_lookup(lemma)
        if layer:
            out["layer"] = layer
            out["layer_label"] = LAYER_META.get(layer, {}).get("label", layer)
    except Exception:
        pass
    return out


def senti_info(senti_engine: Any, lemma: str) -> dict:
    """{sentiment, senti_type} по RuSentiLex (или нейтрально)."""
    out = {"sentiment": "", "senti_type": ""}
    if senti_engine is None:
        return out
    try:
        hit = senti_engine.lookup(lemma)
        if hit:
            out["sentiment"], out["senti_type"] = hit[0], hit[1]
    except Exception:
        pass
    return out


# ── Сборка карточки ──────────────────────────────────────────────────────────
def build_card(
    token: dict,
    lemma_counts: dict[str, int],
    freq_engine: Any = None,
    strat_lookup: Optional[Callable[[str], Optional[str]]] = None,
    senti_engine: Any = None,
) -> dict:
    """
    Полная карточка токена.
    token: {text, lemma, pos, feats, sent_idx, idx}; lemma_counts — частоты
    лемм в ЭТОМ документе (для hapax и счётчика употреблений).
    """
    word = token.get("text") or ""
    lemma = (token.get("lemma") or word).lower()
    count = lemma_counts.get(lemma, 0)

    card = {
        "word": word,
        "lemma": lemma,
        "pos": token.get("pos") or "",
        "feats": token.get("feats") or "—",
        "sent_idx": token.get("sent_idx"),
        "count_in_doc": count,
        "is_hapax": count == 1,
        "links": dictionary_links(word, lemma),
    }
    card.update(frequency_info(freq_engine, lemma))
    card.update(strat_info(strat_lookup, lemma))
    card.update(senti_info(senti_engine, lemma))

    # Бейджи для эксперта: сочетания, интересные для идиостиля.
    badges: list[str] = []
    if card["is_hapax"]:
        badges.append("hapax в документе")
    if card["band"] in ("rare", "absent"):
        badges.append("редкое слово")
    if card["layer"] and card["layer"] not in ("book_neutral", "neutral"):
        badges.append("маркированный регистр")
    if card["sentiment"] and card["sentiment"] != "neutral":
        badges.append(f"тональность: {card['sentiment']}")
    if len(badges) >= 2:
        badges.insert(0, "★ потенциальный маркер идиостиля")
    card["badges"] = badges
    return card
