"""Замер тематического смешения; Stanza и тексты не нужны — только метки."""
import csv
import json

import pytest

from authoroved_core.tools.measure_topic_overlap import (
    measure, overlap, parse_tags, read_pairs, read_tags,
)


def test_tags_are_read_as_a_json_list_and_case_is_ignored():
    assert parse_tags('["Моё", "История"]') == {"моё", "история"}
    assert parse_tags("") == frozenset()
    assert parse_tags("[]") == frozenset()


def test_tags_written_through_commas_are_still_read():
    """Ранние сборки корпуса писали метки не списком."""
    assert parse_tags("моё, история") == {"моё", "история"}
    assert parse_tags("моё; история") == {"моё", "история"}


def test_overlap_is_the_share_of_shared_tags():
    assert overlap(frozenset({"а", "б"}), frozenset({"б", "в"})) == round(1 / 3, 6)
    assert overlap(frozenset({"а"}), frozenset({"а"})) == 1.0
    assert overlap(frozenset({"а"}), frozenset({"б"})) == 0.0


def test_a_pair_without_tags_on_one_side_is_not_counted():
    """Отсутствие меток — не нулевая близость тем, а отсутствие сведений."""
    assert overlap(frozenset(), frozenset({"а"})) is None


def test_identical_topics_within_an_author_are_reported_as_confounding():
    pairs = [{"case_id": f"S{n}", "relation": "SAME",
              "document_a": f"a{n}", "document_b": f"b{n}"} for n in range(3)]
    pairs += [{"case_id": f"D{n}", "relation": "DIFFERENT",
               "document_a": f"c{n}", "document_b": f"d{n}"} for n in range(3)]
    tags = {}
    for n in range(3):
        tags[f"a{n}"] = tags[f"b{n}"] = frozenset({"история"})
        tags[f"c{n}"], tags[f"d{n}"] = frozenset({"история"}), frozenset({"политика"})

    report = measure(pairs, tags)

    assert report["topic_separation"] == 1.0
    assert report["median_overlap_same"] == 1.0
    assert report["median_overlap_different"] == 0.0


def test_equal_topics_in_both_groups_leave_nothing_to_explain():
    pairs = [{"case_id": "S1", "relation": "SAME", "document_a": "a", "document_b": "b"},
             {"case_id": "D1", "relation": "DIFFERENT", "document_a": "c", "document_b": "d"}]
    tags = {key: frozenset({"история", "моё"}) for key in "abcd"}

    report = measure(pairs, tags)

    assert report["topic_separation"] == 0.5
    assert report["above_chance"] is False


def test_pairs_without_tags_are_listed_rather_than_counted_as_zero():
    pairs = [{"case_id": "S1", "relation": "SAME", "document_a": "a", "document_b": "b"},
             {"case_id": "S2", "relation": "SAME", "document_a": "a", "document_b": "нет"}]
    tags = {"a": frozenset({"история"}), "b": frozenset({"история"}), "нет": frozenset()}

    report = measure(pairs, tags)

    assert report["pairs"] == 1
    assert report["pairs_without_tags"] == ["S2"]


def test_report_states_that_it_is_not_an_authorship_conclusion():
    report = measure([], {})

    assert "не оценка авторства" in report["kind"]
    assert "Выводов об авторстве отсюда не следует" in report["measure"]
    assert report["topic_separation"] is None and report["above_chance"] is None


def _corpus(tmp_path, manifest_rows, gold_rows):
    with (tmp_path / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["document_id", "tags"])
        writer.writeheader()
        writer.writerows(manifest_rows)
    with (tmp_path / "cases_gold_private.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["case_id", "document_a", "document_b", "expected_relation"])
        writer.writeheader()
        writer.writerows(gold_rows)
    return tmp_path


def test_tags_and_relations_are_read_from_the_corpus(tmp_path):
    corpus = _corpus(
        tmp_path,
        [{"document_id": "A001_003", "tags": json.dumps(["Моё"], ensure_ascii=False)},
         {"document_id": "A001_005", "tags": json.dumps(["моё", "текст"], ensure_ascii=False)}],
        [{"case_id": "CASE_001", "document_a": "A001_003", "document_b": "A001_005",
          "expected_relation": "SAME"}],
    )

    assert read_tags(corpus)["A001_003"] == {"моё"}
    assert read_pairs(corpus)[0]["relation"] == "SAME"


def test_missing_manifest_is_reported_plainly(tmp_path):
    with pytest.raises(FileNotFoundError, match="манифест"):
        read_tags(tmp_path)


def test_missing_answer_key_is_reported_plainly(tmp_path):
    with pytest.raises(FileNotFoundError, match="эталонный ключ"):
        read_pairs(tmp_path)


def test_manifest_without_a_tags_column_is_refused(tmp_path):
    with (tmp_path / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["document_id"])
        writer.writeheader()
        writer.writerow({"document_id": "A001_003"})

    with pytest.raises(ValueError, match="нет столбца меток"):
        read_tags(tmp_path)
