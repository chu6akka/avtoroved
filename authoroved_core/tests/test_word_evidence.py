"""Детерминированная справка по словоформе; модель не участвует."""
import pytest

from authoroved_core.core.models import Candidate, Span, Token
from authoroved_core.core.word_evidence import (
    FrequencyDictionary, collect, count_occurrences, damerau_levenshtein,
    deterministic_verdict, lemma_for, nearest_replacement, summary_lines,
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


def test_typo_verdict_leans_on_languagetool_not_on_a_lemma_dictionary():
    """Снимок НКРЯ построен по леммам: словоформа «пришол» давала ближайшим
    «прикол» — верный вердикт при ложном обосновании."""
    text = "Он пришол домой вчера вечером."

    evidence = collect(candidate("пришол", text, ("пришёл",)), text, (), dictionary())

    assert evidence.verdict == "spelling_error"
    assert evidence.nearest_replacement == "пришёл"
    assert "прикол" not in evidence.verdict_reason


def test_word_known_to_the_corpus_is_a_dictionary_gap():
    text = "Вся беда в этом одном слове."

    evidence = collect(candidate("беда", text), text, (), dictionary())

    assert evidence.verdict == "dictionary_gap"
    assert evidence.known_to_corpus and evidence.frequency_ipm == 93.45


def test_repetition_blocks_the_typo_verdict_but_decides_nothing_else():
    """Повтор отличает опечатку от не-опечатки и только это.

    Окказионализм, неологизм и заимствование повторяются одинаково.
    """
    text = "Был тимбилдинг, потом ещё тимбилдинг и снова тимбилдинг."

    evidence = collect(candidate("тимбилдинг", text, ("тимбилдинге",)), text, (), dictionary())

    assert evidence.repeats_in_text == 3
    assert evidence.verdict == ""
    assert "на опечатку не похоже" in evidence.verdict_reason


def test_unknown_and_unlike_anything_goes_to_the_expert():
    text = "Вся инфоцыганщина тут и заканчивается."

    evidence = collect(candidate("инфоцыганщина", text), text, (), dictionary())

    assert evidence.verdict == ""
    assert not evidence.known_to_corpus


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


def test_evidence_works_without_a_dictionary_snapshot():
    text = "Текст со словом движе внутри."

    evidence = collect(candidate("движе", text), text)

    assert evidence.frequency_ipm is None
    assert evidence.verdict == ""
    assert summary_lines(evidence)[0] == "НКРЯ: слова нет в снимке словаря"


def test_summary_shows_the_same_numbers_the_model_receives():
    text = "Он пришол домой."

    lines = summary_lines(collect(candidate("пришол", text, ("пришёл",)), text, (), dictionary()))

    assert any("В тексте встречается: 1" in line for line in lines)
    assert any("пришёл" in line for line in lines)


def test_latin_and_tripled_letter_are_reported_not_judged():
    text = "Он написал ghbdtn в раскладке."

    evidence = collect(candidate("ghbdtn", text), text, (), dictionary())

    assert evidence.has_latin and not evidence.has_tripled_letter
    # Латиница сама по себе вердикта не даёт: это может быть и транслитерация.
    assert evidence.verdict == ""


def test_verdict_is_pure_and_recomputable_from_the_numbers():
    text = "Он пришол домой."
    evidence = collect(candidate("пришол", text, ("пришёл",)), text, (), dictionary())

    assert deterministic_verdict(evidence) == (evidence.verdict, evidence.verdict_reason)
