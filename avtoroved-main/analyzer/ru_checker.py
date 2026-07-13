"""
analyzer/ru_checker.py — собственные офлайн-детекторы ошибок (без LT и Java).

Экспертный протокол не должен зависеть от LanguageTool: этот модуль даёт
локальное покрытие орфографии, грамматики и лексики на чистом Python
(pymorphy3 уже в зависимостях — используется стратификацией).

Четыре детектора, принцип «не навреди» (лучше пропустить, чем ложно сработать):
  1. Орфография — словарная проверка pymorphy3/OpenCorpora: слово вне словаря
     и вне регистровых словарей программы → кандидат опечатки. Слова с
     заглавной буквы, аббревиатуры, латиница и короткие слова пропускаются.
  2. Орфография (-тся/-ться) — по левому контексту: маркер инфинитива
     (надо, может, будет…) требует «-ться»; личное местоимение (он/она/оно)
     требует «-тся». Правописание глагольных форм — орфографический навык.
  3. Грамматика — согласование прилагательное+существительное по токенам
     NLP-разметки: флаг только если НИ ОДНА комбинация морфологических
     разборов пары не согласуется (устойчиво к омонимии).
  4. Лексика — тавтология (повтор знаменательной леммы в окне внутри
     предложения) и малый словарь плеоназмов.

Все срабатывания — кандидаты «требует проверки»: решение за экспертом
(карта признаков). RULES_VERSION пишется в audit_log протокола.
"""
from __future__ import annotations

import re
from typing import List, Optional

from analyzer.errors import TextError

# Менять при любом изменении правил ниже (воспроизводимость протокола).
RULES_VERSION = "1.0"

