"""Generate Patch C.2 DEVELOPMENT calibration and INTERNAL HOLDOUT reports."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Sequence


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from analyzer.semantic_layers.style_calibration import (  # noqa: E402
    CALIBRATION_PARTITION,
    HOLDOUT_PARTITION,
    StyleCalibrationRecord,
    build_deterministic_split,
    optimize_style_selection,
)
from analyzer.semantic_layers.style_detectors import (  # noqa: E402
    STYLE_DETECTOR_SPECS,
    STYLE_FAMILIES,
    STYLE_LABELS,
)
from analyzer.semantic_layers.style_selection import (  # noqa: E402
    CALIBRATED_STYLE_SELECTION_PARAMETERS,
    LEGACY_STYLE_SELECTION_PARAMETERS,
)
from scripts.evaluate_style_engines import (  # noqa: E402
    analyze_fixtures,
    calculate_metrics,
    calculate_per_style,
    load_fixtures,
)


_SPLIT_PATH = _ROOT / "tests" / "fixtures" / "style_v2" / "split.json"
_ERROR_MD = _ROOT / "docs" / "style_v2_error_analysis.md"
_SCORE_CSV = _ROOT / "docs" / "style_v2_score_analysis.csv"
_DETECTOR_CSV = _ROOT / "docs" / "style_v2_detector_diagnostics.csv"
_CALIBRATION_MD = _ROOT / "docs" / "style_v2_calibration.md"


def load_and_verify_split(fixtures: Sequence[dict]) -> dict:
    split = json.loads(_SPLIT_PATH.read_text("utf-8"))
    generated = build_deterministic_split(
        fixtures, seed=split["seed"], holdout_size=split["holdout_count"])
    for key in ("calibration_ids", "holdout_ids"):
        if generated[key] != split[key]:
            raise RuntimeError(f"stored split is not deterministic: {key}")
    fixture_ids = {fixture["id"] for fixture in fixtures}
    calibration_ids = set(split["calibration_ids"])
    holdout_ids = set(split["holdout_ids"])
    if calibration_ids & holdout_ids or calibration_ids | holdout_ids != fixture_ids:
        raise RuntimeError("split must cover every fixture exactly once")
    return split


def _partition(fixtures: Sequence[dict], ids: Sequence[str]) -> list[dict]:
    wanted = set(ids)
    return [fixture for fixture in fixtures if fixture["id"] in wanted]


def _metrics(fixtures: list[dict], analysis: dict) -> dict:
    return calculate_metrics(
        fixtures, analysis["v2_predictions"], analysis["v2_dominant"])


def _records(fixtures: list[dict], analysis: dict,
             partition: str) -> tuple[StyleCalibrationRecord, ...]:
    return tuple(
        StyleCalibrationRecord(
            fixture_id=fixture["id"],
            expected_styles=tuple(fixture["expected_styles"]),
            ranked_styles=result.styles,
            partition=partition,
        )
        for fixture, result in zip(fixtures, analysis["v2_results"])
    )


def _score_rows(fixtures: list[dict], analysis: dict) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for fixture, result, predicted, leading in zip(
            fixtures, analysis["v2_results"], analysis["v2_predictions"],
            analysis["v2_dominant"]):
        expected = set(fixture["expected_styles"])
        row: dict[str, object] = {
            "fixture_id": fixture["id"],
            "expected_styles": ";".join(fixture["expected_styles"]),
            "selected_styles": ";".join(sorted(predicted)),
            "leading_style": leading or "",
            "ranked_styles": ";".join(style.style_id for style in result.styles),
            "abstention": not predicted,
            "false_positives": ";".join(sorted(predicted - expected)),
            "false_negatives": ";".join(sorted(expected - predicted)),
        }
        by_style = {style.style_id: style for style in result.styles}
        for style_id in STYLE_LABELS:
            style = by_style[style_id]
            row[f"{style_id}_score"] = style.support_score
            for family in STYLE_FAMILIES:
                row[f"{style_id}_{family}_support"] = (
                    style.feature_family_support[family])
            row[f"{style_id}_detected_feature_ids"] = ";".join(
                feature.feature_id for feature in style.detected_features)
            row[f"{style_id}_evidence_count"] = len(style.evidence)
        rows.append(row)
    return rows


def _write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"no rows for {path}")
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _detector_rows(fixtures: list[dict], analysis: dict) -> list[dict[str, object]]:
    detected_by_fixture: dict[str, set[str]] = {}
    evidence_by_fixture: dict[str, Counter[str]] = {}
    for fixture, result in zip(fixtures, analysis["v2_results"]):
        detected_by_fixture[fixture["id"]] = {
            feature.feature_id for style in result.styles
            for feature in style.detected_features
        }
        evidence_by_fixture[fixture["id"]] = Counter(
            evidence.feature_id for style in result.styles for evidence in style.evidence)

    specs = {spec.feature_id: spec for spec in STYLE_DETECTOR_SPECS.values()
             if spec.automation_status != "EXPERT_ONLY"}
    rows: list[dict[str, object]] = []
    for feature_id in sorted(specs):
        spec = specs[feature_id]
        fired = [fixture for fixture in fixtures
                 if feature_id in detected_by_fixture[fixture["id"]]]
        in_expected = sum(bool(set(spec.style_ids) & set(fixture["expected_styles"]))
                          for fixture in fired)
        distribution: Counter[str] = Counter()
        for fixture in fired:
            if fixture["expected_styles"]:
                distribution.update(fixture["expected_styles"])
            else:
                distribution["<none>"] += 1
        rows.append({
            "feature_id": feature_id,
            "style_ids": ";".join(spec.style_ids),
            "family": spec.family,
            "automation_status": spec.automation_status,
            "method_status": spec.method_status,
            "firing_documents": len(fired),
            "expected_style_documents": in_expected,
            "outside_expected_style_documents": len(fired) - in_expected,
            "rough_signal_precision": round(in_expected / len(fired), 6)
            if fired else 0.0,
            "evidence_count": sum(evidence_by_fixture[fixture["id"]][feature_id]
                                  for fixture in fired),
            "expected_styles_distribution": json.dumps(
                dict(sorted(distribution.items())), ensure_ascii=False,
                sort_keys=True),
        })
    return rows


def _fmt_styles(values: Iterable[str]) -> str:
    values = list(values)
    return ", ".join(values) if values else "—"


def _error_report(fixtures: list[dict], analysis: dict,
                  metrics: dict, detector_rows: Sequence[dict]) -> str:
    lines = [
        "# StyleEngineV2: DEVELOPMENT error analysis",
        "",
        "> Baseline зафиксирован для commit `1909a4f48cda1bedc65423b5da8ea975dc1cf7c9`. "
        "Это инженерный development corpus, а не научная валидация.",
        "",
        "## Baseline",
        "",
        f"35 fixtures; top-1 `{metrics['top1_accuracy']:.6f}`; micro P/R/F1 "
        f"`{metrics['micro_precision']:.6f}/{metrics['micro_recall']:.6f}/"
        f"{metrics['micro_f1']:.6f}`; macro F1 `{metrics['macro_f1']:.6f}`; "
        f"abstentions `{metrics['abstention_count']}`; mixed recall "
        f"`{metrics['mixed_case_recall']:.6f}`.",
        "",
        "## Full fixture matrix",
        "",
        "| Fixture | Expected | Selected | Leading | Ranked support | FP | FN |",
        "|---|---|---|---|---|---|---|",
    ]
    publicistic_false_negatives = []
    conversational_false_positives = []
    abstentions = []
    mixed = []
    for fixture, result, predicted, leading in zip(
            fixtures, analysis["v2_results"], analysis["v2_predictions"],
            analysis["v2_dominant"]):
        expected = set(fixture["expected_styles"])
        ranked = ", ".join(
            f"{style.style_id}={style.support_score:.6f}" for style in result.styles)
        fp = predicted - expected
        fn = expected - predicted
        lines.append(
            f"| `{fixture['id']}` | {_fmt_styles(fixture['expected_styles'])} | "
            f"{_fmt_styles(sorted(predicted))} | {leading or '—'} | {ranked} | "
            f"{_fmt_styles(sorted(fp))} | {_fmt_styles(sorted(fn))} |")
        if "publicistic" in expected and "publicistic" not in predicted:
            publicistic_false_negatives.append((fixture, result))
        if "conversational" in predicted and "conversational" not in expected:
            conversational_false_positives.append((fixture, result))
        if not predicted:
            abstentions.append((fixture, not expected))
        if len(expected) > 1:
            mixed.append((fixture, result, predicted))

    lines += [
        "",
        "Полные пять family-level значений, feature IDs и evidence counts находятся "
        "в `docs/style_v2_score_analysis.csv`.",
        "",
        "## Publicistic false negatives",
        "",
    ]
    for fixture, result in publicistic_false_negatives:
        publicistic = next(row for row in result.styles
                           if row.style_id == "publicistic")
        rank = next(index for index, row in enumerate(result.styles, 1)
                    if row.style_id == "publicistic")
        competing = result.styles[0]
        active = [family for family, value in
                  publicistic.feature_family_support.items() if value]
        present = {feature.feature_id for feature in publicistic.detected_features}
        possible = {spec.feature_id for spec in STYLE_DETECTOR_SPECS.values()
                    if "publicistic" in spec.style_ids
                    and spec.automation_status != "EXPERT_ONLY"}
        classification = (
            "insufficient independent detector coverage"
            if len(active) < 2 else "selection calibration")
        lines += [
            f"### `{fixture['id']}`",
            "",
            f"Rank `{rank}`; support `{publicistic.support_score:.6f}`; competing "
            f"style `{competing.style_id}` (`{competing.support_score:.6f}`); "
            f"families `{_fmt_styles(active)}`.",
            "",
            f"Signals present: `{_fmt_styles(sorted(present))}`. Potential existing "
            f"detectors without evidence: `{_fmt_styles(sorted(possible - present))}`. "
            f"Diagnosis: **{classification}**. The fixture is not relabelled and no "
            "missing detector is implemented in C.2.",
            "",
        ]

    lines += ["## Conversational false positives", ""]
    for fixture, result in conversational_false_positives:
        style = next(row for row in result.styles
                     if row.style_id == "conversational")
        features = [feature.feature_id for feature in style.detected_features]
        families = [family for family, value in
                    style.feature_family_support.items() if value]
        lines += [
            f"- `{fixture['id']}`: score `{style.support_score:.6f}`, families "
            f"`{_fmt_styles(families)}`, features `{_fmt_styles(features)}`. "
            "The false positive is secondary or weak CANDIDATE_ONLY support, not a "
            "new independent conversational detector.",
        ]

    lines += [
        "",
        "The recurring sources are the legacy stratified-lexicon signal and the "
        "incomplete-sentence proxy. General punctuation does not enter the score as "
        "an independent AUTO confirmation. Calibration therefore acts on selection "
        "gates rather than changing method significance or detector weights.",
        "",
        "## Detector diagnostics",
        "",
        "`docs/style_v2_detector_diagnostics.csv` contains firing counts, in-style "
        "and outside-style counts, rough signal precision and style distribution for "
        f"all `{len(detector_rows)}` non-EXPERT_ONLY runtime detectors. These figures "
        "are engineering diagnostics on a small corpus and are not feature validation.",
        "",
        "## Family dominance",
        "",
        "Support is the equal mean of five family maxima. A saturated single family "
        "therefore contributes at most `0.2`; it cannot pass selection without the "
        "independent-family gate. The error matrix confirms that publicistic misses "
        "with punctuation-only evidence must remain abstentions rather than being "
        "rescued by a lower score floor.",
        "",
        "## Mixed cases",
        "",
    ]
    for fixture, result, predicted in mixed:
        lines.append(
            f"- `{fixture['id']}`: expected `{_fmt_styles(fixture['expected_styles'])}`; "
            f"selected `{_fmt_styles(sorted(predicted))}`; ranked "
            + ", ".join(f"`{row.style_id}={row.support_score:.6f}`"
                        for row in result.styles) + ".")

    good = [fixture["id"] for fixture, is_good in abstentions if is_good]
    bad = [fixture["id"] for fixture, is_good in abstentions if not is_good]
    lines += [
        "",
        "## Abstention and short texts",
        "",
        f"Good abstentions (`{len(good)}`): `{_fmt_styles(good)}`.",
        "",
        f"Bad abstentions (`{len(bad)}`): `{_fmt_styles(bad)}`.",
        "",
        "Short ambiguous/list/neutral fixtures remain legitimate abstentions. A single "
        "marker is intentionally insufficient; no length correction is introduced.",
        "",
        "## Conclusion",
        "",
        "Publicistic recall is detector-coverage limited. Conversational precision can "
        "be improved by relative-to-best and weak-evidence abstention gates while "
        "preserving ranking, evidence, registry metadata and production behavior.",
        "",
    ]
    return "\n".join(lines)


def _metric_line(metrics: dict) -> str:
    return (
        f"top1 `{metrics['top1_accuracy']:.6f}`, micro P/R/F1 "
        f"`{metrics['micro_precision']:.6f}/{metrics['micro_recall']:.6f}/"
        f"{metrics['micro_f1']:.6f}`, macro F1 `{metrics['macro_f1']:.6f}`, "
        f"avg styles `{metrics['average_selected_styles']:.6f}`, abstentions "
        f"`{metrics['abstention_count']}`, mixed recall "
        f"`{metrics['mixed_case_recall']:.6f}`"
    )


def _calibration_report(
        baseline_full: dict, calibrated_full: dict,
        calibration_baseline: dict, calibration_final: dict,
        holdout_baseline: dict, holdout_final: dict,
        holdout_per_style: dict, grid_rows: Sequence[dict], split: dict,
        holdout_fixtures: list[dict], holdout_analysis: dict,
        runtime: dict[str, float]) -> str:
    top_grid = sorted(
        grid_rows,
        key=lambda row: (row["metrics"]["micro_f1"],
                         row["metrics"]["macro_f1"],
                         row["metrics"]["mixed_case_recall"]),
        reverse=True)[:8]
    lines = [
        "# StyleEngineV2: DEVELOPMENT calibration",
        "",
        "> This is DEVELOPMENT CALIBRATION with one INTERNAL HOLDOUT evaluation. "
        "It is not scientific validation and support scores are not probabilities.",
        "",
        "## 1. Baseline",
        "",
        _metric_line(baseline_full),
        "",
        "## 2. Error analysis",
        "",
        "The frozen matrix is in `style_v2_score_analysis.csv`; the detailed analysis "
        "is in `style_v2_error_analysis.md`.",
        "",
        "## 3. Publicistic false negatives",
        "",
        "The missed publicistic fixtures typically expose only punctuation or one "
        "candidate family. Lowering the floor would simulate missing independent "
        "evidence, so C.2 does not attempt to force recall to 1.0.",
        "",
        "## 4. Conversational false positives",
        "",
        "False positives are mainly secondary weak-only combinations of the legacy "
        "stratified lexicon and incomplete-sentence proxy. They motivate global weak-"
        "evidence abstention and relative-to-best gates; detector weights are unchanged.",
        "",
        "## 5. Detector diagnostics",
        "",
        "See `style_v2_detector_diagnostics.csv`. Rough precision is descriptive only; "
        "no detector was removed or promoted from this small corpus.",
        "",
        "## 6. Score distributions",
        "",
        "The full per-fixture and per-family distributions are in "
        "`style_v2_score_analysis.csv`. One-family publicistic scores cluster below the "
        "independent-family gate; false conversational labels are weak-only or far "
        "below the leading style.",
        "",
        "## 7. Calibration strategy",
        "",
        f"Split: seed `{split['seed']}`; DEVELOPMENT CALIBRATION "
        f"`{split['calibration_count']}` fixtures; INTERNAL HOLDOUT "
        f"`{split['holdout_count']}` fixtures. The optimizer accepts only records "
        "marked `CALIBRATION` and rejects holdout records before reading them.",
        "",
        "Tested A–F: current threshold only; absolute floor; relative margin; floor + "
        "margin; floor + independent families; and the four-parameter hybrid.",
        "",
        "Frozen F_HYBRID parameters: `absolute_floor=0.12`, "
        "`relative_margin=0.08`, `minimum_family_support=2`, "
        "`weak_style_abstention_threshold=0.14`.",
        "",
        "| Strategy | Parameters | micro F1 | macro F1 | mixed recall | FP |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in top_grid:
        strategy_label = row["strategy"]
        if row["parameters"] == CALIBRATED_STYLE_SELECTION_PARAMETERS.as_dict():
            strategy_label = "**F_HYBRID (frozen winner)**"
        lines.append(
            f"| {strategy_label} | "
            f"`{json.dumps(row['parameters'], sort_keys=True)}` | "
            f"{row['metrics']['micro_f1']:.6f} | {row['metrics']['macro_f1']:.6f} | "
            f"{row['metrics']['mixed_case_recall']:.6f} | "
            f"{row['metrics']['false_positives']} |")
    lines += [
        "",
        "## 8. DEVELOPMENT CALIBRATION metrics",
        "",
        f"Baseline: {_metric_line(calibration_baseline)}.",
        "",
        f"Frozen strategy: {_metric_line(calibration_final)}.",
        "",
        "## 9. INTERNAL HOLDOUT metrics",
        "",
        f"Baseline: {_metric_line(holdout_baseline)}.",
        "",
        f"One frozen-parameter run: {_metric_line(holdout_final)}; mixed exact-set "
        f"accuracy `{holdout_final['mixed_exact_set_accuracy']:.6f}`.",
        "",
        "| Style | Precision | Recall | F1 | Support |",
        "|---|---:|---:|---:|---:|",
    ]
    for style_id, row in holdout_per_style.items():
        lines.append(
            f"| {style_id} | {row['precision']:.6f} | {row['recall']:.6f} | "
            f"{row['f1']:.6f} | {row['support']} |")
    lines += ["", "## 10. Mixed cases", ""]
    for fixture, result, predicted in zip(
            holdout_fixtures, holdout_analysis["v2_results"],
            holdout_analysis["v2_predictions"]):
        if len(fixture["expected_styles"]) <= 1:
            continue
        lines.append(
            f"- `{fixture['id']}`: expected `{_fmt_styles(fixture['expected_styles'])}`; "
            f"selected `{_fmt_styles(sorted(predicted))}`; "
            + ", ".join(
                f"`{row.style_id}={row.support_score:.6f}` "
                f"families={sum(value > 0 for value in row.feature_family_support.values())}"
                for row in result.styles) + ".")
    good = sum(not fixture["expected_styles"] and not predicted
               for fixture, predicted in zip(
                   holdout_fixtures, holdout_analysis["v2_predictions"]))
    bad = sum(bool(fixture["expected_styles"]) and not predicted
              for fixture, predicted in zip(
                  holdout_fixtures, holdout_analysis["v2_predictions"]))
    lines += [
        "",
        "## 11. Abstention analysis",
        "",
        f"INTERNAL HOLDOUT: good abstentions `{good}`, bad abstentions `{bad}`. "
        "Weak ambiguous evidence can still produce a leading rank while "
        "`selected_styles` remains empty.",
        "",
        "## 12. Limitations",
        "",
        "The corpus has only 35 authored fixtures. The split is internal, small and "
        "not independent external validation. Scores depend on existing heuristic "
        "detectors and optional legacy stratification/sentiment resources. No forensic "
        "or expert significance is assigned automatically.",
        "",
        "## 13. Future detector coverage",
        "",
        "Broader corpus validation is required before any production switch. "
        "Publicistic recall should next be studied through independently justified "
        "METHOD detector coverage, not further threshold relaxation. No missing "
        "detector is implemented in Patch C.2.",
        "",
        "## Full-corpus calibrated shadow result",
        "",
        _metric_line(calibrated_full),
        "",
        "## Engineering performance",
        "",
        f"Warm development-corpus timing: V1 `{runtime['v1_total_seconds']:.6f}` s; "
        f"V2 `{runtime['v2_total_seconds']:.6f}` s; mean V2 "
        f"`{runtime['v2_mean_ms_per_document']:.3f}` ms/document. Timing is an "
        "engineering benchmark, not a scientific metric; the selection gates use "
        "constant-time comparisons per style.",
        "",
    ]
    return "\n".join(lines)


def run() -> dict:
    fixtures = load_fixtures()
    split = load_and_verify_split(fixtures)

    # Freeze and report Patch C behavior before any optimizer call.
    baseline_analysis = analyze_fixtures(
        fixtures, LEGACY_STYLE_SELECTION_PARAMETERS)
    baseline_metrics = _metrics(fixtures, baseline_analysis)
    score_rows = _score_rows(fixtures, baseline_analysis)
    detector_rows = _detector_rows(fixtures, baseline_analysis)

    calibration_fixtures = _partition(fixtures, split["calibration_ids"])
    calibration_baseline_analysis = analyze_fixtures(
        calibration_fixtures, LEGACY_STYLE_SELECTION_PARAMETERS)
    calibration_records = _records(
        calibration_fixtures, calibration_baseline_analysis,
        CALIBRATION_PARTITION)
    winner, grid_rows = optimize_style_selection(calibration_records)
    if winner.parameters != CALIBRATED_STYLE_SELECTION_PARAMETERS:
        raise RuntimeError(
            "frozen runtime parameters differ from DEVELOPMENT CALIBRATION winner: "
            f"{winner.parameters!r}")
    calibration_final_analysis = analyze_fixtures(
        calibration_fixtures, winner.parameters)

    # INTERNAL HOLDOUT is evaluated only after the winning parameters are frozen.
    holdout_fixtures = _partition(fixtures, split["holdout_ids"])
    holdout_baseline_analysis = analyze_fixtures(
        holdout_fixtures, LEGACY_STYLE_SELECTION_PARAMETERS)
    holdout_final_analysis = analyze_fixtures(holdout_fixtures, winner.parameters)
    calibrated_full_analysis = analyze_fixtures(fixtures, winner.parameters)

    calibration_baseline = _metrics(
        calibration_fixtures, calibration_baseline_analysis)
    calibration_final = _metrics(calibration_fixtures, calibration_final_analysis)
    holdout_baseline = _metrics(holdout_fixtures, holdout_baseline_analysis)
    holdout_final = _metrics(holdout_fixtures, holdout_final_analysis)
    calibrated_full = _metrics(fixtures, calibrated_full_analysis)
    holdout_per_style = calculate_per_style(
        holdout_fixtures, holdout_final_analysis["v2_predictions"])
    runtime = {
        "v1_total_seconds": round(calibrated_full_analysis["v1_seconds"], 6),
        "v2_total_seconds": round(calibrated_full_analysis["v2_seconds"], 6),
        "v2_mean_ms_per_document": round(
            calibrated_full_analysis["v2_seconds"] * 1000 / len(fixtures), 3),
    }

    _write_csv(_SCORE_CSV, score_rows)
    _write_csv(_DETECTOR_CSV, detector_rows)
    _ERROR_MD.write_text(_error_report(
        fixtures, baseline_analysis, baseline_metrics, detector_rows), "utf-8")
    _CALIBRATION_MD.write_text(_calibration_report(
        baseline_metrics, calibrated_full,
        calibration_baseline, calibration_final,
        holdout_baseline, holdout_final, holdout_per_style,
        grid_rows, split, holdout_fixtures, holdout_final_analysis, runtime), "utf-8")

    return {
        "label": "DEVELOPMENT CALIBRATION / INTERNAL HOLDOUT — NOT VALIDATION",
        "winner": {
            "strategy": winner.strategy,
            "parameters": winner.parameters.as_dict(),
        },
        "baseline": baseline_metrics,
        "calibration_baseline": calibration_baseline,
        "calibration": calibration_final,
        "holdout_baseline": holdout_baseline,
        "holdout": holdout_final,
        "holdout_per_style": holdout_per_style,
        "calibrated_full": calibrated_full,
        "runtime": runtime,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = run()
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, "utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
