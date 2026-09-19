"""Проверка пригодности AUTO-признаков на слепых парах; Stanza не запускается."""
import csv

import pytest

from authoroved_core.core.feature_models import (
    Applicability, FeatureObservation, SourceReference,
)
from authoroved_core.core.models import AnalysisResult
from authoroved_core.tools.validate_features_on_blind_pairs import (
    feature_distance, flatten_numeric, observations_by_feature, read_cases,
    family_threshold, run, separation, significance_threshold, summarize,
)


def test_scalar_and_distribution_values_flatten_the_same_way():
    assert flatten_numeric({"mattr": 0.8}) == {"mattr": 0.8}
    assert flatten_numeric({"per_1000_words": {"и": 30.0, "в": 20.0}}) == {
        "per_1000_words.и": 30.0, "per_1000_words.в": 20.0,
    }
    # Нечисловые составляющие в расстояние не входят.
    assert flatten_numeric({"note": "текст", "value": 2}) == {"value": 2.0}


def test_distance_over_a_distribution_counts_missing_forms_as_zero():
    """Словоформа, которой нет во втором тексте, расхождением является."""
    first = {"p": {"и": 30.0, "в": 20.0}}
    second = {"p": {"и": 25.0, "на": 5.0}}

    assert feature_distance(first, second) == 5.0 + 20.0 + 5.0


def test_distance_is_none_when_a_side_is_missing():
    assert feature_distance(None, {"mattr": 0.5}) is None
    assert feature_distance({}, {}) is None


@pytest.mark.parametrize("same,different,expected", [
    ([1.0, 2.0], [8.0, 9.0], 1.0),
    ([8.0, 9.0], [1.0, 2.0], 0.0),
    ([1.0, 2.0], [1.0, 2.0], 0.5),
    ([], [1.0], None),
])
def test_separation_is_half_when_the_feature_carries_nothing(same, different, expected):
    assert separation(same, different) == expected


def test_separation_counts_ties_as_half():
    assert separation([1.0], [1.0]) == 0.5
    assert separation([1.0, 1.0], [1.0, 3.0]) == 0.75


def test_ten_pairs_against_ten_cannot_show_anything_below_three_quarters():
    """Порог первого прогона: на 10 против 10 ниже 0,76 всё объяснимо случаем.

    В Pilot 01 наибольшее разделение было 0,73 — то есть от случайного
    разброса не отличалось ни одно значение, и это была не таблица признаков,
    а шум. Порог считается здесь, чтобы этого нельзя было не заметить.
    """
    assert significance_threshold(10, 10) == 0.7593
    assert significance_threshold(8, 10) == 0.7757


def test_eighty_pairs_against_eighty_lower_the_threshold_to_point_five_nine():
    assert significance_threshold(80, 80) == 0.5897


def test_the_strict_threshold_accounts_for_ten_features_tested_at_once():
    """При десяти проверках одиночного порога для суждения о таблице мало."""
    assert family_threshold(12, 37, 1) == significance_threshold(12, 37)
    assert family_threshold(12, 37, 10) == 0.7719
    assert family_threshold(12, 37, 10) > significance_threshold(12, 37)


def test_threshold_is_absent_without_both_groups():
    assert significance_threshold(0, 10) is None
    assert significance_threshold(10, 0) is None
    assert family_threshold(0, 10, 5) is None
    assert family_threshold(10, 10, 0) is None


def test_summary_marks_a_value_the_sample_cannot_support():
    """Разделение 0,72 на 10 парах против 10 — ниже порога, а не признак.

    Ровно так выглядел лучший результат Pilot 01 (0,73 у MOR_003).
    """
    cases = [{"case_id": f"S{n}", "relation": "SAME", "distances": {"MOR_003": float(n)}}
             for n in range(10)]
    cases += [{"case_id": f"D{n}", "relation": "DIFFERENT", "distances": {"MOR_003": n + 2.6}}
              for n in range(10)]

    summary = summarize(cases)["MOR_003"]

    assert summary["separation"] == 0.72
    assert summary["significance_threshold"] == 0.7593
    assert summary["above_chance"] is False


def test_summary_orders_features_by_separation():
    cases = [
        {"case_id": "C1", "relation": "SAME", "distances": {"LEX_005": 0.1, "PUN_001": 5.0}},
        {"case_id": "C2", "relation": "SAME", "distances": {"LEX_005": 0.2, "PUN_001": 1.0}},
        {"case_id": "C3", "relation": "DIFFERENT", "distances": {"LEX_005": 9.0, "PUN_001": 3.0}},
    ]

    summary = summarize(cases)

    assert list(summary) == ["LEX_005", "PUN_001"]
    assert summary["LEX_005"]["separation"] == 1.0
    assert summary["LEX_005"]["same_pairs"] == 2 and summary["LEX_005"]["different_pairs"] == 1
    assert summary["LEX_005"]["median_same"] == 0.15


