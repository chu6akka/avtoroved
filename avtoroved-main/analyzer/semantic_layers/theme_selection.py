"""Development calibration layer for ThemeEngineV2 multi-label output.

The ranking scores are produced elsewhere and remain untouched.  This module
only decides which ranked rows have enough engineering support to be exposed as
``selected_themes``.  Scores are similarities, not probabilities.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

from analyzer.semantic_layers.contracts import ThemeV2Score


SELECTION_STRATEGIES = {
    "absolute", "relative_margin", "relative_ratio", "top_k_support", "hybrid"
}


@dataclass(frozen=True)
class ThemeSelectionParameters:
    """Small interpretable parameter set selected on the calibration split."""

    strategy: str = "hybrid"
    absolute_floor: float = 0.40
    relative_margin: float | None = 0.08
    relative_ratio: float | None = None
    minimum_coverage: float = 0.0
    minimum_supported_segments: int = 1
    top_k: int | None = None
    safety_max_labels: int = 4

    def __post_init__(self) -> None:
        if self.strategy not in SELECTION_STRATEGIES:
            raise ValueError(f"unknown selection strategy: {self.strategy}")
        if not 0.0 <= self.absolute_floor <= 1.0:
            raise ValueError("absolute_floor must be between 0 and 1")
        if self.relative_margin is not None and not 0.0 <= self.relative_margin <= 1.0:
            raise ValueError("relative_margin must be between 0 and 1")
        if self.relative_ratio is not None and not 0.0 <= self.relative_ratio <= 1.0:
            raise ValueError("relative_ratio must be between 0 and 1")
        if not 0.0 <= self.minimum_coverage <= 1.0:
            raise ValueError("minimum_coverage must be between 0 and 1")
        if self.minimum_supported_segments < 0:
            raise ValueError("minimum_supported_segments cannot be negative")
        if self.top_k is not None and self.top_k < 1:
            raise ValueError("top_k must be positive")
        if self.safety_max_labels < 1:
            raise ValueError("safety_max_labels must be positive")

    def as_dict(self) -> dict:
        return asdict(self)


# Development-calibrated default.  The value is deliberately kept in one place
# and is not part of the methodological/expert feature registry.
DEFAULT_THEME_SELECTION_PARAMETERS = ThemeSelectionParameters(
    strategy="hybrid",
    absolute_floor=0.44,
    relative_margin=0.08,
    relative_ratio=None,
    minimum_coverage=0.0,
    minimum_supported_segments=1,
    top_k=None,
    safety_max_labels=4,
)


def select_themes(
    ranked_themes: Sequence[ThemeV2Score],
    parameters: ThemeSelectionParameters = DEFAULT_THEME_SELECTION_PARAMETERS,
) -> tuple[ThemeV2Score, ...]:
    """Select labels without changing order or score of ``ranked_themes``."""
    if not ranked_themes:
        return ()

    best_score = ranked_themes[0].combined_score
    selected: list[ThemeV2Score] = []
    for rank, row in enumerate(ranked_themes, start=1):
        support_ok = (
            row.coverage >= parameters.minimum_coverage
            and row.segment_support_count >= parameters.minimum_supported_segments
        )
        floor_ok = row.combined_score >= parameters.absolute_floor
        margin_ok = (
            parameters.relative_margin is None
            or row.combined_score >= best_score - parameters.relative_margin
        )
        ratio_ok = (
            parameters.relative_ratio is None
            or (best_score > 0 and row.combined_score / best_score
                >= parameters.relative_ratio)
        )
        top_k_ok = parameters.top_k is None or rank <= parameters.top_k

        if parameters.strategy == "absolute":
            accepted = support_ok and floor_ok
        elif parameters.strategy == "relative_margin":
            accepted = support_ok and margin_ok
        elif parameters.strategy == "relative_ratio":
            accepted = support_ok and ratio_ok
        elif parameters.strategy == "top_k_support":
            accepted = support_ok and top_k_ok
        else:
            accepted = support_ok and floor_ok and margin_ok and ratio_ok and top_k_ok

        if accepted:
            selected.append(row)

    # Safety only: calibration does the real filtering before this cap.
    return tuple(selected[:parameters.safety_max_labels])
