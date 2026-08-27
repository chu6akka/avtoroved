"""Стабильные интерфейсы тематического и стилевого анализа.

Patch A сохраняет legacy-алгоритмы и только изолирует их за адаптерами.
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

__all__ = [
    "STYLE_ENGINE_VERSION",
    "THEME_ENGINE_VERSION",
    "StyleAnalysisResult",
    "StyleEngine",
    "StyleEvidence",
    "StyleScore",
    "ThemeAnalysisResult",
    "ThemeEngine",
    "ThemeEvidence",
    "ThemeScore",
]
