from authoroved_core.core.comparison import compare_results
from authoroved_core.core.models import AnalysisResult, Candidate, Metric, ReviewStatus, Span, Token


def candidate(identifier, document_id, category, status, span, fragment="фрагмент", rule="RULE"):
    item = Candidate(identifier, document_id, "Наблюдение", category, "Пояснение", fragment, span, rule)
    item.status = status
    return item


def base_result(identifier, words, sentences, extra=(), candidates=(), tokens=()):
    return AnalysisResult(identifier, tokens=list(tokens), candidates=list(candidates), metrics=[
        Metric("Слова", str(words), "Число слов", "Количественные показатели"),
        Metric("Предложения", str(sentences), "Число предложений", "Количественные показатели"),
        *extra,
    ])


def test_comparison_uses_percentages_and_has_no_authorship_score():
    first = base_result("a", 50, 10, [
        Metric("Существительные", "20 · 40 %", "Доля слов", "Морфология", (Span(0, 3),)),
        Metric("Частотные слова: дом", "3", "Частота", "Лексика"),
    ])
    second = base_result("b", 60, 12, [
        Metric("Существительные", "30 · 50 %", "Доля слов", "Морфология", (Span(4, 7),)),
        Metric("Частотные слова: дом", "8", "Частота", "Лексика"),
    ])
    result = compare_results(first, second)
    by_name = {metric.name: metric for metric in result.metrics}
    assert by_name["Существительные"].difference == "10 п. п."
    assert by_name["Существительные"].direction == "выше в тексте 2"
    assert by_name["Слова"].group == "Объём и состав материала"
    assert "Частотные слова: дом" not in by_name
    assert not hasattr(result, "similarity") and not hasattr(result, "authorship_score")


def test_punctuation_counts_are_normalized_by_available_volume():
    first = base_result("a", 100, 10, [
        Metric("Предложения с вопросительным знаком", "2", "Вопросы", "Структура"),
        Metric("Многоточия", "2", "Многоточия", "Структура"),
    ])
    second = base_result("b", 200, 20, [
        Metric("Предложения с вопросительным знаком", "4", "Вопросы", "Структура"),
        Metric("Многоточия", "2", "Многоточия", "Структура"),
    ])
    by_name = {metric.name: metric for metric in compare_results(first, second).metrics}
    assert by_name["Предложения с вопросительным знаком"].difference == "0 на 100 предложений"
    assert by_name["Многоточия"].difference == "10 на 1000 слов"
    assert by_name["Многоточия"].direction == "выше в тексте 1"


def test_stanza_dependency_codes_from_old_cases_are_excluded():
    group = "Служебная синтаксическая разметка Stanza"
    first = base_result("a", 100, 10, [
        Metric("подлежащее (код Stanza: nsubj)", "20 · 20 %", "Служебный код", group),
    ])
    second = base_result("b", 100, 10, [
        Metric("подлежащее (код Stanza: nsubj)", "25 · 25 %", "Служебный код", group),
    ])

    assert not any(item.name.startswith("подлежащее")
                   for item in compare_results(first, second).metrics)


def test_legacy_ud_pos_names_are_merged_before_comparison():
    first = base_result("a", 100, 10, [
        Metric("Глаголы", "20 · 20 %", "Техническая разметка", "Морфология"),
        Metric("Вспомогательные глаголы", "5 · 5 %", "Техническая разметка", "Морфология"),
        Metric("Местоимения", "10 · 10 %", "Техническая разметка", "Морфология"),
        Metric("Определители", "3 · 3 %", "Техническая разметка", "Морфология"),
    ])
    second = base_result("b", 100, 10, [
        Metric("Глаголы", "30 · 30 %", "Техническая разметка", "Морфология"),
        Metric("Вспомогательные глаголы", "2 · 2 %", "Техническая разметка", "Морфология"),
        Metric("Местоимения", "8 · 8 %", "Техническая разметка", "Морфология"),
        Metric("Определители", "4 · 4 %", "Техническая разметка", "Морфология"),
    ])

    metrics = {item.name: item for item in compare_results(first, second).metrics}

    assert metrics["Глаголы"].value_first == "25 · 25 %"
    assert metrics["Местоименные слова"].value_first == "13 · 13 %"
    assert "Вспомогательные глаголы" not in metrics
    assert "Определители" not in metrics


