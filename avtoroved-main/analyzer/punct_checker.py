"""
analyzer/punct_checker.py — Правила пунктуации русского текста.

Реализованы четыре высокоточных правила:
  1. Запятая перед «который» и его формами (придаточные определительные).
  2. Запятая перед противительными союзами «однако», «зато» в середине предложения.
  3. Запятая перед составными подчинительными союзами
     (потому что, так как, несмотря на то что, для того чтобы …).
  4. Запятая после вводных слов в начале предложения.

Принцип «не навреди»: лучше пропустить ошибку, чем создать ложное срабатывание.
Правило 4 для «что/если/когда» не реализовано из-за высокой омонимии.
"""
from __future__ import annotations

import re
from typing import List

from analyzer.errors import TextError

# ── Вспомогательные константы ──────────────────────────────────────────────────

# Предлоги, допустимые перед «который» (входят в состав придаточного)
_PREP = (
    r"в|на|с|со|из|к|ко|до|для|за|под|над|при|о|об|обо|по|от|без|"
    r"через|перед|после|между|вместо|вокруг|около|у|возле|среди|против"
)
_RE_PREP_SUFFIX = re.compile(
    r"\b(?:" + _PREP + r")\s*$",
    re.IGNORECASE,
)

# Формы «который»
_RE_KOTORY = re.compile(
    r"\b(котор(?:ый|ая|ое|ые|ого|ому|ой|ых|ым|ыми|ом|ую))\b",
    re.IGNORECASE,
)

# Противительные союзы в середине предложения
_RE_ADVERSE = re.compile(
    r"(?<=[а-яёА-ЯЁ])\s+(однако|зато)\b",
    re.IGNORECASE,
)

# Составные подчинительные союзы (надёжные — практически всегда нужна запятая)
_COMPOUND_CONJUNCTIONS: List[tuple] = [
    (re.compile(r"\bпотому\s+что\b",           re.IGNORECASE), "потому что"),
    (re.compile(r"\bтак\s+как\b",              re.IGNORECASE), "так как"),
    (re.compile(r"\bнесмотря\s+на\s+то\s+что\b", re.IGNORECASE), "несмотря на то что"),
    (re.compile(r"\bдля\s+того\s+чтобы\b",     re.IGNORECASE), "для того чтобы"),
    (re.compile(r"\bвместо\s+того\s+чтобы\b",  re.IGNORECASE), "вместо того чтобы"),
    (re.compile(r"\bкак\s+только\b",           re.IGNORECASE), "как только"),
    (re.compile(r"\bпрежде\s+чем\b",           re.IGNORECASE), "прежде чем"),
    (re.compile(r"\bдо\s+того\s+как\b",        re.IGNORECASE), "до того как"),
    (re.compile(r"\bпосле\s+того\s+как\b",     re.IGNORECASE), "после того как"),
    (re.compile(r"\bс\s+тех\s+пор\s+как\b",   re.IGNORECASE), "с тех пор как"),
    (re.compile(r"\bв\s+то\s+время\s+как\b",  re.IGNORECASE), "в то время как"),
]

# Вводные слова / конструкции (в начале предложения без запятой после)
_INTRODUCTORY_WORDS: List[str] = [
    "конечно", "разумеется", "очевидно", "видимо", "по-видимому",
    "по всей видимости", "вероятно", "возможно", "наверное", "пожалуй",
    "кажется", "似乎",
    "во-первых", "во-вторых", "в-третьих", "наконец", "итак",
    "следовательно", "таким образом", "таким образом",
    "например", "в частности", "в особенности",
    "кстати", "между прочим", "впрочем", "однако",
    "с одной стороны", "с другой стороны",
    "в общем", "в целом", "в принципе",
]
# Предварительно скомпилируем паттерн для начала предложения
_RE_SENT_START = re.compile(r"(?:^|(?<=[.!?\n]))\s*", re.MULTILINE)

_INTRO_PATTERNS: List[tuple] = []
for _w in _INTRODUCTORY_WORDS:
    _INTRO_PATTERNS.append((
        re.compile(
            r"(?:(?:^|(?<=[.!?\n\u2014]))\s*)"
            r"(" + re.escape(_w) + r")"
            r"(?!\s*,)"           # нет запятой после
            r"\s+([а-яёА-ЯЁ])",  # продолжение — слово
            re.IGNORECASE | re.MULTILINE,
        ),
        _w,
    ))


# ── Утилиты ─────────────────────────────────────────────────────────────────

def _ctx(text: str, start: int, end: int, window: int = 50) -> str:
    cs = max(0, start - window)
    ce = min(len(text), end + window)
    s = text[cs:ce].replace("\n", " ").strip()
    if cs > 0:
        s = "…" + s
    if ce < len(text):
        s = s + "…"
    return s


