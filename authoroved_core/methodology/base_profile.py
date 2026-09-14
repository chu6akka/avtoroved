"""Только представление; ведомственных правил и форм вывода в Core нет."""
from dataclasses import dataclass


@dataclass(frozen=True)
class BaseProfile:
    name: str = "Базовое исследование текста"
    analyzers: tuple[str, ...] = (
        "stanza", "languagetool", "basic_metrics", "auto_features_0.1.0",
    )
    categories: tuple[str, ...] = (
        "Лексика", "Морфология", "Предложения", "Структура",
        "Методические AUTO-показатели",
    )
    help_text: str = "Показатели описывают текст. Их интерпретирует эксперт."
