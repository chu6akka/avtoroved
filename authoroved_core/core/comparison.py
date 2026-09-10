"""Нормированное сопоставление двух текстов без вывода об авторстве."""
from collections import Counter
from dataclasses import dataclass
import re

from authoroved_core.core.lt_grouping import GROUP_BY_KEY, candidate_group_key
from authoroved_core.core.models import AnalysisResult, Candidate, Metric, ReviewStatus, Span


_DYNAMIC_LEXICAL_PREFIXES = ("Частотные слова:", "Частотные знаменательные слова:")
_VOLUME_NAMES = {"Символы", "Слова", "Предложения", "Абзацы", "Уникальные словоформы", "Уникальные леммы"}
_SENTENCE_RATE_NAMES = {"Предложения с вопросительным знаком", "Предложения с восклицательным знаком"}
_WORD_RATE_NAMES = {"Многоточия"}
_FUNCTION_POS = {"ADP", "PART", "CCONJ", "SCONJ", "PRON", "DET", "AUX"}
_STANZA_DEPENDENCY_GROUP = "Служебная синтаксическая разметка Stanza"


@dataclass(frozen=True)
class MetricComparison:
    name: str
    group: str
    value_first: str
    value_second: str
    difference: str
    direction: str
    basis: str
    explanation: str
    caution: str
    spans_first: tuple[Span, ...]
    spans_second: tuple[Span, ...]


@dataclass(frozen=True)
class AcceptedGroup:
    category: str
    label: str
    count_first: int
    count_second: int
    relation: str
    basis: str
    spans_first: tuple[Span, ...]
    spans_second: tuple[Span, ...]


@dataclass(frozen=True)
class ComparisonResult:
    metrics: tuple[MetricComparison, ...]
    accepted_groups: tuple[AcceptedGroup, ...]
    limitations: tuple[str, ...]


def _number(value: str, *, percentage=False) -> float | None:
    source = value.split("·", 1)[1] if percentage and "·" in value else value
    match = re.search(r"-?\d+(?:[,.]\d+)?", source)
    return float(match.group().replace(",", ".")) if match else None


