"""Прозрачное сопоставление двух результатов без вывода об авторстве."""
from dataclasses import dataclass
import re

from authoroved_core.core.models import AnalysisResult, ReviewStatus, Span


_DYNAMIC_LEXICAL_PREFIXES = (
    "Частотные слова:",
    "Частотные знаменательные слова:",
)


@dataclass(frozen=True)
class MetricComparison:
    name: str
    group: str
    value_first: str
    value_second: str
    difference: str
    explanation: str
    spans_first: tuple[Span, ...]
    spans_second: tuple[Span, ...]


@dataclass(frozen=True)
class AcceptedGroup:
    category: str
    count_first: int
    count_second: int
    relation: str
    spans_first: tuple[Span, ...]
    spans_second: tuple[Span, ...]


@dataclass(frozen=True)
class ComparisonResult:
    metrics: tuple[MetricComparison, ...]
    accepted_groups: tuple[AcceptedGroup, ...]


def _number(value: str) -> tuple[float, str] | None:
    """Извлекает сопоставимую величину и её единицу из значения метрики."""
    if "·" in value and "%" in value:
        tail = value.split("·", 1)[1]
        match = re.search(r"-?\d+(?:[,.]\d+)?", tail)
        return (float(match.group().replace(",", ".")), "п. п.") if match else None
    match = re.fullmatch(r"\s*(-?\d+(?:[,.]\d+)?)\s*(.*?)\s*", value)
    if not match:
        return None
    unit = match.group(2).replace("%", "п. п.")
    return float(match.group(1).replace(",", ".")), unit


def _format_difference(first: str, second: str) -> str:
    parsed_first, parsed_second = _number(first), _number(second)
    if parsed_first is None or parsed_second is None:
        return "Не рассчитана"
    value = abs(parsed_first[0] - parsed_second[0])
    rendered = f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    unit = parsed_first[1] if parsed_first[1] == parsed_second[1] else ""
    return f"{rendered} {unit}".strip()


def compare_results(first: AnalysisResult, second: AnalysisResult) -> ComparisonResult:
    """Сопоставляет одноимённые измерения и только принятые наблюдения."""
    first_metrics = {
        (metric.group, metric.name): metric for metric in first.metrics
        if not metric.name.startswith(_DYNAMIC_LEXICAL_PREFIXES)
    }
    second_metrics = {
        (metric.group, metric.name): metric for metric in second.metrics
        if not metric.name.startswith(_DYNAMIC_LEXICAL_PREFIXES)
    }
    common = sorted(first_metrics.keys() & second_metrics.keys())
    metrics = tuple(
        MetricComparison(
            name=name,
            group=group,
            value_first=first_metrics[(group, name)].value,
            value_second=second_metrics[(group, name)].value,
            difference=_format_difference(
                first_metrics[(group, name)].value,
                second_metrics[(group, name)].value,
            ),
            explanation=first_metrics[(group, name)].explanation,
            spans_first=first_metrics[(group, name)].spans,
            spans_second=second_metrics[(group, name)].spans,
        )
        for group, name in common
    )

    accepted_first = [c for c in first.candidates if c.status == ReviewStatus.ACCEPTED]
    accepted_second = [c for c in second.candidates if c.status == ReviewStatus.ACCEPTED]
    categories = sorted({c.category for c in accepted_first + accepted_second})
    groups = []
    for category in categories:
        items_first = [c for c in accepted_first if c.category == category]
        items_second = [c for c in accepted_second if c.category == category]
        if items_first and items_second:
            relation = "В обоих текстах"
        elif items_first:
            relation = "Только в тексте 1"
        else:
            relation = "Только в тексте 2"
        groups.append(AcceptedGroup(
            category, len(items_first), len(items_second), relation,
            tuple(c.span for c in items_first), tuple(c.span for c in items_second),
        ))
    return ComparisonResult(metrics, tuple(groups))
