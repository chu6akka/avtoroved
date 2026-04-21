"""
Модуль статистического анализа и POS-биграмм.
"""
from __future__ import annotations
import math
import re
import statistics
from collections import Counter
from typing import List, Dict

from analyzer.stanza_backend import TokenInfo, UPOS_RU, UPOS_SHORT, WORD_RE

STYLE_MARKERS = {
    "частицы": ["же", "ли", "вот", "ну", "уж", "даже", "лишь", "только"],
    "связки": ["в общем", "короче", "на самом деле", "так сказать", "как бы"],
    "союзы": ["потому что", "так как", "однако", "поэтому", "следовательно"],
}


def calculate_pos_bigrams(tokens: List[TokenInfo]) -> Dict:
    """
    Вычисление коэффициентов сочетаемости частеречных пар (POS-биграммы).
    Научная основа: Litvinova et al. (2015-2016).
    """
    words = [t for t in tokens if t.pos != "PUNCT" and WORD_RE.search(t.text)]
    if len(words) < 2:
        return {"bigram_counts": Counter(), "bigram_freq": {}, "matrix": {},
                "top_bigrams": [], "pos_labels": [], "total_bigrams": 0}

    bigrams = [(words[i].pos, words[i + 1].pos) for i in range(len(words) - 1)]
    bigram_counts = Counter(bigrams)
    total_bigrams = len(bigrams)

    bigram_freq = {bg: round(cnt / total_bigrams, 5) for bg, cnt in bigram_counts.items()}

    pos_set = sorted(set(t.pos for t in words))
    matrix = {}
    for p1 in pos_set:
        matrix[p1] = {}
        for p2 in pos_set:
            matrix[p1][p2] = bigram_freq.get((p1, p2), 0.0)

    top = sorted(bigram_counts.items(), key=lambda x: -x[1])[:20]
    top_bigrams = [
        {
            "pair": bg,
            "pair_ru": f"{UPOS_SHORT.get(bg[0], bg[0])}→{UPOS_SHORT.get(bg[1], bg[1])}",
            "pair_full": f"{UPOS_RU.get(bg[0], bg[0])} → {UPOS_RU.get(bg[1], bg[1])}",
            "count": cnt,
            "freq": round(cnt / total_bigrams, 4),
        }
        for bg, cnt in top
    ]

    return {
        "bigram_counts": bigram_counts,
        "bigram_freq": bigram_freq,
        "matrix": matrix,
        "top_bigrams": top_bigrams,
        "pos_labels": pos_set,
        "total_bigrams": total_bigrams,
    }


def calculate_morph_stats(tokens: List[TokenInfo]) -> dict:
    """
    Статистика морфологических признаков на 100 слов.

    Возвращает словарь категорий:
      { категория: { значение: count_per_100 } }

    Включает: Падеж, Число, Род, Вид, Время, Наклонение,
              Форма_глагола, Одушевлённость.
    """
    words = [t for t in tokens if WORD_RE.search(t.text) and t.pos != "PUNCT"]
    total = len(words)
    if total == 0:
        return {}

    # Интересующие категории → кандидаты ключей в feats-строке
    CATEGORIES = {
        "Падеж":           "Падеж",
        "Число":           "Число",
        "Род":             "Род",
        "Вид":             "Вид",
        "Время":           "Время",
        "Наклонение":      "Наклонение",
        "Форма глагола":   "Форма глагола",
        "Одушевлённость":  "Одушевлённость",
    }

    raw: dict[str, Counter] = {cat: Counter() for cat in CATEGORIES}

    for tok in words:
        feats = tok.feats or ""
        if feats == "—" or not feats:
            continue
        # Формат: "Ключ: значение; Ключ2: значение2"
        for chunk in feats.split(";"):
            chunk = chunk.strip()
            if ": " not in chunk:
                continue
            key, val = chunk.split(": ", 1)
            key = key.strip()
            val = val.strip().lower()
            if key in CATEGORIES:
                raw[key][val] += 1

    # Нормировать на 100 слов, убрать пустые категории
    result: dict[str, dict] = {}
    for cat, counter in raw.items():
        if not counter:
            continue
        result[cat] = {
            val: round(cnt / total * 100, 2)
            for val, cnt in sorted(counter.items(), key=lambda x: -x[1])
        }

    return result


