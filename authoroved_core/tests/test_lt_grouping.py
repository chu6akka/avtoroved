from authoroved_core.core.lt_grouping import candidate_group_key, group_candidates
from authoroved_core.core.models import Candidate, ReviewStatus, Span


def item(identifier, category, rule="RULE", status=ReviewStatus.NEW):
    return Candidate(identifier, "d", category, category, "Проверить", "слово",
                     Span(0, 5), rule, status=status)


def test_unknown_dictionary_form_is_separate_from_spelling():
    unknown = item("u", "Слово не распознано словарём", "MORFOLOGIK_RULE_RU_RU")
    spelling = item("s", "Орфография")

    assert candidate_group_key(unknown) == "unknown_words"
    assert candidate_group_key(spelling) == "spelling"


def test_groups_have_stable_order_and_review_counts():
    candidates = [
        item("p", "Пунктуация", status=ReviewStatus.REJECTED),
        item("u", "Слово не распознано словарём", "MORFOLOGIK_RULE_RU_RU",
             ReviewStatus.ACCEPTED),
        item("g", "Грамматика"),
    ]

    groups = group_candidates(candidates)

    assert [group.definition.key for group in groups] == [
        "unknown_words", "grammar", "punctuation",
    ]
    assert (groups[0].new, groups[0].accepted, groups[0].rejected) == (0, 1, 0)
    assert "не доказательство ошибки" in groups[0].definition.description
