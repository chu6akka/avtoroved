"""Версионируемые контракты semantic layers.

Контракты V2 намеренно не совместимы с ``feature_candidates`` напрямую:
результат shadow-анализа хранит инженерные similarity/evidence, но не назначает
экспертную идентификационную значимость.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class ThemeEvidence:
    label: str
    fragment: str
    start: Optional[int]
    end: Optional[int]
    source: str
    score: float


@dataclass(frozen=True)
class ThemeScore:
    theme_id: str
    label: str
    score: float
    evidence: tuple[ThemeEvidence, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ThemeAnalysisResult:
    themes: tuple[ThemeScore, ...]
    dominant_theme: Optional[ThemeScore]
    engine_version: str


@dataclass(frozen=True)
class PrototypeSimilarity:
    """Сходство сегмента с одним инженерным прототипом темы."""

    prototype: str
    score: float


@dataclass(frozen=True)
class ThemeSegmentEvidence:
    """Проверяемое основание результата V2 с координатами исходного текста."""

    segment_id: str
    start: int
    end: int
    fragment: str
    semantic_score: float
    prototype_max: float = 0.0
    prototype_top3_mean: float = 0.0
    prototype_top5_mean: float = 0.0
    lexical_match_count: int = 0
    lexical_unique_match_count: int = 0
    lexical_coverage: float = 0.0
    lexical_matches: tuple[str, ...] = ()
    matched_phrases: tuple[str, ...] = ()
    prototype_matches: tuple[PrototypeSimilarity, ...] = ()


@dataclass(frozen=True)
class ThemeV2Score:
    """Одна строка multi-label профиля V2.

    ``combined_score`` — инженерный ranking score, не вероятность. Поле
    ``expert_identification_value`` всегда остаётся ``None`` в Patch B.
    """

    theme_id: str
    label: str
    semantic_score: float
    lexical_score: float
    combined_score: float
    coverage: float
    segment_support_count: int
    segment_count: int
    evidence: tuple[ThemeSegmentEvidence, ...] = ()
    method_status: str = "UNRESOLVED"
    method_feature_id: Optional[str] = None
    expert_identification_value: Optional[str] = None


@dataclass(frozen=True)
class ThemeAnalysisResultV2:
    """Shadow-only тематический профиль документа."""

    themes: tuple[ThemeV2Score, ...]
    dominant_theme: Optional[ThemeV2Score]
    selected_themes: tuple[ThemeV2Score, ...]
    segment_count: int
    engine_version: str
    model_info: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    reason: Optional[str] = None


@dataclass(frozen=True)
class StyleEvidence:
    feature_id: str
    label: str
    fragment: str
    count: int
    score: float
    source: str


@dataclass(frozen=True)
class StyleScore:
    style_id: str
    label: str
    score: float
    evidence: tuple[StyleEvidence, ...] = ()


@dataclass(frozen=True)
class StyleAnalysisResult:
    styles: tuple[StyleScore, ...]
    dominant_style: Optional[StyleScore]
    engine_version: str


@dataclass(frozen=True)
class StyleFeatureEvidenceV2:
    """Проверяемый фрагмент одного инженерного стилевого сигнала."""

    feature_id: str
    style_id: str
    family: str
    automation_status: str
    role: str
    start: int
    end: int
    fragment: str
    raw_value: float
    normalized_value: float
    method_status: str = "AUXILIARY"
    method_feature_id: Optional[str] = None
    accepted: bool = False
    reliability: str = "engineering"


@dataclass(frozen=True)
class StyleDetectedFeatureV2:
    """Агрегат detector-а; не является автоматически принятым признаком."""

    feature_id: str
    label: str
    style_id: str
    family: str
    automation_status: str
    role: str
    raw_count: int
    normalized_value: float
    evidence: tuple[StyleFeatureEvidenceV2, ...] = ()
    method_status: str = "AUXILIARY"
    method_feature_id: Optional[str] = None
    accepted: bool = False
    limitations: tuple[str, ...] = ()
    expert_identification_value: Optional[str] = None


@dataclass(frozen=True)
class StyleSegmentResultV2:
    segment_id: str
    start: int
    end: int
    text: str
    detected_style_features: tuple[str, ...]
    style_support: dict[str, float]


@dataclass(frozen=True)
class StyleScoreV2:
    style_id: str
    label: str
    support_score: float
    feature_family_support: dict[str, float]
    detected_features: tuple[StyleDetectedFeatureV2, ...]
    segment_coverage: float
    evidence: tuple[StyleFeatureEvidenceV2, ...]
    expert_identification_value: Optional[str] = None


@dataclass(frozen=True)
class StyleMethodFeatureCandidateV2:
    """Source-traceable METHOD_FEATURE candidate projected from V2 evidence.

    Detection never means expert acceptance and never carries identification
    value.  The candidate is a shadow/debug artifact until an expert explicitly
    creates and qualifies a case feature through the protocol workflow.
    """

    method_feature_id: str
    label: str
    functional_style: str
    automation_status: str
    evidence: tuple[StyleFeatureEvidenceV2, ...]
    detection_reliability: float
    method_group: str = "linguistic"
    method_subgroup: str = "stylistic"
    role: str = "METHOD_FEATURE"
    source_kind: str = "METHOD"
    accepted: bool = False
    status: str = "detected_candidate"
    limitations: tuple[str, ...] = ()
    expert_identification_value: Optional[str] = None


@dataclass(frozen=True)
class StyleAnalysisResultV2:
    styles: tuple[StyleScoreV2, ...]
    selected_styles: tuple[StyleScoreV2, ...]
    leading_style: Optional[StyleScoreV2]
    segments: tuple[StyleSegmentResultV2, ...]
    segment_count: int
    engine_version: str
    parameters: dict[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()
    status: str = "ok"
    reason: Optional[str] = None
    method_feature_candidates: tuple[StyleMethodFeatureCandidateV2, ...] = ()