def _feat(tok: TokenInfo, key: str) -> str:
    """Вернуть значение морфологического признака из tok.feats."""
    for part in tok.feats.split(";"):
        part = part.strip()
        if part.startswith(key + ":"):
            return part.split(":", 1)[1].strip()
    return ""


def calculate_sae_coefficients(tokens: List[TokenInfo]) -> dict:
    """
    Вычисление 20 морфологических коэффициентов по методике
    судебной автороведческой экспертизы (С.М. Вул, Е.И. Галяшина).

    Местоимения = PRON + DET (по традиционной рус. грамматике;
      "мой/твой/этот" в UD тегируются как DET, а не PRON)
    Глаголы = VERB + AUX, но без Причастий и Деепричастий
    Краткие прилагательные — через признак Variant: Short
    Притяжательные местоимения — через признак Poss: Yes
    """
    words = [t for t in tokens if WORD_RE.search(t.text) and t.pos != "PUNCT"]
    total = len(words)
    if total == 0:
        return {}

    pos_lbl = Counter(t.pos_label for t in words)

    # ── базовые категории ──────────────────────────────────────────
    # Местоимения (PRON + DET) — в рус. грамматике одна категория
    N_pron = pos_lbl.get("Местоимение", 0) + pos_lbl.get("Определительное слово", 0)
    # Глаголы личной формы (без причастий и деепричастий, но с вспомогательными)
    N_verb = pos_lbl.get("Глагол", 0) + pos_lbl.get("Вспомогательный глагол", 0)
    N_adj  = pos_lbl.get("Прилагательное", 0)
    N_adv  = pos_lbl.get("Наречие", 0)
    N_noun = pos_lbl.get("Существительное", 0) + pos_lbl.get("Имя собственное", 0)
    N_part = pos_lbl.get("Причастие", 0)       # VerbForm=Part
    N_conv = pos_lbl.get("Деепричастие", 0)    # VerbForm=Conv
    N_num  = pos_lbl.get("Числительное", 0)
    N_prep = pos_lbl.get("Предлог", 0)
    N_ptcl = pos_lbl.get("Частица", 0)
    N_conj = (pos_lbl.get("Сочинительный союз", 0)
              + pos_lbl.get("Подчинительный союз", 0))

    # ── подкатегории из морф. признаков ────────────────────────────
    # Краткие прилагательные (Variant: Short)
    N_short_adj = sum(
        1 for t in words
        if t.pos_label == "Прилагательное" and "Variant: Short" in t.feats
    )
    # Притяжательные местоимения (Poss: Yes) — PRON или DET
    N_poss = sum(
        1 for t in words
        if t.pos in ("PRON", "DET") and "Poss: Yes" in t.feats
    )
    # Личные местоимения (PronType: Prs)
    N_pers = sum(
        1 for t in words
        if t.pos == "PRON" and "PronType: Prs" in t.feats
    )

    def _k(a: int, b: int) -> str:
        """Форматирует коэффициент: числитель/знаменатель = значение."""
        if b == 0:
            return f"{a}/0 = н/д"
        return f"{a}/{b} = {round(a / b, 3)}"

    coefficients = [
        # (номер, описание, числитель, знаменатель)
        (1,  "Местоимения / текст",                           N_pron,          total),
        (2,  "Глаголы / текст",                               N_verb,          total),
        (3,  "Прилагательные / текст",                        N_adj,           total),
        (4,  "Наречия / текст",                               N_adv,           total),
        (5,  "Краткие формы / все прилагательные",            N_short_adj,     N_adj),
        (6,  "Притяжательные местоимения / все местоимения",  N_poss,          N_pron),
        (7,  "Прилагательные / существительные",              N_adj,           N_noun),
        (8,  "Местоимения / прилагательные",                  N_pron,          N_adj),
        (9,  "Существительные / глаголы",                     N_noun,          N_verb),
        (10, "Местоимения / глаголы",                         N_pron,          N_verb),
        (11, "Числительные / текст",                          N_num,           total),
        (12, "Предлоги / текст",                              N_prep,          total),
        (13, "Частицы / текст",                               N_ptcl,          total),
        (14, "Союзы / текст",                                 N_conj,          total),
        (15, "Наречия / прилагательные",                      N_adv,           N_adj),
        (16, "Причастия / текст",                             N_part,          total),
        (17, "Деепричастия / текст",                          N_conv,          total),
        (18, "Глаголы / наречия",                             N_verb,          N_adv),
        (19, "(Прилагательные + Причастия) / Деепричастия",  N_adj + N_part,  N_conv),
        (20, "(Прилагательные + Числительные) / текст",       N_adj + N_num,   total),
    ]

    rows = [
        {
            "n": n,
            "label": lbl,
            "numerator": a,
            "denominator": b,
            "value": round(a / b, 3) if b else None,
            "display": _k(a, b),
        }
        for n, lbl, a, b in coefficients
    ]

    base_counts = {
        "Всего слов": total,
        "Местоимения (PRON + DET)": N_pron,
        "  в т.ч. личные": N_pers,
        "  в т.ч. притяжательные": N_poss,
        "Глаголы (личные формы)": N_verb,
        "Прилагательные": N_adj,
        "  в т.ч. краткие формы": N_short_adj,
        "Наречия": N_adv,
        "Существительные": N_noun,
        "Причастия": N_part,
        "Деепричастия": N_conv,
        "Числительные": N_num,
        "Предлоги": N_prep,
        "Частицы": N_ptcl,
        "Союзы": N_conj,
    }

    return {"rows": rows, "base_counts": base_counts}


