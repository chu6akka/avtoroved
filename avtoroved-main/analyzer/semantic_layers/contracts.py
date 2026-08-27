"""Версионируемые контракты будущих ThemeEngineV2 и StyleEngineV2."""
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
