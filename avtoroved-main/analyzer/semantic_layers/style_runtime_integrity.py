"""Machine-checkable runtime coverage for canonical style method features."""
from __future__ import annotations

from dataclasses import dataclass

from analyzer import metrics
from analyzer.semantic_layers import config_loader
from analyzer.semantic_layers.style_detectors import STYLE_DETECTOR_SPECS
from analyzer.semantic_layers.style_method_projection import (
    AGGREGATE_DETECTOR_IDS,
    runtime_reachable_detector_ids,
)
from expert_core.style_method_registry import (
    legacy_style_method_mapping_by_id,
    load_style_method_registry,
)


@dataclass(frozen=True)
class StyleMethodRuntimeCoverage:
    method_feature_id: str
    automation_status: str
    implementation_status: str
    detectors: tuple[str, ...]
    producer: str | None
    evidence_type: str | None
    detector_registered: bool
    runtime_reachable: bool
    runtime_route: str
    notes: str


def _legacy_detector_is_real(detector_id: str, method_feature_id: str) -> bool:
    legacy_rows = {row["id"]: row for row in config_loader.load_style_features()}
    row = legacy_rows.get(detector_id)
    if row is None or row.get("producer") != "regex:analyzer.metrics.STYLE_MARKERS":
        return False
    marker_values = {value for values in metrics.STYLE_MARKERS.values() for value in values}
    mapped = legacy_style_method_mapping_by_id().get(detector_id, ())
    return row.get("label") in marker_values and method_feature_id in mapped


def audit_style_method_runtime() -> tuple[StyleMethodRuntimeCoverage, ...]:
    reached = runtime_reachable_detector_ids()
    registered_v2 = set(STYLE_DETECTOR_SPECS) | set(AGGREGATE_DETECTOR_IDS)
    output = []
    for row in load_style_method_registry():
        detectors = tuple(row["detectors"])
        implementation = row["implementation_status"]
        if implementation == "IMPLEMENTED":
            expected_producer = (
                "analyzer.semantic_layers.style_engine_v2.StyleEngineV2.analyze:"
                "selected_styles"
                if all(detector in AGGREGATE_DETECTOR_IDS for detector in detectors)
                else "analyzer.semantic_layers.style_detectors.detect_style_features"
            )
            registered = (bool(detectors)
                          and all(detector in registered_v2 for detector in detectors)
                          and row["producer"] == expected_producer)
            reachable = registered and any(detector in reached for detector in detectors)
            route = "StyleEngineV2"
            notes = "Detector registered and executed through the V2 analysis route."
        elif implementation == "PARTIAL":
            registered = bool(detectors) and all(
                _legacy_detector_is_real(detector, row["method_feature_id"])
                for detector in detectors) and (
                    row["producer"] == "analyzer.metrics.STYLE_MARKERS")
            reachable = registered
            route = "legacy_evidence_only"
            notes = "Legacy producer is real and mapped; no complete canonical V2 detector."
        else:
            registered = not detectors
            reachable = False
            route = "none"
            notes = (
                "Deliberately expert-only." if implementation == "NOT_APPLICABLE"
                else "Canonical feature registered; detector not implemented."
            )
        output.append(StyleMethodRuntimeCoverage(
            method_feature_id=row["method_feature_id"],
            automation_status=row["automation_status"],
            implementation_status=implementation,
            detectors=detectors,
            producer=row["producer"],
            evidence_type=row["evidence_type"],
            detector_registered=registered,
            runtime_reachable=reachable,
            runtime_route=route,
            notes=notes,
        ))
    return tuple(output)


def assert_style_method_runtime_integrity() -> None:
    """Fail on a false claim of current implementation or partial support."""
    invalid = [
        row.method_feature_id for row in audit_style_method_runtime()
        if row.implementation_status in {"IMPLEMENTED", "PARTIAL"}
        and not (row.detector_registered and row.runtime_reachable)
    ]
    if invalid:
        raise ValueError(f"Unreachable implemented style method features: {invalid}")