def calculate_metrics(tokens: List[TokenInfo], text: str) -> dict:
    words = [t for t in tokens if WORD_RE.search(t.text) and t.pos != "PUNCT"]
    total = len(words)
    if total == 0:
        return {"частоты": {}, "дополнительно": {"Всего слов": 0},
                "профиль_служебных_слов": {}, "pos_bigrams": {}}

    pos_counts = Counter(t.pos_label for t in words)
    freq = {p: {"количество": c, "коэффициент": round(c / total, 4)}
            for p, c in sorted(pos_counts.items(), key=lambda x: (-x[1], x[0]))}

    lemmas = [t.lemma.lower() for t in words]
    sent_lens = [len(WORD_RE.findall(s)) for s in re.split(r"[.!?]+", text) if WORD_RE.findall(s)]
    word_lengths = [len(w.text) for w in words]

    content_set = {"Существительное", "Имя собственное", "Глагол", "Причастие",
                   "Деепричастие", "Прилагательное", "Наречие"}
    function_set = {"Предлог", "Частица", "Сочинительный союз", "Подчинительный союз",
                    "Местоимение", "Определительное слово"}
    content = sum(pos_counts.get(p, 0) for p in content_set)
    function = sum(pos_counts.get(p, 0) for p in function_set)
    noun_cnt = pos_counts.get("Существительное", 0) + pos_counts.get("Имя собственное", 0)
    verb_cnt = pos_counts.get("Глагол", 0) + pos_counts.get("Вспомогательный глагол", 0)

    additional = {
        "Всего слов": total,
        "Всего предложений": len(sent_lens),
        "Средняя длина слова (букв)": round(sum(word_lengths) / len(word_lengths), 2),
        "Лексическое разнообразие (TTR)": round(len(set(w.text.lower() for w in words)) / total, 4),
        "Лемматическое разнообразие": round(len(set(lemmas)) / total, 4),
        "Доля hapax-лемм": round(sum(1 for _, c in Counter(lemmas).items() if c == 1) / total, 4),
        "Средняя длина предложения (слов)": round(sum(sent_lens) / len(sent_lens), 2) if sent_lens else 0.0,
        "Дисперсия длины предложений": round(statistics.pvariance(sent_lens), 2) if len(sent_lens) > 1 else 0.0,
        "Содержательные/служебные": round(content / function, 4) if function else "∞",
        "Существительные/глаголы": round(noun_cnt / verb_cnt, 4) if verb_cnt else "∞",
    }

    lowered = text.lower()
    style_markers = {
        g: {m: len(re.findall(rf"(?<!\w){re.escape(m)}(?!\w)", lowered)) for m in marks}
        for g, marks in STYLE_MARKERS.items()
    }

    pos_bigrams = calculate_pos_bigrams(tokens)
    morph_stats = calculate_morph_stats(tokens)
    morph_indices = calculate_morphological_indices(tokens, text)
    sae = calculate_sae_coefficients(tokens)

    return {
        "частоты": freq,
        "дополнительно": additional,
        "профиль_служебных_слов": style_markers,
        "pos_bigrams": pos_bigrams,
        "morph_stats": morph_stats,
        "morph_indices": morph_indices,
        "sae_coefficients": sae,
    }


