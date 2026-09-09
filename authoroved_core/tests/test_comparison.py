from authoroved_core.core.comparison import compare_results
from authoroved_core.core.models import AnalysisResult, Candidate, Metric, ReviewStatus, Span


def candidate(identifier, document_id, category, status, span):
    item = Candidate(identifier, document_id, "Наблюдение", category, "Пояснение",
                     "фрагмент", span, "RULE")
    item.status = status
    return item


def test_comparison_uses_percentages_and_has_no_authorship_score():
    first = AnalysisResult("a", metrics=[
        Metric("Существительные", "20 · 40 %", "Доля слов", "Морфология", (Span(0, 3),)),
        Metric("Слова", "50", "Число слов", "Количественные показатели"),
        Metric("Частотные слова: дом", "3", "Частота", "Лексика"),
    ])
    second = AnalysisResult("b", metrics=[
        Metric("Существительные", "30 · 50 %", "Доля слов", "Морфология", (Span(4, 7),)),
        Metric("Слова", "60", "Число слов", "Количественные показатели"),
        Metric("Частотные слова: дом", "8", "Частота", "Лексика"),
    ])

    result = compare_results(first, second)

    by_name = {metric.name: metric for metric in result.metrics}
    assert by_name["Существительные"].difference == "10 п. п."
    assert by_name["Слова"].difference == "10"
    assert "Частотные слова: дом" not in by_name
    assert not hasattr(result, "similarity")
    assert not hasattr(result, "authorship_score")


def test_only_accepted_candidates_are_grouped_transparently():
    first = AnalysisResult("a", candidates=[
        candidate("a1", "a", "Орфография", ReviewStatus.ACCEPTED, Span(0, 2)),
        candidate("a2", "a", "Пунктуация", ReviewStatus.REJECTED, Span(3, 4)),
    ])
    second = AnalysisResult("b", candidates=[
        candidate("b1", "b", "Орфография", ReviewStatus.ACCEPTED, Span(5, 7)),
        candidate("b2", "b", "Грамматика", ReviewStatus.NEW, Span(8, 9)),
    ])

    result = compare_results(first, second)

    assert len(result.accepted_groups) == 1
    group = result.accepted_groups[0]
    assert (group.category, group.count_first, group.count_second, group.relation) == (
        "Орфография", 1, 1, "В обоих текстах",
    )
    assert group.spans_first == (Span(0, 2),)
    assert group.spans_second == (Span(5, 7),)
