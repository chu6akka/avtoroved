"""Человекочитаемое русское представление технической разметки Stanza/UD.

Каждый код Universal Dependencies, который Stanza выдаёт для русского языка
(модели SynTagRus), получает русское описание. Для синтаксических связей
дополнительно указывается ближайшее понятие школьной грамматики — с пометкой
«приблизительно»: UD и традиционный русский синтаксис членят предложение
по-разному, поэтому метка nsubj не равна подлежащему по определению.
"""
from __future__ import annotations

from dataclasses import dataclass

from authoroved_core.core.auto_features import CASE_RU, FEATURE_NAME_RU, FEATURE_VALUE_RU
from authoroved_core.core.models import Span, Token
from authoroved_core.core.russian_word_classes import russian_word_class
from authoroved_core.metrics.morphology import morph_class


FEATURE_NAMES = {
    **FEATURE_NAME_RU,
    "Case": "падеж", "Animacy": "одушевлённость", "Degree": "степень сравнения",
    "Gender": "род", "VerbForm": "форма глагола", "Voice": "залог",
    "Polarity": "отрицание", "Variant": "краткая или полная форма",
    "Reflex": "возвратность", "Poss": "притяжательность",
    "NumType": "разряд числительного", "NumForm": "форма записи числа",
    "Abbr": "сокращение", "Foreign": "иноязычная запись", "Typo": "опечатка в исходном тексте",
    "Hyph": "часть слова с дефисом", "ExtPos": "служебная роль сочетания",
}
FEATURE_VALUES = {
    **FEATURE_VALUE_RU,
    "Case": {**CASE_RU, "Loc": "предложный", "Par": "второй родительный (частичный)",
             "Voc": "звательная форма"},
    "Animacy": {"Anim": "одушевлённое", "Inan": "неодушевлённое"},
    "Degree": {"Pos": "положительная", "Cmp": "сравнительная", "Sup": "превосходная"},
    "Gender": {"Masc": "мужской род", "Fem": "женский род", "Neut": "средний род", "Com": "общий род"},
    "Number": {**FEATURE_VALUE_RU["Number"], "Ptan": "только множественное число",
               "Count": "счётная форма"},
    "VerbForm": {"Fin": "личная форма", "Inf": "инфинитив", "Part": "причастие", "Conv": "деепричастие"},
    "Voice": {"Act": "действительный", "Pass": "страдательный",
              "Mid": "возвратная форма на -ся (средний залог)"},
    "Mood": {**FEATURE_VALUE_RU["Mood"], "Cnd": "сослагательное (условное)"},
    "Polarity": {"Neg": "отрицательная форма", "Pos": "утвердительная форма"},
    "Variant": {"Short": "краткая форма", "Long": "полная форма"},
    "Reflex": {"Yes": "возвратная форма"},
    "Poss": {"Yes": "притяжательное значение"},
    "NumType": {"Card": "количественное", "Ord": "порядковое", "Coll": "собирательное",
                "Frac": "дробное", "Mult": "кратное"},
    "NumForm": {"Digit": "цифрами", "Word": "словом", "Roman": "римскими цифрами"},
    "Abbr": {"Yes": "сокращение"},
    "Foreign": {"Yes": "иноязычная запись"},
    "Typo": {"Yes": "в исходном тексте опечатка"},
    "Hyph": {"Yes": "часть слова с дефисом"},
    "ExtPos": {"ADP": "составной предлог", "ADV": "составное наречие",
               "CCONJ": "составной сочинительный союз", "SCONJ": "составной подчинительный союз",
               "PRON": "составное местоимение"},
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
    "nummod": "количественное слово при имени",
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
    "orphan": "слово, замещающее пропущенное сказуемое",
    "list": "элемент перечня",
    "dislocated": "вынесенный за пределы предложения элемент",
    "goeswith": "часть слова, ошибочно написанного раздельно",
    "reparandum": "оговорка, исправленная в тексте",
    "clf": "счётное слово",
    "dep": "неуточнённая техническая связь",
}
# Уточнения подтипов связи (метка:подтип), которые встречаются в русских моделях.
DEPENDENCY_SUBTYPES = {
    "nsubj:pass": "участник, над которым совершается действие в страдательной конструкции",
    "csubj:pass": "зависимая часть в роли участника страдательной конструкции",
    "aux:pass": "компонент составной формы страдательной конструкции",
    "obl:agent": "обозначение производителя действия в страдательной конструкции",
    "obl:tmod": "обозначение времени",
    "acl:relcl": "зависимая часть с союзным словом «который», «что», «где» и т. п.",
    "nummod:gov": "числительное, управляющее падежом существительного",
    "nummod:entity": "числовое обозначение при имени",
    "flat:name": "часть имени, отчества или фамилии",
    "flat:foreign": "часть иноязычного наименования",
    "flat:title": "часть названия",
    "nmod:poss": "обозначение принадлежности",
    "advmod:neg": "отрицание",
    "compound:prt": "часть составного слова",
}
# Ближайшее понятие школьной грамматики. Соответствие приблизительное.
SCHOOL_GRAMMAR = {
    "root": "грамматическая основа (главный член) предложения",
    "nsubj": "подлежащее",
    "nsubj:pass": "подлежащее страдательной конструкции",
    "csubj": "подлежащее, выраженное инфинитивом или придаточным (придаточное подлежащное)",
    "csubj:pass": "подлежащее страдательной конструкции, выраженное придаточным",
    "obj": "прямое дополнение",
    "iobj": "косвенное дополнение",
    "obl": "обстоятельство или косвенное дополнение с предлогом",
    "obl:agent": "дополнение со значением производителя действия (творительный деятеля)",
    "obl:tmod": "обстоятельство времени",
    "advmod": "обстоятельство",
    "advmod:neg": "отрицательная частица",
    "amod": "согласованное определение",
    "det": "согласованное определение, выраженное местоимением",
    "nmod": "несогласованное определение или дополнение при имени",
    "nmod:poss": "несогласованное определение со значением принадлежности",
    "nummod": "числительное в составе словосочетания с существительным",
    "nummod:gov": "числительное, управляющее существительным (в составе неделимого словосочетания)",
    "nummod:entity": "числовое обозначение при имени",
    "appos": "приложение",
    "cop": "связка составного именного сказуемого",
    "aux": "часть составной формы глагола (например, «буду» в «буду писать»)",
    "aux:pass": "глагол «быть» в составе страдательной конструкции («был построен»)",
    "xcomp": "часть составного глагольного или именного сказуемого либо дополнение-инфинитив",
    "ccomp": "придаточное изъяснительное (или прямая речь)",
    "advcl": "придаточное обстоятельственное или деепричастный оборот",
    "acl": "причастный оборот или обособленное определение",
    "acl:relcl": "придаточное определительное",
    "conj": "однородный член предложения или часть сложносочинённого предложения",
    "cc": "сочинительный союз",
    "mark": "подчинительный союз или союзное слово",
    "case": "предлог",
    "parataxis": "вводная конструкция, вставка или часть бессоюзного сложного предложения",
    "vocative": "обращение",
    "discourse": "вводное слово, междометие или модальная частица",
    "flat": "часть составного наименования",
    "flat:name": "часть составного имени собственного (ФИО)",
    "flat:foreign": "часть иноязычного наименования",
    "fixed": "часть составного предлога, союза или частицы",
    "compound": "часть сложного слова",
    "orphan": "член неполного предложения",
    "list": "элемент перечня",
    "expl": "формальный (служебный) элемент",
    "dislocated": "вынесенный (сегментированный) член предложения",
    "goeswith": "часть одного слова",
    "reparandum": "оговорка",
}
SCHOOL_GRAMMAR_NOTE = "ближайшее понятие школьной грамматики (приблизительно)"