def test_function_words_are_compared_per_thousand_words_with_spans():
    tokens_first = [Token("и", "и", "CCONJ", {}, "cc", 2, 0, 1, Span(0, 1))]
    tokens_second = [Token("и", "и", "CCONJ", {}, "cc", 2, 0, 1, Span(3, 4)),
                     Token("и", "и", "CCONJ", {}, "cc", 2, 0, 2, Span(5, 6))]
    first = base_result("a", 100, 10, tokens=tokens_first)
    second = base_result("b", 100, 10, tokens=tokens_second)
    metric = next(item for item in compare_results(first, second).metrics if item.name == "Служебное слово «и»")
    assert metric.value_first == "1 · 10 на 1000 слов"
    assert metric.value_second == "2 · 20 на 1000 слов"
    assert metric.spans_first == (Span(0, 1),)
    assert "не проверен" in metric.caution


def test_pronouns_and_aux_are_not_called_service_words():
    tokens = [
        Token("я", "я", "PRON", {}, "nsubj", 2, 0, 1, Span(0, 1)),
        Token("был", "быть", "AUX", {}, "cop", 2, 0, 2, Span(2, 5)),
        Token("и", "и", "PART", {}, "cc", 2, 0, 3, Span(6, 7)),
    ]
    first = base_result("a", 100, 10, tokens=tokens)
    second = base_result("b", 100, 10, tokens=tokens)

    names = {item.name for item in compare_results(first, second).metrics}
    assert "Служебное слово «и»" in names
    assert "Служебное слово «я»" not in names
    assert "Служебное слово «был»" not in names


def test_accepted_observations_match_by_fragment_not_only_category():
    first = base_result("a", 10, 2, candidates=[
        candidate("a1", "a", "Орфография", ReviewStatus.ACCEPTED, Span(0, 2), "ЗЫ"),
        candidate("a2", "a", "Пунктуация", ReviewStatus.REJECTED, Span(3, 4), ","),
    ])
    second = base_result("b", 10, 2, candidates=[
        candidate("b1", "b", "Орфография", ReviewStatus.ACCEPTED, Span(5, 7), "зы"),
        candidate("b2", "b", "Орфография", ReviewStatus.ACCEPTED, Span(8, 10), "ваще"),
    ])
    result = compare_results(first, second)
    shared = next(group for group in result.accepted_groups if "ЗЫ" in group.label)
    unique = next(group for group in result.accepted_groups if "ваще" in group.label)
    assert (shared.count_first, shared.count_second, shared.relation) == (1, 1, "В обоих текстах")
    assert shared.basis == "одинаковая словоформа или фрагмент без различия регистра"
    assert unique.relation == "Только в тексте 2"


def test_unknown_word_comparison_keeps_expert_classification():
    first_item = candidate(
        "a1", "a", "Слово не распознано словарём", ReviewStatus.ACCEPTED,
        Span(0, 12), "кодемашине", "MORFOLOGIK_RULE_RU_RU",
    )
    second_item = candidate(
        "b1", "b", "Слово не распознано словарём", ReviewStatus.ACCEPTED,
        Span(0, 12), "Кодемашине", "MORFOLOGIK_RULE_RU_RU",
    )
    first_item.expert_classification = "authorial"
    second_item.expert_classification = "authorial"

    group = compare_results(
        base_result("a", 10, 1, candidates=[first_item]),
        base_result("b", 10, 1, candidates=[second_item]),
    ).accepted_groups[0]

    assert group.label == "Авторское образование или окказионализм: «кодемашине»"
    assert "вне словаря LT" in group.basis


def test_comparison_reports_material_limitations():
    first = base_result("a", 100, 10, candidates=[
        candidate("a", "a", "Грамматика", ReviewStatus.NEW, Span(0, 1), "а"),
    ])
    second = base_result("b", 200, 20)
    limitations = compare_results(first, second).limitations
    assert any("полтора раза" in item for item in limitations)
    assert any("не завершена" in item for item in limitations)
