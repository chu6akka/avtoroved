from hashlib import sha256

import pytest

from authoroved_core.core.auto_features import FeatureExtractionService
from authoroved_core.core.document import Document
from authoroved_core.core.feature_models import Applicability
from authoroved_core.core.feature_registry import FeatureRegistry
from authoroved_core.core.models import Span, Token
from authoroved_core.nlp.parsed_document import ParsedDocument
from authoroved_core.nlp.russian.adapter import RussianGrammarAdapter


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
        ("Иду", "VERB", {"VerbForm": "Fin", "Tense": "Pres", "Person": "1", "Aspect": "Imp", "Mood": "Ind"}, 0),
        ("в", "ADP", {}, 0),
        ("дом", "NOUN", {"Case": "Acc"}, 0),
        ("eMail", "NOUN", {"Case": "Nom"}, 1),
        ("ёлка", "NOUN", {"Case": "Nom"}, 1),
        ("Он", "PRON", {"Person": "3", "Number": "Sing", "PronType": "Prs", "Case": "Nom"}, 2),
        ("видел", "VERB", {"VerbForm": "Fin", "Tense": "Past", "Aspect": "Imp", "Mood": "Ind"}, 2),
        ("дом", "NOUN", {"Case": "Acc"}, 2),
    ])

    observations = service.analyze_object(document(text), tokens)
    by_id = {item.feature_id: item for item in observations}

    assert len(observations) == 10
    assert by_id["LEX_001"].raw_value["counts"] == {"в": 1, "и": 1}
    assert by_id["LEX_002"].raw_value["features"]["лицо"] == {
        "1-е лицо": 1, "2-е лицо": 1, "3-е лицо": 1,
    }
    assert by_id["LEX_005"].applicability is Applicability.INSUFFICIENT_DATA
    assert by_id["MOR_001"].normalized_value["percent_of_words"]["Местоименные слова"] > 0
    assert by_id["MOR_003"].raw_value["counts"] == {
        "винительный": 2, "именительный": 5,
    }
    assert by_id["MOR_004"].raw_value["counts"]["время"] == {
        "настоящее": 1, "прошедшее": 1,
    }
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


def test_mor_003_uses_russian_representation_instead_of_raw_ud_tokens(service):
    text = "дома"
    source = Token(
        "дома", "дом", "NOUN", {"Case": "Gen"}, "root", 0, 0, 1, Span(0, 4),
    )
    russian_document = RussianGrammarAdapter().adapt(
        ParsedDocument.from_tokens(text, [source])
    )
    conflicting_raw_token = Token(
        "дома", "дома", "X", {"Case": "Acc"}, "root", 0, 0, 1, Span(0, 4),
    )

    observations = service.analyze_object(
        document(text), [conflicting_raw_token], russian_document=russian_document,
    )
    feature = next(item for item in observations if item.feature_id == "MOR_003")

    assert feature.raw_value["counts"] == {"родительный": 1}
    assert feature.evidence[0].label == "падеж: родительный"
    assert feature.method_version == "auto-0.2.0"


def test_mor_004_uses_russian_categories_and_human_readable_features(service):
    text = "писал"
    source = Token(
        "писал", "писать", "VERB",
        {"VerbForm": "Fin", "Tense": "Past", "Person": "1",
         "Aspect": "Imp", "Mood": "Ind"},
        "root", 0, 0, 1, Span(0, 5),
    )
    russian_document = RussianGrammarAdapter().adapt(
        ParsedDocument.from_tokens(text, [source])
    )
    conflicting_raw_token = Token(
        "писал", "писал", "NOUN", {"Case": "Nom"},
        "root", 0, 0, 1, Span(0, 5),
    )

    observations = service.analyze_object(
        document(text), [conflicting_raw_token], russian_document=russian_document,
    )
    feature = next(item for item in observations if item.feature_id == "MOR_004")

    assert feature.raw_value["verb_forms"] == 1
    assert feature.raw_value["counts"] == {
        "время": {"прошедшее": 1},
        "вид": {"несовершенный вид": 1},
        "лицо": {"1-е лицо": 1},
        "наклонение": {"изъявительное": 1},
    }
    assert "время: прошедшее" in feature.evidence[0].label
    assert feature.method_version == "auto-0.2.0"


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
