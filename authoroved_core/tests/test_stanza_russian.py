from authoroved_core.core.models import Span, Token
from authoroved_core.core.stanza_russian import explain_stanza_tokens


def token(text, lemma, pos, feats, dependency, head, index, start):
    return Token(text, lemma, pos, feats, dependency, head, 1, index,
                 Span(start, start + len(text)))


def test_stanza_codes_are_presented_as_russian_language_categories():
    tokens = [
        token("Он", "он", "PRON", {"Case": "Nom", "Number": "Sing"}, "nsubj", 2, 1, 0),
        token("будет", "быть", "AUX", {"Tense": "Fut", "Person": "3"}, "aux", 3, 2, 3),
        token("писать", "писать", "VERB", {"VerbForm": "Inf", "Aspect": "Imp"}, "root", 0, 3, 9),
    ]

    values = explain_stanza_tokens(tokens)

    assert values[0].word_class == "Местоименные слова"
    assert "падеж: именительный" in values[0].morphology
    assert "число: единственное число" in values[0].morphology
    assert values[1].word_class == "Глаголы"
    assert all("вспомогатель" not in text.casefold() for text in values[1].morphology)
    assert "связано со словом «писать»" in values[1].relation
    assert "AUX не показывается как отдельная часть речи" in values[1].technical
    assert values[2].word_class == "Инфинитив — неопределённая форма глагола"
    assert "форма глагола: инфинитив" in values[2].morphology
    assert "служебная машинная разметка" in values[2].technical


def test_unknown_stanza_values_do_not_leak_as_russian_grammar_terms():
    value = explain_stanza_tokens([
        token("тест", "тест", "X", {"UnknownFeature": "AlienValue"}, "mystery", 0, 1, 0),
    ])[0]

    assert value.word_class == "Не классифицировано"
    assert value.morphology == (
        "другая характеристика модели: значение указано только в технических данных",
    )
    assert value.relation == "другая техническая связь Stanza"
    assert "UnknownFeature" in value.technical


def test_punctuation_is_not_presented_as_unknown_part_of_speech():
    value = explain_stanza_tokens([
        token(".", ".", "PUNCT", {}, "punct", 1, 2, 4),
    ])[0]

    assert value.word_class == "Знак препинания"
    assert value.relation == "знак препинания"
