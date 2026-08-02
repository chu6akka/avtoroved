"""Общее состояние сессии нового интерфейса."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class TextSlot:
    """Один исследуемый текст и результаты его раздельного анализа."""
    name: str = ""
    text: str = ""
    # Результаты раздельного исследования (заполняются на Стадии 2)
    tokens: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    error_result: Any = None
    strat_result: Any = None
    thematic_result: Any = None
    ogorelkov_result: Any = None    # служебная лексика (Огорелков), ipm
    diagnostic_result: Any = None
    analyzed: bool = False

    def word_count(self) -> int:
        import re
        return len(re.findall(r"[А-Яа-яЁёA-Za-z]+", self.text))


@dataclass
class AppState:
    # "diagnostic" — один текст (профиль); "identification" — два текста (сравнение)
    mode: str = "identification"
    slot1: TextSlot = field(default_factory=lambda: TextSlot(name="Текст 1"))
    slot2: TextSlot = field(default_factory=lambda: TextSlot(name="Текст 2"))
    comparison: Any = None          # ComparisonResult (Стадия 3, идентификация)
    comparison_aux: dict = field(default_factory=dict)
    expert_verdict: str = ""

    def active_slots(self):
        return [self.slot1] if self.mode == "diagnostic" else [self.slot1, self.slot2]
