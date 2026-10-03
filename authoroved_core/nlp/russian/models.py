"""Доменные модели русской интерпретации с полной трассируемостью к UD."""
from __future__ import annotations

from dataclasses import dataclass, field

from authoroved_core.core.models import Span, Token
from authoroved_core.nlp.parsed_document import ParsedDocument
from authoroved_core.nlp.russian.enums import (
    InterpretationStatus,
    MappingType,
    RussianConstructionType,
    RussianPOS,
)


@dataclass(frozen=True)
class RawUDAnnotation:
    upos: str
    xpos: str
    features: dict[str, str]
    deprel: str
    head: int
    sentence_id: int
    token_id: int

    @classmethod
    def from_token(cls, token: Token) -> "RawUDAnnotation":
        return cls(
            upos=token.pos,
            xpos=token.xpos,
            features=dict(token.feats),
            deprel=token.dependency,
            head=token.head,
            sentence_id=token.sentence,
            token_id=token.index,
        )


@dataclass(frozen=True)
class RussianLinguisticAnnotation:
    source_span: Span | None
    source_text: str
    lemma: str
    raw_ud: RawUDAnnotation
    russian_category: RussianPOS
    russian_features: dict[str, str]
    russian_function: str
    russian_construction: RussianConstructionType | None
    rule_id: str
    triggered_rule_ids: tuple[str, ...]
    mapping_type: MappingType
    status: InterpretationStatus
    explanation: str
    requires_review: bool


@dataclass(frozen=True)
class RussianConstruction:
    id: str
    type: RussianConstructionType
    sentence_id: int
    source_span: Span | None
    member_token_ids: tuple[int, ...]
    head_token_id: int
    rule_id: str
    mapping_type: MappingType
    status: InterpretationStatus
    explanation: str


@dataclass(frozen=True)
class GrammarAmbiguityCase:
    sentence_text: str
    source_span: Span | None
    stanza_annotation: RawUDAnnotation
    candidate_interpretations: tuple[str, ...]
    triggered_rules: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class RussianParsedDocument:
    source: ParsedDocument
    annotations: tuple[RussianLinguisticAnnotation, ...]
    constructions: tuple[RussianConstruction, ...] = ()
    ambiguity_cases: tuple[GrammarAmbiguityCase, ...] = ()
    adapter_version: str = ""
    rules_version: str = ""
    rules_hash: str = ""

    def annotation_at(self, sentence_id: int, token_id: int) -> RussianLinguisticAnnotation | None:
        return next(
            (item for item in self.annotations
             if item.raw_ud.sentence_id == sentence_id and item.raw_ud.token_id == token_id),
            None,
        )

    def find_constructions(self, construction_type: RussianConstructionType) -> tuple[RussianConstruction, ...]:
        return tuple(item for item in self.constructions if item.type is construction_type)

    @property
    def word_annotations(self) -> tuple[RussianLinguisticAnnotation, ...]:
        """Буквенные единицы для предметных детекторов без обращения к Token.pos."""
        return tuple(
            item for item in self.annotations
            if any(char.isalpha() for char in item.source_text)
            and item.raw_ud.upos not in {"PUNCT", "SYM"}
        )

    @property
    def review_required(self) -> tuple[RussianLinguisticAnnotation, ...]:
        return tuple(item for item in self.annotations if item.requires_review)
