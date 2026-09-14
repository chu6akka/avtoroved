import copy
from pathlib import Path

import pytest
import yaml

from authoroved_core.nlp.russian.rules import KNOWN_HANDLERS
from authoroved_core.nlp.russian.validator import RussianGrammarRegistryError, validate_registry


SOURCE = Path(__file__).parents[1] / "methodology" / "russian_grammar_rules.yaml"


def registry_value():
    return yaml.safe_load(SOURCE.read_text(encoding="utf-8"))


def test_current_registry_is_valid():
    validate_registry(registry_value(), known_handlers=KNOWN_HANDLERS)


@pytest.mark.parametrize("field,value,message", [
    ("mapping_type", "CERTAIN_99", "MappingType"),
    ("implementation", "missing_handler", "обработчик"),
    ("enabled", "yes", "enabled"),
    ("description", "", "описание"),
    ("source", "", "источник"),
])
def test_invalid_registry_fields_are_rejected(field, value, message):
    data = registry_value()
    data["rules"][0][field] = value
    with pytest.raises(RussianGrammarRegistryError, match=message):
        validate_registry(data, known_handlers=KNOWN_HANDLERS)


def test_duplicate_rule_id_and_direct_conditions_are_rejected():
    data = registry_value()
    duplicate = copy.deepcopy(data["rules"][0])
    data["rules"].append(duplicate)
    with pytest.raises(RussianGrammarRegistryError, match="уникальными"):
        validate_registry(data, known_handlers=KNOWN_HANDLERS)

    data = registry_value()
    duplicate = copy.deepcopy(data["rules"][0])
    duplicate["id"] = "RU_POS_999"
    data["rules"].append(duplicate)
    with pytest.raises(RussianGrammarRegistryError, match="дублируют"):
        validate_registry(data, known_handlers=KNOWN_HANDLERS)
