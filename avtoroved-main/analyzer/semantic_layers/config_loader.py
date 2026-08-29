"""Безопасная локальная загрузка конфигурации semantic layers."""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from expert_core.style_method_registry import (
    load_legacy_style_method_mappings as _load_legacy_style_method_mappings,
    load_style_method_registry as _load_style_method_registry,
)


class SemanticConfigError(ValueError):
    """Конфигурация отсутствует, повреждена или имеет неверную структуру."""


_THEME_REQUIRED = {
    "id", "label", "method_status", "method_feature_id", "keywords",
    "legacy_threshold", "active",
}
_STYLE_REQUIRED = {
    "id", "label", "style", "method_status", "method_feature_id",
    "automation_status", "producer", "metric_type", "normalization",
    "active", "description", "limitations", "detector", "legacy_weight",
}
_METHOD_STATUSES = {"METHOD", "AUXILIARY", "EXPERIMENTAL", "UNRESOLVED"}
_AUTOMATION_STATUSES = {"AUTO", "CANDIDATE_ONLY", "EXPERT_ONLY"}
_FUNCTIONAL_STYLES = {
    "official_business", "scientific", "publicistic", "oratorical",
    "conversational", "unresolved",
}


def _data_dir() -> Path:
    """Вернуть data/ и в исходниках, и в PyInstaller bundle."""
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        bundled = Path(bundled_root) / "data"
        if bundled.is_dir():
            return bundled
    return Path(__file__).resolve().parents[2] / "data"


def _load_json(filename: str) -> Any:
    path = _data_dir() / filename
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except FileNotFoundError as exc:
        raise SemanticConfigError(f"Файл конфигурации не найден: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SemanticConfigError(
            f"Некорректный JSON в {path}: строка {exc.lineno}, столбец {exc.colno}"
        ) from exc
    except OSError as exc:
        raise SemanticConfigError(f"Не удалось прочитать конфигурацию {path}: {exc}") from exc


def _require_fields(item: dict, required: set[str], location: str) -> None:
    missing = sorted(required - set(item))
    if missing:
        raise SemanticConfigError(
            f"{location}: отсутствуют обязательные поля: {', '.join(missing)}")


@lru_cache(maxsize=1)
def load_theme_ontology() -> dict[str, dict]:
    payload = _load_json("theme_ontology.json")
    if not isinstance(payload, dict) or not payload:
        raise SemanticConfigError("theme_ontology.json: ожидается непустой JSON-объект")
    seen_ids: set[str] = set()
    for key, item in payload.items():
        location = f"theme_ontology.json[{key!r}]"
        if not isinstance(item, dict):
            raise SemanticConfigError(f"{location}: ожидается объект")
        _require_fields(item, _THEME_REQUIRED, location)
        if item["id"] != key:
            raise SemanticConfigError(f"{location}: поле id должно совпадать с ключом")
        if item["id"] in seen_ids:
            raise SemanticConfigError(f"{location}: повторяющийся id {item['id']!r}")
        seen_ids.add(item["id"])
        if item["method_status"] not in _METHOD_STATUSES:
            raise SemanticConfigError(
                f"{location}: неизвестный method_status {item['method_status']!r}")
        if not isinstance(item["keywords"], list) or not all(
                isinstance(value, str) for value in item["keywords"]):
            raise SemanticConfigError(f"{location}: keywords должен быть массивом строк")
        if not isinstance(item["active"], bool):
            raise SemanticConfigError(f"{location}: active должен быть boolean")
    return payload


@lru_cache(maxsize=1)
def load_theme_prototypes() -> dict[str, dict]:
    payload = _load_json("theme_prototypes.json")
    if not isinstance(payload, dict):
        raise SemanticConfigError("theme_prototypes.json: ожидается JSON-объект")
    known = set(load_theme_ontology())
    for key, item in payload.items():
        location = f"theme_prototypes.json[{key!r}]"
        if key not in known:
            raise SemanticConfigError(f"{location}: тема отсутствует в ontology")
        if not isinstance(item, dict):
            raise SemanticConfigError(f"{location}: ожидается объект")
        missing = {"provenance", "prototypes"} - set(item)
        if missing:
            raise SemanticConfigError(
                f"{location}: отсутствуют поля {', '.join(sorted(missing))}")
        if item["provenance"] not in {"engineered_for_v2", "method_description"}:
            raise SemanticConfigError(f"{location}: неизвестный provenance")
        values = item["prototypes"]
        if not isinstance(values, list) or not all(
                isinstance(value, str) and value.strip() for value in values):
            raise SemanticConfigError(
                f"{location}.prototypes: ожидается массив непустых строк")
        if len(values) != len(set(values)):
            raise SemanticConfigError(f"{location}: prototypes должны быть уникальны")
    return payload


@lru_cache(maxsize=1)
def load_style_features() -> list[dict]:
    payload = _load_json("style_features.json")
    if not isinstance(payload, list):
        raise SemanticConfigError("style_features.json: ожидается JSON-массив")
    seen_ids: set[str] = set()
    for index, item in enumerate(payload):
        location = f"style_features.json[{index}]"
        if not isinstance(item, dict):
            raise SemanticConfigError(f"{location}: ожидается объект")
        _require_fields(item, _STYLE_REQUIRED, location)
        feature_id = item["id"]
        if not isinstance(feature_id, str) or not feature_id:
            raise SemanticConfigError(f"{location}: id должен быть непустой строкой")
        if feature_id in seen_ids:
            raise SemanticConfigError(f"{location}: повторяющийся id {feature_id!r}")
        seen_ids.add(feature_id)
        styles = item["style"] if isinstance(item["style"], list) else [item["style"]]
        if not styles or not all(style in _FUNCTIONAL_STYLES for style in styles):
            raise SemanticConfigError(f"{location}: неизвестный functional style")
        if item["method_status"] not in _METHOD_STATUSES:
            raise SemanticConfigError(
                f"{location}: неизвестный method_status {item['method_status']!r}")
        if item["automation_status"] not in _AUTOMATION_STATUSES:
            raise SemanticConfigError(
                f"{location}: неизвестный automation_status")
        if item["method_feature_id"] is not None:
            raise SemanticConfigError(
                f"{location}: registry mapping отсутствует; ожидался null")
        if not isinstance(item["limitations"], list):
            raise SemanticConfigError(f"{location}: limitations должен быть массивом")
        for field in ("producer", "metric_type", "normalization", "description"):
            if not isinstance(item[field], str) or not item[field]:
                raise SemanticConfigError(f"{location}: {field} должен быть строкой")
        if not isinstance(item["active"], bool):
            raise SemanticConfigError(f"{location}: active должен быть boolean")
    return payload


@lru_cache(maxsize=1)
def load_style_method_features() -> list[dict]:
    """Canonical METHOD_FEATURE definitions; separate from 32 legacy signals."""
    return _load_style_method_registry()


@lru_cache(maxsize=1)
def load_style_legacy_method_mappings() -> list[dict]:
    """Evidence-only links from every legacy style signal to 0..N methods."""
    mappings = _load_legacy_style_method_mappings()
    legacy_ids = {row["id"] for row in load_style_features()}
    mapping_ids = {row["legacy_feature_id"] for row in mappings}
    if mapping_ids != legacy_ids:
        missing = sorted(legacy_ids - mapping_ids)
        extra = sorted(mapping_ids - legacy_ids)
        raise SemanticConfigError(
            f"legacy style mapping mismatch; missing={missing}, extra={extra}")
    return mappings