_WORD_RE = re.compile(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*")
_SENT_SPLIT_RE = re.compile(r"[.!?…\n]+")

_morph = None
_MORPH_FAILED = False


def _get_morph():
    global _morph, _MORPH_FAILED
    if _morph is None and not _MORPH_FAILED:
        try:
            import pymorphy3
            _morph = pymorphy3.MorphAnalyzer()
        except Exception:
            _MORPH_FAILED = True
    return _morph


def _ctx(text: str, start: int, end: int, window: int = 45) -> str:
    cs, ce = max(0, start - window), min(len(text), end + window)
    return (("…" if cs > 0 else "") + text[cs:ce].replace("\n", " ")
            + ("…" if ce < len(text) else ""))


def _registry_lemmas() -> dict:
    """Леммы регистровых словарей (жаргон и т.п.) — не считаем опечатками."""
    try:
        from analyzer import stratification_engine
        eng = stratification_engine.get()
        eng.load()
        return eng._lemma_to_layer
    except Exception:
        return {}


def _internet_slang() -> set:
    try:
        from analyzer.errors import INTERNET_SLANG, INTERNET_ABBREVIATIONS
        return set(INTERNET_SLANG) | set(INTERNET_ABBREVIATIONS)
    except Exception:
        return set()


# ── 1. Орфография: словарная проверка ────────────────────────────────────────
def spelling_errors(text: str) -> List[TextError]:
    morph = _get_morph()
    if morph is None or not text:
        return []
    registry = _registry_lemmas()
    slang = _internet_slang()
    out: List[TextError] = []
    seen: set = set()
    for m in _WORD_RE.finditer(text):
        word = m.group(0)
        low = word.lower()
        # «Не навреди»: пропускаем короткие, с заглавной (имена собственные,
        # начала предложений), аббревиатуры капсом и уже виденные формы.
        if len(low) < 4 or word[0].isupper() or low in seen:
            continue
        if low in slang or low in registry:
            continue
        parts = low.split("-")
        if all(morph.word_is_known(p) for p in parts if p):
            continue
        # Лемма части может быть в регистровых словарях (жаргон со словоизм.).
        lemma = morph.parse(parts[0])[0].normal_form if parts else low
        if lemma in registry:
            continue
        seen.add(low)
        out.append(TextError(
            error_type="Орфографическая",
            subtype="Слово вне словаря",
            fragment=word,
            description=f"«{word}» отсутствует в словаре OpenCorpora — "
                        "возможна опечатка либо окказионализм",
            suggestion="Проверьте написание",
            position=(m.start(), m.end()),
            rule_ref="RU:SPELL_DICT",
            source="MORPH",
            context=_ctx(text, m.start(), m.end()),
            significance="средняя",
        ))
    return out


# ── 2. Орфография: -тся/-ться по левому контексту ────────────────────────────
# Маркеры, после которых требуется инфинитив («-ться»).
_INF_MARKER = (r"надо|нужно|нельзя|должн[аоы]?|может|могут|мог|буд[еу]т|"
               r"стоит|следует|хоч(?:ет|ут)|начал[аио]?|перестал[аио]?|"
               r"собира(?:ется|ются)|пыта(?:ется|ются)|готов[аоы]?|"
               r"стал[аио]?|продолжа(?:ет|ют)|люб(?:ит|ят)|боится|боятся")
_RE_TSYA_AFTER_INF = re.compile(
    r"\b(" + _INF_MARKER + r")\s+([а-яё]+[тч]ся)\b", re.IGNORECASE)
# Личное местоимение → личная форма («-тся»).
_RE_TSYA_AFTER_PRON = re.compile(
    r"\b(он|она|оно)\s+([а-яё]+ться)\b", re.IGNORECASE)


def tsya_errors(text: str) -> List[TextError]:
    """Правописание -тся/-ться (орфографический навык по методике)."""
    if not text:
        return []
    out: List[TextError] = []
    for m in _RE_TSYA_AFTER_INF.finditer(text):
        verb = m.group(2)
        if verb.lower().endswith("ться"):
            continue    # уже инфинитив — ошибки нет
        out.append(TextError(
            error_type="Орфографическая",
            subtype="-тся вместо -ться",
            fragment=m.group(0),
            description=f"После «{m.group(1)}» требуется инфинитив: "
                        f"«{verb}» → «{verb[:-3]}ться»",
            suggestion=f"→ {verb[:-3]}ться",
            position=(m.start(), m.end()),
            rule_ref="RU:TSYA_INF",
            source="GRAM",
            context=_ctx(text, m.start(), m.end()),
            significance="высокая",
        ))
    for m in _RE_TSYA_AFTER_PRON.finditer(text):
        verb = m.group(2)
        out.append(TextError(
            error_type="Орфографическая",
            subtype="-ться вместо -тся",
            fragment=m.group(0),
            description=f"После «{m.group(1)}» требуется личная форма: "
                        f"«{verb}» → «{verb[:-4]}тся»",
            suggestion=f"→ {verb[:-4]}тся",
            position=(m.start(), m.end()),
            rule_ref="RU:TSYA_PRON",
            source="GRAM",
            context=_ctx(text, m.start(), m.end()),
            significance="высокая",
        ))
    return out


# ── 3. Грамматика: согласование прилагательное + существительное ─────────────
# Пары падежей, считающиеся совместимыми (варианты одного падежа в OpenCorpora).
_CASE_EQUIV = ({"gent", "gen2"}, {"loct", "loc2"}, {"accs", "acc2"})


def _cases_match(c1, c2) -> bool:
    if c1 == c2:
        return True
    return any(c1 in grp and c2 in grp for grp in _CASE_EQUIV)


def _pair_agrees(adj_p, noun_p) -> bool:
    """Согласована ли пара разборов (род/число/падеж)."""
    if not _cases_match(adj_p.tag.case, noun_p.tag.case):
        return False
    if adj_p.tag.number != noun_p.tag.number:
        return False
    # Род сравнивается только в единственном числе (во мн. он не выражен).
    if adj_p.tag.number == "sing" and adj_p.tag.gender and noun_p.tag.gender \
            and adj_p.tag.gender != noun_p.tag.gender:
        return False
    return True


def agreement_errors(text: str, tokens) -> List[TextError]:
    """
    Нарушение согласования в соседней паре ADJ + NOUN (по UPOS из разметки).
    Флаг только когда НИ ОДНА комбинация морфологических разборов пары не
    согласуется — омонимия не даёт ложных срабатываний.
    """
    morph = _get_morph()
    if morph is None or not tokens:
        return []
    out: List[TextError] = []
    for t1, t2 in zip(tokens, tokens[1:]):
        if (getattr(t1, "pos", "") != "ADJ" or getattr(t2, "pos", "") != "NOUN"
                or getattr(t1, "sent_id", 0) != getattr(t2, "sent_id", 0)
                or getattr(t2, "token_id", 0) - getattr(t1, "token_id", 0) != 1):
            continue
        w1, w2 = t1.text.lower(), t2.text.lower()
        if not (_WORD_RE.fullmatch(w1) and _WORD_RE.fullmatch(w2)):
            continue
        adj_parses = [p for p in morph.parse(w1)
                      if str(p.tag.POS) in ("ADJF", "PRTF") and p.tag.case]
        noun_parses = [p for p in morph.parse(w2)
                       if str(p.tag.POS) == "NOUN" and p.tag.case]
        if not adj_parses or not noun_parses:
            continue
        if any(_pair_agrees(a, n) for a in adj_parses for n in noun_parses):
            continue
        start = getattr(t1, "char_start", 0)
        end = getattr(t2, "char_end", 0)
        if end <= start:
            continue
        out.append(TextError(
            error_type="Грамматическая",
            subtype="Нарушение согласования",
            fragment=text[start:end][:60],
            description=f"«{t1.text} {t2.text}»: определение не согласуется "
                        "с существительным ни в одном разборе (род/число/падеж)",
            suggestion="Согласуйте определение с существительным",
            position=(start, end),
            rule_ref="RU:AGREE",
            source="GRAM",
            context=_ctx(text, start, end),
            significance="высокая",
        ))
    return out


# ── 4. Лексика: тавтология и плеоназмы ───────────────────────────────────────
_TAUT_WINDOW = 8            # окно повторов, слов
_TAUT_STOP_LEMMAS = {
    "быть", "весь", "это", "этот", "тот", "свой", "который", "такой",
    "самый", "один", "мочь", "год", "человек", "время", "дело", "раз",
    "становиться", "стать", "говорить", "сказать",
}
_TAUT_POS = {"NOUN", "VERB", "INFN", "ADJF", "ADJS", "ADVB"}

_PLEONASMS = (
    (r"свободн\w{1,3}\s+ваканси\w{1,3}", "свободная вакансия"),
    (r"памятн\w{1,3}\s+сувенир\w{0,3}", "памятный сувенир"),
    (r"период\w{0,3}\s+времени", "период времени"),
    (r"главн\w{1,3}\s+суть", "главная суть"),
    (r"предельн\w{1,3}\s+лимит\w{0,3}", "предельный лимит"),
    (r"совместн\w{1,3}\s+сотрудничеств\w{1,3}", "совместное сотрудничество"),
    (r"внутренн\w{1,3}\s+интерьер\w{0,3}", "внутренний интерьер"),
    (r"перв\w{1,3}\s+премьер\w{1,3}", "первая премьера"),
    (r"более\s+луч?ше", "более лучше"),
    (r"впервые\s+дебютировал\w{0,2}", "впервые дебютировал"),
)
_RE_PLEONASMS = [(re.compile(p, re.IGNORECASE), name) for p, name in _PLEONASMS]


def lexical_errors(text: str) -> List[TextError]:
    if not text:
        return []
    out: List[TextError] = []

    for rx, name in _RE_PLEONASMS:
        for m in rx.finditer(text):
            out.append(TextError(
                error_type="Лексическая",
                subtype=f"Плеоназм: {name}",
                fragment=m.group(0),
                description=f"Плеоназм «{m.group(0)}» — избыточное сочетание",
                suggestion="Уберите избыточное слово",
                position=(m.start(), m.end()),
                rule_ref="RU:PLEONASM",
                source="LEX",
                context=_ctx(text, m.start(), m.end()),
                significance="средняя",
            ))

    morph = _get_morph()
    if morph is None:
        return out
    # Тавтология: одна знаменательная лемма дважды в окне внутри предложения.
    offset = 0
    reported: set = set()
    for sent in _SENT_SPLIT_RE.split(text):
        recent: list = []           # [(lemma, слово, start, end)]
        for m in _WORD_RE.finditer(sent):
            word = m.group(0).lower()
            if len(word) < 4:
                continue
            p = morph.parse(word)[0]
            if str(p.tag.POS) not in _TAUT_POS:
                continue
            lemma = p.normal_form
            if lemma in _TAUT_STOP_LEMMAS:
                continue
            for l2, w2, s2, e2 in recent:
                if l2 == lemma and w2 != word and lemma not in reported:
                    reported.add(lemma)
                    start, end = offset + s2, offset + m.end()
                    out.append(TextError(
                        error_type="Лексическая",
                        subtype="Тавтология",
                        fragment=text[start:end][:80],
                        description=f"Повтор леммы «{lemma}» "
                                    f"(«{w2}» … «{m.group(0)}») в узком окне",
                        suggestion="Замените повтор синонимом",
                        position=(start, end),
                        rule_ref="RU:TAUT",
                        source="TAUT",
                        context=_ctx(text, start, end),
                        significance="низкая",
                    ))
                    break
            recent.append((lemma, word, m.start(), m.end()))
            recent = recent[-_TAUT_WINDOW:]
        offset += len(sent) + 1
    return out


def check(text: str, tokens=None) -> List[TextError]:
    """
    Все офлайн-детекторы разом (для профиля протокола). tokens — разметка
    Stanza (для согласования); без неё грамматический детектор пропускается.
    Словарные опечатки, перекрытые контекстным правилом -тся/-ться,
    отбрасываются — одно явление не считается дважды.
    """
    tsya = tsya_errors(text)
    spans = [e.position for e in tsya]
    spelling = [e for e in spelling_errors(text)
                if not any(s < e.position[1] and e.position[0] < t
                           for s, t in spans)]
    agreement = agreement_errors(text, tokens) if tokens else []
    return spelling + tsya + agreement + lexical_errors(text)
