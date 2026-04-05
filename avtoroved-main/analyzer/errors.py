"""
analyzer/errors.py — Анализ ошибок письменной речи
====================================================
Текущая версия: только LanguageTool (внешняя проверка).
Все regex-детекторы удалены — раздел ошибок переразрабатывается.

Сохранены:
  - Датаклассы (TextError, SkillLevel, InternetProfile, ErrorAnalysisResult)
  - Профиль интернет-коммуникации (по Колокольцевой Т.Н.)
  - Оценка навыков по С.М. Вул (работает на LT-ошибках)
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional


# ============================================================================
# ДАТАКЛАССЫ
# ============================================================================

@dataclass
class TextError:
    """Единичная ошибка в тексте."""
    error_type: str       # Пунктуационная / Орфографическая / Грамматическая / Лексическая
    subtype: str
    fragment: str
    description: str
    suggestion: str
    position: Tuple[int, int] = (0, 0)
    rule_ref: str = ""
    source: str = "LT"
    context: str = ""


@dataclass
class SkillLevel:
    """Степень развития языкового навыка (по С.М. Вул)."""
    skill_name: str
    level: str            # высокая / средняя / низкая / нулевая
    description: str
    error_count: int = 0
    error_rate: float = 0.0


@dataclass
class InternetProfile:
    """Профиль интернет-коммуникации (по Колокольцевой Т.Н.)."""
    internet_comm_score: float = 0.0
    emoji_count: int = 0
    emoticon_count: int = 0
    hashtag_count: int = 0
    mention_count: int = 0
    url_count: int = 0
    caps_words: int = 0
    slang_count: int = 0
    abbreviation_count: int = 0
    repeated_punct_count: int = 0
    missing_caps_sentences: int = 0
    features: Dict[str, int] = field(default_factory=dict)


@dataclass
class ErrorAnalysisResult:
    """Результат анализа ошибок."""
    errors: List[TextError]
    skill_levels: List[SkillLevel]
    internet_profile: InternetProfile
    total_words: int = 0
    total_sentences: int = 0


# ============================================================================
# ИНТЕРНЕТ-КОММУНИКАЦИЯ (Колокольцева Т.Н., 2016)
# ============================================================================

INTERNET_SLANG = [
    "лол", "кек", "рофл", "имхо", "кмк", "мб", "хз", "пжл", "спс",
    "ок", "нзч", "лс", "дм", "тг", "вк", "инст", "тик-ток",
    "кринж", "рил", "вайб", "чилл", "гоу", "изи", "хейт",
    "зашквар", "топ", "краш", "флекс", "рандом", "ливнуть",
    "агонь", "жиза", "лайк", "репост", "сторис", "рилс",
    "бро", "чел", "зумер", "бумер", "миллениал",
    "фейк", "хайп", "мем", "контент", "блогер",
    "донат", "стрим", "подкаст", "фолловер",
    "пруф", "сурс", "оффтоп", "флуд", "спам",
    "бан", "мут", "кик", "варн", "модер",
    "лмао", "омг", "втф", "фу", "шок",
    "норм", "оч", "прост", "типа", "короч",
]

INTERNET_ABBREVIATIONS = [
    "др", "дн", "чсв", "чб", "тж", "бтв", "имхо", "кмк",
    "нзч", "мб", "хз", "пжл", "спс", "пж", "ок", "кст",
    "сбр", "лан", "хор", "ладн", "пон", "збс", "лс",
    "тчк", "зпт", "кавычк",
]

EMOJI_PATTERN = re.compile(
    "[\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002600-\U000026FF"
    "]+", flags=re.UNICODE
)

EMOTICON_PATTERN = re.compile(
    r'(?:[:;=][-~]?[)(DPpOo3><\]\[}{|/\\])|'
    r'(?:[)(DPpOo><\]\[}{][-~]?[:;=])|'
    r'(?:\^\^|<3|xD|XD|:3|OwO|UwU|>\.<|T_T|;_;|o_O|O_o|=\))'
)

HASHTAG_PATTERN  = re.compile(r'#[A-Za-zА-Яа-яЁё_]\w{1,}')
MENTION_PATTERN  = re.compile(r'@[A-Za-zА-Яа-яЁё_]\w{1,}')
URL_PATTERN      = re.compile(r'https?://\S+|www\.\S+')
REPEATED_PUNCT   = re.compile(r'[!?]{2,}|\.{4,}')


# ============================================================================
# АНАЛИЗАТОР
# ============================================================================

class ErrorAnalyzer:
    """
    Анализатор ошибок — скелет.
    Сейчас возвращает пустой список ошибок; LT-ошибки добавляются в AnalysisThread.
    Раздел переразрабатывается.
    """

    def analyze(self, text: str, tokens=None) -> ErrorAnalysisResult:
        words = re.findall(r'[А-Яа-яЁё]+', text)
        sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
        total_words = len(words)
        total_sentences = len(sentences)

        errors: List[TextError] = []
        skill_levels = self._assess_skills(errors, total_words)
        internet_profile = analyze_internet_communication(text)

        return ErrorAnalysisResult(
            errors=errors,
            skill_levels=skill_levels,
            internet_profile=internet_profile,
            total_words=total_words,
            total_sentences=total_sentences,
        )

    def _get_context(self, text: str, start: int, end: int, window: int = 45) -> str:
        cs = max(0, start - window)
        ce = min(len(text), end + window)
        snippet = text[cs:ce].replace('\n', ' ')
        if cs > 0:
            snippet = "…" + snippet
        if ce < len(text):
            snippet = snippet + "…"
        return snippet

    def _dedup_by_span(self, errors: List[TextError]) -> List[TextError]:
        """Удалить дублирующиеся ошибки по пересечению позиций. LT имеет приоритет."""
        PRIO = {"LT": 5, "MORPH": 4, "TAUT": 2, "LEX": 1, "REGEX": 0}

        with_pos = [e for e in errors if e.position != (0, 0)]
        no_pos   = [e for e in errors if e.position == (0, 0)]

        with_pos.sort(key=lambda e: (e.position[0], -PRIO.get(e.source, 0)))

        kept: List[TextError] = []
        for err in with_pos:
            s, e_end = err.position
            overlap = any(
                not (e_end <= k.position[0] or s >= k.position[1])
                for k in kept
            )
            if not overlap:
                kept.append(err)

        return kept + no_pos

    def _assess_skills(self, errors: List[TextError], total_words: int) -> List[SkillLevel]:
        """Оценка навыков по С.М. Вул (на основе LT-ошибок)."""
        if total_words == 0:
            return [
                SkillLevel(n, "нулевая", "Нет текста для анализа")
                for n in ["Пунктуационные навыки", "Орфографические навыки",
                          "Грамматические навыки", "Лексические навыки"]
            ]

        norm = 200 / max(total_words, 1)

        def _rate(count, thresholds=(1, 3, 7)):
            normed = count * norm
            if normed <= thresholds[0]:  return "высокая", f"{count} ош. (≈{normed:.1f} на 200 слов)"
            if normed <= thresholds[1]:  return "средняя", f"{count} ош. (≈{normed:.1f} на 200 слов)"
            if normed <= thresholds[2]:  return "низкая",  f"{count} ош. (≈{normed:.1f} на 200 слов)"
            return "нулевая", f"{count} ош. (≈{normed:.1f} на 200 слов)"

        groups = {
            "Пунктуационные навыки":          [e for e in errors if e.error_type == "Пунктуационная"],
            "Орфографические навыки":         [e for e in errors if e.error_type == "Орфографическая"],
            "Грамматические навыки":          [e for e in errors if e.error_type == "Грамматическая"],
            "Лексико-фразеологические навыки":[e for e in errors if e.error_type in ("Лексическая", "Стилистическая")],
        }
        thresholds_map = {
            "Пунктуационные навыки":          (2, 5, 10),
            "Орфографические навыки":         (1, 3, 6),
            "Грамматические навыки":          (1, 3, 7),
            "Лексико-фразеологические навыки":(2, 5, 10),
        }
        levels = []
        for name, errs in groups.items():
            lv, desc = _rate(len(errs), thresholds_map[name])
            levels.append(SkillLevel(
                skill_name=name, level=lv, description=desc,
                error_count=len(errs), error_rate=len(errs) * norm,
            ))
        return levels


# ============================================================================
# ПРОФИЛЬ ИНТЕРНЕТ-КОММУНИКАЦИИ
# ============================================================================

def analyze_internet_communication(text: str) -> InternetProfile:
    """Анализ признаков интернет-коммуникации (Колокольцева Т.Н., 2016)."""
    profile = InternetProfile()

    profile.emoji_count      = len(EMOJI_PATTERN.findall(text))
    profile.emoticon_count   = len(EMOTICON_PATTERN.findall(text))
    profile.hashtag_count    = len(HASHTAG_PATTERN.findall(text))
    profile.mention_count    = len(MENTION_PATTERN.findall(text))
    profile.url_count        = len(URL_PATTERN.findall(text))
    profile.repeated_punct_count = len(REPEATED_PUNCT.findall(text))

    caps_words = re.findall(r'\b[А-ЯЁA-Z]{3,}\b', text)
    profile.caps_words = len([w for w in caps_words if len(w) > 3])

    lower = text.lower()
    profile.slang_count = sum(
        len(re.findall(r'(?<!\w)' + re.escape(s) + r'(?!\w)', lower))
        for s in INTERNET_SLANG
    )
    profile.abbreviation_count = sum(
        len(re.findall(r'(?<!\w)' + re.escape(a) + r'(?!\w)', lower))
        for a in INTERNET_ABBREVIATIONS
    )

    sentences = re.split(r'[.!?]+\s+', text)
    profile.missing_caps_sentences = sum(1 for s in sentences if s and s[0].islower())

    features = {
        'emoji': profile.emoji_count, 'emoticons': profile.emoticon_count,
        'hashtags': profile.hashtag_count, 'mentions': profile.mention_count,
        'urls': profile.url_count, 'caps': profile.caps_words,
        'slang': profile.slang_count, 'abbreviations': profile.abbreviation_count,
        'repeated_punct': profile.repeated_punct_count,
        'missing_caps': profile.missing_caps_sentences,
    }
    profile.features = features

    weights = {
        'emoji': 3.0, 'emoticons': 2.5, 'hashtags': 2.0, 'mentions': 2.0,
        'urls': 1.0, 'caps': 1.5, 'slang': 3.0, 'abbreviations': 2.0,
        'repeated_punct': 1.5, 'missing_caps': 1.0,
    }
    total_words = max(len(re.findall(r'[А-Яа-яЁёA-Za-z]+', text)), 1)
    raw_score = sum(features[k] * weights[k] for k in features) / total_words
    profile.internet_comm_score = min(1.0, raw_score * 5)

    return profile


# ============================================================================
# ФОРМАТИРОВАНИЕ
# ============================================================================

def format_error_report(result: ErrorAnalysisResult) -> str:
    lines = ["=" * 60, "АНАЛИЗ ОШИБОК ПИСЬМЕННОЙ РЕЧИ", "=" * 60, ""]
    lines.append("СТЕПЕНИ РАЗВИТИЯ НАВЫКОВ (по С.М. Вул)")
    lines.append("-" * 40)
    for skill in result.skill_levels:
        lines.append(f"  {skill.skill_name}: {skill.level.upper()}")
        lines.append(f"    {skill.description}")
    lines.append("")

    by_type: Dict[str, List[TextError]] = {}
    for e in result.errors:
        by_type.setdefault(e.error_type, []).append(e)

    lines.append(f"ВСЕГО ОШИБОК: {len(result.errors)}")
    lines.append("-" * 40)

    for etype in ["Пунктуационная", "Орфографическая", "Грамматическая", "Лексическая"]:
        errs = by_type.get(etype, [])
        lines.append(f"\n{etype.upper()} ОШИБКИ: {len(errs)}")
        for i, e in enumerate(errs[:15], 1):
            lines.append(f"  {i}. «{e.fragment}»")
            lines.append(f"     {e.description}")
            if e.suggestion:
                lines.append(f"     → {e.suggestion}")

    return "\n".join(lines)


def format_internet_profile(profile: InternetProfile) -> str:
    lines = ["=" * 60, "ПРОФИЛЬ ИНТЕРНЕТ-КОММУНИКАЦИИ", "=" * 60, ""]
    score_pct = round(profile.internet_comm_score * 100, 1)
    if score_pct >= 50:
        assessment = "ВЫСОКАЯ степень"
    elif score_pct >= 25:
        assessment = "СРЕДНЯЯ степень"
    elif score_pct >= 10:
        assessment = "НИЗКАЯ степень"
    else:
        assessment = "МИНИМАЛЬНАЯ степень"

    lines.append(f"  Оценка: {score_pct}% — {assessment} характерности интернет-коммуникации")
    lines.append("")
    lines.append("  Обнаруженные признаки:")
    for label, val in [
        ("Эмодзи", profile.emoji_count),
        ("Смайлики", profile.emoticon_count),
        ("Хештеги", profile.hashtag_count),
        ("Упоминания (@)", profile.mention_count),
        ("Ссылки (URL)", profile.url_count),
        ("Слова КАПСЛОКОМ", profile.caps_words),
        ("Интернет-сленг", profile.slang_count),
        ("Аббревиатуры", profile.abbreviation_count),
        ("Повторяющаяся пунктуация", profile.repeated_punct_count),
        ("Предложения без прописной", profile.missing_caps_sentences),
    ]:
        lines.append(f"    {label}: {val}")

    return "\n".join(lines)
