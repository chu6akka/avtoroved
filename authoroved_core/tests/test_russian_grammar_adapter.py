import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from authoroved_core.core.models import Span, Token
from authoroved_core.core.auto_features import FeatureExtractionService
from authoroved_core.core.document import Document
from authoroved_core.nlp.stanza_adapter import convert_document
from authoroved_core.nlp.parsed_document import ParsedDocument
from authoroved_core.nlp.russian.adapter import RussianGrammarAdapter
from authoroved_core.nlp.russian.enums import InterpretationStatus, MappingType
from authoroved_core.nlp.russian.rules import RussianGrammarRuleRegistry


FIXTURE = Path(__file__).parent / "fixtures" / "russian_grammar_mvp.json"


def token(value):
    return Token(
        value["text"], value["lemma"], value["pos"], value["feats"],
        value["dependency"], value["head"], 0, value["index"], Span(*value["span"]),
        xpos=value.get("xpos", ""),
    )


@pytest.fixture(scope="module")
def examples():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("example_id", [
    "aux_be", "gerund", "participle", "finite_advcl", "coordinated_members",
    "coordinated_clauses", "det_pronominal", "ambiguous_parataxis",
])
def test_required_russian_examples(example_id, examples):
    example = next(item for item in examples if item["id"] == example_id)
    parsed = ParsedDocument.from_tokens(example["text"], [token(item) for item in example["tokens"]])
    result = RussianGrammarAdapter().adapt(parsed)
    expected = example["expected"]
    annotation = result.annotation_at(0, expected["token"])

    assert result.source is parsed
    assert annotation.source_text == example["text"][annotation.source_span.start:annotation.source_span.end]
    if "category" in expected:
        assert annotation.russian_category.value == expected["category"]
    if "rule" in expected:
        assert annotation.rule_id == expected["rule"]
    if "syntax_rule" in expected:
        assert expected["syntax_rule"] in annotation.triggered_rule_ids
    if "status" in expected:
        assert annotation.status.value == expected["status"]
    if "construction" in expected:
        assert any(item.type.value == expected["construction"] for item in result.constructions)
    if "not_construction" in expected:
        assert not any(item.type.value == expected["not_construction"] for item in result.constructions)
    if "not_label" in expected:
        assert expected["not_label"].casefold() not in annotation.explanation.casefold()
    if "not_category" in expected:
        assert annotation.russian_category.value != expected["not_category"]


def test_mapping_types_and_raw_ud_are_preserved(examples):
    source = next(item for item in examples if item["id"] == "aux_be")
    tokens = [token(item) for item in source["tokens"]]
    result = RussianGrammarAdapter().adapt(ParsedDocument.from_tokens(source["text"], tokens))

    pronoun = result.annotation_at(0, 1)
    auxiliary = result.annotation_at(0, 2)
    infinitive = result.annotation_at(0, 3)
    assert pronoun.mapping_type is MappingType.CONTEXTUAL
    assert auxiliary.mapping_type is MappingType.NON_ISOMORPHIC
    assert infinitive.mapping_type is MappingType.DIRECT
    assert auxiliary.raw_ud.upos == "AUX"
    assert auxiliary.raw_ud.features == tokens[1].feats
    assert result.source.tokens[1] is tokens[1]


def test_pronominal_feature_codes_receive_russian_labels(examples):
    source = next(item for item in examples if item["id"] == "det_pronominal")
    tokens = [token(item) for item in source["tokens"]]
    result = RussianGrammarAdapter().adapt(
        ParsedDocument.from_tokens(source["text"], tokens)
    )

    demonstrative = result.annotation_at(0, 1)
    assert demonstrative.russian_features["тип местоименного слова"] == "указательные"
    assert "PronType" not in demonstrative.russian_features


@pytest.mark.parametrize("relation,expected_rule", [
    ("nsubj", "RU_SYN_001"), ("obj", "RU_SYN_002"), ("iobj", "RU_SYN_003"),
    ("amod", "RU_SYN_004"), ("nmod", "RU_SYN_005"), ("advmod", "RU_SYN_006"),
    ("acl:relcl", "RU_SYN_007"), ("cc", "RU_SYN_012"), ("mark", "RU_SYN_013"),
    ("cop", "RU_SYN_014"), ("orphan", "RU_SYN_016"), ("appos", "RU_SYN_017"),
    ("vocative", "RU_SYN_018"),
])
def test_syntax_registry_rules_are_traceable(relation, expected_rule):
    value = Token("слово", "слово", "NOUN", {}, relation, 0, 0, 1, Span(0, 5))
    result = RussianGrammarAdapter().adapt(ParsedDocument.from_tokens("слово", [value]))
    assert expected_rule in result.annotations[0].triggered_rule_ids


