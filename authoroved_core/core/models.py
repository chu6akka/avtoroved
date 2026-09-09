from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class Span:
    start: int
    end: int

    def valid_for(self, text: str) -> bool:
        return 0 <= self.start <= self.end <= len(text)


@dataclass(frozen=True)
class Token:
    text: str
    lemma: str
    pos: str
    feats: dict[str, str]
    dependency: str
    head: int
    sentence: int
    index: int
    span: Span | None


@dataclass(frozen=True)
class Metric:
    name: str
    value: str
    explanation: str
    group: str
    spans: tuple[Span, ...] = ()


class ReviewStatus(str, Enum):
    NEW = "new"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


STATUS_LABELS = {ReviewStatus.NEW: "Не рассмотрен", ReviewStatus.ACCEPTED: "Принят",
                 ReviewStatus.REJECTED: "Отклонён"}


@dataclass
class Candidate:
    id: str
    document_id: str
    name: str
    category: str
    explanation: str
    fragment: str
    span: Span
    rule_id: str
    replacements: tuple[str, ...] = ()
    source: str = "LanguageTool"
    status: ReviewStatus = ReviewStatus.NEW
    comment: str = ""

    def review(self, status: ReviewStatus, comment: str | None = None) -> None:
        self.status = ReviewStatus(status)
        if comment is not None:
            self.comment = comment


@dataclass
class AnalysisResult:
    document_id: str
    tokens: list[Token] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    metrics: list[Metric] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
