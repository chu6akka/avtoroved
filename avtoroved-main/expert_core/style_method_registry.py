"""Canonical methodological style features and legacy evidence mappings.

The registry is deliberately separate from ``data/style_features.json``:
legacy metrics and V2 detector signals remain engineering observations, while
the records loaded here are source-traceable METHOD_FEATURE definitions.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
STYLE_METHOD_REGISTRY_PATH = _DATA_DIR / "style_method_features.json"
STYLE_LEGACY_MAPPING_PATH = _DATA_DIR / "style_legacy_method_mappings.json"

AUTOMATION_STATUSES = {"AUTO", "CANDIDATE_ONLY", "EXPERT_ONLY"}
FUNCTIONAL_STYLES = {
    "official_business", "scientific", "publicistic", "oratorical",
    "conversational",
}
_REQUIRED_FIELDS = {
    "method_feature_id", "label", "method_group", "method_subgroup",
    "functional_style", "source_kind", "method_reference", "source_registry",
    "source_wording", "automation_status", "detectors", "limitations", "active",
}


def _load_json(path: Path):
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except FileNotFoundError as exc:
        raise ValueError(f"Method registry file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}"
        ) from exc


@lru_cache(maxsize=1)
def load_style_method_registry() -> list[dict]:
    """Load and validate source-traceable canonical style METHOD_FEATURE rows."""
    payload = _load_json(STYLE_METHOD_REGISTRY_PATH)
    if not isinstance(payload, list) or not payload:
        raise ValueError("style_method_features.json must contain a non-empty list")
    seen: set[str] = set()
    for index, row in enumerate(payload):
        location = f"style_method_features.json[{index}]"
        if not isinstance(row, dict):
            raise ValueError(f"{location}: object expected")
        missing = _REQUIRED_FIELDS - set(row)
        if missing:
            raise ValueError(f"{location}: missing fields {sorted(missing)}")
        feature_id = row["method_feature_id"]
        if not isinstance(feature_id, str) or not feature_id:
            raise ValueError(f"{location}: method_feature_id must be non-empty")
        if feature_id in seen:
            raise ValueError(f"Duplicate style method feature: {feature_id}")
        seen.add(feature_id)
        if row["method_group"] != "linguistic" or row["method_subgroup"] != "stylistic":
            raise ValueError(f"{location}: expected linguistic/stylistic grouping")
        if row["functional_style"] not in FUNCTIONAL_STYLES:
            raise ValueError(f"{location}: unknown functional style")
        if row["source_kind"] != "METHOD":
            raise ValueError(f"{location}: canonical feature must have METHOD source")
        if not row["method_reference"] or not row["source_wording"]:
            raise ValueError(f"{location}: source traceability is incomplete")
        if row["automation_status"] not in AUTOMATION_STATUSES:
            raise ValueError(f"{location}: unknown automation_status")
        if not isinstance(row["detectors"], list) or not all(
                isinstance(value, str) and value for value in row["detectors"]):
            raise ValueError(f"{location}: detectors must be a string list")
        if not isinstance(row["limitations"], list):
            raise ValueError(f"{location}: limitations must be a list")
        if not isinstance(row["active"], bool):
            raise ValueError(f"{location}: active must be boolean")
        forbidden = {"expert_identification_value", "method_reference_informativeness"}
        if forbidden & set(row):
            raise ValueError(f"{location}: expert/reference values must not be assigned")
    return payload


@lru_cache(maxsize=1)
def style_method_registry_by_id() -> dict[str, dict]:
    return {row["method_feature_id"]: row for row in load_style_method_registry()}


@lru_cache(maxsize=1)
def load_legacy_style_method_mappings() -> list[dict]:
    payload = _load_json(STYLE_LEGACY_MAPPING_PATH)
    if not isinstance(payload, list):
        raise ValueError("style_legacy_method_mappings.json must contain a list")
    known = set(style_method_registry_by_id())
    seen: set[str] = set()
    for index, row in enumerate(payload):
        location = f"style_legacy_method_mappings.json[{index}]"
        if set(row) != {"legacy_feature_id", "supported_method_feature_ids"}:
            raise ValueError(f"{location}: invalid mapping fields")
        legacy_id = row["legacy_feature_id"]
        targets = row["supported_method_feature_ids"]
        if legacy_id in seen:
            raise ValueError(f"Duplicate legacy feature mapping: {legacy_id}")
        seen.add(legacy_id)
        if not isinstance(targets, list) or len(targets) != len(set(targets)):
            raise ValueError(f"{location}: target IDs must be a unique list")
        unknown = set(targets) - known
        if unknown:
            raise ValueError(f"{location}: unknown method features {sorted(unknown)}")
    return payload


@lru_cache(maxsize=1)
def legacy_style_method_mapping_by_id() -> dict[str, tuple[str, ...]]:
    return {
        row["legacy_feature_id"]: tuple(row["supported_method_feature_ids"])
        for row in load_legacy_style_method_mappings()
    }


def method_features_for_detector(detector_id: str, functional_style: str
                                 ) -> tuple[dict, ...]:
    """Return compatible canonical targets without promoting the detector itself."""
    return tuple(
        row for row in load_style_method_registry()
        if row["active"] and detector_id in row["detectors"]
        and row["functional_style"] == functional_style
    )
