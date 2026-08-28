"""Прозрачные инженерные формулы ThemeEngineV2."""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean
from typing import Sequence


# ENGINEERING thresholds/weights: не методические и не экспертные величины.
ENGINEERING_PROTOTYPE_TOP_K = 3
ENGINEERING_LEXICAL_SATURATION_COUNT = 6
ENGINEERING_LEXICAL_MIN_UNIQUE = 2
ENGINEERING_SEMANTIC_WEIGHT = 0.75
ENGINEERING_LEXICAL_WEIGHT = 0.25
ENGINEERING_SEGMENT_SUPPORT_THRESHOLD = 0.25
ENGINEERING_SEMANTIC_ONLY_SUPPORT_THRESHOLD = 0.42
ENGINEERING_EVIDENCE_SIMILARITY_THRESHOLD = 0.20


@dataclass(frozen=True)
class PrototypeScoreSummary:
    prototype_max: float
    prototype_top3_mean: float
    prototype_top5_mean: float
    ranked: tuple[tuple[int, float], ...]


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding vectors must have equal dimensions")
    left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
    right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


def summarise_prototypes(segment_vector: Sequence[float],
                         prototype_vectors: Sequence[Sequence[float]]
                         ) -> PrototypeScoreSummary:
    ranked = sorted(
        ((index, cosine_similarity(segment_vector, vector))
         for index, vector in enumerate(prototype_vectors)),
        key=lambda row: row[1], reverse=True)
    values = [score for _index, score in ranked]

    def top_mean(count: int) -> float:
        top = values[:count]
        return fmean(top) if top else 0.0

    return PrototypeScoreSummary(
        prototype_max=round(values[0], 6) if values else 0.0,
        prototype_top3_mean=round(top_mean(3), 6),
        prototype_top5_mean=round(top_mean(5), 6),
        ranked=tuple((index, round(score, 6)) for index, score in ranked),
    )


def lexical_score(unique_match_count: int) -> float:
    """Насыщающийся lexical support score, не probability."""
    if unique_match_count <= 0:
        return 0.0
    return round(min(1.0,
                     unique_match_count / ENGINEERING_LEXICAL_SATURATION_COUNT), 6)


def combined_theme_score(semantic_similarity_score: float,
                         lexical_support_score: float) -> float:
    """Engineering ranking: clipped cosine + lexical support.

    Косинус ограничивается [0, 1], но результат не калиброван и не должен
    называться вероятностью или уверенностью.
    """
    semantic = max(0.0, min(1.0, semantic_similarity_score))
    lexical = max(0.0, min(1.0, lexical_support_score))
    return round(
        ENGINEERING_SEMANTIC_WEIGHT * semantic
        + ENGINEERING_LEXICAL_WEIGHT * lexical,
        6,
    )


def segment_supports_theme(combined_score: float, semantic_score: float,
                           unique_match_count: int) -> bool:
    """Отсечь одиночный keyword без достаточного совокупного сигнала."""
    return (
        combined_score >= ENGINEERING_SEGMENT_SUPPORT_THRESHOLD
        and (
            unique_match_count >= ENGINEERING_LEXICAL_MIN_UNIQUE
            or semantic_score >= ENGINEERING_SEMANTIC_ONLY_SUPPORT_THRESHOLD
        )
    )


def engineering_parameters() -> dict:
    return {
        "prototype_top_k": ENGINEERING_PROTOTYPE_TOP_K,
        "lexical_saturation_count": ENGINEERING_LEXICAL_SATURATION_COUNT,
        "lexical_min_unique": ENGINEERING_LEXICAL_MIN_UNIQUE,
        "semantic_weight": ENGINEERING_SEMANTIC_WEIGHT,
        "lexical_weight": ENGINEERING_LEXICAL_WEIGHT,
        "segment_support_threshold": ENGINEERING_SEGMENT_SUPPORT_THRESHOLD,
        "semantic_only_support_threshold": ENGINEERING_SEMANTIC_ONLY_SUPPORT_THRESHOLD,
        "evidence_similarity_threshold": ENGINEERING_EVIDENCE_SIMILARITY_THRESHOLD,
        "threshold_kind": "ENGINEERING",
        "score_semantics": "similarity_and_ranking_not_probability",
    }