def _last_punct_pos(text: str) -> int:
    """Позиция последнего знака завершения предложения (. ! ? \\n)."""
    for i in range(len(text) - 1, -1, -1):
        if text[i] in ".!?\n":
            return i
    return -1


# ── Правило 1: запятая перед «который» ───────────────────────────────────────

def _check_kotory(text: str) -> List[TextError]:
    errors: List[TextError] = []
    for m in _RE_KOTORY.finditer(text):
        pos = m.start()

        # Текст до «который»
        before = text[:pos].rstrip()

        # Убрать предлог, если он непосредственно предшествует «который»
        prep_m = _RE_PREP_SUFFIX.search(before)
        if prep_m:
            before = before[: prep_m.start()].rstrip()

        if not before:
            continue  # начало текста

        last_ch = before[-1]

        # Если перед (предлогом +) «который» стоит знак препинания — ОК
        if last_ch in ",;:.!?\n\u2014–-":
            continue

        # Должна быть русская буква — значит, запятая пропущена
        if not last_ch.isalpha():
            continue

        # Находим границу последней запятой / начала предложения
        # для определения фрагмента
        frag_start = max(
            before.rfind(","),
            before.rfind(";"),
            before.rfind("."),
            before.rfind("!"),
            before.rfind("?"),
            before.rfind("\n"),
        )
        frag_start = frag_start + 1 if frag_start >= 0 else 0
        frag_text = text[frag_start : m.end()].strip()
        if len(frag_text) > 50:
            frag_text = "…" + frag_text[-48:]

        errors.append(TextError(
            error_type="Пунктуационная",
            subtype="Пропущена запятая перед придаточным определительным",
            fragment=frag_text,
            description=(
                f"Перед словом «{m.group(0)}» нужна запятая: "
                f"придаточное определительное отделяется запятой."
            ),
            suggestion=f"Вставьте запятую перед «{m.group(0)}»",
            position=(frag_start, m.end()),
            rule_ref="PUNCT:KOTORY",
            source="PUNCT",
            context=_ctx(text, pos, m.end()),
        ))
    return errors


# ── Правило 2: запятая перед «однако/зато» ───────────────────────────────────

def _check_adverse(text: str) -> List[TextError]:
    errors: List[TextError] = []
    for m in _RE_ADVERSE.finditer(text):
        # m.start() — конец предыдущего слова; союз — в группе 1
        full_start = m.start()
        word_start = m.start(1)
        conj = m.group(1)

        before_ch = text[full_start] if full_start < len(text) else ""
        # Предыдущий символ — последний символ предшествующего слова
        if text[full_start] in ",;:.!?\n":
            continue

        errors.append(TextError(
            error_type="Пунктуационная",
            subtype=f"Пропущена запятая перед «{conj}»",
            fragment=text[max(0, full_start - 15): word_start + len(conj)].strip(),
            description=(
                f"Перед союзом «{conj}» в сложносочинённом предложении "
                f"нужна запятая."
            ),
            suggestion=f"Вставьте запятую перед «{conj}»",
            position=(full_start, word_start + len(conj)),
            rule_ref="PUNCT:ADVERSE",
            source="PUNCT",
            context=_ctx(text, full_start, word_start + len(conj)),
        ))
    return errors


# ── Правило 3: запятая перед составными союзами ───────────────────────────────

def _check_compound_conj(text: str) -> List[TextError]:
    errors: List[TextError] = []
    for pattern, label in _COMPOUND_CONJUNCTIONS:
        for m in pattern.finditer(text):
            pos = m.start()
            # Проверить символ непосредственно перед союзом
            before = text[:pos].rstrip()
            if not before:
                continue
            last_ch = before[-1]
            if last_ch in ",;:.!?\n":
                continue
            if not last_ch.isalpha():
                continue

            # Не флажить, если союз в начале предложения
            sent_start = max(
                before.rfind("."), before.rfind("!"), before.rfind("?"),
                before.rfind("\n"),
            )
            text_since_sent = before[sent_start + 1:].strip()
            if not text_since_sent:
                continue  # начало предложения

            frag = text[max(0, pos - 20): m.end()].strip()

            errors.append(TextError(
                error_type="Пунктуационная",
                subtype=f"Пропущена запятая перед «{label}»",
                fragment=frag,
                description=(
                    f"Перед составным союзом «{label}» нужна запятая."
                ),
                suggestion=f"Вставьте запятую перед «{label}»",
                position=(pos, m.end()),
                rule_ref="PUNCT:COMPOUND",
                source="PUNCT",
                context=_ctx(text, pos, m.end()),
            ))
    return errors


# ── Правило 4: запятая после вводных слов ─────────────────────────────────────

