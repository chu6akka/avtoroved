"""Безопасная локальная загрузка конфигурации semantic layers."""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any


class SemanticConfigError(ValueError):
    """Конфигурация отсутствует, повреждена или имеет неверную структуру."""


_THEME_REQUIRED = {
    "id", "label", "method_status", "method_feature_id", "keywords",
    "legacy_threshold", "active",
}
_STYLE_REQUIRED = {
    "id", "label", "style", "detector", "legacy_weight",
    "method_feature_id", "active",
}
_METHOD_STATUSES = {"METHOD", "AUXILIARY", "EXPERIMENTAL", "UNRESOLVED"}


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
        if not isinstance(item["active"], bool):
            raise SemanticConfigError(f"{location}: active должен быть boolean")
    return payload
