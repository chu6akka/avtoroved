"""Shadow-only multi-layer functional StyleEngineV2."""
from __future__ import annotations

from collections import defaultdict
from statistics import fmean
from typing import Sequence

from analyzer.semantic_layers.contracts import (
    StyleAnalysisResultV2,
    StyleScoreV2,
    StyleSegmentResultV2,
)
from analyzer.semantic_layers.style_detectors import (
    STYLE_FAMILIES,
    STYLE_LABELS,
    detect_style_features,
)
from analyzer.semantic_layers.style_scoring import (
    engineering_style_parameters,
    score_style_features,
)
from analyzer.semantic_layers.theme_segmenter import (
    SegmentationParameters,
    segment_text,
)


STYLE_ENGINE_V2_VERSION = "v2-shadow"


class StyleEngineV2:
    """Explicit shadow analyzer; no production consumer calls it implicitly."""

    version = STYLE_ENGINE_V2_VERSION

    def __init__(self, segmentation_parameters: SegmentationParameters | None = None):
        self.segmentation_parameters = segmentation_parameters or SegmentationParameters()

    def _parameters(self) -> dict:
        return {
            **engineering_style_parameters(),
            "segmentation": {
                "min_tokens": self.segmentation_parameters.min_tokens,
                "target_tokens": self.segmentation_parameters.target_tokens,
                "max_tokens": self.segmentation_parameters.max_tokens,
                "shared_with": "ThemeEngineV2",
            },
            "nlp_policy": "reuse_injected_parsed_tokens_never_start_stanza",
        }

    def _controlled(self, status: str, reason: str) -> StyleAnalysisResultV2:
        return StyleAnalysisResultV2(
            styles=(), selected_styles=(), leading_style=None, segments=(),
            segment_count=0, engine_version=self.version,
            parameters=self._parameters(),
            limitations=("Недостаточно материала для стилевого синтеза.",),
            status=status, reason=reason)

    def analyze(self, text: str, *, parsed_tokens: Sequence[object] | None = None,
                stratification_result=None, sentiment_result=None
                ) -> StyleAnalysisResultV2:
        if not text or not text.strip():
            return self._controlled("empty", "empty text")

        segments = segment_text(text, self.segmentation_parameters)
        if not segments:
            return self._controlled("empty", "no valid text segments")
        parsed_tokens = tuple(parsed_tokens or ())

        all_features = []
        segment_rows: list[StyleSegmentResultV2] = []
        segment_style_hits: dict[str, int] = defaultdict(int)
        for segment in segments:
            features = detect_style_features(
                segment.text, base_offset=segment.start,
                parsed_tokens=parsed_tokens,
                stratification_result=stratification_result,
                sentiment_result=sentiment_result)
            all_features.extend(features)
            scored = score_style_features(features)
            support = {
                style_id: row["support_score"] for style_id, row in scored.items()
            }
            for style_id, row in scored.items():
                if row["selected"]:
                    segment_style_hits[style_id] += 1
            segment_rows.append(StyleSegmentResultV2(
                segment_id=segment.segment_id, start=segment.start, end=segment.end,
                text=segment.text,
                detected_style_features=tuple(sorted({
                    feature.feature_id for feature in features})),
                style_support=support))

        scored_document = score_style_features(all_features)
        style_rows: list[StyleScoreV2] = []
        for style_id, label in STYLE_LABELS.items():
            features = tuple(feature for feature in all_features
                             if feature.style_id == style_id)
            evidence = tuple(evidence for feature in features
                             for evidence in feature.evidence)
            row = scored_document[style_id]
            style_rows.append(StyleScoreV2(
                style_id=style_id, label=label,
                support_score=row["support_score"],
                feature_family_support=row["family_support"],
                detected_features=features,
                segment_coverage=round(
                    segment_style_hits[style_id] / len(segments), 6),
                evidence=evidence,
                expert_identification_value=None))
        style_rows.sort(key=lambda row: (-row.support_score, row.style_id))
        selected = tuple(
            row for row in style_rows if scored_document[row.style_id]["selected"])
        leading = style_rows[0] if style_rows and style_rows[0].support_score > 0 else None

        limitations = [
            "DEVELOPMENT shadow result; support_score is not probability.",
            "No feature is accepted as METHOD_FEATURE automatically.",
            "CANDIDATE_ONLY evidence requires expert confirmation.",
        ]
        if not parsed_tokens:
            limitations.append(
                "Parsed tokens were not supplied; morphology/dependency detectors are limited.")
        if not selected:
            limitations.append("No style passed engineering selection gates.")
        return StyleAnalysisResultV2(
            styles=tuple(style_rows), selected_styles=selected,
            leading_style=leading, segments=tuple(segment_rows),
            segment_count=len(segments), engine_version=self.version,
            parameters=self._parameters(), limitations=tuple(limitations),
            status="ok", reason=None)


def compare_style_v1_v2(v1_result, v2_result: StyleAnalysisResultV2) -> dict:
    return {
        "v1_layer_counts": dict(getattr(v1_result, "layer_counts", {}) or {}),
        "v1_marked_ratio": getattr(v1_result, "marked_ratio", None),
        "v2_leading_style": (
            v2_result.leading_style.style_id if v2_result.leading_style else None),
        "v2_selected_styles": [row.style_id for row in v2_result.selected_styles],
        "v2_ranked_styles": [
            {"style_id": row.style_id, "style_support_score": row.support_score}
            for row in v2_result.styles
        ],
        "notes": (
            "V1 is lexical register stratification; V2 is functional-style shadow analysis.",
            "The outputs are not methodologically interchangeable.",
        ),
    }
