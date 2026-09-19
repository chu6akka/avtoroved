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


def test_author_cap_allows_a_larger_sample():
    """Потолок в 15 авторов делал невозможной статистически значимую проверку.

    При десяти авторах мера разделения признаков отличима от случайной лишь
    выше 0,76; наблюдаемые значения до неё не дотягивали.
    """
    import inspect

    from pilot_corpus.finalize import MAX_AUTHORS, finalize_approved_corpus

    assert MAX_AUTHORS >= 60
    signature = inspect.signature(finalize_approved_corpus)
    assert "case_author_count" in signature.parameters
    # Прежнее поведение сохраняется: Pilot 01 остаётся воспроизводимым.
    assert signature.parameters["case_author_count"].default is None


def test_author_count_outside_the_range_is_refused(tmp_path):
    from pilot_corpus.finalize import MAX_AUTHORS, finalize_approved_corpus

    for value in (9, MAX_AUTHORS + 1):
        with pytest.raises(ValueError, match="от 10 до"):
            finalize_approved_corpus(tmp_path, value)


def test_cases_cannot_use_more_authors_than_selected(tmp_path):
    from pilot_corpus.finalize import finalize_approved_corpus

    with pytest.raises(ValueError, match="не может быть больше"):
        finalize_approved_corpus(tmp_path, 20, case_author_count=25)

    with pytest.raises(ValueError, match="не может быть больше"):
        finalize_approved_corpus(tmp_path, 20, case_author_count=1)


def test_one_same_author_pair_per_author():
    """Пары от одного автора не независимы, поэтому с каждого берётся одна."""
    import inspect

    from pilot_corpus.finalize import _write_cases

    source = inspect.getsource(_write_cases)
    # Пара «тот же автор» строится из первых двух текстов, а не из всех сочетаний.
    assert "docs[0], docs[1]" in source
    assert "combinations" not in source


def _memory_scan_state(authors):
    """База сканирования в памяти: authors — {id: (ник, сколько постов с ником)}."""
    import sqlite3

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE posts (
            source_post_id TEXT PRIMARY KEY, source_author_id TEXT, username TEXT,
            text_markdown TEXT, status TEXT, date TEXT, priority_score REAL,
            word_count INTEGER, tags TEXT)"""
    )
    for author_id, (username, self_named) in authors.items():
        for index in range(6):
            text = (f"Текст номер {index} автора, тут упомянут {username}."
                    if index < self_named else f"Обычный текст номер {index}.")
            connection.execute(
                "INSERT INTO posts VALUES (?,?,?,?,?,?,?,?,?)",
                (f"{author_id}_{index}", author_id, username, text, "candidate",
                 "2019-05-01", 1.0, 500, '["моё"]'),
            )
    connection.commit()
    return connection


def test_author_without_six_blind_safe_texts_is_skipped_not_fatal():
    """Пост, где автор назван своим ником, раскрыл бы слепое соответствие.

    Такой текст выбрасывается, и автор мог пройти отбор по числу чистых
    постов, но не дать шести пригодных. Прежде это роняло сборку целиком.
    """
    from pilot_corpus.finalize import _authors_with_six_blind_safe

    connection = _memory_scan_state({
        "1000": ("ivanov", 0),      # все шесть пригодны
        "1908276": ("petrov", 2),   # два текста называют автора
        "1002": ("sidorov", 0),
    })

    # Просим всех, чтобы обход дошёл до непригодного независимо от порядка.
    selected, skipped = _authors_with_six_blind_safe(connection, 3)

    assert sorted(str(row["source_author_id"]) for row in selected) == ["1000", "1002"]
    assert skipped == ["1908276"]
    # Сборка не падает: непригодный автор просто не попал в выборку.
    assert len(selected) == 2


def test_shortfall_names_how_many_were_skipped():
    from pilot_corpus.finalize import _authors_with_six_blind_safe

    connection = _memory_scan_state({"1000": ("ivanov", 0), "1001": ("petrov", 1)})

    selected, skipped = _authors_with_six_blind_safe(connection, 5)

    assert len(selected) == 1 and skipped == ["1001"]


def test_short_username_does_not_disqualify_a_text():
    """Ник короче четырёх знаков слишком част в обычных словах."""
    from pilot_corpus.finalize import _authors_with_six_blind_safe

    connection = _memory_scan_state({"1000": ("ох", 6)})

    selected, _ = _authors_with_six_blind_safe(connection, 1)

    assert len(selected) == 1


def test_finalize_creates_the_directories_it_writes_into(tmp_path):
    """Каталог отчётов раньше доставался от шага сканирования.

    В свежей папке сборка падала на последнем шаге, уже разложив все тексты:
    каталог reports отсутствовал, а код его не создавал.
    """
    import inspect

    from pilot_corpus.finalize import finalize_approved_corpus

    source = inspect.getsource(finalize_approved_corpus)
    assert '(root / "reports").mkdir(parents=True, exist_ok=True)' in source
    # Каталог создаётся до открытия базы, то есть до любой длительной работы.
    assert source.index('"reports"') < source.index("_connect(database)")
