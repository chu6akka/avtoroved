from authoroved_core.core.models import Span
from authoroved_core.core.obscene import find_obscene, obscene_root
from authoroved_core.metrics.basic import obscene_metric
from authoroved_core.nlp.languagetool_adapter import candidates_from_matches, is_paragraph_indent

OBSCENE = ("хуй нахуй похуй нихуя хуёвый охуенно пизда спиздил пиздец ебать ёбаный заебал "
           "выёбываться съебаться уебок долбоёб ебучем ебаной еб ебло еблан наебнулся отъебись "
           "бля блять блядь выблядок проебал поебень доебался").split()
# Обычные слова с теми же сочетаниями букв.
ORDINARY = ("небо хлеб учеба себе требовать ребёнок лебедь колебаться служебный небоскреб "
            "тихую сухую плохую лихую глухую страхуй застрахуюсь углублять ослаблять употреблять "
            "оскорблять корабля худой хула художник хурма хутор зебра вебинар погреб гребень "
            "Глеб учебник ребята бляшка бляха").split()


def test_all_four_roots_are_recognized():
    assert [word for word in OBSCENE if obscene_root(word) is None] == []


def test_ordinary_words_are_not_obscene():
    assert [word for word in ORDINARY if obscene_root(word)] == []


def test_obscene_metric_counts_words_with_spans():
    text = "Под небом, бля, в ебаной конторе тихую жизнь не найти."
    metric = obscene_metric(text)

    assert metric.value == "2"
    assert [text[span.start:span.end] for span in metric.spans] == ["бля", "ебаной"]
    assert [item.root for item in find_obscene(text)] == ["бляд", "еб"]


def test_paragraph_indent_is_not_a_repeated_space_candidate():
    text = "Первый абзац.\n\xa0 \xa0 Второй  абзац."
    indent = Span(14, 18)
    inner = Span(text.index("  "), text.index("  ") + 2)
    assert is_paragraph_indent(text, indent)
    assert not is_paragraph_indent(text, inner)
    matches = [
        {"offset": 14, "length": 4, "rule": {"id": "WHITESPACE_RULE", "category": {"id": "TYPOGRAPHY"}},
         "message": "Повтор пробела", "replacements": [{"value": " "}]},
        {"offset": inner.start, "length": 2, "rule": {"id": "WHITESPACE_RULE", "category": {"id": "TYPOGRAPHY"}},
         "message": "Повтор пробела", "replacements": [{"value": " "}]},
    ]
    kept = candidates_from_matches("d", text, matches)
    assert [candidate.span for candidate in kept] == [inner]
