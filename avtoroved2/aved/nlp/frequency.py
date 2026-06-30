"""Частотность лемм (частотный словарь Ляшевской–Шарова, НКРЯ; оффлайн).

Используется для оценки информативности слова: редкие слова индивидуализируют автора
сильнее частотных служебных. Формат файла: {лемма: [ранг, ipm, часть_речи]}.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from aved.core.registry import find_data_dir

_FREQ: dict[str, float] | None = None


def _load() -> dict[str, float]:
    global _FREQ
    if _FREQ is None:
        path = find_data_dir() / "freq" / "freqrnc.json"
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            _FREQ = {k.lower(): float(v[1]) for k, v in raw.items()}
        else:
            _FREQ = {}
    return _FREQ


def ipm(lemma: str) -> float:
    """Частота леммы в ipm (вхождений на миллион); 0.0 — нет в словаре."""
    return _load().get(lemma.lower(), 0.0)


def informativeness(lemma: str) -> float:
    """Вес информативности леммы в [~0.09, 1.0]: редкое/незнакомое слово → выше."""
    return 1.0 / (1.0 + math.log1p(ipm(lemma)))
