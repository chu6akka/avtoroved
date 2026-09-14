import json
from pathlib import Path

import pytest

from authoroved_core.core.models import Span, Token
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
    }
    assert len(registry.sha256) == 64
