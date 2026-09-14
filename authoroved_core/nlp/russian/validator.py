"""Строгая проверка реестра правил Russian Grammar Adapter."""
from __future__ import annotations

import json

from authoroved_core.nlp.russian.enums import MappingType, RussianConstructionType, RussianPOS


class RussianGrammarRegistryError(ValueError):
    pass


RULE_FIELDS = {
    "id", "level", "name", "description", "mapping_type", "conditions",
    "result", "requires_context", "requires_review", "source",
    "implementation", "enabled",
}


def validate_registry(value, *, known_handlers: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != {"registry", "rules"}:
        raise RussianGrammarRegistryError("Реестр русской грамматики имеет неизвестную структуру.")
    meta, rules = value["registry"], value["rules"]
    if not isinstance(meta, dict) or not all(meta.get(key) for key in ("id", "version", "source")):
        raise RussianGrammarRegistryError("В реестре обязательны id, version и source.")
    if not isinstance(rules, list) or not rules:
        raise RussianGrammarRegistryError("Реестр русской грамматики не содержит правил.")

    seen_ids: set[str] = set()
    direct_conditions: dict[str, str] = {}
    for item in rules:
        if not isinstance(item, dict) or set(item) != RULE_FIELDS:
            raise RussianGrammarRegistryError("Правило содержит неизвестные или пропущенные поля.")
        rule_id = item["id"]
        if not isinstance(rule_id, str) or not rule_id or rule_id in seen_ids:
            raise RussianGrammarRegistryError("Идентификаторы правил должны быть непустыми и уникальными.")
        seen_ids.add(rule_id)
        if item["level"] not in {"morphology", "syntax"}:
            raise RussianGrammarRegistryError(f"{rule_id}: неизвестный уровень правила.")
        try:
            mapping_type = MappingType(item["mapping_type"])
        except (TypeError, ValueError) as exc:
            raise RussianGrammarRegistryError(f"{rule_id}: неизвестный MappingType.") from exc
        if not isinstance(item["enabled"], bool):
            raise RussianGrammarRegistryError(f"{rule_id}: enabled должен быть логическим значением.")
        if not isinstance(item["requires_context"], bool) or not isinstance(item["requires_review"], bool):
            raise RussianGrammarRegistryError(f"{rule_id}: неверные признаки контекстности.")
        if not isinstance(item["conditions"], dict) or not item["conditions"]:
            raise RussianGrammarRegistryError(f"{rule_id}: условия обязательны.")
        if not isinstance(item["result"], dict) or not item["result"]:
            raise RussianGrammarRegistryError(f"{rule_id}: результат обязателен.")
        if not isinstance(item["description"], str) or not item["description"].strip():
            raise RussianGrammarRegistryError(f"{rule_id}: описание обязательно.")
        if not isinstance(item["source"], str) or not item["source"].strip():
            raise RussianGrammarRegistryError(f"{rule_id}: источник обязателен.")
        if item["implementation"] not in known_handlers:
            raise RussianGrammarRegistryError(
                f"{rule_id}: обработчик {item['implementation']} не зарегистрирован."
            )
        category = item["result"].get("russian_category")
        if category is not None:
            try:
                RussianPOS(category)
            except (TypeError, ValueError) as exc:
                raise RussianGrammarRegistryError(f"{rule_id}: неизвестная русская категория.") from exc
        construction = item["result"].get("construction")
        if construction is not None:
            try:
                RussianConstructionType(construction)
            except (TypeError, ValueError) as exc:
                raise RussianGrammarRegistryError(f"{rule_id}: неизвестный тип конструкции.") from exc
        if mapping_type is MappingType.DIRECT and item["enabled"]:
            signature = json.dumps(item["conditions"], ensure_ascii=False, sort_keys=True)
            if signature in direct_conditions:
                raise RussianGrammarRegistryError(
                    f"{rule_id}: условия DIRECT дублируют {direct_conditions[signature]}."
                )
            direct_conditions[signature] = rule_id
