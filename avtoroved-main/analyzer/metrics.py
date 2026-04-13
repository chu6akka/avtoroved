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

    return {
        "частоты": freq,
        "дополнительно": additional,
        "профиль_служебных_слов": style_markers,
        "pos_bigrams": pos_bigrams,
        "morph_stats": morph_stats,
        "morph_indices": morph_indices,
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
    noun_all    = noun + propn
    pron        = pc("PRON")
    verb        = pc("VERB", "AUX")
    adj         = pc("ADJ")
    adv         = pc("ADV")
    num         = pc("NUM")
    adp         = pc("ADP")
    conj        = pc("CCONJ", "SCONJ")
    part_pos    = pc("PART")
    det         = pc("DET")

    func_words    = sum(1 for t in words if t.pos in ("ADP", "CCONJ", "SCONJ", "PART", "DET", "INTJ"))
    service_words = sum(1 for t in words if t.pos in ("ADP", "CCONJ", "SCONJ", "PART"))

    PERS_LEMMAS = {"я", "ты", "он", "она", "оно", "мы", "вы", "они"}
    personal_pron = sum(1 for t in words if t.pos == "PRON" and t.lemma.lower() in PERS_LEMMAS)

    verb_pres  = feat_count("Время", "настоящее")
    verb_fut   = feat_count("Время", "будущее")
    verb_past  = feat_count("Время", "прошедшее")
    participles = feat_count("Форма глагола", "причастие")
    gerunds     = feat_count("Форма глагола", "деепричастие")

    case_nom   = feat_count("Падеж", "именительный")
    case_gen   = feat_count("Падеж", "родительный")
    case_words = sum(1 for t in words
                     if t.pos in ("NOUN", "PROPN", "PRON", "ADJ", "DET", "NUM")
                     and "Падеж:" in (t.feats or ""))

    def r(a, b):
        if b == 0 or a is None or b is None:
            return None
        return round(a / b, 3)

    adj_det_part = adj + det + part_pos
    nominal      = noun_all + adj + adv + num + pron
    verb_pf      = verb_pres + verb_fut

    indices = [
        ("1. Существительные / объём текста",
         noun, total, r(noun, total)),
        ("2. Местоимения / объём текста",
         pron, total, r(pron, total)),
        ("3. Глаголы / объём текста",
         verb, total, r(verb, total)),
        ("4. Местоимения / незнаменательные слова",
         pron, func_words, r(pron, func_words)),
        ("5. Личные местоимения / все местоимения",
         personal_pron, pron, r(personal_pron, pron)),
        ("6. Собственные сущ. / все существительные",
         propn, noun_all, r(propn, noun_all)),
        ("7. Абстрактные / конкретные сущ.",
         None, None, None),          # требует семантич. разметки
        ("8. Глаголы наст.+буд. / прошедшее время",
         verb_pf, verb_past, r(verb_pf, verb_past)),
        ("9. Существительные / (прил. + опред. + частицы)",
         noun_all, adj_det_part, r(noun_all, adj_det_part)),
        ("10. Существительные / местоимения",
         noun_all, pron, r(noun_all, pron)),
        ("11. Прилагательные / объём текста",
         adj, total, r(adj, total)),
        ("12. Причастия / объём текста",
         participles, total, r(participles, total)),
        ("13. Деепричастия / объём текста",
         gerunds, total, r(gerunds, total)),
        ("14. Наречия / объём текста",
         adv, total, r(adv, total)),
        ("15. Незнаменательные слова / предложения",
         func_words, sent_count, r(func_words, sent_count)),
        ("16. Именные ЧР / глаголы",
         nominal, verb, r(nominal, verb)),
        ("17. Служебные слова / объём текста",
         service_words, total, r(service_words, total)),
        ("18. Союзы / предлоги",
         conj, adp, r(conj, adp)),
        ("19. (Им. + Род. пад.) / все падежные формы",
         case_nom + case_gen, case_words, r(case_nom + case_gen, case_words)),
        ("20. (Глаголы + существительные) / объём текста",
         verb + noun_all, total, r(verb + noun_all, total)),
    ]

    return {
        "indices": indices,
        "total_words": total,
        "sent_count": sent_count,
    }


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
