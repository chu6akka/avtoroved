"""Загрузка версионированного реестра правил русской интерпретации."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml

from authoroved_core.nlp.russian.enums import MappingType
from authoroved_core.nlp.russian.validator import RussianGrammarRegistryError, validate_registry


DEFAULT_RULES_PATH = Path(__file__).parents[2] / "methodology" / "russian_grammar_rules.yaml"
KNOWN_HANDLERS = {
    "direct_pos", "contextual_pos", "verb_form", "aux_be",
    "syntax_relation", "participial_construction", "gerund_construction",
    "finite_advcl", "coordination", "ambiguous_syntax",
}


@dataclass(frozen=True)
class RussianGrammarRule:
    id: str
    level: str
    name: str
    description: str
    mapping_type: MappingType
    conditions: dict[str, Any]
    result: dict[str, str]
    requires_context: bool
    requires_review: bool
    source: str
    implementation: str
    enabled: bool


@dataclass(frozen=True)
class RussianGrammarRuleRegistry:
    registry_id: str
    version: str
    source: str
    rules: tuple[RussianGrammarRule, ...]
    sha256: str

    @classmethod
    def load(cls, path: str | Path = DEFAULT_RULES_PATH) -> "RussianGrammarRuleRegistry":
        path = Path(path)
        try:
            raw = path.read_bytes()
            value = yaml.safe_load(raw.decode("utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise RussianGrammarRegistryError("Не удалось прочитать реестр русской грамматики.") from exc
        validate_registry(value, known_handlers=KNOWN_HANDLERS)
        meta = value["registry"]
        rules = tuple(RussianGrammarRule(
            id=item["id"], level=item["level"], name=item["name"],
            description=item["description"], mapping_type=MappingType(item["mapping_type"]),
            conditions=dict(item["conditions"]), result=dict(item["result"]),
            requires_context=item["requires_context"], requires_review=item["requires_review"],
            source=item["source"], implementation=item["implementation"], enabled=item["enabled"],
        ) for item in value["rules"] if item["enabled"])
        return cls(meta["id"], meta["version"], meta["source"], rules, sha256(raw).hexdigest())

    def get(self, rule_id: str) -> RussianGrammarRule:
        try:
            return next(rule for rule in self.rules if rule.id == rule_id)
        except StopIteration as exc:
            raise KeyError(rule_id) from exc

    def by_level(self, level: str) -> tuple[RussianGrammarRule, ...]:
        return tuple(rule for rule in self.rules if rule.level == level)