def _check_introductory(text: str) -> List[TextError]:
    errors: List[TextError] = []
    for pattern, word in _INTRO_PATTERNS:
        for m in pattern.finditer(text):
            word_start = m.start(1)
            word_end   = m.start(1) + len(m.group(1))
            errors.append(TextError(
                error_type="Пунктуационная",
                subtype=f"Пропущена запятая после вводного слова «{m.group(1)}»",
                fragment=m.group(0).strip(),
                description=(
                    f"После вводного слова «{m.group(1)}» нужна запятая."
                ),
                suggestion=f"Поставьте запятую после «{m.group(1)}»",
                position=(word_start, word_end),
                rule_ref="PUNCT:INTRO",
                source="PUNCT",
                context=_ctx(text, word_start, word_end),
            ))
    return errors


# ── Публичный API ──────────────────────────────────────────────────────────────

def check(text: str) -> List[TextError]:
    """
    Проверить текст на пунктуационные ошибки (regex-правила).
    Возвращает список TextError с source='PUNCT'.
    """
    errors: List[TextError] = []
    errors.extend(_check_kotory(text))
    errors.extend(_check_adverse(text))
    errors.extend(_check_compound_conj(text))
    errors.extend(_check_introductory(text))
    return errors


# ── Depparse-правила ───────────────────────────────────────────────────────────

def _get_sentence_groups(tokens) -> dict:
    sents: dict = {}
    for t in tokens:
        sents.setdefault(t.sent_id, []).append(t)
    return sents


def _build_subtree(token_id: int, tid_map: dict, visited: set | None = None) -> set:
    """Возвращает множество token_id всего поддерева, включая сам токен."""
    if visited is None:
        visited = set()
    if token_id in visited:
        return visited
    visited.add(token_id)
    for tid, tok in tid_map.items():
        if tok.head == token_id and tid != token_id:
            _build_subtree(tid, tid_map, visited)
    return visited


def _comma_before(text: str, pos: int) -> bool:
    """True если непосредственно перед pos (игнорируя пробелы) стоит знак препинания."""
    i = pos - 1
    while i >= 0 and text[i] in ' \t\xa0':
        i -= 1
    return i < 0 or text[i] in ',;:.!?\n\u2014–-('


def _comma_after(text: str, pos: int) -> bool:
    """True если непосредственно после pos (игнорируя пробелы) стоит знак препинания."""
    i = pos
    while i < len(text) and text[i] in ' \t\xa0':
        i += 1
    return i >= len(text) or text[i] in ',;:.!?\n\u2014–-)'


def _check_deeprichastie_oborot(text: str, tokens) -> List[TextError]:
    """
    Запятая при деепричастном обороте.
    Правило: деепричастие (VerbForm=Conv) и его зависимые должны выделяться запятыми.
    """
    errors: List[TextError] = []
    sent_groups = _get_sentence_groups(tokens)

    for sent_id, sent_toks in sent_groups.items():
        tid_map = {t.token_id: t for t in sent_toks if t.token_id > 0}

        # Все токены с валидными позициями в этом предложении
        valid_sent = [t for t in sent_toks if t.char_start < t.char_end]
        if not valid_sent:
            continue
        sent_cs = min(t.char_start for t in valid_sent)
        sent_ce = max(t.char_end for t in valid_sent)

        deeps = [t for t in sent_toks if t.pos_label == "Деепричастие"
                 and t.char_start < t.char_end and t.token_id > 0]

        for deep in deeps:
            subtree_ids = _build_subtree(deep.token_id, tid_map)
            subtree_toks = [tid_map[i] for i in subtree_ids if i in tid_map
                            and tid_map[i].char_start < tid_map[i].char_end]
            if not subtree_toks:
                continue

            span_cs = min(t.char_start for t in subtree_toks)
            span_ce = max(t.char_end for t in subtree_toks)

            # Оборот в начале/конце предложения?
            at_start = text[sent_cs:span_cs].strip() == ""
            tail = text[span_ce:sent_ce].strip().lstrip('.,;:!?')
            at_end = tail == ""

            frag = text[span_cs:span_ce].strip()
            if len(frag) > 50:
                frag = "…" + frag[-48:]

            if not at_start and not _comma_before(text, span_cs):
                errors.append(TextError(
                    error_type="Пунктуационная",
                    subtype="Пропущена запятая перед деепричастным оборотом",
                    fragment=frag,
                    description=(
                        f"Деепричастный оборот «{frag}» нужно выделить запятой "
                        f"(запятая перед оборотом)."
                    ),
                    suggestion="Поставьте запятую перед деепричастным оборотом",
                    position=(span_cs, span_ce),
                    rule_ref="PUNCT:DEEPR_BEFORE",
                    source="PUNCT",
                    context=_ctx(text, span_cs, span_ce),
                ))

            if not at_end and not _comma_after(text, span_ce):
                errors.append(TextError(
                    error_type="Пунктуационная",
                    subtype="Пропущена запятая после деепричастного оборота",
                    fragment=frag,
                    description=(
                        f"Деепричастный оборот «{frag}» нужно выделить запятой "
                        f"(запятая после оборота)."
                    ),
                    suggestion="Поставьте запятую после деепричастного оборота",
                    position=(span_cs, span_ce),
                    rule_ref="PUNCT:DEEPR_AFTER",
                    source="PUNCT",
                    context=_ctx(text, span_cs, span_ce),
                ))

    return errors


