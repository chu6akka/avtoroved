"""Человекочитаемое русское представление технической разметки Stanza/UD."""
from __future__ import annotations

from dataclasses import dataclass

from authoroved_core.core.auto_features import CASE_RU, FEATURE_NAME_RU, FEATURE_VALUE_RU
from authoroved_core.core.models import Span, Token
from authoroved_core.core.russian_word_classes import russian_word_class


FEATURE_NAMES = {
    **FEATURE_NAME_RU,
    "Case": "падеж", "Animacy": "одушевлённость", "Degree": "степень сравнения",
    "Gender": "род", "VerbForm": "форма глагола", "Voice": "залог",
    "Polarity": "отрицание", "Variant": "краткая или полная форма",
    "Reflex": "возвратность", "Poss": "притяжательность",
    "NumType": "тип числительного", "NumForm": "форма записи числа",
    "Abbr": "сокращение", "Foreign": "иноязычная запись",
}
FEATURE_VALUES = {
    **FEATURE_VALUE_RU,
    "Case": CASE_RU,
    "Animacy": {"Anim": "одушевлённое", "Inan": "неодушевлённое"},
    "Degree": {"Pos": "положительная", "Cmp": "сравнительная", "Sup": "превосходная"},
    "Gender": {"Masc": "мужской род", "Fem": "женский род", "Neut": "средний род"},
    "VerbForm": {"Fin": "личная форма", "Inf": "инфинитив", "Part": "причастие", "Conv": "деепричастие"},
    "Voice": {"Act": "действительный", "Pass": "страдательный", "Mid": "средний"},
    "Polarity": {"Neg": "отрицательная форма", "Pos": "утвердительная форма"},
    "Variant": {"Short": "краткая форма"},
    "Reflex": {"Yes": "возвратная форма"},
    "Poss": {"Yes": "притяжательное значение"},
    "Abbr": {"Yes": "сокращение"},
    "Foreign": {"Yes": "иноязычная запись"},
}
DEPENDENCIES = {
    "root": "центр машинного разбора предложения",
    "nsubj": "обозначение участника, соотнесённого со сказуемым",
    "csubj": "часть высказывания, соотнесённая со сказуемым как участник",
    "obj": "обозначение объекта действия",
    "iobj": "обозначение косвенного объекта действия",
    "obl": "обстоятельственное или косвенно-объектное распространение",
    "advmod": "слово с обстоятельственным значением",
    "amod": "признак предмета",
    "nmod": "зависимое именное распространение",
    "det": "местоименное определение",
    "case": "предлог или другой показатель связи именной формы",
    "cc": "союз, связывающий однородные части",
    "conj": "часть сочинительного ряда",
    "mark": "союз или частица, вводящие зависимую часть",
    "cop": "связочный компонент составного сказуемого",
    "aux": "компонент составной глагольной формы",
    "punct": "знак препинания",
    "parataxis": "присоединённая или соположенная часть",
    "xcomp": "зависимое действие без собственного выраженного участника",
    "ccomp": "зависимая предикативная часть",
    "acl": "определительная часть при имени",
    "advcl": "обстоятельственная зависимая часть",
    "appos": "поясняющее наименование",
    "flat": "часть составного наименования",
    "fixed": "часть устойчивого служебного сочетания",
    "compound": "часть сложного обозначения",
    "vocative": "обращение",
    "discourse": "элемент организации речи",
    "expl": "служебный элемент конструкции",
    "dep": "неуточнённая техническая связь",
}


@dataclass(frozen=True)
class RussianStanzaToken:
    text: str
    span: Span | None
    word_class: str
    lemma: str
    morphology: tuple[str, ...]
    relation: str
    technical: str


def _display_word_class(token: Token) -> str:
    if token.pos == "PUNCT":
        return "Знак препинания"
    if token.pos == "SYM":
        return "Символ"
    if token.feats.get("VerbForm") == "Part":
        return "Причастие — особая форма глагола"
    if token.feats.get("VerbForm") == "Conv":
        return "Деепричастие — особая форма глагола"
    if token.feats.get("VerbForm") == "Inf":
        return "Инфинитив — неопределённая форма глагола"
    return russian_word_class(token).title


def _technical_basis(token: Token) -> str:
    if token.pos == "PUNCT":
        return "метка PUNCT означает знак препинания"
    if token.pos == "SYM":
        return "метка SYM означает отдельный символ"
    return russian_word_class(token).technical_basis


def explain_stanza_tokens(tokens: list[Token]) -> tuple[RussianStanzaToken, ...]:
    by_position = {(item.sentence, item.index): item for item in tokens}
    result = []
    for token in tokens:
        morphology = []
        for key, value in sorted(token.feats.items()):
            name = FEATURE_NAMES.get(key, "другая характеристика модели")
            translated = FEATURE_VALUES.get(key, {}).get(value, "значение указано только в технических данных")
            morphology.append(f"{name}: {translated}")
        base_dependency = token.dependency.split(":", 1)[0] if token.dependency else "dep"
        relation = DEPENDENCIES.get(base_dependency, "другая техническая связь Stanza")
        if token.head:
            head = by_position.get((token.sentence, token.head))
            if head:
                relation += f"; связано со словом «{head.text}»"
        technical = (
            f"Stanza: часть речи {token.pos or 'не указана'}, "
            f"признаки {token.feats or 'не указаны'}, "
            f"связь {token.dependency or 'не указана'}, вершина {token.head}. "
            f"Русское представление: {_technical_basis(token)}. "
            "Это служебная машинная разметка, а не самостоятельный термин русской грамматики."
        )
        result.append(RussianStanzaToken(
            token.text, token.span, _display_word_class(token), token.lemma,
            tuple(morphology), relation, technical,
        ))
    return tuple(result)
