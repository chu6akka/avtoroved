"""Контракт локального поставщика кандидатов без подключения какой-либо модели."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Protocol

from authoroved_core.core.feature_models import AutomationMode, FeatureEvidence
from authoroved_core.core.feature_registry import FeatureRegistry
from authoroved_core.core.models import Span


class LLMContractError(ValueError):
    pass


class LLMDetectionStatus(str, Enum):
    DETECTED = "DETECTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class ValidatedLLMCandidate:
    feature_id: str
    evidence: FeatureEvidence


@dataclass(frozen=True)
class ValidatedLLMResponse:
    raw_response: str
    status: LLMDetectionStatus
    candidates: tuple[ValidatedLLMCandidate, ...]


class LocalCandidateProvider(Protocol):
    """Интерфейс будущего локального поставщика; сетевых методов здесь нет."""

    def propose(self, text: str, registry_version: str) -> str:
        """Вернуть исходный JSON как строку без изменения текста документа."""


LLM_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "observations"],
    "properties": {
        "status": {"enum": [item.value for item in LLMDetectionStatus]},
        "observations": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["feature_id", "quote"],
                "properties": {
                    "feature_id": {"type": "string"},
                    "quote": {"type": "string", "minLength": 1},
                },
            },
        },
    },
}


class LLMResponseValidator:
    """Проверяет JSON, реестр, дословность цитаты и вычисляет координаты сам."""

    def __init__(self, registry: FeatureRegistry):
        self.registry = registry

    def validate(self, raw_response: str, text: str) -> ValidatedLLMResponse:
        if not isinstance(raw_response, str):
            raise LLMContractError("Исходный ответ модели должен быть строкой.")
        try:
            value = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise LLMContractError("Ответ не является корректным JSON.") from exc
        if not isinstance(value, dict) or set(value) != {"status", "observations"}:
            raise LLMContractError("Ответ содержит неизвестные или пропущенные поля.")
        try:
            status = LLMDetectionStatus(value["status"])
        except (TypeError, ValueError) as exc:
            raise LLMContractError("Неизвестный статус ответа.") from exc
        observations = value["observations"]
        if not isinstance(observations, list):
            raise LLMContractError("observations должен быть массивом.")
        if status is LLMDetectionStatus.INSUFFICIENT_DATA and observations:
            raise LLMContractError("При INSUFFICIENT_DATA список наблюдений должен быть пуст.")
        if status is LLMDetectionStatus.DETECTED and not observations:
            raise LLMContractError("При DETECTED требуется хотя бы одно наблюдение.")

        candidates = []
        for item in observations:
            if not isinstance(item, dict) or set(item) != {"feature_id", "quote"}:
                raise LLMContractError("Наблюдение содержит неизвестные или пропущенные поля.")
            feature_id, quote = item["feature_id"], item["quote"]
            if not isinstance(feature_id, str) or not isinstance(quote, str) or not quote:
                raise LLMContractError("feature_id и непустая quote должны быть строками.")
            try:
                definition = self.registry.get(feature_id)
            except KeyError as exc:
                raise LLMContractError(f"Признак {feature_id} отсутствует в реестре.") from exc
            if definition.automation_mode is not AutomationMode.LLM_ASSISTED:
                raise LLMContractError(f"Признак {feature_id} не разрешён для LLM-кандидатов.")
            starts = []
            offset = 0
            while True:
                found = text.find(quote, offset)
                if found < 0:
                    break
                starts.append(found)
                offset = found + max(1, len(quote))
            if not starts:
                raise LLMContractError("Цитата отсутствует в исходном тексте.")
            if len(starts) > 1:
                raise LLMContractError("Цитата встречается несколько раз и не задаёт однозначные координаты.")
            span = Span(starts[0], starts[0] + len(quote))
            candidates.append(ValidatedLLMCandidate(
                feature_id, FeatureEvidence(quote=quote, span=span, label="дословная цитата"),
            ))
        return ValidatedLLMResponse(raw_response, status, tuple(candidates))
