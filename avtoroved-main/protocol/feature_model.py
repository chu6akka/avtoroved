"""Нормализованная модель ролей элементов автороведческого профиля."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

from expert_core.style_method_registry import load_style_method_registry

METHOD_FEATURE = "METHOD_FEATURE"
AUX_METRIC = "AUX_METRIC"
EVIDENCE = "EVIDENCE"
GENERAL_SKILL = "GENERAL_SKILL"
ROLES = (METHOD_FEATURE, AUX_METRIC, EVIDENCE, GENERAL_SKILL)

SOURCE_METHOD = "METHOD"
SOURCE_EXPERIMENTAL = "EXPERIMENTAL"
SOURCE_ENGINEERING = "ENGINEERING"
SOURCE_KINDS = (SOURCE_METHOD, SOURCE_EXPERIMENTAL, SOURCE_ENGINEERING)

CANDIDATE_ORIGIN_AUTO = "AUTO"
CANDIDATE_ORIGIN_EXPERT = "EXPERT"
CANDIDATE_ORIGINS = (CANDIDATE_ORIGIN_AUTO, CANDIDATE_ORIGIN_EXPERT)

REFERENCE_VALUES = ("низкая", "средняя", "высокая")
AUTOMATION_LEVELS = ("AUTO_DETECTABLE", "CANDIDATE_ONLY", "EXPERT_ONLY")

ROLE_LABELS = {
    METHOD_FEATURE: "[МЕТОДИЧЕСКИЙ ПРИЗНАК]",
    AUX_METRIC: "[МЕТРИКА]",
    EVIDENCE: "[НАБЛЮДЕНИЕ]",
    GENERAL_SKILL: "[ОБЩИЙ НАВЫК]",
}

REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "method_features.json")


def get_field(item: Any, name: str, default: Any = None) -> Any:
    try:
        value = item[name]
    except (KeyError, IndexError, TypeError):
        value = default
    return default if value is None else value


def normalized_role(item: Any) -> str:
    """Роль новой модели либо безопасная адаптация legacy kind."""
    role = get_field(item, "role", "")
    if role in ROLES:
        return role
    kind = get_field(item, "kind", "")
    if kind == "общий_признак":
        return GENERAL_SKILL
    if kind == "счётчик":
        return AUX_METRIC
    # Неизвестный legacy-кандидат не повышается до методического признака.
    return EVIDENCE


@lru_cache(maxsize=1)
def load_method_registry() -> list[dict]:
    with open(REGISTRY_PATH, encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, list):
        raise ValueError("method_features.json должен содержать список")
    ids = set()
    for row in data:
        missing = {"id", "label", "group", "subgroup", "source",
                   "source_section", "reference_informativeness",
                   "automation_level"} - set(row)
        if missing:
            raise ValueError(f"Неполная запись method registry: {sorted(missing)}")
        if row["id"] in ids:
            raise ValueError(f"Дублирующий method feature id: {row['id']}")
        if row["reference_informativeness"] not in REFERENCE_VALUES + (None,):
            raise ValueError(f"Недопустимая справочная информативность: {row['id']}")
        if row["automation_level"] not in AUTOMATION_LEVELS:
            raise ValueError(f"Недопустимый automation_level: {row['id']}")
        ids.add(row["id"])
    return data


@lru_cache(maxsize=1)
def registry_by_detector_key() -> dict[str, dict]:
    return {row["detector_key"]: row for row in load_method_registry()
            if row.get("detector_key")}


@lru_cache(maxsize=1)
def registry_by_id() -> dict[str, dict]:
    """Реестр методических признаков по стабильному method_feature_id."""
    rows = {row["id"]: row for row in load_method_registry()}
    automation = {
        "AUTO": "AUTO_DETECTABLE",
        "CANDIDATE_ONLY": "CANDIDATE_ONLY",
        "EXPERT_ONLY": "EXPERT_ONLY",
    }
    for style_row in load_style_method_registry():
        feature_id = style_row["method_feature_id"]
        if feature_id in rows:
            raise ValueError(f"Дублирующий method feature id: {feature_id}")
        reference = style_row["method_reference"]
        source_section = reference.rsplit(", ", 1)[-1] if ", " in reference else ""
        rows[feature_id] = {
            "id": feature_id,
            "label": style_row["label"],
            "group": "языковые",
            "subgroup": "стилистические",
            "source": reference,
            "source_section": source_section,
            # Информативность источника намеренно не переносится автоматически.
            "reference_informativeness": None,
            "automation_level": automation[style_row["automation_status"]],
            "detector_key": None,
            "functional_style": style_row["functional_style"],
            "canonical_style_method_feature": True,
            "implementation_status": style_row["implementation_status"],
            "detectors": tuple(style_row["detectors"]),
            "producer": style_row["producer"],
            "evidence_type": style_row["evidence_type"],
        }
    return rows


def registered_method_feature(method_feature_id: str | None) -> dict | None:
    """Вернуть запись registry; неизвестный ID никогда не считается методическим."""
    return registry_by_id().get(method_feature_id or "")
