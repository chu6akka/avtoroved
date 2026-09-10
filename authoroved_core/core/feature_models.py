"""Типизированные результаты методических измерений Автороведа Core."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from authoroved_core.core.models import Span


class AutomationMode(str, Enum):
    AUTO = "AUTO"
    LLM_ASSISTED = "LLM_ASSISTED"
    EXPERT_ONLY = "EXPERT_ONLY"


class Applicability(str, Enum):
    APPLICABLE = "APPLICABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ExpertFeatureStatus(str, Enum):
    UNREVIEWED = "UNREVIEWED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    CORRECTED = "CORRECTED"


@dataclass(frozen=True)
class SourceReference:
    title: str
    locator: str
    role: str
    verification: str


@dataclass(frozen=True)
class FeatureDefinition:
    id: str
    name_ru: str
    group: str
    automation_mode: AutomationMode
    definition: str
    criteria: tuple[str, ...]
    exclusions: tuple[str, ...]
    unit: str
    normalization: str
    minimum_words: int | None
    minimum_volume_status: str
    evidence_method: str
    sources: tuple[SourceReference, ...]
    dependency_group: str
    method_version: str


@dataclass(frozen=True)
class FeatureEvidence:
    quote: str
    span: Span
    label: str = ""


@dataclass
class FeatureObservation:
    feature_id: str
    raw_value: Any
    normalized_value: Any
    evidence: tuple[FeatureEvidence, ...]
    applicability: Applicability
    limitations: tuple[str, ...]
    method_version: str
    source: tuple[SourceReference, ...]
    confidence: str = "не вычисляется"
    expert_status: ExpertFeatureStatus = ExpertFeatureStatus.UNREVIEWED
    expert_value: Any = None
    expert_comment: str = ""

    def review(self, status: ExpertFeatureStatus, *, corrected_value: Any = None,
               comment: str = "") -> None:
        status = ExpertFeatureStatus(status)
        if status is ExpertFeatureStatus.CORRECTED and corrected_value is None:
            raise ValueError("Для исправленного наблюдения нужно указать значение эксперта.")
        if status is not ExpertFeatureStatus.CORRECTED and corrected_value is not None:
            raise ValueError("Исправленное значение допустимо только для статуса CORRECTED.")
        self.expert_status = status
        self.expert_value = corrected_value
        self.expert_comment = comment


class SuitabilityStatus(str, Enum):
    PASSED = "PASSED"
    REQUIRES_EXPERT = "REQUIRES_EXPERT"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class MaterialConditions:
    language: str | None = None
    independent_authorship: bool | None = None
    genre: str | None = None
    period: str | None = None
    addressee: str | None = None
    communicative_situation: str | None = None


@dataclass(frozen=True)
class SuitabilityAssessment:
    status: SuitabilityStatus
    language: str
    volume_words: tuple[int, ...]
    independent_authorship: str
    genre: str
    period: str
    addressee: str
    communicative_situation: str
    comparable: bool
    blocking_reasons: tuple[str, ...] = ()
    expert_questions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    @property
    def allows_expert_synthesis(self) -> bool:
        return self.status is SuitabilityStatus.PASSED and self.comparable


@dataclass(frozen=True)
class FeaturePair:
    feature_id: str
    first: FeatureObservation
    second: FeatureObservation
    dependency_group: str


@dataclass(frozen=True)
class FeatureComparison:
    allowed: bool
    pairs: tuple[FeaturePair, ...] = ()
    ignored_feature_ids: tuple[str, ...] = ()
    dependency_groups: dict[str, tuple[str, ...]] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()
