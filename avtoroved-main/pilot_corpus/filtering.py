"""Conservative, non-authorship filters for Pilot 01 source material.

The functions in this module only describe corpus suitability.  They are not
features of the Authoroved analysis pipeline and must never be used as
authorship evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import html
import re
from typing import Any, Iterable


WORD_RE = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", re.UNICODE)
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
MARKUP_RE = re.compile(r"(?:```|`[^`]+`|!\[[^]]*]\([^)]*\)|\[[^]]+]\([^)]*\)|</?\w+[^>]*>)")
QUOTE_LINE_RE = re.compile(r"(?m)^\s*>.+$")

PREFERRED_TAGS = {
    "моё", "мое", "истории из жизни", "реальная история из жизни",
    "воспоминания", "личный опыт", "работа", "семья", "детство",
    "ситуация", "мнение", "мысли", "наблюдение",
}

HARD_EXCLUSION_TERMS = {
    "новости", "копипаста", "перевод", "реклама", "промо", "стихи",
    "стишки", "стишки-пирожки", "фанфик", "цитаты", "анекдот",
    "анекдоты", "рецепт", "рецепты",
}

REPOST_TERMS = {
    "копипаста", "перепечатка", "новости", "новость", "сми", "цитаты",
    "источник", "автор не я", "не мое", "не моё",
}
TRANSLATION_TERMS = {"перевод", "переведено", "перевод статьи"}
COMMERCIAL_TERMS = {
    "реклама", "промо", "магазин", "интернет-магазин", "продажа",
    "акция", "скидка", "бренд", "компания", "наш сайт", "заказать",
}
REPLY_TERMS = {"ответ", "ответ на пост", "ответ на комментарий"}

SERIES_RE = re.compile(
    r"(?:\b(?:часть|глава|эпизод|серия)\s*[№#.:\-]?\s*\d+\b|\bпродолжение\b)",
    re.IGNORECASE,
)
ACCOUNT_RISK_RE = re.compile(
    r"(?:\.ru$|news|analytics|official|press|agency|company|magazine|shop|store)",
    re.IGNORECASE,
)
NARRATIVE_RE = re.compile(
    r"\b(?:я|мы|мне|нас|мой|моя|помню|случилось|однажды|тогда|работал|работала)\b",
    re.IGNORECASE,
)
OPINION_RE = re.compile(
    r"\b(?:думаю|считаю|по[- ]моему|на мой взгляд|мнение|кажется|полагаю|вывод)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FilterResult:
    status: str
    rejection_reasons: tuple[str, ...]
    flags: tuple[str, ...]
    word_count: int
    char_count: int
    russian_ratio: float
    quote_ratio: float
    markup_ratio: float
    content_type: str
    priority_score: int
    date: str
    exact_text_sha256: str
    simhash: str


def words(text: str) -> list[str]:
    return WORD_RE.findall(text or "")


def count_words(text: str) -> int:
    return len(words(text))


def timestamp_to_date(value: Any) -> str:
    try:
        return datetime.fromtimestamp(int(value), timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def russian_letter_ratio(text: str) -> float:
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return 0.0
    cyrillic = sum("а" <= char.lower() <= "я" or char.lower() == "ё" for char in letters)
    return cyrillic / len(letters)


def quote_ratio(text: str) -> float:
    if not text:
        return 0.0
    quoted = sum(len(match.group(0)) for match in QUOTE_LINE_RE.finditer(text))
    for match in re.finditer(r"<blockquote\b[^>]*>.*?</blockquote>", text, re.I | re.S):
        quoted += len(match.group(0))
    return min(1.0, quoted / len(text))


def markup_ratio(text: str) -> float:
    if not text:
        return 0.0
    marked = sum(len(match.group(0)) for match in MARKUP_RE.finditer(text))
    marked += sum(len(match.group(0)) for match in URL_RE.finditer(text))
    return min(1.0, marked / len(text))


def normalize_for_duplicate_check(text: str) -> str:
    decoded = html.unescape(text or "").lower()
    return " ".join(WORD_RE.findall(decoded))


def exact_text_sha256(text: str) -> str:
    normalized = normalize_for_duplicate_check(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def text_simhash(text: str) -> str:
    tokens = normalize_for_duplicate_check(text).split()
    if not tokens:
        return "0" * 16
    shingles = tokens if len(tokens) < 5 else [" ".join(tokens[i:i + 5]) for i in range(len(tokens) - 4)]
    vector = [0] * 64
    for shingle in shingles:
        value = int.from_bytes(hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest(), "big")
        for bit in range(64):
            vector[bit] += 1 if value & (1 << bit) else -1
    result = sum((1 << bit) for bit, weight in enumerate(vector) if weight >= 0)
    return f"{result:016x}"


def simhash_distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def classify_content(text: str, tags: Iterable[str] = ()) -> str:
    lowered_tags = {str(tag).strip().lower() for tag in tags or ()}
    narrative = bool(NARRATIVE_RE.search(text or "")) or bool(
        lowered_tags & {"история", "истории из жизни", "личный опыт", "воспоминания"}
    )
    opinion = bool(OPINION_RE.search(text or "")) or bool(
        lowered_tags & {"мнение", "мысли", "наблюдение"}
    )
    if narrative and opinion:
        return "mixed"
    if narrative:
        return "narrative"
    if opinion:
        return "opinion"
    return "other"


def _contains_any(haystack: str, needles: set[str]) -> bool:
    return any(needle in haystack for needle in needles)


def assess_post(row: dict[str, Any]) -> FilterResult:
    text = str(row.get("text_markdown") or "")
    title = str(row.get("title") or "")
    tags = [str(tag) for tag in (row.get("tags") or [])]
    username = str(row.get("username") or "")
    tags_lower = {tag.strip().lower() for tag in tags}
    searchable = " ".join([title.lower(), " ".join(tags_lower), text[:1500].lower()])
    word_count = count_words(text)
    char_count = len(text)
    ru_ratio = russian_letter_ratio(text)
    q_ratio = quote_ratio(text)
    m_ratio = markup_ratio(text)
    date = timestamp_to_date(row.get("timestamp"))
    year = int(date[:4]) if date else None

    reasons: list[str] = []
    flags: list[str] = []
    author_id = row.get("author_id")
    if author_id is None or str(author_id).strip() in {"", "0", "None"}:
        reasons.append("missing_author_id")
    if not text.strip():
        reasons.append("empty_text")
    if word_count < 300:
        reasons.append("below_300_words")
        flags.append("low_content")
    elif word_count > 700:
        reasons.append("above_700_words")
    if ru_ratio < 0.70:
        reasons.append("not_predominantly_russian")
    if not date:
        reasons.append("invalid_timestamp")

    hard_tag_matches = sorted(tags_lower & HARD_EXCLUSION_TERMS)
    if hard_tag_matches:
        reasons.append("excluded_tag:" + ",".join(hard_tag_matches))

    if _contains_any(searchable, REPOST_TERMS):
        flags.append("possible_repost")
    if _contains_any(searchable, TRANSLATION_TERMS):
        flags.append("possible_translation")
    if q_ratio >= 0.25:
        flags.append("high_quote_ratio")
    if _contains_any(searchable, COMMERCIAL_TERMS):
        flags.append("commercial_account")
    if ACCOUNT_RISK_RE.search(username):
        flags.append("commercial_account")
    if SERIES_RE.search(title):
        flags.append("series_post")
    if tags_lower & REPLY_TERMS or title.lower().startswith(("ответ ", "ответ на")):
        flags.append("reply_post")
    if m_ratio >= 0.18:
        flags.append("high_markup")
    url_chars = sum(len(match.group(0)) for match in URL_RE.finditer(text))
    if text and url_chars / len(text) >= 0.20:
        if "low_content" not in flags:
            flags.append("low_content")
        reasons.append("mostly_links")
    code_chars = sum(len(match.group(0)) for match in re.finditer(r"```.*?```", text, re.S))
    if text and code_chars / len(text) >= 0.20:
        reasons.append("high_code_ratio")
        if "high_markup" not in flags:
            flags.append("high_markup")
    if set(flags) & {
        "possible_repost", "possible_translation", "commercial_account",
        "high_quote_ratio", "series_post",
    }:
        flags.append("suspicious_authorship")

    flags = list(dict.fromkeys(flags))
    if reasons:
        status = "rejected"
    elif flags:
        status = "review"
    else:
        status = "candidate"

    priority = 0
    if tags_lower & {"моё", "мое"}:
        priority += 5
    priority += min(4, 2 * len(tags_lower & PREFERRED_TAGS))
    if year is not None and 2017 <= year <= 2021:
        priority += 3
    if 350 <= word_count <= 650:
        priority += 1
    priority -= 2 * len(flags)

    return FilterResult(
        status=status,
        rejection_reasons=tuple(reasons),
        flags=tuple(flags),
        word_count=word_count,
        char_count=char_count,
        russian_ratio=ru_ratio,
        quote_ratio=q_ratio,
        markup_ratio=m_ratio,
        content_type=classify_content(text, tags),
        priority_score=priority,
        date=date,
        exact_text_sha256=exact_text_sha256(text),
        simhash=text_simhash(text),
    )
