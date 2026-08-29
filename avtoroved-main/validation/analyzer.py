from __future__ import annotations

import dataclasses
import logging

from .models import BlindDocument

LOG = logging.getLogger(__name__)


def _plain(value):
    if dataclasses.is_dataclass(value):
        return {field.name: _plain(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    return value


class ProductionValidationAnalyzer:
    """Явный shadow-адаптер; получает только BlindDocument."""

    def __init__(self):
        from analyzer.semantic_layers.style_engine_v2 import StyleEngineV2
        from analyzer.semantic_layers.theme_engine_v2 import ThemeEngineV2
        self.theme = ThemeEngineV2()
        self.style = StyleEngineV2()

    def analyze(self, document: BlindDocument) -> dict:
        theme = self.theme.analyze(document.text)
        style = self.style.analyze(document.text)
        candidates = []
        for candidate in style.method_feature_candidates:
            candidates.append({
                "document_id": document.document_id,
                "method_feature_id": candidate.method_feature_id,
                "detected": True,
                "automation_level": candidate.automation_status,
                "source": "StyleEngineV2",
            })
        return {"document_id": document.document_id,
                "input_sha256": document.input_sha256,
                "theme": _plain(theme), "style": _plain(style),
                "feature_candidates": candidates}


class SyntheticDemoAnalyzer:
    """Детерминированный smoke-анализатор только для синтетического demo."""

    def analyze(self, document: BlindDocument) -> dict:
        lower = document.text.lower()
        features = []
        mapping = {"во-первых": "demo.discourse.sequence",
                   "короче": "demo.style.conversational",
                   "следовательно": "demo.syntax.logical_link"}
        for marker, feature_id in mapping.items():
            if marker in lower:
                features.append({"document_id": document.document_id,
                                 "method_feature_id": feature_id,
                                 "detected": True, "automation_level": "CANDIDATE_ONLY",
                                 "source": "synthetic_demo_rule"})
        themes = ["politics"] if "выбор" in lower else ["everyday"]
        styles = ["publicistic"] if "общество" in lower else ["conversational"]
        return {"document_id": document.document_id,
                "input_sha256": document.input_sha256,
                "theme": {"selected_labels": themes, "status": "synthetic_demo"},
                "style": {"selected_labels": styles, "status": "synthetic_demo"},
                "feature_candidates": features}
