"""Interpretable engineering selection gates for shadow StyleEngineV2.

Ranking and selection are deliberately separate.  Support scores order styles;
the gates below decide whether the available evidence is strong enough to show
the ranked style in ``selected_styles``.  None of these values is a probability
or an expert assessment of identification significance.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from analyzer.semantic_layers.contracts import StyleDetectedFeatureV2


@dataclass(frozen=True)
class StyleSelectionParameters:
    """Small, versioned set of DEVELOPMENT selection parameters."""

    absolute_floor: float
    relative_margin: float | None
    minimum_family_support: int
    weak_style_abstention_threshold: float | None

    def __post_init__(self) -> None:
        if not 0.0 <= self.absolute_floor <= 1.0:
            raise ValueError("absolute_floor must be between 0 and 1")
        if self.relative_margin is not None and not 0.0 <= self.relative_margin <= 1.0:
            raise ValueError("relative_margin must be between 0 and 1")
        if self.minimum_family_support < 1:
            raise ValueError("minimum_family_support must be positive")
        if (self.weak_style_abstention_threshold is not None
                and not 0.0 <= self.weak_style_abstention_threshold <= 1.0):
            raise ValueError(
                "weak_style_abstention_threshold must be between 0 and 1")

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            "absolute_floor": self.absolute_floor,
            "relative_margin": self.relative_margin,
            "minimum_family_support": self.minimum_family_support,
            "weak_style_abstention_threshold": self.weak_style_abstention_threshold,
        }


# Exact Patch C baseline.  Used by regression reports; it is not the production
# pipeline, because StyleEngineV2 itself remains shadow-only.
LEGACY_STYLE_SELECTION_PARAMETERS = StyleSelectionParameters(
    absolute_floor=0.12,
    relative_margin=None,
    minimum_family_support=2,
    weak_style_abstention_threshold=None,
)


# Frozen after the Patch C.2 grid search on DEVELOPMENT CALIBRATION only.
CALIBRATED_STYLE_SELECTION_PARAMETERS = StyleSelectionParameters(
    absolute_floor=0.12,
    relative_margin=0.08,
    minimum_family_support=2,
    weak_style_abstention_threshold=0.14,
)


def _eligible_features(
        features: Sequence[StyleDetectedFeatureV2]) -> tuple[StyleDetectedFeatureV2, ...]:
    return tuple(feature for feature in features
                 if feature.method_status != "EXPERIMENTAL"
                 and feature.automation_status != "EXPERT_ONLY")


def select_style_scores(
        scored: Mapping[str, Mapping[str, object]],
        features_by_style: Mapping[str, Sequence[StyleDetectedFeatureV2]],
        parameters: StyleSelectionParameters,
        ) -> dict[str, dict[str, object]]:
    """Apply transparent gates to already-ranked support scores.

    The weak-evidence gate is global: it applies whenever every available
    signal is CANDIDATE_ONLY, regardless of style.  It therefore does not
    assign a special evidential weight to any functional style.
    """
    best_score = max(
        (float(row["support_score"]) for row in scored.values()), default=0.0)
    decisions: dict[str, dict[str, object]] = {}
    for style_id, row in scored.items():
        score = float(row["support_score"])
        family_count = int(row["active_families"])
        features = _eligible_features(tuple(features_by_style.get(style_id, ())))
        weak_only = bool(features) and all(
            feature.automation_status == "CANDIDATE_ONLY" for feature in features)
        delta = max(0.0, best_score - score)

        floor_passed = score >= parameters.absolute_floor
        margin_passed = (
            parameters.relative_margin is None
            or delta <= parameters.relative_margin + 1e-12
        )
        families_passed = family_count >= parameters.minimum_family_support
        weak_gate_passed = (
            not weak_only
            or parameters.weak_style_abstention_threshold is None
            or score >= parameters.weak_style_abstention_threshold
        )
        selected = (
            floor_passed and margin_passed and families_passed and weak_gate_passed)

        strongest = max(
            features,
            key=lambda feature: (
                feature.normalized_value, feature.raw_count, feature.feature_id),
            default=None,
        )
        failed = [
            name for name, passed in (
                ("absolute_floor", floor_passed),
                ("relative_margin", margin_passed),
                ("minimum_family_support", families_passed),
                ("weak_evidence_abstention", weak_gate_passed),
            ) if not passed
        ]
        summary = (
            f"{'selected' if selected else 'not selected'}: score {score:.6f}; "
            f"floor {parameters.absolute_floor:.6f}; delta from best {delta:.6f}; "
            f"margin {parameters.relative_margin}; {family_count} independent families"
        )
        if failed:
            summary += "; failed " + ", ".join(failed)
        decisions[style_id] = {
            "selected": selected,
            "support_score": round(score, 6),
            "best_support_score": round(best_score, 6),
            "threshold_used": parameters.absolute_floor,
            "absolute_floor_passed": floor_passed,
            "delta_from_best": round(delta, 6),
            "relative_margin": parameters.relative_margin,
            "relative_margin_passed": margin_passed,
            "supporting_family_count": family_count,
            "minimum_family_support": parameters.minimum_family_support,
            "family_support_passed": families_passed,
            "weak_evidence_only": weak_only,
            "weak_style_abstention_threshold": (
                parameters.weak_style_abstention_threshold),
            "weak_style_gate_passed": weak_gate_passed,
            "strongest_evidence": (
                {
                    "feature_id": strongest.feature_id,
                    "family": strongest.family,
                    "normalized_value": strongest.normalized_value,
                    "fragment": (
                        strongest.evidence[0].fragment if strongest.evidence else None),
                }
                if strongest else None
            ),
            "failed_gates": tuple(failed),
            "summary": summary,
            "semantics": "engineering_debug_not_expert_justification",
        }
    return decisions


def engineering_style_parameters(
        parameters: StyleSelectionParameters) -> dict[str, object]:
    return {
        **parameters.as_dict(),
        # Backward-compatible debug aliases retained for Patch C consumers.
        "selection_floor": parameters.absolute_floor,
        "minimum_independent_families": parameters.minimum_family_support,
        "selection_strategy": (
            "absolute_floor_plus_relative_margin_plus_independent_family_support"
            "_plus_weak_evidence_abstention"
        ),
        "score_semantics": "engineering_style_support_not_probability",
        "threshold_kind": "ENGINEERING_DEVELOPMENT_CALIBRATION",
    }
