"""Calculate feature-detection and time-motion metrics after Pilot 01."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean, median


def _truth(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "да"}


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def feature_metrics(rows: list[dict[str, str]]) -> dict:
    complete = [row for row in rows if row.get("feature_id")]
    tp = sum(_truth(row["program_detected"]) and _truth(row["expert_confirmed"]) for row in complete)
    fp = sum(_truth(row["program_detected"]) and _truth(row["expert_rejected"]) for row in complete)
    fn = sum((not _truth(row["program_detected"])) and _truth(row["expert_added_manually"]) for row in complete)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {
        "precision": precision, "recall": recall, "f1": f1,
        "confirmed_candidates": sum(_truth(row["expert_confirmed"]) for row in complete),
        "rejected_candidates": sum(_truth(row["expert_rejected"]) for row in complete),
        "features_added_manually": sum(_truth(row["expert_added_manually"]) for row in complete),
        "annotated_rows": len(complete),
    }


def time_metrics(rows: list[dict[str, str]]) -> dict:
    values = [row for row in rows if str(row.get("duration_seconds", "")).strip()]
    grouped: dict[tuple[str, str], list[float]] = {}
    paired: dict[tuple[str, str, str], dict[str, float]] = {}
    for row in values:
        duration = float(row["duration_seconds"])
        grouped.setdefault((row["mode"], row["stage"]), []).append(duration)
        paired.setdefault((row["case_id"], row["expert_id"], row["stage"]), {})[row["mode"]] = duration
    by_stage = {
        f"{mode}:{stage}": {"mean_seconds": mean(items), "median_seconds": median(items), "n": len(items)}
        for (mode, stage), items in sorted(grouped.items())
    }
    savings = []
    for modes in paired.values():
        if "MANUAL" in modes and "ASSISTED" in modes and modes["MANUAL"]:
            savings.append((modes["MANUAL"] - modes["ASSISTED"]) / modes["MANUAL"] * 100)
    return {
        "by_mode_and_stage": by_stage,
        "mean_saving_percent": mean(savings) if savings else None,
        "median_saving_percent": median(savings) if savings else None,
        "paired_measurements": len(savings),
    }


def reproducibility(rows: list[dict[str, str]]) -> dict:
    grouped: dict[str, set[str]] = {}
    for row in rows:
        if row.get("document_id") and row.get("result_sha256"):
            grouped.setdefault(row["document_id"], set()).add(row["result_sha256"])
    reproducible = sum(len(hashes) == 1 for hashes in grouped.values())
    return {
        "documents": len(grouped),
        "exactly_reproducible": reproducible,
        "rate": reproducible / len(grouped) if grouped else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--time-motion", type=Path, required=True)
    parser.add_argument("--reruns", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {
        "feature_detection": feature_metrics(_read(args.annotations)),
        "time_motion": time_metrics(_read(args.time_motion)),
        "reproducibility": reproducibility(_read(args.reruns)) if args.reruns else None,
        "excluded_metrics": [
            "same_author_accuracy", "author_identification_accuracy",
            "program_conclusion_accuracy", "probability_same_author",
        ],
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
