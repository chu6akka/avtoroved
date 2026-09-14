"""Детерминированный промежуточный слой Stanza/UD -> русская грамматика."""
from __future__ import annotations

from dataclasses import replace

from authoroved_core.core.models import Span, Token
from authoroved_core.nlp.parsed_document import ParsedDocument
from authoroved_core.nlp.russian.enums import (
    InterpretationStatus,
    MappingType,
    RussianConstructionType,
    RussianPOS,
)
from authoroved_core.nlp.russian.models import (
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


_MAPPING_RANK = {
    MappingType.DIRECT: 0,
    MappingType.CONTEXTUAL: 1,
    MappingType.NON_ISOMORPHIC: 2,
    MappingType.AMBIGUOUS: 3,
}
_STATUS_RANK = {
    InterpretationStatus.RESOLVED: 0,
    InterpretationStatus.EXPERT_REVIEW_REQUIRED: 1,
    InterpretationStatus.AMBIGUOUS: 2,
    InterpretationStatus.INVALID_SOURCE: 3,
}


def _combined_mapping(first: MappingType, second: MappingType) -> MappingType:
    return max((first, second), key=_MAPPING_RANK.get)


def _combined_status(first: InterpretationStatus,
                     second: InterpretationStatus) -> InterpretationStatus:
    return max((first, second), key=_STATUS_RANK.get)


class RussianGrammarAdapter:
    """Создаёт отдельную интерпретацию, не изменяя ParsedDocument и его токены."""

    version = RUSSIAN_GRAMMAR_ADAPTER_VERSION

    def __init__(self, registry: RussianGrammarRuleRegistry | None = None):
        self.registry = registry or RussianGrammarRuleRegistry.load()
        self.morphology_rules = self.registry.by_level("morphology")
        self.syntax_rules = self.registry.by_level("syntax")

    def adapt(self, parsed: ParsedDocument) -> RussianParsedDocument:
        annotations = [self._morphology(token, parsed.text) for token in parsed.tokens]
        constructions: list[RussianConstruction] = []
        for position, token in enumerate(parsed.tokens):
            annotation, created = self._syntax(token, annotations[position], parsed, annotations)
            annotations[position] = annotation
            constructions.extend(created)
        return RussianParsedDocument(
            source=parsed, annotations=tuple(annotations), constructions=tuple(constructions),
            adapter_version=self.version,
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

    def _syntax(self, token: Token, annotation: RussianLinguisticAnnotation,
                parsed: ParsedDocument,
                annotations: list[RussianLinguisticAnnotation]) -> tuple[
                    RussianLinguisticAnnotation, tuple[RussianConstruction, ...]]:
        if not token.dependency:
            return replace(
                annotation, status=InterpretationStatus.INVALID_SOURCE,
                requires_review=True,
                explanation=annotation.explanation + " Синтаксическое отношение в UD не указано.",
            ), ()
        matches = [rule for rule in self.syntax_rules if _matches(rule, token)]
        if not matches:
            return annotation, ()
        if len(matches) > 1:
            return replace(
                annotation, mapping_type=MappingType.AMBIGUOUS,
                status=InterpretationStatus.AMBIGUOUS, requires_review=True,
                explanation=annotation.explanation
                + " Для синтаксического отношения одновременно сработало несколько правил.",
                triggered_rule_ids=annotation.triggered_rule_ids
                + tuple(rule.id for rule in matches),
            ), ()

        rule = matches[0]
        function = rule.result.get("russian_function", annotation.russian_function)
        construction_type = (
            RussianConstructionType(rule.result["construction"])
            if rule.result.get("construction") else None
        )
        syntax_status = _status(rule)
        requires_review = annotation.requires_review or rule.requires_review
        constructions: tuple[RussianConstruction, ...] = ()

        if rule.implementation == "participial_construction":
            members = self._subtree(parsed, token)
            meaningful_dependents = [item for item in members if item.index != token.index
                                     and item.pos not in {"PUNCT", "SYM"}]
            if meaningful_dependents:
                constructions = (self._construction(rule, token, members, parsed, construction_type),)
            else:
                construction_type = None
                syntax_status = InterpretationStatus.EXPERT_REVIEW_REQUIRED
                requires_review = True
                function = "причастная форма при имени; состав конструкции требует проверки"
        elif rule.implementation == "gerund_construction":
            members = self._subtree(parsed, token)
            constructions = (self._construction(rule, token, members, parsed, construction_type),)
        elif rule.implementation == "finite_advcl":
            members = self._subtree(parsed, token)
            constructions = (self._construction(rule, token, members, parsed, construction_type),)
        elif rule.implementation == "coordination":
            head = parsed.token_at(token.sentence, token.head)
            head_annotation = next((item for item in annotations
                                    if item.raw_ud.sentence_id == token.sentence
                                    and item.raw_ud.token_id == token.head), None)
            if head is not None and head_annotation is not None:
                finite = {annotation.russian_category, head_annotation.russian_category}
                if finite == {RussianPOS.VERB_FINITE}:
                    construction_type = RussianConstructionType.COORDINATED_CLAUSES
                    function = "сочинительная связь предикативных частей"
                elif (annotation.russian_category is head_annotation.russian_category
                      and annotation.russian_category is not RussianPOS.UNKNOWN):
                    construction_type = RussianConstructionType.COORDINATED_MEMBERS
                    function = "сочинительная связь однородных компонентов"
                else:
                    construction_type = None
                    syntax_status = InterpretationStatus.AMBIGUOUS
                    requires_review = True
                if construction_type is not None:
                    members = (head, token) + tuple(
                        item for item in parsed.dependents_of(token) if item.dependency == "cc"
                    )
                    unique_members = {item.index: item for item in members}
                    constructions = (self._construction(
                        rule, token, tuple(unique_members[index] for index in sorted(unique_members)),
                        parsed, construction_type,
                    ),)
            else:
                syntax_status = InterpretationStatus.INVALID_SOURCE
                requires_review = True
        elif rule.implementation == "ambiguous_syntax":
            syntax_status = (InterpretationStatus.EXPERT_REVIEW_REQUIRED
                             if rule.id == "RU_SYN_016" else InterpretationStatus.AMBIGUOUS)
            requires_review = True
            if construction_type is not None:
                constructions = (self._construction(
                    rule, token, self._subtree(parsed, token), parsed, construction_type,
                    status=syntax_status,
                ),)
        elif construction_type is not None:
            constructions = (self._construction(
                rule, token, self._subtree(parsed, token), parsed, construction_type,
            ),)

        updated = replace(
            annotation,
            russian_function=function,
            russian_construction=construction_type,
            triggered_rule_ids=annotation.triggered_rule_ids + (rule.id,),
            mapping_type=_combined_mapping(annotation.mapping_type, rule.mapping_type),
            status=_combined_status(annotation.status, syntax_status),
            explanation=annotation.explanation + " " + rule.description,
            requires_review=requires_review,
        )
        return updated, constructions

    @staticmethod
    def _subtree(parsed: ParsedDocument, root: Token) -> tuple[Token, ...]:
        members = {root.index: root}
        pending = [root]
        while pending:
            parent = pending.pop()
            for child in parsed.dependents_of(parent):
                if child.index not in members:
                    members[child.index] = child
                    pending.append(child)
        return tuple(members[index] for index in sorted(members))

    @staticmethod
    def _construction(rule: RussianGrammarRule, root: Token, members: tuple[Token, ...],
                      parsed: ParsedDocument, construction_type: RussianConstructionType | None,
                      *, status: InterpretationStatus | None = None) -> RussianConstruction:
        spans = [item.span for item in members
                 if item.span is not None and item.span.valid_for(parsed.text)]
        span = Span(min(item.start for item in spans), max(item.end for item in spans)) if spans else None
        return RussianConstruction(
            id=f"{rule.id}:{root.sentence}:{root.index}",
            type=construction_type or RussianConstructionType.UNKNOWN,
            sentence_id=root.sentence, source_span=span,
            member_token_ids=tuple(item.index for item in members),
            head_token_id=root.index, rule_id=rule.id,
            mapping_type=rule.mapping_type, status=status or _status(rule),
            explanation=rule.description,
        )
