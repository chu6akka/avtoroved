from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class FeatureRule:
    id: str
    name: str
    level: str
    category: str
    source: str
    page: str
    method: str
    unit: str = ""
    min_words: int = 0
    stability: str = "expert"
    expert_confirmation: bool = True
    tolerance: float | None = None
    dependency_group: str = ""
    extractor: str = ""


@dataclass
class MethodProfile:
    id: str
    version: str
    title: str
    source: str
    applicability: dict[str, Any]
    suitability: dict[str, Any]
    allowed_verdicts: list[str]
    features: list[FeatureRule] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "MethodProfile":
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        features = [FeatureRule(**item) for item in raw.pop("features", [])]
        profile = cls(features=features, **raw)
        profile.validate()
        return profile

    def validate(self) -> None:
        if not self.id or not self.version or not self.source:
            raise ValueError("Профиль должен содержать id, version и source")
        ids = [f.id for f in self.features]
        if len(ids) != len(set(ids)):
            raise ValueError("В профиле есть дублирующиеся id признаков")
        for f in self.features:
            if f.level not in {"NN", "NS", "NSV"}:
                raise ValueError(f"Недопустимый уровень {f.level!r}: {f.id}")
            if f.method not in {"auto", "assisted", "expert"}:
                raise ValueError(f"Недопустимый метод {f.method!r}: {f.id}")

    def feature(self, feature_id: str) -> FeatureRule:
        return next(f for f in self.features if f.id == feature_id)

    @staticmethod
    def bundled(profile_id: str) -> "MethodProfile":
        root = Path(__file__).resolve().parent / "profiles"
        return MethodProfile.load(root / f"{profile_id}.yaml")
