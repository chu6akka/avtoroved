"""Стабильные интерфейсы semantic layers.

Production использует legacy Theme/Style adapters. V2 engines доступны только
через явные shadow API и не подключены к экспертному профилю.
"""

from analyzer.semantic_layers.contracts import (
    StyleAnalysisResult,
    StyleAnalysisResultV2,
    StyleDetectedFeatureV2,
    StyleEvidence,
    StyleFeatureEvidenceV2,
    StyleScore,
    StyleScoreV2,
    ThemeAnalysisResult,
    ThemeEvidence,
    ThemeScore,
)
from analyzer.semantic_layers.style_engine import STYLE_ENGINE_VERSION, StyleEngine
from analyzer.semantic_layers.style_engine_v2 import (
    STYLE_ENGINE_V2_VERSION,
    StyleEngineV2,
)
from analyzer.semantic_layers.theme_engine import THEME_ENGINE_VERSION, ThemeEngine
from analyzer.semantic_layers.theme_engine_v2 import (
    THEME_ENGINE_V2_VERSION,
    ThemeEngineV2,
)

__all__ = [
    "STYLE_ENGINE_VERSION",
    "THEME_ENGINE_VERSION",
    "StyleAnalysisResult",
    "StyleAnalysisResultV2",
    "StyleDetectedFeatureV2",
    "StyleEngine",
    "StyleEngineV2",
    "STYLE_ENGINE_V2_VERSION",
    "StyleEvidence",
    "StyleFeatureEvidenceV2",
    "StyleScore",
    "StyleScoreV2",
    "ThemeAnalysisResult",
    "ThemeEngine",
    "ThemeEngineV2",
    "THEME_ENGINE_V2_VERSION",
    "ThemeEvidence",
    "ThemeScore",
]