def test_invalid_unknown_missing_and_malformed_tokens_do_not_abort_document():
    tokens = [
        Token("???", "???", "ALIEN", {}, "dep", 0, 0, 1, Span(0, 3)),
        Token("слово", "слово", "NOUN", {}, "", 0, 0, 2, Span(4, 9)),
        Token("ещё", "ещё", "ADV", "not-a-dict", "advmod", 2, 0, 3, Span(10, 13)),
        Token("дом", "дом", "NOUN", {}, "root", 0, 0, 4, Span(14, 17)),
    ]
    parsed = ParsedDocument.from_tokens("??? слово ещё дом", tokens)
    result = RussianGrammarAdapter().adapt(parsed)

    assert len(result.annotations) == 4
    assert result.annotations[0].status is InterpretationStatus.AMBIGUOUS
    assert result.annotations[1].status is InterpretationStatus.INVALID_SOURCE
    assert result.annotations[2].status is InterpretationStatus.INVALID_SOURCE
    assert result.annotations[3].status is InterpretationStatus.RESOLVED
    assert result.source.tokens == tuple(tokens)


def test_same_ud_input_is_deterministic(examples):
    source = next(item for item in examples if item["id"] == "participle")
    parsed = ParsedDocument.from_tokens(source["text"], [token(item) for item in source["tokens"]])
    adapter = RussianGrammarAdapter()
    assert adapter.adapt(parsed) == adapter.adapt(parsed)


def test_registry_contains_all_mvp_rules_and_real_hash():
    registry = RussianGrammarRuleRegistry.load()
    assert {item.id for item in registry.rules} == {
        *(f"RU_POS_{index:03d}" for index in range(1, 18)),
        *(f"RU_SYN_{index:03d}" for index in range(1, 19)),
        "RU_TECH_001", "RU_TECH_002",
    }
    assert registry.version == "0.1.1"
    assert len(registry.sha256) == 64


@pytest.mark.parametrize("upos,rule_id,function", [
    ("PUNCT", "RU_TECH_001", "знак препинания"),
    ("SYM", "RU_TECH_002", "символ"),
])
def test_nonlexical_ud_tokens_are_preserved_without_false_grammar_review(
        upos, rule_id, function):
    value = Token(".", ".", upos, {}, "punct", 0, 0, 1, Span(0, 1))
    result = RussianGrammarAdapter().adapt(ParsedDocument.from_tokens(".", [value]))
    annotation = result.annotations[0]

    assert annotation.raw_ud.upos == upos
    assert annotation.rule_id == rule_id
    assert function in annotation.russian_function
    assert annotation.status is InterpretationStatus.RESOLVED
    assert not annotation.requires_review
    assert not result.ambiguity_cases


def test_vertical_path_stanza_to_adapter_to_mor_001_observation():
    text = "Этот человек пишет."
    words = [
        NS(text="Этот", lemma="этот", upos="DET", xpos="", feats="Case=Nom|PronType=Dem",
           deprel="det", head=2, id=1, start_char=0, end_char=4),
        NS(text="человек", lemma="человек", upos="NOUN", xpos="", feats="Case=Nom",
           deprel="nsubj", head=3, id=2, start_char=5, end_char=12),
        NS(text="пишет", lemma="писать", upos="VERB", xpos="", feats="VerbForm=Fin|Tense=Pres",
           deprel="root", head=0, id=3, start_char=13, end_char=18),
    ]
    stanza_document = NS(sentences=[NS(tokens=[NS(words=[word]) for word in words])])
    raw_tokens = convert_document(stanza_document, text)
    parsed = ParsedDocument.from_tokens(text, raw_tokens)
    russian = RussianGrammarAdapter().adapt(parsed)
    data = text.encode("utf-8")
    document = Document(
        "vertical", "vertical.txt", text, data, sha256(data).hexdigest(),
        sha256(data).hexdigest(), "utf-8", "fixture",
    )

    observations = FeatureExtractionService.from_default_registry().analyze_object(
        document, raw_tokens, russian_document=russian,
    )
    mor_001 = next(item for item in observations if item.feature_id == "MOR_001")

    assert mor_001.raw_value["counts"] == {
        "Глаголы": 1, "Местоименные слова": 1, "Существительные": 1,
    }
    assert mor_001.method_version == "auto-0.2.0"
    assert len(mor_001.evidence) == 3
    assert russian.annotation_at(0, 1).rule_id == "RU_POS_010"
