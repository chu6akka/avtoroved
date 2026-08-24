from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TextRole(str, Enum):
    DISPUTED = "disputed"
    FREE_SAMPLE = "free_sample"
    CONDITIONALLY_FREE_SAMPLE = "conditionally_free_sample"
    EXPERIMENTAL_SAMPLE = "experimental_sample"

    @property
    def is_sample(self) -> bool:
        return self is not TextRole.DISPUTED


class StageStatus(str, Enum):
    NOT_STARTED = "not_started"
    COMPLETE = "complete"
    NEEDS_EXPERT = "needs_expert"
    BLOCKED = "blocked"


class ExpertStatus(str, Enum):
    UNREVIEWED = "unreviewed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class VerdictType(str, Enum):
    CATEGORICAL_POSITIVE = "categorical_positive"
    PROBABLE_POSITIVE = "probable_positive"
    PROBABLE_NEGATIVE = "probable_negative"
    CATEGORICAL_NEGATIVE = "categorical_negative"
    INCONCLUSIVE = "inconclusive"


class DifferenceQualification(str, Enum):
    SIGNIFICANT = "significant"
    INSIGNIFICANT = "insignificant"
    EXPLAINED_GENRE = "explained_genre"
    EXPLAINED_TIME = "explained_time"
    EXPLAINED_CONDITION = "explained_condition"
    NOT_ASSESSABLE = "not_assessable"


@dataclass
class TextObject:
    id: str
    title: str
    text: str
    role: TextRole
    source_name: str = ""
    source_sha256: str = ""
    imported_at: str = field(default_factory=utc_now)
    genre: str = ""
    topic: str = ""
    addressee: str = ""
    communication_context: str = ""
    creation_date: str = ""
    independent_authorship: bool | None = None
    compilation_suspected: bool | None = None


@dataclass
class Evidence:
    quote: str
    start: int = -1
    stop: int = -1


@dataclass
class FeatureObservation:
    feature_id: str
    value: float | str | bool | None
    unit: str = ""
    present: bool = True
    method_version: str = ""
    source: str = ""
    applicability: str = "applicable"
    evidence: list[Evidence] = field(default_factory=list)
    confidence: float = 1.0
    expert_status: ExpertStatus = ExpertStatus.UNREVIEWED
    limitations: list[str] = field(default_factory=list)
    stable: bool | None = None
    dependency_group: str = ""
    origin: str = "auto"  # auto | assisted | expert | llm_hint

    @property
    def eligible_for_synthesis(self) -> bool:
        if self.origin == "llm_hint" or self.applicability != "applicable":
            return False
        return self.expert_status is ExpertStatus.CONFIRMED


@dataclass
class SuitabilityIssue:
    code: str
    message: str
    blocking: bool = True
    object_id: str = ""


@dataclass
class SuitabilityResult:
    suitable: bool
    issues: list[SuitabilityIssue]
    object_word_counts: dict[str, int]
    sample_to_disputed_ratio: float
    method_version: str


@dataclass
class ComparedFeature:
    feature_id: str
    disputed_object_id: str
    sample_subject_id: str
    outcome: str  # match | difference | not_assessable
    disputed_value: Any = None
    sample_mean: float | None = None
    sample_min: float | None = None
    sample_max: float | None = None
    relative_difference: float | None = None
    tolerance: float | None = None
    expert_status: ExpertStatus = ExpertStatus.UNREVIEWED
    qualification: DifferenceQualification | None = None
    explanation: str = ""
    dependency_group: str = ""


@dataclass
class ComparisonResult:
    disputed_object_id: str
    sample_subject_id: str
    features: list[ComparedFeature]
    limitations: list[str] = field(default_factory=list)


@dataclass
class ExpertDecision:
    verdict: VerdictType
    rationale: str
    expert_name: str
    decided_at: str = field(default_factory=utc_now)
    confirmed_feature_ids: list[str] = field(default_factory=list)


@dataclass
class AuditEvent:
    sequence: int
    timestamp: str
    event_type: str
    actor: str
    details: dict[str, Any]
    previous_hash: str
    hash: str


@dataclass
class ExpertCase:
    id: str
    title: str
    method_profile: str
    created_at: str = field(default_factory=utc_now)
    objects: list[TextObject] = field(default_factory=list)
    observations: dict[str, list[FeatureObservation]] = field(default_factory=dict)
    suitability: SuitabilityResult | None = None
    comparisons: list[ComparisonResult] = field(default_factory=list)
    decision: ExpertDecision | None = None
    audit: list[AuditEvent] = field(default_factory=list)
    stage_statuses: dict[str, StageStatus] = field(default_factory=dict)
    attachments: dict[str, str] = field(default_factory=dict)  # name -> base64

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
