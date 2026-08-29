"""Family-normalized engineering scoring for StyleEngineV2."""
from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from analyzer.semantic_layers.contracts import StyleDetectedFeatureV2
from analyzer.semantic_layers.style_detectors import STYLE_FAMILIES, STYLE_LABELS


# Patch C methodological/engineering score anchors remain frozen.  C.2 changes
# only the separate selection layer and preserves these public constants for
# regression consumers.
STYLE_SELECTION_FLOOR = 0.12
STYLE_MIN_FAMILIES = 2


def score_style_features(features: Sequence[StyleDetectedFeatureV2]) -> dict[str, dict]:
    """Aggregate by family first; repeated same-family hits cannot dominate."""
    grouped: dict[str, dict[str, list[StyleDetectedFeatureV2]]] = defaultdict(
        lambda: defaultdict(list))
    for feature in features:
        if feature.method_status == "EXPERIMENTAL":
            continue
        if feature.automation_status == "EXPERT_ONLY":
            continue
        grouped[feature.style_id][feature.family].append(feature)

    output: dict[str, dict] = {}
    for style_id in STYLE_LABELS:
        families: dict[str, float] = {}
        claimed_spans: set[tuple[int, int]] = set()
        for family in STYLE_FAMILIES:
            eligible: list[StyleDetectedFeatureV2] = []
            for feature in grouped[style_id].get(family, []):
                spans = {(row.start, row.end) for row in feature.evidence}
                if not spans or spans - claimed_spans:
                    eligible.append(feature)
            families[family] = round(max(
                (feature.normalized_value for feature in eligible), default=0.0), 6)
            for feature in eligible:
                claimed_spans.update((row.start, row.end) for row in feature.evidence)
        support = round(sum(families.values()) / len(STYLE_FAMILIES), 6)
        active_families = sum(value > 0 for value in families.values())
        output[style_id] = {
            "family_support": families,
            "support_score": support,
            "active_families": active_families,
        }
    return output