def _render(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _difference(first: float, second: float, unit: str) -> tuple[str, str]:
    delta = abs(first - second)
    difference = f"{_render(delta)} {unit}".strip()
    if delta < 1e-12:
        return difference, "значения равны"
    return difference, f"выше в тексте {1 if first > second else 2}"


def _metric_map(result: AnalysisResult) -> dict[str, Metric]:
    return {metric.name: metric for metric in result.metrics
            if not metric.name.startswith(_DYNAMIC_LEXICAL_PREFIXES)}


def _total(result: AnalysisResult, name: str) -> float:
    metric = next((item for item in result.metrics if item.name == name), None)
    return _number(metric.value) if metric else 0.0


def _compare_metric(first: Metric, second: Metric,
                    first_result: AnalysisResult, second_result: AnalysisResult) -> MetricComparison:
    name = first.name
    group = first.group
    basis = "одноимённое значение"
    caution = "Автоматически рассчитанный показатель требует экспертной интерпретации."
    value_first, value_second = first.value, second.value
    numeric_first = numeric_second = None
    unit = ""

    if name in _SENTENCE_RATE_NAMES:
        denominator_first = _total(first_result, "Предложения")
        denominator_second = _total(second_result, "Предложения")
        raw_first, raw_second = _number(first.value), _number(second.value)
        if denominator_first and denominator_second and raw_first is not None and raw_second is not None:
            numeric_first = raw_first / denominator_first * 100
            numeric_second = raw_second / denominator_second * 100
            value_first = f"{first.value} · {_render(numeric_first)} на 100 предложений"
            value_second = f"{second.value} · {_render(numeric_second)} на 100 предложений"
            unit = "на 100 предложений"
            basis = "частота на 100 предложений"
            group = "Нормированные показатели"
    elif name in _WORD_RATE_NAMES:
        denominator_first = _total(first_result, "Слова")
        denominator_second = _total(second_result, "Слова")
        raw_first, raw_second = _number(first.value), _number(second.value)
        if denominator_first and denominator_second and raw_first is not None and raw_second is not None:
            numeric_first = raw_first / denominator_first * 1000
            numeric_second = raw_second / denominator_second * 1000
            value_first = f"{first.value} · {_render(numeric_first)} на 1000 слов"
            value_second = f"{second.value} · {_render(numeric_second)} на 1000 слов"
            unit = "на 1000 слов"
            basis = "частота на 1000 слов"
            group = "Нормированные показатели"
    elif "%" in first.value and "%" in second.value:
        numeric_first = _number(first.value, percentage=True)
        numeric_second = _number(second.value, percentage=True)
        unit = "п. п."
        basis = "разница долей в процентных пунктах"
        group = (first.group if first.group == _STANZA_DEPENDENCY_GROUP
                 else "Нормированные показатели")
    else:
        numeric_first, numeric_second = _number(first.value), _number(second.value)
        if name in _VOLUME_NAMES:
            group = "Объём и состав материала"
            basis = "абсолютное количество"
            caution = "Показатель зависит от объёма материала и сам по себе не характеризует автора."
        elif name == "Лексическое разнообразие":
            group = "Нормированные показатели"
            basis = "отношение уникальных словоформ к числу слов"
            caution = "Показатель лексического разнообразия существенно зависит от длины текста; сопоставление носит ориентирующий характер."
        elif "длина" in name.casefold():
            group = "Нормированные показатели"
            basis = "среднее или медианное число слов"
            unit = "слова"

    if numeric_first is None or numeric_second is None:
        difference, direction = "не рассчитана", "недостаточно данных"
    else:
        difference, direction = _difference(numeric_first, numeric_second, unit)
    return MetricComparison(
        name=name, group=group, value_first=value_first, value_second=value_second,
        difference=difference, direction=direction, basis=basis,
        explanation=first.explanation, caution=caution,
        spans_first=first.spans, spans_second=second.spans,
    )


def _function_word_metrics(first: AnalysisResult, second: AnalysisResult) -> list[MetricComparison]:
    def selected(result):
        return [token for token in result.tokens if token.pos in _FUNCTION_POS
                and any(char.isalpha() for char in token.text)]

    first_tokens, second_tokens = selected(first), selected(second)
    first_counts = Counter(token.text.casefold() for token in first_tokens)
    second_counts = Counter(token.text.casefold() for token in second_tokens)
    words_first, words_second = _total(first, "Слова"), _total(second, "Слова")
    if not words_first or not words_second:
        return []
    forms = [form for form, _ in (first_counts + second_counts).most_common(12)]
    metrics = []
    for form in forms:
        rate_first = first_counts[form] / words_first * 1000
        rate_second = second_counts[form] / words_second * 1000
        difference, direction = _difference(rate_first, rate_second, "на 1000 слов")
        metrics.append(MetricComparison(
            name=f"Служебное слово «{form}»", group="Служебные слова (на 1000 слов)",
            value_first=f"{first_counts[form]} · {_render(rate_first)} на 1000 слов",
            value_second=f"{second_counts[form]} · {_render(rate_second)} на 1000 слов",
            difference=difference, direction=direction, basis="частота словоформы на 1000 слов",
            explanation=("Словоформа отобрана по автоматической части речи Stanza: местоимение, "
                         "предлог, союз, частица, детерминатив или вспомогательный глагол."),
            caution=("Разметка части речи может ошибаться. Показатель не проверен как "
                     "самостоятельный идентификационный признак."),
            spans_first=tuple(token.span for token in first_tokens
                              if token.text.casefold() == form and token.span is not None),
            spans_second=tuple(token.span for token in second_tokens
                               if token.text.casefold() == form and token.span is not None),
        ))
    return metrics


def _accepted_key(candidate: Candidate):
    group = candidate_group_key(candidate)
    fragment = " ".join(candidate.fragment.casefold().split())
    return (group, "fragment", fragment) if fragment else (group, "rule", candidate.rule_id)


def _accepted_groups(first: AnalysisResult, second: AnalysisResult) -> tuple[AcceptedGroup, ...]:
    first_items = [item for item in first.candidates if item.status == ReviewStatus.ACCEPTED]
    second_items = [item for item in second.candidates if item.status == ReviewStatus.ACCEPTED]
    keys = sorted({_accepted_key(item) for item in first_items + second_items})
    groups = []
    for key in keys:
        items_first = [item for item in first_items if _accepted_key(item) == key]
        items_second = [item for item in second_items if _accepted_key(item) == key]
        definition = GROUP_BY_KEY[key[0]]
        if items_first and items_second:
            relation = "В обоих текстах"
        elif items_first:
            relation = "Только в тексте 1"
        else:
            relation = "Только в тексте 2"
        if key[1] == "fragment":
            sample = (items_first or items_second)[0].fragment.replace("\n", " ").replace("\r", " ")
            label = f"{definition.title}: «{sample}»"
            basis = "одинаковая словоформа или фрагмент без различия регистра"
        else:
            label = definition.title
            basis = "одинаковый тип автоматической рекомендации LanguageTool"
        groups.append(AcceptedGroup(
            category=definition.title, label=label,
            count_first=len(items_first), count_second=len(items_second), relation=relation,
            basis=basis, spans_first=tuple(item.span for item in items_first),
            spans_second=tuple(item.span for item in items_second),
        ))
    return tuple(groups)


def compare_results(first: AnalysisResult, second: AnalysisResult) -> ComparisonResult:
    """Сопоставляет значения и принятые наблюдения, не вычисляя сходство авторов."""
    first_metrics, second_metrics = _metric_map(first), _metric_map(second)
    common_names = sorted(first_metrics.keys() & second_metrics.keys())
    metrics = [_compare_metric(first_metrics[name], second_metrics[name], first, second)
               for name in common_names]
    metrics.extend(_function_word_metrics(first, second))
    group_order = {
        "Объём и состав материала": 0,
        "Нормированные показатели": 1,
        "Служебные слова (на 1000 слов)": 2,
        _STANZA_DEPENDENCY_GROUP: 3,
    }
    metrics.sort(key=lambda item: (group_order.get(item.group, 4), item.name.casefold()))
    limitations = [
        "Разницы показателей не имеют автоматических порогов и интерпретируются экспертом.",
        "Принятые рекомендации LanguageTool остаются наблюдениями, а не готовыми авторскими признаками.",
    ]
    words_first, words_second = _total(first, "Слова"), _total(second, "Слова")
    if min(words_first, words_second) and max(words_first, words_second) / min(words_first, words_second) > 1.5:
        limitations.append("Объёмы текстов различаются более чем в полтора раза; абсолютные количества напрямую не сопоставимы.")
    remaining = [sum(item.status == ReviewStatus.NEW for item in result.candidates)
                 for result in (first, second)]
    if any(remaining):
        limitations.append(f"Проверка кандидатов не завершена: текст 1 — {remaining[0]}, текст 2 — {remaining[1]}.")
    if first.errors or second.errors:
        limitations.append("Один из анализов завершён частично; недоступные показатели нельзя интерпретировать как отсутствие признака.")
    return ComparisonResult(tuple(metrics), _accepted_groups(first, second), tuple(limitations))
