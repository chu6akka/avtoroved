"""DEVELOPMENT-only calibration helpers for shadow StyleEngineV2.

The optimizer accepts records explicitly marked ``CALIBRATION`` and rejects an
``INTERNAL_HOLDOUT`` record before inspecting its labels or scores.  This is a
small engineering evaluation utility, not corpus or scientific validation.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence

from analyzer.semantic_layers.contracts import StyleScoreV2
from analyzer.semantic_layers.style_detectors import STYLE_LABELS
from analyzer.semantic_layers.style_selection import (
    StyleSelectionParameters,
    select_style_scores,
)


CALIBRATION_PARTITION = "CALIBRATION"
HOLDOUT_PARTITION = "INTERNAL_HOLDOUT"
STYLE_SPLIT_SEED = 20260829
STYLE_HOLDOUT_SIZE = 11


@dataclass(frozen=True)
class StyleCalibrationRecord:
    fixture_id: str
    expected_styles: tuple[str, ...]
    ranked_styles: tuple[StyleScoreV2, ...]
    partition: str


@dataclass(frozen=True)
class StyleCalibrationCandidate:
    strategy: str
    parameters: StyleSelectionParameters


def _split_labels(fixture: dict) -> tuple[str, ...]:
    labels = list(fixture["expected_styles"])
    if len(fixture["expected_styles"]) > 1:
        labels.append("mixed")
    if not fixture["expected_styles"]:
        labels.append("empty")
    if fixture["id"].startswith("hard_"):
        labels.append("hard")
    return tuple(labels)


def build_deterministic_split(
        fixtures: Sequence[dict], *, seed: int = STYLE_SPLIT_SEED,
        holdout_size: int = STYLE_HOLDOUT_SIZE) -> dict[str, list[str]]:
    """Greedily approximate label/hard/mixed strata with stable hash ties."""
    if not 0 < holdout_size < len(fixtures):
        raise ValueError("holdout_size must leave both partitions non-empty")
    totals = Counter(label for fixture in fixtures for label in _split_labels(fixture))
    targets = {
        label: max(1, round(count * holdout_size / len(fixtures)))
        for label, count in totals.items()
    }
    selected: list[dict] = []
    selected_counts: Counter[str] = Counter()
    while len(selected) < holdout_size:
        candidates = []
        for fixture in fixtures:
            if fixture in selected:
                continue
            labels = _split_labels(fixture)
            overshoot = sum(max(
                selected_counts[label] + 1 - targets[label], 0)
                for label in labels)
            gain = sum(max(targets[label] - selected_counts[label], 0)
                       / targets[label] for label in labels)
            stable_hash = hashlib.sha256(
                f"{seed}:{fixture['id']}".encode("utf-8")).hexdigest()
            candidates.append((overshoot, -gain, stable_hash, fixture))
        chosen = min(candidates, key=lambda row: row[:3])[3]
        selected.append(chosen)
        selected_counts.update(_split_labels(chosen))

    holdout_ids = [fixture["id"] for fixture in selected]
    holdout = set(holdout_ids)
    return {
        "calibration_ids": [fixture["id"] for fixture in fixtures
                            if fixture["id"] not in holdout],
        "holdout_ids": holdout_ids,
    }


def _scored_mapping(record: StyleCalibrationRecord) -> tuple[dict, dict]:
    scored = {
        row.style_id: {
            "support_score": row.support_score,
            "active_families": sum(
                value > 0 for value in row.feature_family_support.values()),
            "family_support": row.feature_family_support,
        }
        for row in record.ranked_styles
    }
    features = {row.style_id: row.detected_features for row in record.ranked_styles}
    return scored, features


def predict_record(record: StyleCalibrationRecord,
                   parameters: StyleSelectionParameters) -> set[str]:
    scored, features = _scored_mapping(record)
    decisions = select_style_scores(scored, features, parameters)
    return {style_id for style_id, row in decisions.items() if row["selected"]}


def _ratio(a: int, b: int) -> float:
    return a / b if b else 0.0


def calibration_metrics(records: Sequence[StyleCalibrationRecord],
                        parameters: StyleSelectionParameters) -> dict[str, float | int]:
    predictions = [predict_record(record, parameters) for record in records]
    tp = fp = fn = 0
    per_style_f1 = []
    for record, predicted in zip(records, predictions):
        expected = set(record.expected_styles)
        tp += len(expected & predicted)
        fp += len(predicted - expected)
        fn += len(expected - predicted)
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    micro_f1 = _ratio(2 * precision * recall, precision + recall)
    for style_id in STYLE_LABELS:
        style_tp = sum(style_id in record.expected_styles and style_id in predicted
                       for record, predicted in zip(records, predictions))
        style_fp = sum(style_id not in record.expected_styles and style_id in predicted
                       for record, predicted in zip(records, predictions))
        style_fn = sum(style_id in record.expected_styles and style_id not in predicted
                       for record, predicted in zip(records, predictions))
        style_precision = _ratio(style_tp, style_tp + style_fp)
        style_recall = _ratio(style_tp, style_tp + style_fn)
        per_style_f1.append(_ratio(
            2 * style_precision * style_recall, style_precision + style_recall))
    mixed = [(record, predicted) for record, predicted in zip(records, predictions)
             if len(record.expected_styles) > 1]
    mixed_expected = sum(len(record.expected_styles) for record, _ in mixed)
    mixed_hits = sum(len(set(record.expected_styles) & predicted)
                     for record, predicted in mixed)
    good_abstentions = sum(not record.expected_styles and not predicted
                           for record, predicted in zip(records, predictions))
    bad_abstentions = sum(bool(record.expected_styles) and not predicted
                          for record, predicted in zip(records, predictions))
    return {
        "micro_precision": round(precision, 6),
        "micro_recall": round(recall, 6),
        "micro_f1": round(micro_f1, 6),
        "macro_f1": round(sum(per_style_f1) / len(per_style_f1), 6),
        "mixed_case_recall": round(_ratio(mixed_hits, mixed_expected), 6),
        "false_positives": fp,
        "false_negatives": fn,
        "average_selected_styles": round(
            _ratio(sum(len(row) for row in predictions), len(predictions)), 6),
        "abstention_count": sum(not row for row in predictions),
        "good_abstentions": good_abstentions,
        "bad_abstentions": bad_abstentions,
        "abstention_quality": good_abstentions - bad_abstentions,
    }


def calibration_grid() -> tuple[StyleCalibrationCandidate, ...]:
    """Small deterministic A–F grid requested by Patch C.2."""
    candidates: list[StyleCalibrationCandidate] = []

    def add(strategy: str, floors: Iterable[float], margins: Iterable[float | None],
            families: Iterable[int], weak: Iterable[float | None]) -> None:
        for floor in floors:
            for margin in margins:
                for family_count in families:
                    for weak_floor in weak:
                        candidates.append(StyleCalibrationCandidate(
                            strategy,
                            StyleSelectionParameters(
                                floor, margin, family_count, weak_floor)))

    add("A_CURRENT_THRESHOLD_ONLY", (0.12,), (None,), (1,), (None,))
    add("B_ABSOLUTE_FLOOR", (0.10, 0.12, 0.14), (None,), (1,), (None,))
    add("C_RELATIVE_TO_BEST", (0.0,), (0.06, 0.08, 0.10), (1,), (None,))
    add("D_FLOOR_PLUS_MARGIN", (0.10, 0.12, 0.14),
        (0.06, 0.08, 0.10), (1,), (None,))
    add("E_FLOOR_PLUS_FAMILIES", (0.10, 0.12, 0.14),
        (None,), (2, 3), (None,))
    add("F_HYBRID", (0.10, 0.12, 0.14), (0.06, 0.08, 0.10),
        (2, 3), (0.12, 0.14, 0.16))

    unique: dict[tuple, StyleCalibrationCandidate] = {}
    for candidate in candidates:
        values = candidate.parameters.as_dict()
        key = (candidate.strategy, *values.values())
        unique[key] = candidate
    return tuple(unique.values())


def optimize_style_selection(
        records: Sequence[StyleCalibrationRecord]) -> tuple[
            StyleCalibrationCandidate, tuple[dict[str, object], ...]]:
    """Choose parameters without accepting or inspecting holdout records."""
    if not records:
        raise ValueError("calibration records are required")
    forbidden = [record.fixture_id for record in records
                 if record.partition != CALIBRATION_PARTITION]
    if forbidden:
        raise ValueError(
            "optimizer accepts CALIBRATION records only; rejected: "
            + ", ".join(forbidden))

    rows: list[dict[str, object]] = []
    for candidate in calibration_grid():
        metrics = calibration_metrics(records, candidate.parameters)
        complexity = sum(value not in (None, 0, 0.0, 1)
                         for value in candidate.parameters.as_dict().values())
        rows.append({
            "strategy": candidate.strategy,
            "parameters": candidate.parameters.as_dict(),
            "metrics": metrics,
            "complexity": complexity,
            "candidate": candidate,
        })

    def objective(row: dict[str, object]) -> tuple:
        metrics = row["metrics"]
        parameters = row["parameters"]
        return (
            metrics["micro_f1"],
            metrics["macro_f1"],
            metrics["mixed_case_recall"],
            metrics["abstention_quality"],
            -metrics["false_positives"],
            -metrics["average_selected_styles"],
            -row["complexity"],
            # When metrics tie, preserve the Patch C floor and choose the
            # smallest newly introduced restrictive values.
            -abs(float(parameters["absolute_floor"]) - 0.12),
            -float(parameters["relative_margin"] or 1.0),
            -float(parameters["weak_style_abstention_threshold"] or 1.0),
        )

    winner_row = max(rows, key=objective)
    winner = winner_row["candidate"]
    serializable = tuple({key: value for key, value in row.items()
                          if key != "candidate"} for row in rows)
    return winner, serializable