def calculate_morphological_indices(tokens: List[TokenInfo], text: str) -> dict:
    """
    20 морфологических индексов идиостиля автора.
    Источник: Лабораторная работа № 11, СФЭ / Соколова Т.П. (МГЮА).
    Возвращает список кортежей (название, числитель, знаменатель, значение|None).
    """
    words = [t for t in tokens if WORD_RE.search(t.text) and t.pos not in ("PUNCT", "SYM")]
    total = len(words)
    if total == 0:
        return {"indices": [], "total_words": 0, "sent_count": 0}

    sent_lens = [len(WORD_RE.findall(s)) for s in re.split(r"[.!?]+", text) if WORD_RE.findall(s)]
    sent_count = max(len(sent_lens), 1)

    def pc(*tags):
        return sum(1 for t in words if t.pos in tags)

    def feat_count(key_ru: str, val_ru: str) -> int:
        needle = f"{key_ru}: {val_ru}"
        return sum(1 for t in words if needle in (t.feats or ""))

    noun        = pc("NOUN")
    propn       = pc("PROPN")
    noun_all    = noun + propn          # существительные + имена собственные
    det         = pc("DET")
    # В традиционной русской грамматике «местоимения» = PRON + DET
    # (DET = местоимения-прилагательные: этот, мой, тот, наш, какой…)
    pron_pron   = pc("PRON")            # только местоимения-существительные (я/ты/он/что)
    pron_all    = pc("PRON", "DET")     # все местоимения (для индексов 2, 5, 10)
    verb        = pc("VERB", "AUX")
    adj         = pc("ADJ")
    adv         = pc("ADV")
    num         = pc("NUM")
    adp         = pc("ADP")
    conj        = pc("CCONJ", "SCONJ")
    part_pos    = pc("PART")

    func_words    = sum(1 for t in words if t.pos in ("ADP", "CCONJ", "SCONJ", "PART", "DET", "INTJ"))
    service_words = sum(1 for t in words if t.pos in ("ADP", "CCONJ", "SCONJ", "PART"))

    PERS_LEMMAS = {"я", "ты", "он", "она", "оно", "мы", "вы", "они"}
    personal_pron = sum(1 for t in words if t.pos == "PRON" and t.lemma.lower() in PERS_LEMMAS)

    verb_pres  = feat_count("Время", "настоящее")
    verb_fut   = feat_count("Время", "будущее")
    verb_past  = feat_count("Время", "прошедшее")
    participles = feat_count("Форма глагола", "причастие")
    gerunds     = feat_count("Форма глагола", "деепричастие")

    # Слова категории состояния (предикативные наречия):
    # Stanza тегирует их как ADV, но в методике Соколовой они учитываются
    # в знаменателе индекса 16 вместе с глаголами, а не в индексе 14 (наречия).
    _PRED_ADV = {
        "можно", "нельзя", "нужно", "надо", "необходимо",
        "жалко", "жаль", "больно", "стыдно", "скучно", "смешно",
        "страшно", "странно", "интересно", "важно",
        "видно", "слышно", "понятно", "ясно",
        "пора", "некогда", "незачем",
    }
    pred_adv = sum(1 for t in words if t.pos == "ADV" and t.lemma.lower() in _PRED_ADV)
    adv_pure = adv - pred_adv          # чистые наречия (для индекса 14)

    # Падежные формы — только существительные и местоимения-существительные
    # (методика Соколовой не включает прилагательные в индекс 19)
    _CASE_POS = ("NOUN", "PROPN", "PRON")
    case_nom   = sum(1 for t in words if t.pos in _CASE_POS and "Падеж: именительный" in (t.feats or ""))
    case_gen   = sum(1 for t in words if t.pos in _CASE_POS and "Падеж: родительный"  in (t.feats or ""))
    case_words = sum(1 for t in words if t.pos in _CASE_POS and "Падеж:"              in (t.feats or ""))

    def r(a, b):
        if b == 0 or a is None or b is None:
            return None
        return round(a / b, 3)

    # Именные ЧР: сущ. + прил. + чист.наречия + числит. + все местоимения
    nominal      = noun_all + adj + adv_pure + num + pron_all
    # Знаменатель индекса 16: глаголы + предикативные наречия (СКС)
    verb_pred    = verb + pred_adv
    # Знаменатель индекса 9: прилагательные + определительные слова + частицы
    adj_det_part = adj + det + part_pos
    verb_pf      = verb_pres + verb_fut

    indices = [
        # Индекс 1: все существительные (NOUN + PROPN) / объём
        ("1. Существительные / объём текста",
         noun_all, total, r(noun_all, total)),
        # Индекс 2: все местоимения (PRON + DET) / объём
        ("2. Местоимения / объём текста",
         pron_all, total, r(pron_all, total)),
        ("3. Глаголы / объём текста",
         verb, total, r(verb, total)),
        # Индекс 4: местоимения-существительные / незнаменательные слова
        ("4. Местоимения / незнаменательные слова",
         pron_pron, func_words, r(pron_pron, func_words)),
        # Индекс 5: личные мест. / все местоимения (PRON + DET)
        ("5. Личные местоимения / все местоимения",
         personal_pron, pron_all, r(personal_pron, pron_all)),
        ("6. Собственные сущ. / все существительные",
         propn, noun_all, r(propn, noun_all)),
        ("7. Абстрактные / конкретные сущ.",
         None, None, None),          # требует семантич. разметки
        ("8. Глаголы наст.+буд. / прошедшее время",
         verb_pf, verb_past, r(verb_pf, verb_past)),
        ("9. Существительные / (прил. + опред. + частицы)",
         noun_all, adj_det_part, r(noun_all, adj_det_part)),
        # Индекс 10: сущ. / все местоимения (PRON + DET)
        ("10. Существительные / местоимения",
         noun_all, pron_all, r(noun_all, pron_all)),
        ("11. Прилагательные / объём текста",
         adj, total, r(adj, total)),
        ("12. Причастия / объём текста",
         participles, total, r(participles, total)),
        ("13. Деепричастия / объём текста",
         gerunds, total, r(gerunds, total)),
        # Индекс 14: чистые наречия (без СКС) / объём
        ("14. Наречия / объём текста",
         adv_pure, total, r(adv_pure, total)),
        ("15. Незнаменательные слова / предложения",
         func_words, sent_count, r(func_words, sent_count)),
        # Индекс 16: именные ЧР / (глаголы + СКС)
        ("16. Именные ЧР / (глаголы + предикативные наречия)",
         nominal, verb_pred, r(nominal, verb_pred)),
        ("17. Служебные слова / объём текста",
         service_words, total, r(service_words, total)),
        ("18. Союзы / предлоги",
         conj, adp, r(conj, adp)),
        # Индекс 19: только NOUN+PROPN+PRON (без ADJ/DET/NUM)
        ("19. (Им. + Род. пад.) / все падежные формы сущ. и мест.",
         case_nom + case_gen, case_words, r(case_nom + case_gen, case_words)),
        ("20. (Глаголы + существительные) / объём текста",
         verb + noun_all, total, r(verb + noun_all, total)),
    ]

    return {
        "indices": indices,
        "total_words": total,
        "sent_count": sent_count,
    }


