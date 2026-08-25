"""
protocol/profile.py — стадия «раздельное исследование» (Задача 2Б).

Строит профиль КАЖДОГО текста по отдельности (до всякого сравнения — требование
стадийности по Огорелкову/Моисеевой) и складывает его в таблицу feature_candidates.
Сравнения здесь НЕТ. UI «принять/отклонить признак» здесь НЕТ — но данные
записываются так, чтобы следующий этап пристыковался без переделок
(role/source_kind/method_feature_id заполняются вместе с legacy kind).

Переиспользуются существующие модули анализа (analyzer.*), NLP не дублируется:
токены даёт уже инициализированный в приложении бэкенд (StanzaBackend).
Тяжёлых новых зависимостей нет.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from protocol import db as protocol_db
from protocol import detector_filter
from protocol import feature_model as model

# ── Группы (по методике: 4 группы признаков) ─────────────────────────────────
GROUP_SEMANTIC = "смысловые"
GROUP_TEXTOLOGICAL = "текстологические"
GROUP_LINGUISTIC = "языковые"
GROUP_PSYCHO = "психолингвистические"

# ── Подгруппы языковой группы ────────────────────────────────────────────────
SUB_LEXICAL = "лексические"
SUB_STYLISTIC = "стилистические"
SUB_SYNTACTIC = "синтаксические"
SUB_MORPHOLOGICAL = "морфологические"
SUB_ORTHOGRAPHIC = "орфографические"
SUB_PUNCTUATION = "пунктуационные"
SUB_GRAMMAR = "грамматические"
SUB_INTERNET = "интернет-коммуникация"
SUB_FUNCTION_WORDS = "служебная лексика"

# ── Пороги отбора лемм-кандидатов служебной лексики (Огорелков) ──────────────
# ВНИМАНИЕ: пороги ИНСТРУМЕНТАЛЬНЫЕ — отсев статистического шума, чтобы карта
# признаков не захлебнулась единичными словоупотреблениями. Методика
# Огорелкова (гл. 3, п. 3.2–3.4) значений отсечки не устанавливает: она даёт
# аппарат наблюдения (закрытый перечень классов + ipm-нормирование по НКРЯ).
# Лемма попадает в кандидаты, если отклонение от нормы вне [0.5; 2.0]
# И вхождений не меньше 3.
OGORELKOV_RATIO_LOW = 0.5
OGORELKOV_RATIO_HIGH = 2.0
OGORELKOV_MIN_COUNT = 3

# Порог уверенности тематической атрибуции: ниже — домен не показывается
# вовсе (движок ранее выдавал «доминирующую тему» даже при cosine ~0.06,
# что на разговорных текстах давало мусорные атрибуции).
THEMATIC_MIN_COSINE = 0.15
THEMATIC_WEAK_COSINE = 0.25   # 0.15–0.25 — пометка «слабая атрибуция»

# Спец-значение надёжности для сырых срабатываний, подавленных фильтром:
# сохраняются для воспроизводимости, в карту признаков не попадают,
# в UI показываются отдельным переключателем.
RELIABILITY_SUPPRESSED = "подавлен"

# ── Виды элементов ───────────────────────────────────────────────────────────
KIND_COUNTER = "счётчик"
KIND_CANDIDATE = "кандидат_признак"
KIND_GENERAL = "общий_признак"      # степени развития навыков (общие признаки ПР)

# Навыки, выносимые в протокольный контур как общие признаки.
# Грамматический и лексико-фразеологический — решающие по Вулу (2007, с. 38),
# орфографический и пунктуационный — чувствительны к автокоррекции.
GENERAL_SKILLS = {
    "Орфографический навык": "орфографический",
    "Пунктуационный навык": "пунктуационный",
    "Грамматический навык": "грамматический",
    "Лексико-фразеологический навык": "лексико-фразеологический",
}
# Подгруппы, ненадёжные при автокоррекции (цифровой/опубликованный текст).
_AUTOCORRECT_SENSITIVE = ("орфографический", "пунктуационный")

# Пометки надёжности для кандидатов ошибок.
NOTE_NEEDS_REVIEW = "требует проверки"
NOTE_UNRELIABLE_AUTOCORRECT = "ненадёжен (автокоррекция)"

# Маппинг типа ошибки (TextError.error_type) → подгруппа.
_ERROR_SUBGROUP = {
    "Орфографическая": SUB_ORTHOGRAPHIC,
    "Пунктуационная": SUB_PUNCTUATION,
    "Грамматическая": SUB_GRAMMAR,
    "Лексическая": SUB_LEXICAL,
    "Стилистическая": SUB_STYLISTIC,
}

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+")

# Максимум единичных психолингвистических кандидатов (только подсветка).
MAX_PSYCHO_CANDIDATES = 10


def _c(group: str, kind: str, label: str, value: Any = None,
       subgroup: Optional[str] = None, fragment: Optional[str] = None,
       source: Optional[str] = None, role: Optional[str] = None,
       source_kind: str = model.SOURCE_ENGINEERING,
       method_feature_id: Optional[str] = None,
       method_reference_informativeness: Optional[str] = None,
       detection_reliability: str = "") -> dict:
    """Собрать один элемент профиля в формате feature_candidates."""
    if role is None:
        role = (model.AUX_METRIC if kind == KIND_COUNTER else
                model.GENERAL_SKILL if kind == KIND_GENERAL else model.EVIDENCE)
    return {
        "group_name": group, "subgroup": subgroup, "kind": kind,
        "label": label, "value": None if value is None else str(value),
        "fragment": fragment, "source": source,
        "role": role, "source_kind": source_kind,
        "method_feature_id": method_feature_id,
        "method_reference_informativeness": method_reference_informativeness,
        "expert_identification_value": None,
        "detection_reliability": detection_reliability,
        # Legacy-поле не является решением эксперта и для новых записей пусто.
        "id_value": "",
        "reliability": detection_reliability,
    }


# ── 1. Смысловые (тематические): engineering detection ≠ экспертная оценка ──
def semantic_candidates(thematic_result: Any) -> list[dict]:
    out: list[dict] = []
    if thematic_result is None:
        return out
    for d in getattr(thematic_result, "top_domains", []) or []:
        # Ниже порога уверенности домен не показываем вообще: атрибуция
        # с cosine ~0.06–0.1 — шум словарных пересечений, не тема текста.
        if d.cosine < THEMATIC_MIN_COSINE:
            continue
        weak = " · слабая атрибуция" if d.cosine < THEMATIC_WEAK_COSINE else ""
        examples = ", ".join(getattr(d, "examples", [])[:5])
        registered = model.registry_by_detector_key().get(getattr(d, "key", ""))
        detection_reliability = ("низкая" if d.cosine < THEMATIC_WEAK_COSINE
                                 else "средняя")
        out.append(_c(
            GROUP_SEMANTIC,
            KIND_CANDIDATE if registered else KIND_COUNTER,
            registered["label"] if registered else f"Доминирующая тема: {d.label}",
            value=f"cosine {d.cosine:.2f}, совпадений лемм {d.match_count}{weak}",
            subgroup="тематические", fragment=examples or None,
            source="thematic_engine",
            role=model.METHOD_FEATURE if registered else model.AUX_METRIC,
            source_kind=model.SOURCE_METHOD if registered else model.SOURCE_ENGINEERING,
            method_feature_id=registered["id"] if registered else None,
            method_reference_informativeness=(
                registered["reference_informativeness"] if registered else None),
            detection_reliability=detection_reliability))
    return out


# ── 2. Текстологические: архитектоника (счётчики) ────────────────────────────
def textological_candidates(metrics: dict, text: str) -> list[dict]:
    out: list[dict] = []
    add = (metrics or {}).get("дополнительно", {})

    paragraphs = [p for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    n_par = len(paragraphs)
    par_lens = [len(_WORD_RE.findall(p)) for p in paragraphs]
    avg_par = round(sum(par_lens) / n_par, 1) if n_par else 0

    out.append(_c(GROUP_TEXTOLOGICAL, KIND_COUNTER, "Число абзацев",
                  n_par, subgroup="архитектоника", source="profile"))
    out.append(_c(GROUP_TEXTOLOGICAL, KIND_COUNTER, "Средняя длина абзаца (слов)",
                  avg_par, subgroup="архитектоника", source="profile"))
    for key in ("Всего слов", "Всего предложений",
                "Средняя длина предложения (слов)", "Дисперсия длины предложений"):
        if key in add:
            out.append(_c(GROUP_TEXTOLOGICAL, KIND_COUNTER, key, add[key],
                          subgroup="архитектоника", source="metrics"))
    return out


# ── 3а. Языковые / лексические: TTR, hapax, стратификация ────────────────────
def lexical_candidates(metrics: dict, strat_result: Any) -> list[dict]:
    out: list[dict] = []
    add = (metrics or {}).get("дополнительно", {})
    for key in ("Лексическое разнообразие (TTR)", "Лемматическое разнообразие",
                "Доля hapax-лемм", "Средняя длина слова (букв)"):
        if key in add:
            out.append(_c(GROUP_LINGUISTIC, KIND_COUNTER, key, add[key],
                          subgroup=SUB_LEXICAL, source="metrics"))
    if strat_result is not None:
        for layer, cnt in sorted((strat_result.layer_counts or {}).items(),
                                 key=lambda x: -x[1]):
            words = ", ".join((strat_result.layer_words or {}).get(layer, [])[:5])
            out.append(_c(GROUP_LINGUISTIC, KIND_COUNTER,
                          f"Регистровый слой: {layer}", cnt,
                          subgroup=SUB_LEXICAL, fragment=words or None,
                          source="stratification_engine"))
        out.append(_c(GROUP_LINGUISTIC, KIND_COUNTER,
                      "Доля нелитературной лексики",
                      f"{strat_result.marked_ratio:.1%}",
                      subgroup=SUB_LEXICAL, source="stratification_engine"))
    return out


# ── 3б. Языковые / стилистические: маркеры, интернет-профиль ─────────────────
def stylistic_candidates(metrics: dict, internet_profile: Any) -> list[dict]:
    out: list[dict] = []
    style = (metrics or {}).get("профиль_служебных_слов", {})
    for group_name, markers in style.items():
        found = {m: c for m, c in markers.items() if c > 0}
        if not found:
            continue
        total = sum(found.values())
        frag = ", ".join(f"{m}×{c}" for m, c in sorted(found.items(), key=lambda x: -x[1])[:6])
        out.append(_c(GROUP_LINGUISTIC, KIND_COUNTER,
                      f"Стилевые маркеры: {group_name}", total,
                      subgroup=SUB_STYLISTIC, fragment=frag, source="metrics"))
    if internet_profile is not None:
        pairs = [
            ("Эмодзи", internet_profile.emoji_count, SUB_INTERNET),
            ("Эмотиконы", internet_profile.emoticon_count, SUB_INTERNET),
            ("Хэштеги", internet_profile.hashtag_count, SUB_INTERNET),
            ("Слова КАПСОМ", internet_profile.caps_words, SUB_INTERNET),
            ("Интернет-сленг", internet_profile.slang_count, SUB_INTERNET),
            ("Аббревиатуры", internet_profile.abbreviation_count, SUB_INTERNET),
            ("Повторная пунктуация (!!, ??)", internet_profile.repeated_punct_count,
             SUB_PUNCTUATION),
        ]
        for label, cnt, subgroup in pairs:
            if cnt:
                out.append(_c(GROUP_LINGUISTIC, KIND_COUNTER,
                              f"Интернет-коммуникация: {label}", cnt,
                              subgroup=subgroup, source="errors.internet",
                              role=model.AUX_METRIC,
                              source_kind=model.SOURCE_EXPERIMENTAL))
    return out


# ── 3в. Языковые: морфологические POS-метрики и типы предложений ─────────────
def syntactic_candidates(metrics: dict, text: str) -> list[dict]:
    out: list[dict] = []
    freq = (metrics or {}).get("частоты", {})
    for pos_label, data in list(freq.items())[:8]:
        out.append(_c(GROUP_LINGUISTIC, KIND_COUNTER,
                      f"Доля POS: {pos_label}",
                      f"{data['коэффициент']:.3f} ({data['количество']})",
                      subgroup=SUB_MORPHOLOGICAL, source="metrics"))
    # Типы предложений по финальному знаку.
    sents = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", text or "") if s.strip()]
    if sents:
        q = sum(1 for s in sents if s.endswith("?"))
        e = sum(1 for s in sents if s.endswith("!"))
        ell = sum(1 for s in sents if s.endswith("…") or s.endswith("..."))
        out.append(_c(GROUP_LINGUISTIC, KIND_COUNTER, "Вопросительные предложения",
                      q, subgroup=SUB_SYNTACTIC, source="profile"))
        out.append(_c(GROUP_LINGUISTIC, KIND_COUNTER, "Восклицательные предложения",
                      e, subgroup=SUB_PUNCTUATION, source="profile"))
        out.append(_c(GROUP_LINGUISTIC, KIND_COUNTER, "Предложения с многоточием",
                      ell, subgroup=SUB_PUNCTUATION, source="profile"))
    return out


# ── 3г. Языковые / орфография+пунктуация: кандидаты из модуля ошибок ─────────
def error_candidates(errors: list, autocorrect_unreliable: bool,
                     reliabilities: Optional[list[str]] = None) -> list[dict]:
    """
    Кандидаты признаков из ошибок (TextError). По умолчанию каждый помечен
    «требует проверки»; при флаге автокоррекции из suitability — «ненадёжен
    (автокоррекция)» (орфографические и пунктуационные признаки искажены).

    reliabilities — надёжность каждого срабатывания из слоя фильтрации
    (protocol/detector_filter.py), позиционно к errors. Флаг автокоррекции
    дополнительно понижает надёжность до «низкая».
    """
    def _downgrade(rel: str) -> str:
        # Автокоррекция понижает надёжность НА ОДНУ ступень (а не глушит всё
        # в «низкая» скопом — иначе экран кандидатов пустеет целиком).
        return {"высокая": "средняя", "средняя": "низкая",
                "": "низкая", "низкая": "низкая"}.get(rel, "низкая")

    out: list[dict] = []
    for i, err in enumerate(errors or []):
        subgroup = _ERROR_SUBGROUP.get(err.error_type, SUB_ORTHOGRAPHIC)
        desc = err.description or err.subtype or err.error_type
        rel = reliabilities[i] if reliabilities and i < len(reliabilities) else ""
        note = NOTE_NEEDS_REVIEW
        # Автокоррекция искажает только орфографию и пунктуацию — грамматика
        # и лексика от неё не страдают и надёжность не теряют.
        if autocorrect_unreliable and subgroup in (SUB_ORTHOGRAPHIC, SUB_PUNCTUATION):
            note = NOTE_UNRELIABLE_AUTOCORRECT
            rel = _downgrade(rel)
        c = _c(
            GROUP_LINGUISTIC, KIND_CANDIDATE,
            f"{err.error_type}: {err.subtype or 'без подтипа'}",
            value=f"{desc} · {note}",
            subgroup=subgroup,
            fragment=err.fragment or err.context or None,
            # rule_ref (напр. LT:MORFOLOGIK_RULE_RU_RU) — чтобы правило можно
            # было найти и занести в detector_filter.json прямо из UI.
            source=getattr(err, "rule_ref", "") or err.source or "errors",
            role=model.EVIDENCE, source_kind=model.SOURCE_ENGINEERING,
            detection_reliability=rel)
        out.append(c)
    return out


def suppressed_candidates(suppressed_hits: list) -> list[dict]:
    """
    Сырые срабатывания детектора, ПОДАВЛЕННЫЕ фильтром. Сохраняются в профиль
    с reliability='подавлен' — полная воспроизводимость пути детектора: видно,
    ЧТО нашёл детектор и ПОЧЕМУ фильтр это убрал. В карту признаков не
    попадают, в UI скрыты за отдельным переключателем «показать подавленные».
    """
    out: list[dict] = []
    for err, reason in suppressed_hits or []:
        subgroup = _ERROR_SUBGROUP.get(err.error_type, SUB_ORTHOGRAPHIC)
        desc = err.description or err.subtype or err.error_type
        c = _c(
            GROUP_LINGUISTIC, KIND_CANDIDATE,
            f"{err.error_type}: {err.subtype or 'без подтипа'}",
            value=f"{desc} · подавлен фильтром: {reason}",
            subgroup=subgroup,
            fragment=err.fragment or err.context or None,
            source=getattr(err, "rule_ref", "") or err.source or "errors",
            role=model.EVIDENCE, source_kind=model.SOURCE_ENGINEERING,
            detection_reliability=RELIABILITY_SUPPRESSED)
        out.append(c)
    return out


# ── 3е. Интернет-коммуникация: конкретные кандидаты с фрагментами ────────────
def internet_candidates(text: str, max_items: int = 15) -> list[dict]:
    """
    Конкретные вхождения сленга, эмотиконов, повторной пунктуации и CAPS.
    Это экспериментальные наблюдения: частота влияет только на предъявление,
    но не присваивает экспертную идентификационную значимость.
    Словари/паттерны переиспользуются из analyzer/errors.py (не меняются).
    """
    if not text:
        return []
    from analyzer.errors import (INTERNET_SLANG, EMOTICON_PATTERN,
                                 REPEATED_PUNCT, HASHTAG_PATTERN, EMOJI_PATTERN)

    def ctx(start: int, end: int, window: int = 30) -> str:
        s, e = max(0, start - window), min(len(text), end + window)
        return ("…" if s > 0 else "") + text[s:e].replace("\n", " ") + \
               ("…" if e < len(text) else "")

    found: list[tuple[str, str, int, str]] = []   # (label, value_word, count, fragment)
    lowered = text.lower()

    # Сленг: конкретные слова с числом употреблений.
    slang_hits: dict[str, list] = {}
    for word in set(INTERNET_SLANG):
        for m in re.finditer(rf"(?<![\wЁё]){re.escape(word)}(?![\wЁё])", lowered):
            slang_hits.setdefault(word, []).append(m)
    for word, ms in slang_hits.items():
        found.append(("Интернет-сленг", f"«{word}» ×{len(ms)}",
                      len(ms), ctx(ms[0].start(), ms[0].end())))

    # Эмотиконы, эмодзи, повторная пунктуация, хэштеги — по видам.
    for label, pattern in (("Эмотикон", EMOTICON_PATTERN),
                           ("Эмодзи", EMOJI_PATTERN),
                           ("Повторная пунктуация", REPEATED_PUNCT),
                           ("Хэштег", HASHTAG_PATTERN)):
        by_form: dict[str, list] = {}
        for m in pattern.finditer(text):
            by_form.setdefault(m.group(0), []).append(m)
        for form, ms in by_form.items():
            found.append((label, f"«{form}» ×{len(ms)}",
                          len(ms), ctx(ms[0].start(), ms[0].end())))

    # Слова капсом (3+ буквы) — экспрессивная графика.
    caps: dict[str, list] = {}
    for m in re.finditer(r"(?<![А-ЯЁ])[А-ЯЁ]{3,}(?![А-ЯЁ])", text):
        caps.setdefault(m.group(0), []).append(m)
    for form, ms in caps.items():
        found.append(("Слово КАПСОМ", f"«{form}» ×{len(ms)}",
                      len(ms), ctx(ms[0].start(), ms[0].end())))

    # Самые устойчивые — первыми; ограничение объёма.
    found.sort(key=lambda x: -x[2])
    out: list[dict] = []
    for label, val, count, fragment in found[:max_items]:
        out.append(_c(
            GROUP_LINGUISTIC, KIND_CANDIDATE, f"{label}",
            value=val + (" · устойчивое употребление" if count >= 2 else ""),
            subgroup=SUB_INTERNET, fragment=fragment,
            source="errors.internet",
            role=model.EVIDENCE, source_kind=model.SOURCE_EXPERIMENTAL,
            detection_reliability="средняя" if count >= 2 else "низкая"))
    return out


# ── 3ж. Маркированная лексика: конкретные evidence-наблюдения ───────────────


def lexical_marker_candidates(strat_result: Any, freq_engine: Any = None,
                              max_items: int = 20) -> list[dict]:
    """
    Маркированные словоупотребления как evidence. Частотный ранг сохраняется
    в значении только как инженерная справка и не определяет значимость.
    """
    if strat_result is None:
        return []
    from analyzer.stratification_engine import LAYER_META
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for tok in getattr(strat_result, "tokens", []) or []:
        key = (tok.lemma, tok.layer)
        if key in seen or tok.layer == "book_neutral":
            continue
        seen.add(key)
        frequency_note = ""
        if freq_engine is not None:
            try:
                hit = freq_engine.lookup(tok.lemma)
                frequency_note = (" · частотный ранг: н/д" if hit is None
                                  else f" · частотный ранг: {hit[0]}")
            except Exception:
                frequency_note = " · частотный ранг: н/д"
        label_ru = LAYER_META.get(tok.layer, {}).get("label", tok.layer)
        out.append(_c(
            GROUP_LINGUISTIC, KIND_CANDIDATE,
            f"Маркированная лексика: {label_ru}",
            value=f"«{tok.surface}»{frequency_note}",
            subgroup=SUB_LEXICAL, fragment=tok.context or None,
            source="stratification_engine", role=model.EVIDENCE,
            source_kind=model.SOURCE_ENGINEERING))
        if len(out) >= max_items:
            break
    return out


# ── 3з. Служебная лексика (Огорелков): кандидаты по классам и леммам ────────
def ogorelkov_candidates(og_result: Optional[dict]) -> list[dict]:
    """
    Кандидаты признаков из частотного анализа служебной лексики.

    Основание: Огорелков И.В. «Диагностика пола автора текста политического
    дискурса», гл. 3, п. 3.2–3.4 — закрытый перечень служебных
    лексико-грамматических классов и ipm-нормирование по НКРЯ (словарь
    Ляшевской–Шарова). Заимствован только инструментальный аппарат;
    диагностические модели пола не воспроизводятся.

    Кандидаты порождаются на уровне КАТЕГОРИИ (11 классов) — иначе карта
    признаков захлебнётся; дополнительно — отдельные леммы с отклонением от
    нормы вне [OGORELKOV_RATIO_LOW; OGORELKOV_RATIO_HIGH] при не менее чем
    OGORELKOV_MIN_COUNT вхождениях.

    Программа кандидатов НЕ принимает и НЕ отвергает — решение выносит эксперт
    через append-only механизм карты признаков.
    """
    if not og_result:
        return []

    def _na(v) -> str:
        return "н/д" if v is None else f"{v:g}"

    out: list[dict] = []
    for cat, data in (og_result.get("categories") or {}).items():
        cat_ru = cat.replace("_", " ")
        out.append(_c(
            GROUP_LINGUISTIC, KIND_CANDIDATE,
            f"Употребление: {cat_ru}",
            value=(f"{data['total_count']} вхождений, {_na(data['total_ipm'])} ipm "
                   f"(норма НКРЯ по категории — {_na(data.get('total_ipm_rnc'))} ipm, "
                   f"коэффициент отклонения {_na(data.get('total_ratio'))}); "
                   f"использовано {data['used']} из {data['total_lemmas']} лемм класса"),
            subgroup=SUB_FUNCTION_WORDS,
            source=f"ogorelkov:{cat}",
            role=model.AUX_METRIC, source_kind=model.SOURCE_ENGINEERING))

        for lemma, ld in (data.get("lemmas") or {}).items():
            ratio = ld.get("ratio")
            if ratio is None or ld["count"] < OGORELKOV_MIN_COUNT:
                continue
            if OGORELKOV_RATIO_LOW <= ratio <= OGORELKOV_RATIO_HIGH:
                continue
            direction = "выше" if ratio > OGORELKOV_RATIO_HIGH else "ниже"
            out.append(_c(
                GROUP_LINGUISTIC, KIND_CANDIDATE,
                f"Служебное слово «{lemma}» ({cat_ru})",
                value=(f"{ld['count']} вхождений, {_na(ld['ipm_text'])} ipm "
                       f"(норма НКРЯ — {_na(ld['ipm_rnc'])} ipm, коэффициент "
                       f"отклонения {_na(ratio)} — {direction} нормы)"),
                subgroup=SUB_FUNCTION_WORDS,
                source=f"ogorelkov:{cat}:{lemma}",
                role=model.EVIDENCE, source_kind=model.SOURCE_ENGINEERING,
                detection_reliability="средняя"))
    return out


# ── 3д. Общие признаки: степени развития навыков ─────────────────────────────
def general_skill_candidates(skill_levels: list, general_level: str,
                             general_desc: str,
                             autocorrect_unreliable: bool) -> list[dict]:
    """
    Общие признаки письменной речи в протокольном контуре.

    skill_levels — список SkillLevel из analyzer/errors.py (шкала ЭКЦ МВД,
    с. 13, НЕ изменяется — только читается); числовая основа сопоставления —
    error_rate (ошибок на 200 словоформ), по ней стадия сравнения применяет
    дифференцированные допуски Вула/Минюста. Общий уровень — по единой шкале
    Рубцовой (calculate_general_skill, с. 13).

    При автокоррекции (цифровой/опубликованный) орфографический и
    пунктуационный общие признаки помечаются reliability='низкая'.
    """
    out: list[dict] = []
    for sk in skill_levels or []:
        subgroup = GENERAL_SKILLS.get(sk.skill_name)
        if subgroup is None:
            continue
        c = _c(GROUP_LINGUISTIC, KIND_GENERAL,
               f"Степень развития: {sk.skill_name}",
               value=f"{sk.level} · {sk.error_rate:.1f} ошибок/200 словоформ",
               subgroup=subgroup,
               source="errors.skills",
               role=model.GENERAL_SKILL, source_kind=model.SOURCE_METHOD)
        if autocorrect_unreliable and subgroup in _AUTOCORRECT_SENSITIVE:
            c["reliability"] = "низкая"
            c["detection_reliability"] = "низкая"
            c["value"] += " · ненадёжен (автокоррекция)"
        out.append(c)
    if general_level:
        out.append(_c(GROUP_LINGUISTIC, KIND_GENERAL,
                      "Общий уровень владения письменной речью",
                      value=f"{general_level} · {general_desc}",
                      subgroup="общий_уровень", source="errors.skills",
                      role=model.GENERAL_SKILL, source_kind=model.SOURCE_METHOD))
    return out


# ── 4. Психолингвистические: только подсветка, интерпретация — эксперту ──────
def psycho_candidates(strat_result: Any) -> list[dict]:
    """
    Минимум автоматики: подсвечиваем единичные яркие словоупотребления
    (редкие регистровые маркеры) как кандидатов. Автоматической интерпретации
    нет — оценка остаётся эксперту.
    """
    out: list[dict] = []
    if strat_result is None:
        return out
    # Только эмоционально-экспрессивные слои: остальная маркированная лексика
    # уходит частными лексическими кандидатами (lexical_marker_candidates) —
    # без дублирования между группами.
    _PSYCHO_LAYERS = {"obscene", "euphemistic"}
    seen: set[tuple[str, str]] = set()
    for tok in getattr(strat_result, "tokens", []) or []:
        key = (tok.lemma, tok.layer)
        if key in seen or tok.layer not in _PSYCHO_LAYERS:
            continue
        seen.add(key)
        out.append(_c(
            GROUP_PSYCHO, KIND_CANDIDATE,
            f"Единичный маркер ({tok.layer})",
            value=f"«{tok.surface}» · интерпретация — эксперту",
            fragment=tok.context or None,
            source="stratification_engine", role=model.EVIDENCE,
            source_kind=model.SOURCE_ENGINEERING))
        if len(out) >= MAX_PSYCHO_CANDIDATES:
            break
    return out


# ── сборка профиля из готовых результатов модулей ─────────────────────────────
def build_profile(text: str, metrics: dict,
                  thematic_result: Any = None, strat_result: Any = None,
                  errors: Optional[list] = None, internet_profile: Any = None,
                  autocorrect_unreliable: bool = False,
                  error_reliabilities: Optional[list[str]] = None,
                  suppressed_hits: Optional[list] = None,
                  freq_engine: Any = None,
                  ogorelkov_result: Optional[dict] = None) -> list[dict]:
    """Собрать полный профиль (4 группы) из результатов существующих модулей."""
    profile: list[dict] = []
    profile += semantic_candidates(thematic_result)
    profile += textological_candidates(metrics, text)
    profile += lexical_candidates(metrics, strat_result)
    profile += lexical_marker_candidates(strat_result, freq_engine=freq_engine)
    profile += stylistic_candidates(metrics, internet_profile)
    profile += internet_candidates(text)
    profile += syntactic_candidates(metrics, text)
    profile += ogorelkov_candidates(ogorelkov_result)
    profile += error_candidates(errors or [], autocorrect_unreliable,
                                reliabilities=error_reliabilities)
    profile += suppressed_candidates(suppressed_hits or [])
    profile += psycho_candidates(strat_result)
    return profile


# ── оркестрация: документ из БД → профиль → feature_candidates + журнал ───────
def has_autocorrect_flag(pdb: "protocol_db.ProtocolDB",
                         project_id: int, document_id: int) -> bool:
    """Стоит ли на документе флаг «автокоррекция» из стадии пригодности (2А)."""
    for row in pdb.fetch_suitability(project_id):
        if row["document_id"] != document_id or not row["flags"]:
            continue
        try:
            flags = json.loads(row["flags"])
        except Exception:
            continue
        if any(f.get("code") == "автокоррекция" for f in flags):
            return True
    return False


def run_for_document(
    pdb: "protocol_db.ProtocolDB",
    project_id: int,
    document_id: int,
    backend: Any,
    program_version: Optional[str] = None,
    status_cb=None,
    use_lt: bool = True,
) -> dict:
    """
    Построить и сохранить профиль одного документа (идемпотентно: старый
    профиль удаляется). NLP — через переданный уже инициализированный бэкенд;
    остальные модули — синглтоны analyzer.* (не дублируются).
    """
    def _status(msg: str):
        if status_cb:
            status_cb(msg)

    doc = pdb.get_document(document_id)
    if doc is None:
        raise ValueError(f"Документ #{document_id} не найден")
    text = pdb.get_layer(document_id, protocol_db.LAYER_CLEANED) or ""

    _status("NLP-разметка (переиспользуем бэкенд)...")
    tokens = backend.analyze(text) if text else []

    _status("Метрики (TTR, hapax, POS, архитектоника)...")
    from analyzer.metrics import calculate_metrics
    metrics = calculate_metrics(tokens, text)

    # Кандидаты ошибок: собственные офлайн-правила + LanguageTool СТРОГО в
    # локальном режиме (материалы дела нельзя отправлять на внешний сервер;
    # публичный API LT в протокольном пути не используется).
    _status("Кандидаты ошибок (офлайн-правила)...")
    errors = []
    punct_rules_version = ""
    try:
        from analyzer import punct_checker
        punct_rules_version = getattr(punct_checker, "RULES_VERSION", "")
        errors = punct_checker.check_with_tokens(text, tokens) or []
    except Exception:
        pass

    lt_meta = {"режим": "не использован", "версия": ""}
    if use_lt:
        try:
            from analyzer import lt_checker as lt_module
            lt = lt_module.get()
            _status("LanguageTool: инициализация (только локальный сервер)...")
            lt.ensure_loaded()
            if lt.mode == "local":
                _status("LanguageTool: проверка текста (локально)...")
                errors += lt.check(text) or []
                try:
                    from importlib.metadata import version as _pkg_version
                    lt_meta = {"режим": "local",
                               "версия": _pkg_version("language-tool-python")}
                except Exception:
                    lt_meta = {"режим": "local", "версия": "?"}
            else:
                # Публичный API доступен, но для протокола запрещён.
                lt_meta = {"режим": f"пропущен ({lt.mode or 'недоступен'})", "версия": ""}
        except Exception:
            lt_meta = {"режим": "ошибка инициализации", "версия": ""}

    # Слой фильтрации (единственная точка между детектором и feature_candidates).
    _status("Фильтрация срабатываний детектора...")
    filter_config, filter_hash = detector_filter.load_config()
    filtered = detector_filter.apply_filter(errors, filter_config)
    errors = [e for e, _rel in filtered.kept]
    error_reliabilities = [rel for _e, rel in filtered.kept]

    _status("Интернет-профиль...")
    internet_profile = None
    try:
        from analyzer.errors import analyze_internet_communication
        internet_profile = analyze_internet_communication(text)
    except Exception:
        pass

    _status("Лексическая стратификация...")
    strat_result = None
    try:
        from analyzer import stratification_engine
        strat_result = stratification_engine.get().analyze(text)
    except Exception:
        pass

    _status("Тематическая атрибуция...")
    thematic_result = None
    try:
        from analyzer import thematic_engine
        lemmas = [t.lemma.lower() for t in tokens
                  if _WORD_RE.search(t.text) and t.pos not in ("PUNCT", "NUM")]
        thematic_result = thematic_engine.get().analyze(lemmas)
    except Exception:
        pass

    autocorrect = has_autocorrect_flag(pdb, project_id, document_id)

    # Общие признаки: степени развития навыков по ОТФИЛЬТРОВАННЫМ ошибкам
    # (ложные срабатывания детектора не искажают степень). Шкала — ЭКЦ МВД
    # с. 13 (errors.py только читается), сопоставление — по числовому rate.
    _status("Общие признаки (степени развития навыков)...")
    general_candidates: list[dict] = []
    try:
        from analyzer.errors import ErrorAnalyzer, calculate_general_skill
        wc_words = len(_WORD_RE.findall(text))
        skill_levels = ErrorAnalyzer()._assess_skills(errors, wc_words)
        g_level, g_desc, _n_unique = calculate_general_skill(errors, wc_words)
        general_candidates = general_skill_candidates(
            skill_levels, g_level, g_desc, autocorrect)
    except Exception:
        pass

    # Частотный движок (словарь Ляшевской–Шарова, офлайн): нужен и для оценки
    # редкости маркированной лексики, и для ipm-нормирования Огорелкова.
    # Экземпляр один на процесс (синглтон freq_engine.get()).
    freq_eng = None
    try:
        from analyzer import freq_engine as freq_module
        freq_eng = freq_module.get()
        if not freq_eng.is_loaded:
            freq_eng.load()
    except Exception:
        pass

    # Служебная лексика (Огорелков): ipm-частоты закрытого перечня служебных
    # лексико-грамматических классов. Токены переиспользуются (второй пайплайн
    # не создаётся). Сбой модуля не должен ронять построение профиля.
    _status("Служебная лексика (Огорелков)...")
    ogorelkov_result = None
    try:
        from analyzer import ogorelkov_engine
        lookup = (freq_eng.lookup if freq_eng is not None and freq_eng.is_loaded
                  else None)
        ogorelkov_result = ogorelkov_engine.analyze(tokens, freq_lookup=lookup)
        # Хеш материала берём зафиксированный при импорте (protocol/ingest.py),
        # заново по строке не считаем — воспроизводимость привязана к файлу.
        pdb.save_ogorelkov_result(
            text_sha256=doc["file_sha256"],
            dict_sha256=ogorelkov_result["dict_sha256"],
            total_words=ogorelkov_result["total_words"],
            results=ogorelkov_result,
            label=f"{doc['filename']} ({doc['role']})",
            program_version=program_version)
    except Exception as e:  # noqa: BLE001
        _status(f"Служебная лексика недоступна: {e}")
        ogorelkov_result = None

    profile = build_profile(
        text, metrics,
        thematic_result=thematic_result, strat_result=strat_result,
        errors=errors, internet_profile=internet_profile,
        autocorrect_unreliable=autocorrect,
        error_reliabilities=error_reliabilities,
        suppressed_hits=filtered.suppressed_hits,
        freq_engine=freq_eng,
        ogorelkov_result=ogorelkov_result)
    profile += general_candidates

    pdb.clear_feature_candidates(document_id)
    n = pdb.save_feature_candidates(document_id, profile)
    pdb.log_action(
        "построен профиль (раздельное исследование)", project_id=project_id,
        details={"document_id": document_id, "filename": doc["filename"],
                 "элементов": n,
                 "групп": sorted({c["group_name"] for c in profile}),
                 "автокоррекция_ненадёжность": autocorrect,
                 # Воспроизводимость: версии движков и конфига фильтра.
                 "фильтр_конфиг_hash": filter_hash,
                 "версия_правил_пунктуации": punct_rules_version,
                 "словарь_Огорелкова_sha256": (
                     ogorelkov_result["dict_sha256"] if ogorelkov_result else None),
                 "languagetool": lt_meta,
                 # Подавленные срабатывания не исчезают бесследно.
                 "срабатываний_детектора": filtered.total_in,
                 "подавлено_всего": filtered.total_suppressed,
                 "подавлено_по_правилам": dict(filtered.suppressed)},
        program_version=program_version)

    return {"document_id": document_id, "count": n,
            "autocorrect_unreliable": autocorrect, "profile": profile,
            "ogorelkov": ogorelkov_result,
            "detector_total": filtered.total_in,
            "suppressed": dict(filtered.suppressed),
            "filter_hash": filter_hash}
