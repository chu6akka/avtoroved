"""Project engineering StyleEngineV2 evidence to unaccepted METHOD candidates."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from analyzer.semantic_layers.contracts import (
    StyleDetectedFeatureV2,
    StyleMethodFeatureCandidateV2,
    StyleScoreV2,
)
from expert_core.style_method_registry import method_features_for_detector


_STATUS_RANK = {"AUTO": 0, "CANDIDATE_ONLY": 1, "EXPERT_ONLY": 2}


def _effective_status(method_status: str, detector_status: str) -> str:
    return max((method_status, detector_status), key=_STATUS_RANK.__getitem__)


def _dedupe_evidence(rows: Iterable) -> tuple:
    output = []
    seen = set()
    for row in rows:
        key = (row.feature_id, row.start, row.end, row.fragment)
        if key not in seen:
            seen.add(key)
            output.append(row)
    return tuple(output)


def project_method_feature_candidates(
    detected_features: Iterable[StyleDetectedFeatureV2],
    selected_styles: Iterable[StyleScoreV2],
) -> tuple[StyleMethodFeatureCandidateV2, ...]:
    """Create evidence-backed candidates without changing V2 style scoring."""
    grouped: dict[str, dict] = {}

    def add(target: dict, evidence: Iterable, reliability: float,
            detector_status: str) -> None:
        if target["automation_status"] == "EXPERT_ONLY":
            return
        feature_id = target["method_feature_id"]
        current = grouped.setdefault(feature_id, {
            "target": target, "evidence": [], "reliability": 0.0,
            "automation_status": target["automation_status"],
        })
        current["evidence"].extend(evidence)
        current["reliability"] = max(current["reliability"], float(reliability))
        current["automation_status"] = _effective_status(
            current["automation_status"], detector_status)

    for feature in detected_features:
        for target in method_features_for_detector(
                feature.feature_id, feature.style_id):
            add(target, feature.evidence, feature.normalized_value,
                feature.automation_status)

    for style in selected_styles:
        detector_id = f"v2.aggregate.functional_style.{style.style_id}"
        for target in method_features_for_detector(detector_id, style.style_id):
            add(target, style.evidence, style.support_score, "CANDIDATE_ONLY")

    candidates = []
    for feature_id in sorted(grouped):
        row = grouped[feature_id]
        target = row["target"]
        candidates.append(StyleMethodFeatureCandidateV2(
            method_feature_id=feature_id,
            label=target["label"],
            functional_style=target["functional_style"],
            automation_status=row["automation_status"],
            evidence=_dedupe_evidence(row["evidence"]),
            detection_reliability=round(row["reliability"], 6),
            method_group=target["method_group"],
            method_subgroup=target["method_subgroup"],
            limitations=tuple(target["limitations"]),
            accepted=False,
            expert_identification_value=None,
        ))
    return tuple(candidates)
