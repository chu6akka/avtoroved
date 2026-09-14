"""Русскоязычное представление технических меток Stanza/UD."""
from __future__ import annotations

from dataclasses import dataclass

from authoroved_core.core.models import Token


@dataclass(frozen=True)
class RussianWordClass:
    key: str
    title: str
    technical_basis: str


WORD_CLASSES = (
    RussianWordClass(
        "noun", "Существительные",
        "технические метки Stanza NOUN и PROPN; имена собственные не выделяются в отдельную часть речи",
    ),
    RussianWordClass(
        "verb", "Глаголы",
        "технические метки Stanza VERB и AUX; AUX не показывается как отдельная часть речи русского языка",
    ),
    RussianWordClass("adjective", "Прилагательные", "метка Stanza ADJ"),
    RussianWordClass("adverb", "Наречия", "метка Stanza ADV"),
    RussianWordClass(
        "pronoun", "Местоименные слова",
        "технические метки Stanza PRON и DET; DET не показывается как отдельная часть речи русского языка",
    ),
    RussianWordClass("numeral", "Числительные", "метка Stanza NUM"),
    RussianWordClass("preposition", "Предлоги", "метка Stanza ADP"),
    RussianWordClass(
        "conjunction", "Союзы",
        "метки Stanza CCONJ и SCONJ; также PART при синтаксической метке cc",
    ),
    RussianWordClass("particle", "Частицы", "метка Stanza PART"),
    RussianWordClass("interjection", "Междометия", "метка Stanza INTJ"),
    RussianWordClass("other", "Не классифицировано", "прочие технические метки Stanza"),
)

CLASS_BY_KEY = {item.key: item for item in WORD_CLASSES}


def russian_word_class_key(token: Token) -> str:
    """Укрупняет UPOS; это представление, а не исправление модели Stanza."""
    dependency = token.dependency.split(":", 1)[0] if token.dependency else ""
    if dependency == "cc" and token.pos in {"PART", "CCONJ", "SCONJ"}:
        return "conjunction"
    if token.pos in {"NOUN", "PROPN"}:
        return "noun"
    if token.pos in {"VERB", "AUX"}:
        return "verb"
    if token.pos == "ADJ":
        return "adjective"
    if token.pos == "ADV":
        return "adverb"
    if token.pos in {"PRON", "DET"}:
        return "pronoun"
    if token.pos == "NUM":
        return "numeral"
    if token.pos == "ADP":
        return "preposition"
    if token.pos in {"CCONJ", "SCONJ"}:
        return "conjunction"
    if token.pos == "PART":
        return "particle"
    if token.pos == "INTJ":
        return "interjection"
    return "other"


def russian_word_class(token: Token) -> RussianWordClass:
    return CLASS_BY_KEY[russian_word_class_key(token)]


def is_service_word(token: Token) -> bool:
    """В интерфейсе служебные слова — только предлоги, союзы и частицы."""
    return russian_word_class_key(token) in {"preposition", "conjunction", "particle"}