def _check_prichastnyi_oborot(text: str, tokens) -> List[TextError]:
    """
    Запятая при постпозитивном причастном обороте.
    Правило: причастный оборот ПОСЛЕ определяемого слова выделяется запятыми.
    Оборот должен содержать хотя бы одно зависимое слово (иначе не оборот, а одиночное причастие).
    """
    errors: List[TextError] = []
    sent_groups = _get_sentence_groups(tokens)

    for sent_id, sent_toks in sent_groups.items():
        tid_map = {t.token_id: t for t in sent_toks if t.token_id > 0}

        valid_sent = [t for t in sent_toks if t.char_start < t.char_end]
        if not valid_sent:
            continue
        sent_cs = min(t.char_start for t in valid_sent)
        sent_ce = max(t.char_end for t in valid_sent)

        parts = [t for t in sent_toks if t.pos_label == "Причастие"
                 and t.char_start < t.char_end and t.token_id > 0]

        for part in parts:
            head = tid_map.get(part.head)
            if head is None or head.char_end == 0:
                continue

            # Нас интересует только постпозиция: голова (существительное) стоит ДО причастия
            if head.char_end > part.char_start:
                continue

            subtree_ids = _build_subtree(part.token_id, tid_map)
            subtree_toks = [tid_map[i] for i in subtree_ids if i in tid_map
                            and tid_map[i].char_start < tid_map[i].char_end]

            # Нужен хотя бы один зависимый (оборот, а не одиночное причастие)
            non_punct_deps = [t for t in subtree_toks
                              if t.token_id != part.token_id and t.pos != "PUNCT"]
            if not non_punct_deps:
                continue

            span_cs = min(t.char_start for t in subtree_toks)
            span_ce = max(t.char_end for t in subtree_toks)

            # Убедиться, что причастие действительно идёт ПОСЛЕ головы
            if span_cs <= head.char_end:
                continue

            frag = text[span_cs:span_ce].strip()
            if len(frag) > 50:
                frag = "…" + frag[-48:]

            at_start = text[sent_cs:span_cs].strip() == ""
            tail = text[span_ce:sent_ce].strip().lstrip('.,;:!?')
            at_end = tail == ""

            if not at_start and not _comma_before(text, span_cs):
                errors.append(TextError(
                    error_type="Пунктуационная",
                    subtype="Пропущена запятая перед причастным оборотом",
                    fragment=frag,
                    description=(
                        f"Причастный оборот «{frag}» стоит после определяемого слова "
                        f"«{head.text}» и должен выделяться запятыми (запятая перед оборотом)."
                    ),
                    suggestion="Поставьте запятую перед причастным оборотом",
                    position=(span_cs, span_ce),
                    rule_ref="PUNCT:PART_BEFORE",
                    source="PUNCT",
                    context=_ctx(text, span_cs, span_ce),
                ))

            if not at_end and not _comma_after(text, span_ce):
                errors.append(TextError(
                    error_type="Пунктуационная",
                    subtype="Пропущена запятая после причастного оборота",
                    fragment=frag,
                    description=(
                        f"Причастный оборот «{frag}» стоит после определяемого слова "
                        f"«{head.text}» и должен выделяться запятыми (запятая после оборота)."
                    ),
                    suggestion="Поставьте запятую после причастного оборота",
                    position=(span_cs, span_ce),
                    rule_ref="PUNCT:PART_AFTER",
                    source="PUNCT",
                    context=_ctx(text, span_cs, span_ce),
                ))

    return errors


def check_with_tokens(text: str, tokens) -> List[TextError]:
    """
    Полная проверка пунктуации: regex-правила + depparse-правила.
    tokens — список TokenInfo из StanzaBackend.analyze() (с depparse).
    """
    errors: List[TextError] = check(text)
    try:
        errors.extend(_check_deeprichastie_oborot(text, tokens))
        errors.extend(_check_prichastnyi_oborot(text, tokens))
    except Exception:
        pass  # депарсинг опционален — не ломаем весь анализ
    return errors
