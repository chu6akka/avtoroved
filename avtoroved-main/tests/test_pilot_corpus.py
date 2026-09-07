from __future__ import annotations

import csv
from pathlib import Path

import pytest

from pilot_corpus.filtering import (
    assess_post,
    classify_content,
    count_words,
    exact_text_sha256,
    simhash_distance,
    text_simhash,
)
from pilot_corpus.scanner import _write_csv


def _row(text: str, **overrides):
    row = {
        "id": 1,
        "author_id": 10,
        "username": "writer",
        "title": "Личная история",
        "text_markdown": text,
        "timestamp": 1577836800,
        "url": "https://pikabu.ru/story/1",
        "tags": ["Моё", "Истории из жизни"],
    }
    row.update(overrides)
    return row


def test_word_counter_keeps_hyphenated_word_together():
    assert count_words("По-моему, это чья-то история.") == 4


def test_clean_russian_post_is_candidate_without_changing_text():
    text = " ".join(["Однажды я рассказал эту домашнюю историю подробно."] * 50)
    result = assess_post(_row(text))
    assert result.status == "candidate"
    assert result.word_count == 350
    assert result.date == "2020-01-01"
    assert result.content_type == "narrative"
    assert result.priority_score > 0
    assert _row(text)["text_markdown"] == text


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"author_id": None}, "missing_author_id"),
        ({"text_markdown": "короткий текст"}, "below_300_words"),
        ({"text_markdown": "english " * 350}, "not_predominantly_russian"),
        ({"tags": ["Новости"]}, "excluded_tag:новости"),
    ],
)
def test_hard_filters_preserve_rejection_reason(overrides, reason):
    text = " ".join(["Я подробно описываю случай из своей жизни."] * 50)
    result = assess_post(_row(text, **overrides))
    assert result.status == "rejected"
    assert reason in result.rejection_reasons


def test_risky_translation_is_not_auto_selected():
    text = " ".join(["Я подробно пересказываю интересную историю."] * 60)
    result = assess_post(_row(text, title="Перевод статьи", tags=["Моё"]))
    assert result.status == "review"
    assert "possible_translation" in result.flags
    assert "suspicious_authorship" in result.flags


def test_organizational_looking_username_requires_review():
    text = " ".join(["Я подробно описываю личную историю из своей жизни."] * 45)
    result = assess_post(_row(text, username="ExampleNews"))
    assert result.status == "review"
    assert "commercial_account" in result.flags


def test_genre_is_metadata_only():
    text = "Считаю, что это важный вывод. " * 60
    assert classify_content(text) == "opinion"
    assert assess_post(_row(text)).status == "candidate"


def test_duplicate_hash_and_simhash_are_deterministic():
    left = "Это самостоятельный текст автора. " * 20
    right = "  ЭТО самостоятельный   текст автора! " * 20
    assert exact_text_sha256(left) == exact_text_sha256(left)
    assert text_simhash(left) == text_simhash(left)
    assert simhash_distance(text_simhash(left), text_simhash(right)) <= 3


def test_csv_writer_is_utf8_bom_and_atomic(tmp_path: Path):
    target = tmp_path / "items.csv"
    _write_csv(target, ["id", "title"], [{"id": 1, "title": "История"}])
    assert target.read_bytes().startswith(b"\xef\xbb\xbf")
    with target.open(encoding="utf-8-sig", newline="") as handle:
        assert list(csv.DictReader(handle))[0]["title"] == "История"
    assert not target.with_suffix(".csv.new").exists()