@dataclass(frozen=True)
class RussianStanzaToken:
    text: str
    span: Span | None
    word_class: str
    lemma: str
    morphology: tuple[str, ...]
    relation: str
    technical: str
    grammar_term: str = ""


def _display_word_class(token: Token, has_subject: bool = True) -> str:
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
    if morph_class(token, has_subject) == "predicative":
        return "Слово категории состояния"
    if token.pos == "ADJ" and token.feats.get("Variant") == "Short":
        return "Прилагательные — краткая форма"
    return russian_word_class(token).title


def _technical_basis(token: Token) -> str:
    if token.pos == "PUNCT":
        return "метка PUNCT означает знак препинания"
    if token.pos == "SYM":
        return "метка SYM означает отдельный символ"
    return russian_word_class(token).technical_basis


def dependency_description(dependency: str) -> tuple[str, str]:
    """Возвращает описание машинной связи и ближайший школьный термин (или пустую строку)."""
    label = dependency or "dep"
    base = label.split(":", 1)[0]
    description = DEPENDENCY_SUBTYPES.get(label) or DEPENDENCIES.get(base, "другая техническая связь Stanza")
    school = SCHOOL_GRAMMAR.get(label) or SCHOOL_GRAMMAR.get(base, "")
    return description, school


def explain_stanza_tokens(tokens: list[Token]) -> tuple[RussianStanzaToken, ...]:
    by_position = {(item.sentence, item.index): item for item in tokens}
    with_subject = {(item.sentence, item.head) for item in tokens
                    if item.dependency.split(":", 1)[0] in {"nsubj", "csubj"}
                    and item.pos not in {"VERB", "AUX"}}
    result = []
    for token in tokens:
        morphology = []
        for key, value in sorted(token.feats.items()):
            name = FEATURE_NAMES.get(key, "другая характеристика модели")
            translated = FEATURE_VALUES.get(key, {}).get(value, "значение указано только в технических данных")
            morphology.append(f"{name}: {translated}")
        relation, school = dependency_description(token.dependency)
        if token.head:
            head = by_position.get((token.sentence, token.head))
            if head:
                relation += f"; связано со словом «{head.text}»"
        grammar_term = "" if token.pos == "PUNCT" else school
        technical = (
            f"Stanza: часть речи {token.pos or 'не указана'}, "
            f"признаки {token.feats or 'не указаны'}, "
            f"связь {token.dependency or 'не указана'}, вершина {token.head}. "
            f"Русское представление: {_technical_basis(token)}. "
            "Это служебная машинная разметка, а не самостоятельный термин русской грамматики."
        )
        result.append(RussianStanzaToken(
            token.text, token.span,
            _display_word_class(token, (token.sentence, token.index) in with_subject), token.lemma,
            tuple(morphology), relation, technical, grammar_term,
        ))
    return tuple(result)
