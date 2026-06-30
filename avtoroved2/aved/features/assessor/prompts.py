"""Построение промптов для оценки качественных признаков локальной LLM."""
from __future__ import annotations

from aved.core.models import Feature

_SYSTEM = (
    "Ты — ассистент судебного эксперта-автороведа. Твоя задача — по тексту определить, "
    "проявляется ли в нём каждый из перечисленных признаков письменной речи. "
    "Будь осторожен: отмечай признак present=true только при явных основаниях в тексте."
)


def build_batch_prompt(features: list[Feature], excerpt: str) -> str:
    lines = "\n".join(f"{i + 1}. {f.name}" for i, f in enumerate(features))
    n = len(features)
    return (
        f"{_SYSTEM}\n\n"
        f'Верни СТРОГО JSON-объект: {{"items": [...]}} — РОВНО {n} элемент(ов), '
        "ПО ОДНОМУ на каждый признак, В ТОМ ЖЕ ПОРЯДКЕ, что и список ниже. "
        'Каждый элемент: {"present": true|false, "confidence": <0..1>, '
        '"evidence": "<короткая цитата из текста или пустая строка>"}.\n\n'
        f"ПРИЗНАКИ ({n}):\n{lines}\n\n"
        f'ТЕКСТ:\n"""\n{excerpt}\n"""\n'
    )
