"""Проверка сухих показателей и высокоточных маркеров."""

from aved import markers, metrics
from aved.nlp import analyze


def test_metrics_basic():
    m = metrics.compute(analyze("Кот спит. Собака бежит быстро по улице."))
    assert m["Слов (знаменательных)"] > 0
    assert m["Предложений"] == 2
    assert "Существительные, %" in m
    assert 0.0 <= m["Лексическое разнообразие (TTR)"] <= 1.0


def test_markers_find_office_stamp_with_examples():
    found = {x["name"]: x for x in markers.scan(
        analyze("Прошу принять меры в соответствии с договорённостью в течение месяца.")
    )}
    assert "Штампы официально-делового стиля" in found
    assert found["Штампы официально-делового стиля"]["examples"]  # есть примеры


def test_markers_empty_on_neutral_text():
    names = {x["name"] for x in markers.scan(analyze("Кот спит на тёплом окне."))}
    assert "Обсценная лексика" not in names
