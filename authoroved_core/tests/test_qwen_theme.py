import json

import pytest

from authoroved_core.core.llm_contract import LLMContractError
from authoroved_core.core.qwen_shadow import ProviderCompletion
from authoroved_core.core.qwen_theme import (
    QwenThemeService, ThemeResponseValidator, ThemeRunStatus,
)


class FakeProvider:
    def __init__(self, response):
        self.response = response
        self.call = None

    def complete(self, **kwargs):
        self.call = kwargs
        return ProviderCompletion(self.response, {"provider": "test"})


def test_theme_service_accepts_only_exact_supported_quotes():
    text = "Обсуждались ремонт дороги и сроки укладки асфальта."
    raw = json.dumps({
        "status": "DETECTED",
        "themes": [{"label": "Ремонт дороги", "quotes": ["ремонт дороги"]}],
    }, ensure_ascii=False)
    provider = FakeProvider(raw)

    run = QwenThemeService(provider).analyze(text)

    assert run.status is ThemeRunStatus.VALIDATED_CANDIDATES
    assert run.candidates[0].label == "Ремонт дороги"
    assert run.candidates[0].evidence[0].span.start == text.index("ремонт дороги")
    assert run.expert_use_allowed is False
    assert provider.call["response_schema"]["additionalProperties"] is False
    assert "не определяй автора" in provider.call["system_prompt"]


@pytest.mark.parametrize("payload, message", [
    ({"status": "DETECTED", "themes": [{"label": "Ремонт", "quotes": ["выдумка"]}]}, "отсутствует"),
    ({"status": "DETECTED", "themes": [{"label": "road", "quotes": ["дороги"]}]}, "русской"),
    ({"status": "INSUFFICIENT_DATA", "themes": [{"label": "Ремонт", "quotes": ["дороги"]}]}, "пуст"),
])
def test_theme_validator_rejects_unverifiable_output(payload, message):
    with pytest.raises(LLMContractError, match=message):
        ThemeResponseValidator().validate(
            json.dumps(payload, ensure_ascii=False), "Текст про дороги.",
        )


def test_theme_service_keeps_raw_rejected_response():
    raw = '{"status":"DETECTED","themes":[{"label":"Тема","quotes":["нет в тексте"]}]}'
    run = QwenThemeService(FakeProvider(raw)).analyze("Другой фрагмент.")

    assert run.status is ThemeRunStatus.SYSTEM_REJECTED
    assert run.raw_response == raw
    assert not run.candidates


def test_theme_abstention_is_valid_and_empty():
    raw = '{"status":"INSUFFICIENT_DATA","themes":[]}'
    run = QwenThemeService(FakeProvider(raw)).analyze("Коротко.")

    assert run.status is ThemeRunStatus.MODEL_ABSTAINED
    assert not run.candidates
