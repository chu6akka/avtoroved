"""Детерминированная справка по словоформе; модель не участвует."""
import pytest

from authoroved_core.core.models import Candidate, Span, Token
from authoroved_core.core.word_evidence import (
    FrequencyDictionary, collect, count_occurrences, damerau_levenshtein,
    is_space_split, lemma_for, nearest_replacement,
    plausible_lemma, summary_lines,
)


def dictionary():
    return FrequencyDictionary({
        "беда": [1184, 93.45, "noun"],
        "привет": [2000, 40.0, "noun"],
        "прикол": [9000, 3.10, "noun"],
    })


def candidate(form, text, replacements=()):
    start = text.index(form)
    return Candidate(
        "c1", "d1", "Слово не распознано словарём", "Слово не распознано словарём",
        "пояснение", form, Span(start, start + len(form)),
        "MORFOLOGIK_RULE_RU_RU", tuple(replacements),
    )


def test_transposition_counts_as_one_edit():
    """Перестановка — обычная опечатка, обычное расстояние считает её за две."""
    assert damerau_levenshtein("првиет", "привет") == 1
    assert damerau_levenshtein("привет", "привет") == 0
    assert damerau_levenshtein("движе", "привет") > 2


def test_replacement_equal_to_the_word_is_not_a_correction():
    assert nearest_replacement("пришол", ("пришол",)) == ("", None)
    assert nearest_replacement("пришол", ("пришол", "пришёл")) == ("пришёл", 1)


@pytest.mark.parametrize("text,form,expected", [
    ("Был тимбилдинг и ещё Тимбилдинг тут.", "тимбилдинг", 2),
    ("Слово встречается внутри тимбилдингами один раз.", "тимбилдинг", 0),
    ("Ровно один раз слово движе.", "движе", 1),
])
def test_occurrences_count_whole_words_ignoring_case(text, form, expected):
    assert count_occurrences(text, form) == expected


def test_lemma_comes_from_the_stanza_token_covering_the_span():
    text = "Он пришол домой."
    start = text.index("пришол")
    tokens = [Token("пришол", "прийти", "VERB", {}, "root", 0, 0, 0,
                    Span(start, start + len("пришол")))]

    assert lemma_for(candidate("пришол", text), tokens) == "прийти"


def test_summary_shows_the_same_numbers_the_model_receives():
    text = "Он пришол домой."

    lines = summary_lines(collect(candidate("пришол", text, ("пришёл",)), text, (), dictionary()))

    assert any("В тексте встречается: 1" in line for line in lines)
    assert any("пришёл" in line for line in lines)


def test_latin_and_tripled_letter_are_reported_not_judged():
    text = "Он написал ghbdtn в раскладке."

    evidence = collect(candidate("ghbdtn", text), text, (), dictionary())

    assert evidence.has_latin and not evidence.has_tripled_letter


@pytest.mark.parametrize("form,replacement,expected", [
    ("вахтовика", "вахт овика", True),
    ("авиаохрана", "авиа охрана", True),
    ("говнометин", "говно метин", True),
    ("Бойярд", "Бой ярд", True),
    ("пришол", "пришёл", False),
    ("гавно", "говно", False),
])
def test_space_split_is_not_a_correction(form, replacement, expected):
    """LanguageTool разбивает незнакомое сложное слово пробелом.

    Такое предложение стоит в одной правке и давало ложный вердикт
    «орфографическая ошибка» на нормальных словах: из 54 вердиктов
    контрольного набора одиннадцать возникли так.
    """
    assert is_space_split(form, replacement) is expected


def test_space_split_never_becomes_the_nearest_correction():
    assert nearest_replacement("вахтовика", ("вахт овика",)) == ("", None)
    assert nearest_replacement("вахтовика", ("вахт овика", "вахтовику")) == ("вахтовику", 1)


@pytest.mark.parametrize("form,lemma,expected", [
    ("бзди", "брать", False),
    ("бля", "брать", False),
    ("беды", "беда", True),
    ("вахтовиков", "вахтовик", True),
])
def test_stanza_lemma_must_look_like_the_form(form, lemma, expected):
    """Stanza лемматизирует и незнакомое слово правдоподобной догадкой."""
    assert plausible_lemma(form, lemma) is expected


def test_numbers_are_reported_without_any_verdict():
    """Автоматические метки сняты контрольным набором: 4 верных из 37."""
    text = "Он пришол домой вчера вечером."

    evidence = collect(candidate("пришол", text, ("пришёл",)), text, (), dictionary())

    assert not hasattr(evidence, "verdict")
    assert evidence.nearest_replacement == "пришёл" and evidence.edit_distance == 1
    assert evidence.repeats_in_text == 1


def test_word_known_to_the_corpus_reports_its_frequency():
    text = "Вся беда в этом одном слове."

    evidence = collect(candidate("беда", text), text, (), dictionary())

    assert evidence.known_to_corpus and evidence.frequency_ipm == 93.45


def test_normal_compound_word_gets_no_correction_at_all():
    text = "На пожаре работала авиаохрана и лесники."

    evidence = collect(candidate("авиаохрана", text, ("авиа охрана",)), text, (), dictionary())

    assert evidence.nearest_replacement == "" and evidence.edit_distance is None


def test_guessed_lemma_does_not_make_a_word_known_to_the_corpus():
    """«бзди» превращалось в «брать» и объявлялось известным НКРЯ."""
    text = "Не бзди, не выйдет, сказал он."
    start = text.index("бзди")
    tokens = [Token("бзди", "брать", "VERB", {}, "root", 0, 0, 0, Span(start, start + 4))]

    assert collect(candidate("бзди", text), text, tokens, dictionary()).frequency_ipm is None


def test_capitalized_word_inside_a_sentence_is_not_matched_to_a_common_noun():
    """«Бойе» и «бой» — разные слова, совпадение леммы ничего не значит."""
    text = "По приказу полковника Бойе население было согнано."
    start = text.index("Бойе")
    tokens = [Token("Бойе", "бой", "NOUN", {}, "root", 0, 0, 0, Span(start, start + 4))]
    known = FrequencyDictionary({"бой": [900, 152.86, "noun"]})

    evidence = collect(candidate("Бойе", text), text, tokens, known)

    assert evidence.capitalized_inside_sentence and evidence.frequency_ipm is None


def test_evidence_works_without_a_dictionary_snapshot():
    text = "Текст со словом движе внутри."

    evidence = collect(candidate("движе", text), text)

    assert evidence.frequency_ipm is None
    assert summary_lines(evidence)[0] == "НКРЯ: слова нет в снимке словаря"
