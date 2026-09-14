"""Детерминированный промежуточный слой Stanza/UD -> русская грамматика."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from authoroved_core.core.models import Span, Token
from authoroved_core.nlp.parsed_document import ParsedDocument
from authoroved_core.nlp.russian.enums import (
    InterpretationStatus,
    MappingType,
    RussianConstructionType,
    RussianPOS,
)
from authoroved_core.nlp.russian.models import (
    GrammarAmbiguityCase,
    RawUDAnnotation,
    RussianConstruction,
    RussianLinguisticAnnotation,
    RussianParsedDocument,
)
from authoroved_core.nlp.russian.rules import RussianGrammarRule, RussianGrammarRuleRegistry


RUSSIAN_GRAMMAR_ADAPTER_VERSION = "0.1.0"

FEATURE_NAMES = {
    "Animacy": "одушевлённость", "Aspect": "вид", "Case": "падеж",
    "Degree": "степень сравнения", "Gender": "род", "Mood": "наклонение",
    "Number": "число", "Person": "лицо", "Tense": "время",
    "Variant": "форма", "Voice": "залог", "VerbForm": "форма глагола",
}
FEATURE_VALUES = {
    "Animacy": {"Anim": "одушевлённое", "Inan": "неодушевлённое"},
    "Aspect": {"Perf": "совершенный", "Imp": "несовершенный"},
    "Case": {"Nom": "именительный", "Gen": "родительный", "Dat": "дательный",
             "Acc": "винительный", "Ins": "творительный", "Loc": "предложный",
             "Par": "частичный", "Voc": "звательный"},
    "Degree": {"Pos": "положительная", "Cmp": "сравнительная", "Sup": "превосходная"},
    "Gender": {"Masc": "мужской", "Fem": "женский", "Neut": "средний"},
    "Mood": {"Ind": "изъявительное", "Imp": "повелительное", "Cnd": "условное"},
    "Number": {"Sing": "единственное", "Plur": "множественное"},
    "Person": {"1": "первое", "2": "второе", "3": "третье"},
    "Tense": {"Past": "прошедшее", "Pres": "настоящее", "Fut": "будущее"},
    "Variant": {"Short": "краткая"},
    "Voice": {"Act": "действительный", "Pass": "страдательный", "Mid": "средний"},
    "VerbForm": {"Fin": "личная", "Inf": "инфинитив", "Part": "причастие",
                 "Conv": "деепричастие"},
}


def _safe_raw(token: Token) -> tuple[RawUDAnnotation, bool]:
    malformed = not isinstance(token.feats, dict)
    features = (dict(token.feats) if not malformed
                else {"_invalid_source": repr(token.feats)})
    return RawUDAnnotation(
        upos=str(token.pos or ""), xpos=str(token.xpos or ""), features=features,
        deprel=str(token.dependency or ""), head=token.head if isinstance(token.head, int) else 0,
        sentence_id=token.sentence if isinstance(token.sentence, int) else -1,
        token_id=token.index if isinstance(token.index, int) else -1,
    ), malformed


def _matches(rule: RussianGrammarRule, token: Token) -> bool:
    conditions = rule.conditions
    if "upos" in conditions and token.pos != conditions["upos"]:
        return False
    if "lemma" in conditions and token.lemma.casefold() != str(conditions["lemma"]).casefold():
        return False
    if "deprel" in conditions and token.dependency != conditions["deprel"]:
        return False
    required_features = conditions.get("features", {})
    return isinstance(token.feats, dict) and all(
        token.feats.get(key) == value for key, value in required_features.items()
    )


def _russian_features(features: dict[str, str]) -> dict[str, str]:
    result = {}
    for key, value in sorted(features.items()):
        if key.startswith("_"):
            continue
        name = FEATURE_NAMES.get(key, key)
        result[name] = FEATURE_VALUES.get(key, {}).get(value, value)
    return result


def _status(rule: RussianGrammarRule) -> InterpretationStatus:
    return (InterpretationStatus.EXPERT_REVIEW_REQUIRED
            if rule.requires_review else InterpretationStatus.RESOLVED)


class RussianGrammarAdapter:
    """Создаёт отдельную интерпретацию, не изменяя ParsedDocument и его токены."""

    version = RUSSIAN_GRAMMAR_ADAPTER_VERSION

    def __init__(self, registry: RussianGrammarRuleRegistry | None = None):
        self.registry = registry or RussianGrammarRuleRegistry.load()
        self.morphology_rules = self.registry.by_level("morphology")
        self.syntax_rules = self.registry.by_level("syntax")

    def adapt(self, parsed: ParsedDocument) -> RussianParsedDocument:
        annotations = tuple(self._morphology(token, parsed.text) for token in parsed.tokens)
        return RussianParsedDocument(
            source=parsed, annotations=annotations, adapter_version=self.version,
            rules_version=self.registry.version, rules_hash=self.registry.sha256,
        )

    def _morphology(self, token: Token, text: str) -> RussianLinguisticAnnotation:
        raw, malformed = _safe_raw(token)
        source_text = (
            text[token.span.start:token.span.end]
            if token.span is not None and token.span.valid_for(text) else token.text
        )
        if malformed or not token.pos or not isinstance(token.lemma, str):
            return RussianLinguisticAnnotation(
                token.span, source_text, str(token.lemma or ""), raw, RussianPOS.UNKNOWN, {}, "",
                None, "INVALID_SOURCE", (), MappingType.AMBIGUOUS,
                InterpretationStatus.INVALID_SOURCE,
                "Исходная UD-разметка неполна или имеет неверный формат.", True,
            )
        matches = [rule for rule in self.morphology_rules if _matches(rule, token)]
        if len(matches) != 1:
            reason = ("Для технической метки не зарегистрировано однозначное русское соответствие."
                      if not matches else "Одновременно сработало несколько грамматических правил.")
            return RussianLinguisticAnnotation(
                token.span, source_text, token.lemma, raw, RussianPOS.UNKNOWN,
                _russian_features(raw.features), "", None, "AMBIGUOUS", (),
                MappingType.AMBIGUOUS, InterpretationStatus.AMBIGUOUS, reason, True,
            )
        rule = matches[0]
        category = RussianPOS(rule.result["russian_category"])
        function = rule.result.get("russian_function", "")
        explanation = rule.description
        if rule.id == "RU_POS_006":
            explanation += " Возможная адъективация этим правилом не разрешается."
        if rule.id == "RU_POS_008":
            explanation += " Пользовательская часть речи AUX не создаётся."
        return RussianLinguisticAnnotation(
            token.span, source_text, token.lemma, raw, category,
            _russian_features(raw.features), function, None, rule.id, (rule.id,),
            rule.mapping_type, _status(rule), explanation,
            rule.requires_review,
        )
