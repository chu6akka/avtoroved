"""Deterministic development calibration of ThemeEngineV2 label selection.

The split is frozen before tuning.  ``tune_selection`` has no holdout input and
therefore cannot use holdout labels or results to select parameters.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from statistics import fmean
from typing import Iterable, Sequence


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from analyzer.semantic_layers.embedding_backend import (  # noqa: E402
    SentenceTransformerEmbeddingBackend,
)
from analyzer.semantic_layers.theme_engine_v2 import ThemeEngineV2  # noqa: E402
from analyzer.semantic_layers.theme_selection import (  # noqa: E402
    DEFAULT_THEME_SELECTION_PARAMETERS,
    ThemeSelectionParameters,
    select_themes,
)
from scripts.evaluate_theme_engines import (  # noqa: E402
    calculate_metrics,
    calculate_per_theme,
    load_fixtures,
)


SPLIT_SEED = 20260828
SPLIT_RATIO = 0.30
SPLIT_PATH = _ROOT / "tests" / "fixtures" / "theme_v2" / "split.json"
SCORE_CSV_PATH = _ROOT / "docs" / "theme_v2_score_analysis.csv"
REPORT_PATH = _ROOT / "docs" / "theme_v2_calibration.md"
PROTECTED_SEMANTIC_CASES = (
    "medicine_vaccination",
    "science_experiment",
    "science_article",
    "religion_service",
    "politics_diplomacy",
    "hard_semantic_without_direct_keyword",
)


def _stable_order(seed: int, fixture_id: str) -> str:
    return hashlib.sha256(f"{seed}:{fixture_id}".encode("utf-8")).hexdigest()


def create_split_manifest(fixtures: Sequence[dict], seed: int = SPLIT_SEED,
                          holdout_ratio: float = SPLIT_RATIO) -> dict:
    """Stratify deterministically by the first expected theme.

    Labels are used only to freeze the split.  Selection tuning happens later
    through a function that receives the calibration subset alone.
    """
    by_primary: dict[str, list[dict]] = defaultdict(list)
    for fixture in fixtures:
        expected = fixture["expected_themes"]
        primary = expected[0] if expected else "__neutral__"
        by_primary[primary].append(fixture)

    target = round(len(fixtures) * holdout_ratio)
    quotas: dict[str, int] = {}
    for primary, rows in by_primary.items():
        if primary == "__neutral__":
            quotas[primary] = 0
        else:
            quotas[primary] = min(len(rows) - 1, max(1, math.floor(
                len(rows) * holdout_ratio)))

    while sum(quotas.values()) < target:
        candidates = [
            primary for primary, rows in by_primary.items()
            if quotas[primary] < len(rows) - 1
        ]
        if not candidates:
            break
        primary = max(candidates, key=lambda key: (
            len(by_primary[key]) * holdout_ratio - quotas[key],
            _stable_order(seed, key),
        ))
        quotas[primary] += 1
    while sum(quotas.values()) > target:
        candidates = [key for key, quota in quotas.items() if quota > 1]
        primary = min(candidates, key=lambda key: (
            len(by_primary[key]) * holdout_ratio - quotas[key],
            _stable_order(seed, key),
        ))
        quotas[primary] -= 1

    holdout_ids: set[str] = set()
    for primary, rows in by_primary.items():
        ordered = sorted(rows, key=lambda row: _stable_order(seed, row["id"]))
        holdout_ids.update(row["id"] for row in ordered[:quotas[primary]])

    all_ids = {row["id"] for row in fixtures}
    calibration_ids = all_ids - holdout_ids
    all_themes = {
        theme for fixture in fixtures for theme in fixture["expected_themes"]
    }
    for subset_name, subset_ids in (
            ("calibration", calibration_ids), ("holdout", holdout_ids)):
        represented = {
            theme for fixture in fixtures if fixture["id"] in subset_ids
            for theme in fixture["expected_themes"]
        }
        if represented != all_themes:
            raise RuntimeError(
                f"{subset_name} does not represent: {sorted(all_themes-represented)}")
        mixed_count = sum(
            len(fixture["expected_themes"]) > 1
            for fixture in fixtures if fixture["id"] in subset_ids
        )
        if mixed_count == 0:
            raise RuntimeError(f"{subset_name} has no mixed-theme fixture")

    return {
        "schema_version": 1,
        "seed": seed,
        "holdout_ratio": holdout_ratio,
        "algorithm": "primary-theme-stratified-sha256-v1",
        "fixture_count": len(fixtures),
        "calibration_ids": sorted(calibration_ids),
        "holdout_ids": sorted(holdout_ids),
    }


def write_split_manifest(fixtures: Sequence[dict]) -> dict:
    manifest = create_split_manifest(fixtures)
    SPLIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPLIT_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def write_score_csv(fixtures: Sequence[dict], results: Sequence[object]) -> None:
    SCORE_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SCORE_CSV_PATH.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=(
            "fixture_id", "theme_id", "expected", "rank", "semantic_score",
            "lexical_score", "combined_score", "coverage", "delta_from_best",
            "ratio_to_best", "segment_support_count", "segment_count",
        ))
        writer.writeheader()
        for fixture, result in zip(fixtures, results):
            best = result.themes[0].combined_score if result.themes else 0.0
            expected = set(fixture["expected_themes"])
            for rank, row in enumerate(result.themes, start=1):
                writer.writerow({
                    "fixture_id": fixture["id"],
                    "theme_id": row.theme_id,
                    "expected": int(row.theme_id in expected),
                    "rank": rank,
                    "semantic_score": f"{row.semantic_score:.6f}",
                    "lexical_score": f"{row.lexical_score:.6f}",
                    "combined_score": f"{row.combined_score:.6f}",
                    "coverage": f"{row.coverage:.6f}",
                    "delta_from_best": f"{best-row.combined_score:.6f}",
                    "ratio_to_best": (
                        f"{row.combined_score/best:.6f}" if best else "0.000000"),
                    "segment_support_count": row.segment_support_count,
                    "segment_count": row.segment_count,
                })


def _candidate_parameters() -> tuple[ThemeSelectionParameters, ...]:
    candidates: list[ThemeSelectionParameters] = []
    base = ThemeSelectionParameters(safety_max_labels=4)
    for floor in (0.32, 0.36, 0.40, 0.44, 0.48, 0.52):
        candidates.append(replace(
            base, strategy="absolute", absolute_floor=floor,
            relative_margin=None, relative_ratio=None))
    for margin in (0.04, 0.06, 0.08, 0.10, 0.12, 0.16):
        candidates.append(replace(
            base, strategy="relative_margin", absolute_floor=0.0,
            relative_margin=margin, relative_ratio=None))
    for ratio in (0.70, 0.75, 0.80, 0.85, 0.90, 0.95):
        candidates.append(replace(
            base, strategy="relative_ratio", absolute_floor=0.0,
            relative_margin=None, relative_ratio=ratio))
    for top_k in (2, 3, 4):
        for support in (1, 2):
            candidates.append(replace(
                base, strategy="top_k_support", absolute_floor=0.0,
                relative_margin=None, relative_ratio=None, top_k=top_k,
                minimum_supported_segments=support))
    for floor in (0.32, 0.36, 0.40, 0.44):
        for margin in (0.04, 0.08, 0.12):
            for coverage in (0.0, 0.5):
                for support in (1, 2):
                    candidates.append(replace(
                        base, strategy="hybrid", absolute_floor=floor,
                        relative_margin=margin, relative_ratio=None,
                        minimum_coverage=coverage,
                        minimum_supported_segments=support))
        for ratio in (0.75, 0.82, 0.90):
            for coverage in (0.0, 0.5):
                for support in (1, 2):
                    candidates.append(replace(
                        base, strategy="hybrid", absolute_floor=floor,
                        relative_margin=None, relative_ratio=ratio,
                        minimum_coverage=coverage,
                        minimum_supported_segments=support))
    return tuple(candidates)


def _predictions(results: Sequence[object], parameters: ThemeSelectionParameters
                 ) -> list[set[str]]:
    return [
        {row.theme_id for row in select_themes(result.themes, parameters)}
        for result in results
    ]


def _dominant(results: Sequence[object]) -> list[str | None]:
    return [
        result.dominant_theme.theme_id if result.dominant_theme else None
        for result in results
    ]


def tune_selection(calibration_fixtures: Sequence[dict],
                   calibration_results: Sequence[object]) -> tuple[
                       ThemeSelectionParameters, dict, dict[str, dict]]:
    """Tune on calibration data only; holdout cannot be passed to this API."""
    best_by_strategy: dict[str, tuple[ThemeSelectionParameters, dict]] = {}
    scored: list[tuple[ThemeSelectionParameters, dict]] = []
    fixtures = list(calibration_fixtures)
    dominant = _dominant(calibration_results)
    for parameters in _candidate_parameters():
        metrics = calculate_metrics(
            fixtures, _predictions(calibration_results, parameters), dominant)
        scored.append((parameters, metrics))
        current = best_by_strategy.get(parameters.strategy)
        if current is None or _metric_key(metrics) > _metric_key(current[1]):
            best_by_strategy[parameters.strategy] = (parameters, metrics)

    viable = [row for row in scored if row[1]["micro_recall"] >= 0.50]
    chosen, chosen_metrics = max(viable or scored, key=lambda row: _metric_key(row[1]))
    strategy_summary = {
        strategy: {"parameters": parameters.as_dict(), "metrics": metrics}
        for strategy, (parameters, metrics) in sorted(best_by_strategy.items())
    }
    return chosen, chosen_metrics, strategy_summary


def _metric_key(metrics: dict) -> tuple:
    return (
        metrics["micro_f1"], metrics["macro_f1"], metrics["micro_precision"],
        metrics["micro_recall"], -metrics["average_labels_per_document"],
    )


def _baseline_metrics(fixtures: Sequence[dict], results: Sequence[object]) -> dict:
    predictions = [
        {row.theme_id for row in result.themes if row.segment_support_count > 0}
        for result in results
    ]
    return calculate_metrics(list(fixtures), predictions, _dominant(results))


def _selected_metrics(fixtures: Sequence[dict], results: Sequence[object],
                      parameters: ThemeSelectionParameters) -> dict:
    return calculate_metrics(
        list(fixtures), _predictions(results, parameters), _dominant(results))


def _distribution_summary(fixtures: Sequence[dict], results: Sequence[object]) -> dict:
    expected_scores: list[float] = []
    other_scores: list[float] = []
    coverage_one = 0
    supported_rows = 0
    total_rows = 0
    for fixture, result in zip(fixtures, results):
        expected = set(fixture["expected_themes"])
        for row in result.themes:
            (expected_scores if row.theme_id in expected else other_scores).append(
                row.combined_score)
            total_rows += 1
            if row.segment_support_count > 0:
                supported_rows += 1
                coverage_one += int(row.coverage == 1.0)

    def stats(values: list[float]) -> dict:
        ordered = sorted(values)
        def percentile(p: float) -> float:
            return ordered[round((len(ordered) - 1) * p)] if ordered else 0.0
        return {
            "count": len(values), "min": min(values, default=0.0),
            "p25": percentile(0.25), "median": percentile(0.5),
            "p75": percentile(0.75), "max": max(values, default=0.0),
            "mean": fmean(values) if values else 0.0,
        }
    return {
        "expected": stats(expected_scores), "non_expected": stats(other_scores),
        "supported_row_fraction": supported_rows / total_rows if total_rows else 0.0,
        "coverage_one_among_supported": (
            coverage_one / supported_rows if supported_rows else 0.0),
        "single_segment_document_fraction": sum(
            result.segment_count == 1 for result in results) / len(results),
    }


def _case_rows(fixtures: Sequence[dict], results: Sequence[object],
               parameters: ThemeSelectionParameters, ids: set[str] | None = None,
               mixed_only: bool = False) -> list[dict]:
    output = []
    for fixture, result in zip(fixtures, results):
        if ids is not None and fixture["id"] not in ids:
            continue
        if mixed_only and len(fixture["expected_themes"]) < 2:
            continue
        selected = select_themes(result.themes, parameters)
        best = result.themes[0].combined_score if result.themes else 0.0
        output.append({
            "id": fixture["id"],
            "expected": fixture["expected_themes"],
            "ranked": [row.theme_id for row in result.themes],
            "selected": [row.theme_id for row in selected],
            "expected_details": {
                theme_id: {
                    "coverage": next(row.coverage for row in result.themes
                                     if row.theme_id == theme_id),
                    "score_delta": best - next(
                        row.combined_score for row in result.themes
                        if row.theme_id == theme_id),
                }
                for theme_id in fixture["expected_themes"]
            },
        })
    return output


def _format_metrics(metrics: dict) -> str:
    return (
        f"top1={metrics['top1_accuracy']:.6f}; "
        f"P={metrics['micro_precision']:.6f}; R={metrics['micro_recall']:.6f}; "
        f"micro F1={metrics['micro_f1']:.6f}; "
        f"macro F1={metrics['macro_f1']:.6f}; "
        f"avg labels={metrics['average_labels_per_document']:.6f}"
    )


def build_report(*, manifest: dict, all_fixtures: Sequence[dict],
                 all_results: Sequence[object], chosen: ThemeSelectionParameters,
                 calibration_metrics: dict, holdout_metrics: dict,
                 strategies: dict[str, dict]) -> str:
    calibration_ids = set(manifest["calibration_ids"])
    holdout_ids = set(manifest["holdout_ids"])
    calibration_pairs = [
        (f, r) for f, r in zip(all_fixtures, all_results)
        if f["id"] in calibration_ids
    ]
    holdout_pairs = [
        (f, r) for f, r in zip(all_fixtures, all_results)
        if f["id"] in holdout_ids
    ]
    baseline = _baseline_metrics(all_fixtures, all_results)
    distributions = _distribution_summary(all_fixtures, all_results)
    mixed = _case_rows(all_fixtures, all_results, chosen, mixed_only=True)
    semantic = _case_rows(
        all_fixtures, all_results, chosen, ids=set(PROTECTED_SEMANTIC_CASES))
    holdout_fixtures = [row[0] for row in holdout_pairs]
    holdout_results = [row[1] for row in holdout_pairs]
    per_theme = calculate_per_theme(
        holdout_fixtures, _predictions(holdout_results, chosen))

    lines = [
        "# ThemeEngineV2 multi-label development calibration",
        "",
        "> This is development calibration on a small synthetic corpus, not an",
        "> independent scientific validation.",
        "",
        "## Split discipline",
        "",
        (f"The corpus was frozen first with seed `{manifest['seed']}`: "
         f"{len(calibration_pairs)} calibration and {len(holdout_pairs)} untouched "
         "holdout fixtures. The tuning function accepts only calibration fixtures "
         "and their V2 ranking results; holdout labels/results are evaluated only "
         "after the parameters are fixed."),
        "",
        "## Why baseline over-selected",
        "",
        ("Baseline treated every theme with at least one permissive segment-support "
         "hit as positive. Rubert similarities put many unrelated themes above the "
         "absolute semantic-only support threshold, so recall reached 1.0 while "
         "precision collapsed. Coverage is often 1.0 because most fixtures form a "
         "single segment: coverage then becomes binary, and one permissive hit means "
         "full coverage. Ranking still separates the correct top theme well."),
        "",
        ("For the 98% single-segment documents, the chosen document-level relative "
         "margin is equivalent to a within-segment relative comparison. The raw "
         "segment-support threshold was retained to preserve the recorded baseline; "
         "retuning it after holdout disclosure would invalidate this calibration "
         "cycle. Multi-segment coverage requires a later dedicated corpus."),
        "",
        "## Score distributions",
        "",
        "```json", json.dumps(distributions, ensure_ascii=False, indent=2), "```",
        "",
        "Full row-level scores are in `docs/theme_v2_score_analysis.csv`.",
        "",
        "## Strategies evaluated on calibration only",
        "",
        "| Strategy | Best parameters | Calibration metrics |",
        "|---|---|---|",
    ]
    for strategy, row in strategies.items():
        lines.append(
            f"| `{strategy}` | `{json.dumps(row['parameters'], sort_keys=True)}` | "
            f"{_format_metrics(row['metrics'])} |")
    lines.extend([
        "",
        "## Chosen calibration layer",
        "",
        "```json", json.dumps(chosen.as_dict(), ensure_ascii=False, indent=2), "```",
        "",
        "The layer applies after ranking and does not alter embeddings, prototypes,",
        "semantic/lexical weights or `dominant_theme`. Empty selection is allowed.",
        "",
        "## Metrics",
        "",
        "| Set | Top-1 | Micro P | Micro R | Micro F1 | Macro F1 | Avg labels/doc |",
        "|---|---:|---:|---:|---:|---:|---:|",
        (f"| Baseline V2 (all 50) | {baseline['top1_accuracy']:.6f} | "
         f"{baseline['micro_precision']:.6f} | {baseline['micro_recall']:.6f} | "
         f"{baseline['micro_f1']:.6f} | {baseline['macro_f1']:.6f} | "
         f"{baseline['average_labels_per_document']:.6f} |"),
        (f"| Calibrated V2 — calibration | {calibration_metrics['top1_accuracy']:.6f} | "
         f"{calibration_metrics['micro_precision']:.6f} | "
         f"{calibration_metrics['micro_recall']:.6f} | "
         f"{calibration_metrics['micro_f1']:.6f} | "
         f"{calibration_metrics['macro_f1']:.6f} | "
         f"{calibration_metrics['average_labels_per_document']:.6f} |"),
        (f"| Calibrated V2 — untouched holdout | {holdout_metrics['top1_accuracy']:.6f} | "
         f"{holdout_metrics['micro_precision']:.6f} | "
         f"{holdout_metrics['micro_recall']:.6f} | "
         f"{holdout_metrics['micro_f1']:.6f} | "
         f"{holdout_metrics['macro_f1']:.6f} | "
         f"{holdout_metrics['average_labels_per_document']:.6f} |"),
        "",
        "## Holdout per-theme F1",
        "",
        "Small support makes every per-theme value unstable.",
        "",
        "| Theme | Precision | Recall | F1 | Support |",
        "|---|---:|---:|---:|---:|",
    ])
    for theme_id, row in per_theme.items():
        lines.append(
            f"| `{theme_id}` | {row['precision']:.6f} | {row['recall']:.6f} | "
            f"{row['f1']:.6f} | {row['support']} |")
    for heading, cases in (("Mixed-theme cases", mixed),
                           ("Protected semantic-only/weak-lexical cases", semantic)):
        lines.extend(["", f"## {heading}", "",
                      "| Fixture | Expected | Ranked themes | Selected | Expected coverage/delta |",
                      "|---|---|---|---|---|"])
        for case in cases:
            details = "; ".join(
                f"{theme}: coverage={row['coverage']:.3f}, delta={row['score_delta']:.3f}"
                for theme, row in case["expected_details"].items())
            lines.append(
                f"| `{case['id']}` | `{case['expected']}` | `{case['ranked']}` | "
                f"`{case['selected']}` | "
                f"{details} |")
    lines.extend([
        "", "## Interpretation", "",
        "The holdout is internal to the same constructed development corpus. These",
        "numbers justify keeping V2 in shadow mode and proceeding to broader corpus",
        "validation; they do not establish forensic validity.", "",
    ])
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tune-only", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    fixtures = load_fixtures(include_hard=True)
    manifest = write_split_manifest(fixtures)
    engine = ThemeEngineV2(embedding_backend=SentenceTransformerEmbeddingBackend())
    results = [engine.analyze(fixture["text"]) for fixture in fixtures]
    failures = [result for result in results if result.status != "ok"]
    if failures:
        raise RuntimeError(f"V2 backend failed: {failures[0].reason}")
    write_score_csv(fixtures, results)

    calibration_ids = set(manifest["calibration_ids"])
    calibration_pairs = [
        (fixture, result) for fixture, result in zip(fixtures, results)
        if fixture["id"] in calibration_ids
    ]
    calibration_fixtures = [row[0] for row in calibration_pairs]
    calibration_results = [row[1] for row in calibration_pairs]
    chosen, calibration_metrics, strategies = tune_selection(
        calibration_fixtures, calibration_results)
    tuning_output = {
        "parameters": chosen.as_dict(),
        "calibration_metrics": calibration_metrics,
        "best_by_strategy": strategies,
    }
    if args.tune_only:
        print(json.dumps(tuning_output, ensure_ascii=False, indent=2))
        return 0

    if chosen != DEFAULT_THEME_SELECTION_PARAMETERS:
        raise RuntimeError(
            "calibrated parameters differ from engine default; freeze them first")
    holdout_ids = set(manifest["holdout_ids"])
    holdout_pairs = [
        (fixture, result) for fixture, result in zip(fixtures, results)
        if fixture["id"] in holdout_ids
    ]
    holdout_metrics = _selected_metrics(
        [row[0] for row in holdout_pairs], [row[1] for row in holdout_pairs], chosen)
    REPORT_PATH.write_text(build_report(
        manifest=manifest, all_fixtures=fixtures, all_results=results,
        chosen=chosen, calibration_metrics=calibration_metrics,
        holdout_metrics=holdout_metrics, strategies=strategies,
    ), encoding="utf-8")
    print(json.dumps({
        **tuning_output,
        "baseline": _baseline_metrics(fixtures, results),
        "holdout_metrics": holdout_metrics,
        "holdout_per_theme": calculate_per_theme(
            [row[0] for row in holdout_pairs],
            _predictions([row[1] for row in holdout_pairs], chosen)),
        "mixed_cases": _case_rows(fixtures, results, chosen, mixed_only=True),
        "semantic_cases": _case_rows(
            fixtures, results, chosen, ids=set(PROTECTED_SEMANTIC_CASES)),
        "score_distribution": _distribution_summary(fixtures, results),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
