"""Только представление; ведомственных правил и форм вывода в Core нет."""
from dataclasses import dataclass


@dataclass(frozen=True)
class BaseProfile:
    name: str = "Базовое исследование текста"
    analyzers: tuple[str, ...] = ("stanza", "languagetool", "basic_metrics")
    categories: tuple[str, ...] = (
        "Лексика", "Морфология", "Предложения", "Структура",
        "Технические связи Stanza (UD)",
    )
    help_text: str = "Показатели описывают текст. Их интерпретирует эксперт."
