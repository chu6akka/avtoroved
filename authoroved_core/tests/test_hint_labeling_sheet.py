"""Лист разметки нераспознанных словоформ; ни модель, ни LanguageTool не нужны."""
import csv

import pytest

from authoroved_core.core.models import AnalysisResult, Candidate, Span, Token
from authoroved_core.core.word_evidence import FrequencyDictionary
from authoroved_core.tools.build_hint_labeling_sheet import (
    FIELDS, build_rows, context_line, one_line, write_legend, write_sheet,
)


class FakeAnalysis:
    """Подменяет разбор: отдаёт заранее заданных кандидатов LanguageTool."""

    def __init__(self, by_document):
        self.by_document = by_document

    def analyze(self, document):
        candidates, tokens = self.by_document.get(document.id, ([], []))
        return AnalysisResult(
            document_id=document.id, tokens=list(tokens), metrics=[],
            candidates=list(candidates), metadata={}, errors=[],
        )


def unknown(form, text, replacements=()):
    start = text.index(form)
    return Candidate(
        f"c-{form}", "d1", "Слово не распознано словарём", "Слово не распознано словарём",
        "пояснение", form, Span(start, start + len(form)),
        "MORFOLOGIK_RULE_RU_RU", tuple(replacements),
    )


def punctuation(text):
    return Candidate(
        "c-punct", "d1", "Пунктуация", "Пунктуация", "пояснение", ",",
        Span(text.index(","), text.index(",") + 1), "COMMA_RULE",
    )


def dictionary():
    return FrequencyDictionary({"беда": [1184, 93.45, "noun"]})


def test_context_marks_the_word_and_stays_on_one_line():
    text = "Начало.\nОн написал\r\nслово пикабушник в тексте.\nКонец."
    start = text.index("пикабушник")

    line = context_line(text, start, start + len("пикабушник"))

    assert "[пикабушник]" in line
    assert "\n" not in line and "\r" not in line


def test_one_line_collapses_any_whitespace():
    assert one_line("а\nб\r\n  в\t г") == "а б в г"


def test_same_word_from_several_documents_is_one_row():
    """Иначе «пикабушник» занял бы десяток строк подряд."""
    first = "Первый текст, слово пикабушник тут."
    second = "Второй текст, снова пикабушник и ещё пикабушник."
    documents = [("CASE_001/TEXT_A.txt", first), ("CASE_002/TEXT_A.txt", second)]
    service = FakeAnalysis({
        "CASE_001/TEXT_A.txt": ([unknown("пикабушник", first)], []),
        "CASE_002/TEXT_A.txt": ([unknown("пикабушник", second)], []),
    })

    rows = build_rows(documents, service, dictionary())

    assert len(rows) == 1
    assert rows[0]["word"] == "пикабушник"
    assert rows[0]["occurrences"] == 2 and rows[0]["documents"] == 2


def test_only_unknown_word_candidates_reach_the_sheet():
    text = "Текст, где есть пикабушник и запятая."
    documents = [("CASE_001/TEXT_A.txt", text)]
    service = FakeAnalysis({
        "CASE_001/TEXT_A.txt": ([unknown("пикабушник", text), punctuation(text)], []),
    })

    rows = build_rows(documents, service, dictionary())

    assert [row["word"] for row in rows] == ["пикабушник"]


def test_rows_are_ordered_by_word():
    """Автоматических вердиктов нет, поэтому и особого порядка не требуется."""
    text = "Тут беда и пикабушник вместе."
    documents = [("CASE_001/TEXT_A.txt", text)]
    service = FakeAnalysis({
        "CASE_001/TEXT_A.txt": ([unknown("пикабушник", text), unknown("беда", text)], []),
    })

    rows = build_rows(documents, service, dictionary())

    assert [row["word"] for row in rows] == ["беда", "пикабушник"]
    assert "deterministic" not in rows[0]


def test_lemma_from_stanza_reaches_the_frequency_column():
    """Без леммы столбец заполнялся бы реже, чем в самой программе."""
    text = "Случилась беды какая-то странная."
    start = text.index("беды")
    documents = [("CASE_001/TEXT_A.txt", text)]
    tokens = [Token("беды", "беда", "NOUN", {}, "root", 0, 0, 0, Span(start, start + 4))]
    service = FakeAnalysis({"CASE_001/TEXT_A.txt": ([unknown("беды", text)], tokens)})

    rows = build_rows(documents, service, dictionary())

    assert rows[0]["corpus_ipm"] == "93.45"


def test_limit_caps_the_sheet(tmp_path):
    text = "Слова пикабушник, инфоцыганщина и беда тут."
    documents = [("CASE_001/TEXT_A.txt", text)]
    service = FakeAnalysis({"CASE_001/TEXT_A.txt": (
        [unknown("пикабушник", text), unknown("инфоцыганщина", text), unknown("беда", text)], [],
    )})

    rows = build_rows(documents, service, dictionary(), limit=2)

    assert len(rows) == 2
    assert [row["row_id"] for row in rows] == ["W0001", "W0002"]


def test_written_sheet_is_readable_and_has_empty_expert_columns(tmp_path):
    text = "Текст со словом пикабушник внутри строки."
    documents = [("CASE_001/TEXT_A.txt", text)]
    service = FakeAnalysis({"CASE_001/TEXT_A.txt": ([unknown("пикабушник", text)], [])})
    rows = build_rows(documents, service, dictionary())
    path = tmp_path / "sheet.csv"

    write_sheet(path, rows)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        written = list(csv.DictReader(handle))

    assert list(written[0]) == FIELDS
    assert written[0]["gold_label"] == "" and written[0]["note"] == ""
    assert written[0]["row_id"] == "W0001"
    # Читаемость: ни одна ячейка не разрывает строку в таблице.
    for row in written:
        for value in row.values():
            assert "\n" not in value and "\r" not in value


def test_legend_lists_every_allowed_label(tmp_path):
    from authoroved_core.core.lt_grouping import UNKNOWN_WORD_CLASSIFICATIONS

    path = tmp_path / "легенда.txt"
    write_legend(path)
    written = path.read_text(encoding="utf-8")

    for key, title in UNKNOWN_WORD_CLASSIFICATIONS:
        assert key in written and title in written
    assert "Оставьте пустым, если не уверены" in written