def test_insufficient_observations_are_left_out():
    source = (SourceReference("Методика", "с. 1", "контекст", "checked"),)
    result = AnalysisResult(
        document_id="d1",
        feature_observations=[
            FeatureObservation("LEX_005", {}, {"mattr": 0.7}, (),
                               Applicability.APPLICABLE, (), "auto-0.1.0", source),
            FeatureObservation("SYN_001", {}, None, (),
                               Applicability.INSUFFICIENT_DATA, ("мало слов",), "auto-0.1.0", source),
        ],
    )

    assert observations_by_feature(result) == {"LEX_005": {"mattr": 0.7}}


def _corpus(tmp_path, rows, public=None):
    """Ключ и публичный список: в ключе стоят идентификаторы, пути — в списке."""
    with (tmp_path / "cases_gold_private.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["case_id", "document_a", "document_b", "expected_relation"])
        writer.writeheader()
        writer.writerows(rows)
    public = public if public is not None else [
        {"case_id": row["case_id"],
         "document_a": f"blind/{row['case_id']}/TEXT_A.txt",
         "document_b": f"blind/{row['case_id']}/TEXT_B.txt"}
        for row in rows
    ]
    with (tmp_path / "cases_public.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "document_a", "document_b"])
        writer.writeheader()
        writer.writerows(public)
    return tmp_path


def test_paths_come_from_the_public_list_and_relation_from_the_key(tmp_path):
    """В ключе в столбцах document_* стоят идентификаторы, а не пути.

    Первый прогон открывал по ним файлы и не разобрал ни одной из 20 пар.
    """
    corpus = _corpus(tmp_path, [
        {"case_id": "CASE_001", "document_a": "A001_003", "document_b": "A001_005",
         "expected_relation": "SAME"},
        {"case_id": "CASE_002", "document_a": "A002_001", "document_b": "A007_004",
         "expected_relation": "DIFFERENT"},
    ])

    cases = read_cases(corpus)

    assert [item["relation"] for item in cases] == ["SAME", "DIFFERENT"]
    assert cases[0]["document_a"] == "blind/CASE_001/TEXT_A.txt"
    assert cases[1]["document_b"] == "blind/CASE_002/TEXT_B.txt"


def test_missing_public_list_is_reported_plainly(tmp_path):
    _corpus(tmp_path, [{"case_id": "CASE_001", "document_a": "A001_003",
                        "document_b": "A001_005", "expected_relation": "SAME"}])
    (tmp_path / "cases_public.csv").unlink()

    with pytest.raises(FileNotFoundError, match="список пар"):
        read_cases(tmp_path)


def test_case_absent_from_the_public_list_is_refused(tmp_path):
    corpus = _corpus(
        tmp_path,
        [{"case_id": "CASE_001", "document_a": "A001_003", "document_b": "A001_005",
          "expected_relation": "SAME"}],
        public=[],
    )

    with pytest.raises(ValueError, match="отсутствует в списке пар"):
        read_cases(corpus)


def test_missing_answer_key_is_reported_plainly(tmp_path):
    with pytest.raises(FileNotFoundError, match="эталонный ключ"):
        read_cases(tmp_path)


def test_unknown_relation_is_refused(tmp_path):
    corpus = _corpus(tmp_path, [{"case_id": "CASE_001", "document_a": "A001_003",
                                 "document_b": "A001_005",
                                 "expected_relation": "МОЖЕТ БЫТЬ"}])

    with pytest.raises(ValueError, match="Неизвестное отношение"):
        read_cases(corpus)


def test_a_broken_pair_does_not_stop_the_whole_check(tmp_path):
    """Одна упавшая пара не должна обесценивать прогон по остальным."""
    class Failing:
        def analyze(self, document):
            raise RuntimeError("разбор не удался")

    (tmp_path / "a.txt").write_text("Текст первый.", encoding="utf-8")
    (tmp_path / "b.txt").write_text("Текст второй.", encoding="utf-8")
    cases = [{"case_id": "CASE_001", "relation": "SAME",
              "document_a": "a.txt", "document_b": "b.txt"}]

    report = run(tmp_path, Failing(), cases)

    assert report["cases"] == 0
    assert report["failures"][0]["case_id"] == "CASE_001"
    assert "разбор не удался" in report["failures"][0]["error"]


def test_a_missing_text_is_reported_as_a_failed_pair(tmp_path):
    class Idle:
        def analyze(self, document):
            return AnalysisResult(document_id=document.id)

    cases = [{"case_id": "CASE_001", "relation": "SAME",
              "document_a": "нет.txt", "document_b": "нет.txt"}]

    report = run(tmp_path, Idle(), cases)

    assert report["cases"] == 0 and len(report["failures"]) == 1
    assert "FileNotFoundError" in report["failures"][0]["error"]


def test_report_states_that_it_is_not_an_authorship_conclusion():
    report = run(None, object(), [])

    assert "не оценка авторства" in report["kind"]
    assert "Порогов отсюда не выводится" in report["measure"]