def calculate_sae_coefficients(tokens: List[TokenInfo]) -> dict:
    """
    Вычисление 20 морфологических коэффициентов по методике
    судебной автороведческой экспертизы (С.М. Вул, Е.И. Галяшина).

    Местоимения = PRON + DET (по традиционной рус. грамматике;
      "мой/твой/этот" в UD тегируются как DET, а не PRON)
    Глаголы = VERB + AUX, но без Причастий и Деепричастий
    Краткие прилагательные — через признак Variant: Short
    Притяжательные местоимения — через признак Poss: Yes
    """
    words = [t for t in tokens if WORD_RE.search(t.text) and t.pos != "PUNCT"]
    total = len(words)
    if total == 0:
        return {}

    pos_lbl = Counter(t.pos_label for t in words)

    # ── базовые категории ──────────────────────────────────────────
    N_pron = pos_lbl.get("Местоимение", 0) + pos_lbl.get("Определительное слово", 0)
    N_verb = pos_lbl.get("Глагол", 0) + pos_lbl.get("Вспомогательный глагол", 0)
    N_adj  = pos_lbl.get("Прилагательное", 0)
    N_adv  = pos_lbl.get("Наречие", 0)
    N_noun = pos_lbl.get("Существительное", 0) + pos_lbl.get("Имя собственное", 0)
    N_part = pos_lbl.get("Причастие", 0)
    N_conv = pos_lbl.get("Деепричастие", 0)
    N_num  = pos_lbl.get("Числительное", 0)
    N_prep = pos_lbl.get("Предлог", 0)
    N_ptcl = pos_lbl.get("Частица", 0)
    N_conj = (pos_lbl.get("Сочинительный союз", 0)
              + pos_lbl.get("Подчинительный союз", 0))

    # ── подкатегории из морф. признаков ────────────────────────────
    N_short_adj = sum(
        1 for t in words
        if t.pos_label == "Прилагательное" and "Variant: Short" in t.feats
    )
    N_poss = sum(
        1 for t in words
        if t.pos in ("PRON", "DET") and "Poss: Yes" in t.feats
    )
    N_pers = sum(
        1 for t in words
        if t.pos == "PRON" and "PronType: Prs" in t.feats
    )

    def _k(a: int, b: int) -> str:
        if b == 0:
            return f"{a}/0 = н/д"
        return f"{a}/{b} = {round(a / b, 3)}"

    coefficients = [
        (1,  "Местоимения / текст",                           N_pron,          total),
        (2,  "Глаголы / текст",                               N_verb,          total),
        (3,  "Прилагательные / текст",                        N_adj,           total),
        (4,  "Наречия / текст",                               N_adv,           total),
        (5,  "Краткие формы / все прилагательные",            N_short_adj,     N_adj),
        (6,  "Притяжательные местоимения / все местоимения",  N_poss,          N_pron),
        (7,  "Прилагательные / существительные",              N_adj,           N_noun),
        (8,  "Местоимения / прилагательные",                  N_pron,          N_adj),
        (9,  "Существительные / глаголы",                     N_noun,          N_verb),
        (10, "Местоимения / глаголы",                         N_pron,          N_verb),
        (11, "Числительные / текст",                          N_num,           total),
        (12, "Предлоги / текст",                              N_prep,          total),
        (13, "Частицы / текст",                               N_ptcl,          total),
        (14, "Союзы / текст",                                 N_conj,          total),
        (15, "Наречия / прилагательные",                      N_adv,           N_adj),
        (16, "Причастия / текст",                             N_part,          total),
        (17, "Деепричастия / текст",                          N_conv,          total),
        (18, "Глаголы / наречия",                             N_verb,          N_adv),
        (19, "(Прилагательные + Причастия) / Деепричастия",  N_adj + N_part,  N_conv),
        (20, "(Прилагательные + Числительные) / текст",       N_adj + N_num,   total),
    ]

    rows = [
        {
            "n": n,
            "label": lbl,
            "numerator": a,
            "denominator": b,
            "value": round(a / b, 3) if b else None,
            "display": _k(a, b),
        }
        for n, lbl, a, b in coefficients
    ]

    base_counts = {
        "Всего слов": total,
        "Местоимения (PRON + DET)": N_pron,
        "  в т.ч. личные": N_pers,
        "  в т.ч. притяжательные": N_poss,
        "Глаголы (личные формы)": N_verb,
        "Прилагательные": N_adj,
        "  в т.ч. краткие формы": N_short_adj,
        "Наречия": N_adv,
        "Существительные": N_noun,
        "Причастия": N_part,
        "Деепричастия": N_conv,
        "Числительные": N_num,
        "Предлоги": N_prep,
        "Частицы": N_ptcl,
        "Союзы": N_conj,
    }

    return {"rows": rows, "base_counts": base_counts}


