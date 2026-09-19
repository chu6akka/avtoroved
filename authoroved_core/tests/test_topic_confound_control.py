"""Пригодность признаков на парах, где тема групп не различает."""
import json

import pytest

from authoroved_core.tools.control_topic_confound import (
    control, load_report, residual_topic_separation, select_topic_neutral,
)


def _features(cases):
    return {"per_case": [{"case_id": case_id, "relation": relation,
                          "distances": distances}
                         for case_id, relation, distances in cases],
            "by_feature": {}}


def _topics(overlaps):
    return {"topic_separation": 0.78,
            "per_case": [{"case_id": case_id, "overlap": value}
                         for case_id, value in overlaps.items()]}


def test_only_pairs_without_shared_tags_are_kept():
    features = _features([("C1", "SAME", {"LEX_001": 1.0}),
                          ("C2", "SAME", {"LEX_001": 2.0}),
                          ("C3", "DIFFERENT", {"LEX_001": 9.0})])

    kept, unknown = select_topic_neutral(features, {"C1": 0.0, "C2": 0.5, "C3": 0.0})

    assert [case["case_id"] for case in kept] == ["C1", "C3"]
    assert unknown == []


def test_a_pair_with_unknown_tags_is_excluded_rather_than_assumed_neutral():
    """Про пару без меток неизвестно ничего; нейтральной она не является."""
    features = _features([("C1", "SAME", {"LEX_001": 1.0}),
                          ("C2", "SAME", {"LEX_001": 2.0})])

    kept, unknown = select_topic_neutral(features, {"C1": 0.0})

    assert [case["case_id"] for case in kept] == ["C1"]
    assert unknown == ["C2"]


def test_a_wider_cutoff_keeps_more_pairs():
    features = _features([("C1", "SAME", {"LEX_001": 1.0}),
                          ("C2", "SAME", {"LEX_001": 2.0})])

    kept, _ = select_topic_neutral(features, {"C1": 0.0, "C2": 0.2}, max_overlap=0.25)

    assert [case["case_id"] for case in kept] == ["C1", "C2"]


def test_topic_stops_separating_the_groups_after_selection():
    """Ради этого отбор и делается: на подвыборке тема групп не различает."""
    kept = [{"case_id": "C1", "relation": "SAME"},
            {"case_id": "C2", "relation": "DIFFERENT"}]

    assert residual_topic_separation(kept, {"C1": 0.0, "C2": 0.0}) == 0.5


def test_a_feature_that_survived_the_selection_is_marked_above_chance():
    same = [("S%d" % n, "SAME", {"LEX_001": float(n)}) for n in range(12)]
    different = [("D%d" % n, "DIFFERENT", {"LEX_001": n + 20.0}) for n in range(12)]
    overlaps = {case_id: 0.0 for case_id, _, _ in same + different}

    report = control(_features(same + different), _topics(overlaps))

    row = report["by_feature"]["LEX_001"]
    assert row["separation_topic_neutral"] == 1.0
    assert row["above_chance_topic_neutral"] is True
    assert report["topic_separation_before"] == 0.78
    assert report["topic_separation_after"] == 0.5
    assert report["pairs_kept"] == 24 and report["same_pairs"] == 12


def test_a_separation_the_smaller_sample_cannot_support_is_marked():
    """Отбор уменьшает выборку, и порог растёт — это надо видеть."""
    same = [("S%d" % n, "SAME", {"LEX_001": float(n)}) for n in range(6)]
    different = [("D%d" % n, "DIFFERENT", {"LEX_001": n + 1.0}) for n in range(6)]
    overlaps = {case_id: 0.0 for case_id, _, _ in same + different}

    report = control(_features(same + different), _topics(overlaps))

    row = report["by_feature"]["LEX_001"]
    assert row["separation_topic_neutral"] < report["significance_threshold"]
    assert row["above_chance_topic_neutral"] is False


def test_the_value_before_selection_is_kept_beside_the_new_one():
    features = _features([("C1", "SAME", {"LEX_001": 1.0}),
                          ("C2", "DIFFERENT", {"LEX_001": 9.0})])
    features["by_feature"] = {"LEX_001": {"separation": 0.663, "above_chance": True}}

    report = control(features, _topics({"C1": 0.0, "C2": 0.0}))

    assert report["by_feature"]["LEX_001"]["separation_all_pairs"] == 0.663
    assert report["by_feature"]["LEX_001"]["above_chance_all_pairs"] is True


def test_a_summary_without_per_pair_data_is_refused(tmp_path):
    """Сводка прогона для этого не годится: нужны расстояния по парам."""
    path = tmp_path / "summary.json"
    path.write_text(json.dumps({"by_feature": {}}), encoding="utf-8")

    with pytest.raises(ValueError, match="нет разбора по парам"):
        load_report(path, "проверки признаков")


def test_a_missing_report_is_reported_plainly(tmp_path):
    with pytest.raises(FileNotFoundError, match="замера меток"):
        load_report(tmp_path / "нет.json", "замера меток")
