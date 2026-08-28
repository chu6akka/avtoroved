"""Стабильные интерфейсы semantic layers.

Production использует legacy Theme/Style adapters. ThemeEngineV2 доступен
только через явный shadow API и не подключён к экспертному профилю.
"""

from analyzer.semantic_layers.contracts import (
    StyleAnalysisResult,
    StyleEvidence,
    StyleScore,
    ThemeAnalysisResult,
    ThemeEvidence,
    ThemeScore,
)
from analyzer.semantic_layers.style_engine import STYLE_ENGINE_VERSION, StyleEngine
from analyzer.semantic_layers.theme_engine import THEME_ENGINE_VERSION, ThemeEngine
from analyzer.semantic_layers.theme_engine_v2 import (
    THEME_ENGINE_V2_VERSION,
    ThemeEngineV2,
)

__all__ = [
    "STYLE_ENGINE_VERSION",
    "THEME_ENGINE_VERSION",
    "StyleAnalysisResult",
    "StyleEngine",
    "StyleEvidence",
    "StyleScore",
    "ThemeAnalysisResult",
    "ThemeEngine",
    "ThemeEngineV2",
    "THEME_ENGINE_V2_VERSION",
    "ThemeEvidence",
    "ThemeScore",
]
