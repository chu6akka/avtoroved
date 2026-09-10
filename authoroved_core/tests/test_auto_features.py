from hashlib import sha256

import pytest

from authoroved_core.core.auto_features import FeatureExtractionService
from authoroved_core.core.document import Document
from authoroved_core.core.feature_models import Applicability
from authoroved_core.core.feature_registry import FeatureRegistry
from authoroved_core.core.models import Span, Token


def document(text: str) -> Document:
    data = text.encode("utf-8")
    digest = sha256(data).hexdigest()
    return Document("doc", "test.txt", text, data, digest, digest, "utf-8", "test")


def tokens_for(text: str, specs):
    result = []
    cursor = 0
    indexes = {}
    for value, pos, feats, sentence in specs:
        start = text.index(value, cursor)
        end = start + len(value)
        cursor = end
        indexes[sentence] = indexes.get(sentence, 0) + 1
        result.append(Token(
            value, value.casefold(), pos, dict(feats), "root", 0,
            sentence, indexes[sentence], Span(start, end),
        ))
    return result


@pytest.fixture
def service():
    return FeatureExtractionService(FeatureRegistry.load())


def test_all_ten_calculators_return_raw_normalized_values_and_exact_evidence(service):
    text = "Я и ТЫ Иду в дом?! eMail — ёлка!!!\r\nОн видел дом."
    tokens = tokens_for(text, [
        ("Я", "PRON", {"Person": "1", "Number": "Sing", "PronType": "Prs", "Case": "Nom"}, 0),
        ("и", "CCONJ", {}, 0),
        ("ТЫ", "PRON", {"Person": "2", "Number": "Sing", "PronType": "Prs", "Case": "Nom"}, 0),
        ("Иду", "VERB", {"Tense": "Pres", "Person": "1", "Aspect": "Imp", "Mood": "Ind"}, 0),
        ("в", "ADP", {}, 0),
        ("дом", "NOUN", {"Case": "Acc"}, 0),
        ("eMail", "NOUN", {"Case": "Nom"}, 1),
        ("ёлка", "NOUN", {"Case": "Nom"}, 1),
        ("Он", "PRON", {"Person": "3", "Number": "Sing", "PronType": "Prs", "Case": "Nom"}, 2),
        ("видел", "VERB", {"Tense": "Past", "Aspect": "Imp", "Mood": "Ind"}, 2),
        ("дом", "NOUN", {"Case": "Acc"}, 2),
    ])

    observations = service.analyze_object(document(text), tokens)
    by_id = {item.feature_id: item for item in observations}

    assert len(observations) == 10
    assert by_id["LEX_001"].raw_value["counts"] == {"в": 1, "и": 1}
    assert by_id["LEX_002"].raw_value["features"]["Person"] == {"1": 1, "2": 1, "3": 1}
    assert by_id["LEX_005"].applicability is Applicability.INSUFFICIENT_DATA
    assert by_id["MOR_001"].normalized_value["percent_of_words"]["местоимения"] > 0
    assert by_id["MOR_003"].raw_value["counts"] == {"Acc": 2, "Nom": 5}
    assert by_id["MOR_004"].raw_value["counts"]["Tense"] == {"Past": 1, "Pres": 1}
    assert by_id["SYN_001"].raw_value["lengths"] == [6, 2, 3]
    assert by_id["SYN_001"].normalized_value == {
        "mean": pytest.approx(11 / 3), "median": 3,
        "population_standard_deviation": pytest.approx(1.699673),
    }
    assert by_id["PUN_001"].raw_value["counts"]["—"] == 1
    assert by_id["PUN_002"].raw_value["counts"]["sequences"] == {"!!!": 1, "?!": 1}
    assert by_id["GRA_001"].raw_value["counts"] == {
        "полностью прописные": 1, "смешанный внутренний регистр": 1,
    }
    for observation in observations:
        for evidence in observation.evidence:
            assert text[evidence.span.start:evidence.span.end] == evidence.quote


def test_mattr_uses_fixed_window_50_and_is_deterministic(service):
    forms = ["слово" if index % 2 else f"форма{index}" for index in range(60)]
    # Цифры остаются внутри технической словоформы теста, но токены заданы явно.
    text = " ".join(forms)
    specs = [(form, "NOUN", {"Case": "Nom"}, index // 10) for index, form in enumerate(forms)]
    tokens = tokens_for(text, specs)

    first = service.analyze_object(document(text), tokens)
    second = service.analyze_object(document(text), tokens)
    mattr = next(item for item in first if item.feature_id == "LEX_005")

    assert first == second
    assert mattr.applicability is Applicability.APPLICABLE
    assert mattr.raw_value == {"word_count": 60, "window": 50, "window_count": 11}
    assert mattr.normalized_value["mattr"] == pytest.approx(0.52)
    assert len(mattr.evidence) == 60


@pytest.mark.parametrize("text", ["", "!!!", "😀😀"])
def test_zero_denominator_returns_insufficient_without_crash(service, text):
    observations = service.analyze_object(document(text), [])
    assert len(observations) == 10
    assert all(item.applicability is Applicability.INSUFFICIENT_DATA for item in observations)
    assert all(item.normalized_value is None for item in observations)


def test_punctuation_excludes_internal_hyphen_and_preserves_unicode_and_newlines(service):
    text = "по-русски — ёлка, елка?!\r\nДА!"
    tokens = tokens_for(text, [
        ("по-русски", "ADV", {}, 0), ("ёлка", "NOUN", {"Case": "Nom"}, 0),
        ("елка", "NOUN", {"Case": "Nom"}, 0), ("ДА", "PART", {}, 1),
    ])
    by_id = {item.feature_id: item for item in service.analyze_object(document(text), tokens)}

    punctuation = by_id["PUN_001"]
    assert "-" not in punctuation.raw_value["counts"]
    assert punctuation.raw_value["counts"]["—"] == 1
    assert punctuation.raw_value["counts"][","] == 1
    assert by_id["PUN_002"].raw_value["counts"]["sequences"] == {"?!": 1}
    assert by_id["GRA_001"].evidence[0].quote == "ДА"


def test_yo_and_e_are_not_silently_merged(service):
    text = "всё все"
    tokens = tokens_for(text, [("всё", "PART", {}, 0), ("все", "PART", {}, 0)])
    feature = next(item for item in service.analyze_object(document(text), tokens)
                   if item.feature_id == "LEX_001")

    assert feature.raw_value["counts"] == {"все": 1, "всё": 1}
