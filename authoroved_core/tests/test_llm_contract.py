import json

import pytest

from authoroved_core.core.feature_models import AutomationMode, FeatureDefinition, SourceReference
from authoroved_core.core.feature_registry import FeatureRegistry
from authoroved_core.core.llm_contract import (
    LLMContractError,
    LLMDetectionStatus,
    LLMResponseValidator,
    LLM_RESPONSE_SCHEMA,
)


def definition(feature_id: str, mode: AutomationMode):
    return FeatureDefinition(
        id=feature_id, name_ru="Тестовый признак", group="Тест",
        automation_mode=mode, definition="Только тест контракта",
        criteria=("точная цитата",), exclusions=("нет",), unit="фрагмент",
        normalization="не применяется", minimum_words=1,
        minimum_volume_status="engineering_only", evidence_method="точная цитата",
        sources=(SourceReference("Источник", "с. 1", "тест", "checked"),),
        dependency_group="test", method_version="test-1",
    )


@pytest.fixture
def registry():
    value = FeatureRegistry(
        registry_id="test", version="1", status="test", notice="test",
        identification_thresholds=None, default_suitability_minimum_words=None,
        features=(
            definition("LEX_900", AutomationMode.LLM_ASSISTED),
            definition("LEX_901", AutomationMode.AUTO),
        ),
    )
    value.validate()
    return value


def test_contract_keeps_raw_response_and_python_calculates_exact_coordinates(registry):
    raw = json.dumps({
        "status": "DETECTED",
        "observations": [{"feature_id": "LEX_900", "quote": "редкая фраза"}],
    }, ensure_ascii=False, separators=(",", ":"))
    text = "Начало — редкая фраза, конец."

    result = LLMResponseValidator(registry).validate(raw, text)

    assert result.raw_response == raw
    assert result.status is LLMDetectionStatus.DETECTED
    evidence = result.candidates[0].evidence
    assert evidence.span.start == text.index("редкая фраза")
    assert text[evidence.span.start:evidence.span.end] == evidence.quote
    assert LLM_RESPONSE_SCHEMA["additionalProperties"] is False


@pytest.mark.parametrize("payload, message", [
    ({"status": "DETECTED", "observations": [{"feature_id": "UNKNOWN_1", "quote": "фраза"}]}, "реестре"),
    ({"status": "DETECTED", "observations": [{"feature_id": "LEX_901", "quote": "фраза"}]}, "не разрешён"),
    ({"status": "DETECTED", "observations": [{"feature_id": "LEX_900", "quote": "выдумка"}]}, "отсутствует"),
    ({"status": "DETECTED", "observations": [{"feature_id": "LEX_900", "quote": "фраза", "score": 1}]}, "неизвестные"),
])
def test_contract_rejects_unknown_features_invented_quotes_and_extra_fields(registry, payload, message):
    with pytest.raises(LLMContractError, match=message):
        LLMResponseValidator(registry).validate(json.dumps(payload, ensure_ascii=False), "Здесь есть фраза.")


def test_contract_rejects_ambiguous_quote(registry):
    raw = json.dumps({
        "status": "DETECTED",
        "observations": [{"feature_id": "LEX_900", "quote": "повтор"}],
    })
    with pytest.raises(LLMContractError, match="несколько раз"):
        LLMResponseValidator(registry).validate(raw, "повтор и повтор")


def test_insufficient_data_requires_empty_observations(registry):
    raw = '{"status":"INSUFFICIENT_DATA","observations":[]}'
    result = LLMResponseValidator(registry).validate(raw, "")
    assert result.status is LLMDetectionStatus.INSUFFICIENT_DATA
    assert not result.candidates

    invalid = '{"status":"INSUFFICIENT_DATA","observations":[{"feature_id":"LEX_900","quote":"x"}]}'
    with pytest.raises(LLMContractError, match="должен быть пуст"):
        LLMResponseValidator(registry).validate(invalid, "x")
