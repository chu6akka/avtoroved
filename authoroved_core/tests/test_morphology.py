from authoroved_core.core.models import Span, Token
from authoroved_core.core.stanza_russian import explain_stanza_tokens
from authoroved_core.metrics.morphology import (
    GROUP_SAE, GROUP_SOKOLOVA, morphology_metrics, pronoun_class,
)


def token(text, lemma, pos, feats, dependency, head, index, start, sentence=1):
    return Token(text, lemma, pos, feats, dependency, head, sentence, index,
                 Span(start, start + len(text)))


# «Нужно было успеть. Он был рад. Письмо написано мной, читая.»
TOKENS = [
    token("Нужно", "нужный", "ADJ", {"Variant": "Short", "Gender": "Neut", "Number": "Sing"}, "root", 0, 1, 0),
    token("было", "быть", "AUX", {"VerbForm": "Fin", "Tense": "Past"}, "cop", 1, 2, 6),
    token("успеть", "успеть", "VERB", {"VerbForm": "Inf", "Aspect": "Perf"}, "csubj", 1, 3, 11),
    token("Он", "он", "PRON", {"Case": "Nom", "Person": "3", "PronType": "Prs"}, "nsubj", 3, 1, 19, 2),
    token("был", "быть", "AUX", {"VerbForm": "Fin", "Tense": "Past"}, "cop", 3, 2, 22, 2),
    token("рад", "рад", "ADJ", {"Variant": "Short", "Gender": "Masc"}, "root", 0, 3, 26, 2),
    token("Письмо", "письмо", "NOUN", {"Case": "Nom", "Animacy": "Inan"}, "nsubj:pass", 2, 1, 31, 3),
    token("написано", "писать", "VERB", {"VerbForm": "Part", "Variant": "Short", "Voice": "Pass"}, "root", 0, 2, 38, 3),
    token("мной", "я", "PRON", {"Case": "Ins", "Person": "1"}, "obl:agent", 2, 3, 47, 3),
    token("читая", "читать", "VERB", {"VerbForm": "Conv", "Aspect": "Imp"}, "advcl", 2, 4, 53, 3),
]


def by_name():
    return {metric.name: metric for metric in morphology_metrics(TOKENS)}


def test_russian_parts_of_speech_follow_traditional_grammar():
    metrics = by_name()

    assert metrics["Слова категории состояния"].value.startswith("1 ")
    assert metrics["Краткие прилагательные"].value.startswith("1 ")  # «рад», но не «нужно»
    assert metrics["Причастия"].value.startswith("1 ")
    assert metrics["Деепричастия"].value.startswith("1 ")
    assert metrics["Инфинитивы"].value.startswith("1 ")
    assert metrics["Глаголы в спрягаемой форме"].value.startswith("2 ")
    assert metrics["Местоимения"].value.startswith("2 ")


def test_all_forty_classic_coefficients_are_computed():
    metrics = morphology_metrics(TOKENS)

    assert sum(m.group == GROUP_SOKOLOVA for m in metrics) == 20
    assert sum(m.group == GROUP_SAE and m.name.startswith("Коэффициент") for m in metrics) == 20
    names = {m.name: m for m in metrics}
    assert names["Индекс 07. Абстрактные / конкретные существительные"].value == "Не рассчитывается автоматически"
    assert names["Коэффициент 01. Местоимения / текст"].value == "0,2 (2 / 10)"
    assert names["Коэффициент 05. Краткие прилагательные / все прилагательные"].value == "1 (1 / 1)"


def test_zero_denominator_is_reported_without_a_misleading_number():
    names = by_name()

    value = names["Коэффициент 15. Наречия / прилагательные"].value
    assert value == "0 (0 / 1)"
    assert "знаменатель равен нулю" in names["Коэффициент 18. Глаголы / наречия"].value


def test_pronoun_classes_use_russian_grammar_categories():
    assert pronoun_class(token("свой", "свой", "DET", {}, "det", 1, 1, 0)) == "possessive"
    assert pronoun_class(token("кое-что", "кое-что", "PRON", {}, "obj", 1, 1, 0)) == "indefinite"
    assert pronoun_class(token("ничей", "ничей", "DET", {}, "det", 1, 1, 0)) == "negative"
    assert pronoun_class(token("себя", "себя", "PRON", {}, "obj", 1, 1, 0)) == "reflexive"


def test_grammatical_categories_are_named_in_russian():
    names = by_name()

    assert "Падеж: именительный" in names
    assert "Форма глагола: деепричастие" in names
    assert "Залог: страдательный" in names


def test_stanza_labels_get_approximate_school_grammar_terms():
    explained = {item.text: item for item in explain_stanza_tokens(TOKENS)}

    assert explained["Нужно"].word_class == "Слово категории состояния"
    assert explained["рад"].word_class == "Прилагательные — краткая форма"
    assert explained["Он"].grammar_term == "подлежащее"
    assert explained["Письмо"].grammar_term == "подлежащее страдательной конструкции"
    assert "производителя действия" in explained["мной"].relation
    assert "творительный деятеля" in explained["мной"].grammar_term
    assert explained["читая"].grammar_term.startswith("придаточное обстоятельственное")
