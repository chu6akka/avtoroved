"""Замороженная конфигурация Patch D.

Значения только документируют конфигурацию проверяемой версии. Модуль не
подменяет параметры production-движков и не участвует в их выборе.
"""

FROZEN_ENGINE_CONFIG = {
    "theme": {
        "engine": "ThemeEngineV2",
        "model": "cointegrated/rubert-tiny2",
        "revision": "e8ed3b0",
        "selection_floor": 0.44,
        "selection_margin": 0.08,
        "minimum_segment_support": 1,
        "safety_cap": 4,
    },
    "style": {
        "engine": "StyleEngineV2",
        "configuration": "F_HYBRID",
        "selection_floor": 0.12,
        "selection_margin": 0.08,
        "minimum_feature_families": 2,
        "weak_signal_threshold": 0.14,
    },
}

SUBSETS = ("DEVELOPMENT", "PILOT", "VALIDATION")
SAMPLE_TYPES = ("CONTROL", "DISPUTED", "REFERENCE")
EXPECTED_RELATIONS = ("SAME_AUTHOR", "DIFFERENT_AUTHOR", "UNKNOWN")
AUTOMATION_LEVELS = ("AUTO", "AUTO_DETECTABLE", "CANDIDATE_ONLY", "EXPERT_ONLY")
METHOD_GROUPS = (
    "semantic", "textological", "lexical", "stylistic", "syntactic",
    "morphological", "orthographic", "punctuation", "psycholinguistic",
)
