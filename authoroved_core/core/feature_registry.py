"""Загрузка и строгая проверка версионированного реестра показателей."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable

import yaml

from authoroved_core.core.feature_models import (
    AutomationMode,
    FeatureDefinition,
    SourceReference,
)


DEFAULT_REGISTRY = Path(__file__).parents[1] / "methodology" / "feature_registry.yaml"
FEATURE_ID = re.compile(r"^(?:LEX|MOR|SYN|PUN|GRA)_\d{3}$")
ALLOWED_STATUSES = {
    "engineering_only",
    "algorithmic_requirement_not_methodological_threshold",
}


class FeatureRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class FeatureRegistry:
    registry_id: str
    version: str
    status: str
    notice: str
    identification_thresholds: Any
    default_suitability_minimum_words: int | None
    features: tuple[FeatureDefinition, ...]

    @classmethod
    def load(cls, path: str | Path = DEFAULT_REGISTRY) -> "FeatureRegistry":
        try:
            value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise FeatureRegistryError("Не удалось прочитать реестр показателей.") from exc
        if not isinstance(value, dict) or not isinstance(value.get("registry"), dict):
            raise FeatureRegistryError("В реестре отсутствует раздел registry.")
        header = value["registry"]
        definitions = tuple(_definition(item) for item in _list(value, "features"))
        registry = cls(
            registry_id=_text(header, "id"),
            version=_text(header, "version"),
            status=_text(header, "status"),
            notice=_text(header, "notice"),
            identification_thresholds=header.get("identification_thresholds"),
            default_suitability_minimum_words=header.get("default_suitability_minimum_words"),
            features=definitions,
        )
        registry.validate()
        return registry

    def validate(self) -> None:
        if not self.version or not self.notice:
            raise FeatureRegistryError("Версия и предупреждение реестра обязательны.")
        if self.identification_thresholds is not None:
            raise FeatureRegistryError("В исследовательском реестре запрещены пороги авторства.")
        if self.default_suitability_minimum_words is not None:
            raise FeatureRegistryError("Неподтверждённый общий порог объёма должен быть null.")
        ids = [item.id for item in self.features]
        if len(ids) != len(set(ids)):
            raise FeatureRegistryError("Идентификаторы показателей должны быть уникальны.")
        for item in self.features:
            if not FEATURE_ID.fullmatch(item.id):
                raise FeatureRegistryError(f"Некорректный идентификатор {item.id}.")
            if not item.sources or any(not source.locator for source in item.sources):
                raise FeatureRegistryError(f"Для {item.id} нужен источник с локатором.")
            if item.minimum_words is not None and item.minimum_words < 1:
                raise FeatureRegistryError(f"Для {item.id} указан некорректный минимум.")
            if item.minimum_volume_status not in ALLOWED_STATUSES:
                raise FeatureRegistryError(f"Для {item.id} не обозначен статус минимума.")
            if not item.dependency_group:
                raise FeatureRegistryError(f"Для {item.id} нужна группа зависимости.")

    def get(self, feature_id: str) -> FeatureDefinition:
        try:
            return next(item for item in self.features if item.id == feature_id)
        except StopIteration as exc:
            raise KeyError(feature_id) from exc

    def by_mode(self, mode: AutomationMode) -> tuple[FeatureDefinition, ...]:
        return tuple(item for item in self.features if item.automation_mode is mode)


def _text(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise FeatureRegistryError(f"Поле {key} должно быть непустой строкой.")
    return result.strip()


def _list(value: dict[str, Any], key: str) -> list[Any]:
    result = value.get(key)
    if not isinstance(result, list):
        raise FeatureRegistryError(f"Поле {key} должно быть списком.")
    return result


def _strings(value: dict[str, Any], key: str) -> tuple[str, ...]:
    items = _list(value, key)
    if not all(isinstance(item, str) and item.strip() for item in items):
        raise FeatureRegistryError(f"Поле {key} содержит некорректное значение.")
    return tuple(item.strip() for item in items)


def _sources(items: Iterable[Any]) -> tuple[SourceReference, ...]:
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise FeatureRegistryError("Описание источника должно быть объектом.")
        result.append(SourceReference(
            title=_text(item, "title"), locator=_text(item, "locator"),
            role=_text(item, "role"), verification=_text(item, "verification"),
        ))
    return tuple(result)


def _definition(value: Any) -> FeatureDefinition:
    if not isinstance(value, dict):
        raise FeatureRegistryError("Описание показателя должно быть объектом.")
    minimum = value.get("minimum_words")
    if minimum is not None and (isinstance(minimum, bool) or not isinstance(minimum, int)):
        raise FeatureRegistryError("minimum_words должен быть целым числом или null.")
    try:
        mode = AutomationMode(_text(value, "automation_mode"))
    except ValueError as exc:
        raise FeatureRegistryError("Неизвестный режим автоматизации.") from exc
    return FeatureDefinition(
        id=_text(value, "id"), name_ru=_text(value, "name_ru"),
        group=_text(value, "group"), automation_mode=mode,
        definition=_text(value, "definition"), criteria=_strings(value, "criteria"),
        exclusions=_strings(value, "exclusions"), unit=_text(value, "unit"),
        normalization=_text(value, "normalization"), minimum_words=minimum,
        minimum_volume_status=_text(value, "minimum_volume_status"),
        evidence_method=_text(value, "evidence_method"),
        sources=_sources(_list(value, "sources")),
        dependency_group=_text(value, "dependency_group"),
        method_version=_text(value, "method_version"),
    )
