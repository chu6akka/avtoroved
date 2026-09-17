"""Построение листа для ручной разметки эталона; модель не запускается."""
import csv

import pytest

from authoroved_core.tools.build_labeling_sheet import (
    FIELDS, build_rows, orthographic_signals, split_sentences, write_sheet,
)


def test_sentence_spans_point_back_into_the_source_text():
    text = ("Ну что, дааа, договорились. Он написал ghbdtn в раскладке! "
            "Ну и что!!! Обычное предложение здесь.")

    pieces = split_sentences(text)

    assert [text[start:end] for start, end, _ in pieces] == [item[2] for item in pieces]
    assert len(pieces) == 4


def test_sentence_split_survives_crlf():
    text = "Первое предложение тут.\r\nВторое предложение тут."

    pieces = split_sentences(text)

    assert [item[2] for item in pieces] == [
        "Первое предложение тут.", "Второе предложение тут.",
    ]


@pytest.mark.parametrize("sentence,expected", [
    ("Ну что, дааа, договорились с ними.", ("тройная буква",)),
    ("Он написал ghbdtn в неверной раскладке.", ("латиница",)),
    ("Ну и что!!! Я предупреждал.", ("повтор знака",)),
    ("Совершенно обычное предложение без сигналов.", ()),
])
def test_signals_are_deterministic_and_model_free(sentence, expected):
    assert orthographic_signals(sentence) == expected


def _corpus(count=60):
    documents = []
    for number in range(count):
        plain = f"Совершенно обычное предложение номер {number} без сигналов. "
        odd = f"А тут он сказал дааа{'а' * (number % 3)} и ушёл домой. "
        documents.append((f"CASE_{number:03d}/TEXT_A.txt", plain * 2 + odd))
    return documents


def test_sheet_keeps_both_strata_and_never_repeats_a_sentence():
    rows, total, enriched_total = build_rows(_corpus(), random_size=20, enriched_size=10)

    assert total > 0 and enriched_total > 0
    assert sum(row["stratum"] == "random" for row in rows) == 20
    assert sum(row["stratum"] == "enriched" for row in rows) == 10
    keys = [(row["document_id"], row["sentence_index"]) for row in rows]
    assert len(keys) == len(set(keys))
    assert [row["row_id"] for row in rows] == [f"R{n:04d}" for n in range(1, 31)]


def test_enriched_stratum_carries_signals_and_random_one_is_not_filtered():
    rows, _, _ = build_rows(_corpus(), random_size=20, enriched_size=10)

    assert all(row["signals"] for row in rows if row["stratum"] == "enriched")
    # Случайная страта не отбирается по сигналам — иначе эталон унаследует
    # слепые зоны отбора и пропуски останутся невидимыми.
    assert any(not row["signals"] for row in rows if row["stratum"] == "random")


def test_sheet_is_reproducible_for_the_same_corpus():
    first, _, _ = build_rows(_corpus(), random_size=20, enriched_size=10)
    second, _, _ = build_rows(_corpus(), random_size=20, enriched_size=10)

    assert [row["sentence"] for row in first] == [row["sentence"] for row in second]


def test_short_sentences_are_left_out():
    documents = [("CASE_001/TEXT_A.txt", "Да. Нет. Совсем короткое предложение тут есть.")]

    rows, total, _ = build_rows(documents, random_size=5, enriched_size=0, min_words=4)

    assert total == 1
    assert [row["sentence"] for row in rows] == ["Совсем короткое предложение тут есть."]


def test_written_sheet_has_empty_columns_for_the_expert(tmp_path):
    rows, _, _ = build_rows(_corpus(), random_size=5, enriched_size=5)
    path = tmp_path / "sheet.csv"

    write_sheet(path, rows)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        written = list(csv.DictReader(handle))

    assert list(written[0]) == FIELDS
    assert all(row["gold_features"] == "" and row["note"] == "" for row in written)