def bigram_similarity(freq1: dict, freq2: dict) -> float:
    """Косинусное сходство POS-биграммных профилей."""
    all_keys = set(freq1.keys()) | set(freq2.keys())
    if not all_keys:
        return 0.0
    dot = sum(freq1.get(k, 0) * freq2.get(k, 0) for k in all_keys)
    n1 = math.sqrt(sum(v * v for v in freq1.values())) or 1e-9
    n2 = math.sqrt(sum(v * v for v in freq2.values())) or 1e-9
    return dot / (n1 * n2)


def compare_texts(tokens1: List[TokenInfo], tokens2: List[TokenInfo],
                  text1: str, text2: str) -> dict:
    w1 = [t for t in tokens1 if t.pos != "PUNCT" and WORD_RE.search(t.text)]
    w2 = [t for t in tokens2 if t.pos != "PUNCT" and WORD_RE.search(t.text)]

    lemmas1 = [t.lemma.lower() for t in w1]
    lemmas2 = [t.lemma.lower() for t in w2]
    set1, set2 = set(lemmas1), set(lemmas2)
    common_lemmas = set1 & set2
    jaccard = len(common_lemmas) / len(set1 | set2) if (set1 | set2) else 0

    pos1 = Counter(t.pos_label for t in w1)
    pos2 = Counter(t.pos_label for t in w2)
    all_pos = set(pos1.keys()) | set(pos2.keys())
    tot1, tot2 = max(sum(pos1.values()), 1), max(sum(pos2.values()), 1)
    pos_diff = sum(abs(pos1.get(p, 0) / tot1 - pos2.get(p, 0) / tot2) for p in all_pos)
    pos_sim = max(0, 1 - pos_diff / 2)

    sl1 = [len(WORD_RE.findall(s)) for s in re.split(r'[.!?]+', text1) if WORD_RE.findall(s)]
    sl2 = [len(WORD_RE.findall(s)) for s in re.split(r'[.!?]+', text2) if WORD_RE.findall(s)]
    avg1 = sum(sl1) / len(sl1) if sl1 else 0
    avg2 = sum(sl2) / len(sl2) if sl2 else 0
    syn_sim = max(0, 1 - abs(avg1 - avg2) / max(avg1, avg2, 1))

    ttr1 = len(set1) / max(len(lemmas1), 1)
    ttr2 = len(set2) / max(len(lemmas2), 1)
    ttr_sim = max(0, 1 - abs(ttr1 - ttr2) / max(ttr1, ttr2, 0.01))

    bg1 = calculate_pos_bigrams(tokens1)
    bg2 = calculate_pos_bigrams(tokens2)
    bg_sim = bigram_similarity(bg1["bigram_freq"], bg2["bigram_freq"])

    overall = jaccard * 0.30 + pos_sim * 0.20 + syn_sim * 0.15 + ttr_sim * 0.15 + bg_sim * 0.20

    service = {"и", "в", "не", "на", "с", "что", "а", "по", "это", "к", "но", "из",
               "у", "за", "о", "же", "от", "он", "она", "оно", "его", "её", "их",
               "все", "бы", "как", "мы", "вы", "они", "если", "или", "ни", "при",
               "до", "тот", "эта", "этот", "быть", "который", "свой", "весь"}
    meaningful = sorted(common_lemmas - service,
                        key=lambda x: -(Counter(lemmas1)[x] + Counter(lemmas2)[x]))[:30]

    return {
        "overall": round(overall, 3),
        "jaccard": round(jaccard, 3),
        "pos_similarity": round(pos_sim, 3),
        "syntactic_similarity": round(syn_sim, 3),
        "ttr_similarity": round(ttr_sim, 3),
        "bigram_similarity": round(bg_sim, 3),
        "common_lemmas": meaningful,
        "words1": len(w1), "words2": len(w2),
        "ttr1": round(ttr1, 4), "ttr2": round(ttr2, 4),
        "avg_sent1": round(avg1, 1), "avg_sent2": round(avg2, 1),
    }
