from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import VALIDATION_FRAMEWORK_VERSION
from .agreement import expert_agreement
from .analyzer import ProductionValidationAnalyzer, SyntheticDemoAnalyzer
from .check_corpus import check_corpus
from .constants import FROZEN_ENGINE_CONFIG
from .evaluate_features import evaluate_features
from .evaluate_labels import evaluate_multilabel
from .evaluate_time import evaluate_time
from .io import load_json, load_jsonl, sha256_file, write_json, write_jsonl
from .models import make_blind_document
from .report import write_reports
from .schema import validate_annotation, validate_case


def _git_commit(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True,
            stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _selected_labels(raw: dict, layer: str) -> list[str]:
    value = raw.get(layer, {}) or {}
    if "selected_labels" in value:
        return list(value["selected_labels"])
    key = "selected_themes" if layer == "theme" else "selected_styles"
    id_key = "theme_id" if layer == "theme" else "style_id"
    return [row[id_key] for row in value.get(key, [])]


def run_validation(corpus: str | Path, annotations: str | Path,
                   output: str | Path, mode: str, *, analyzer=None,
                   run_id: str | None = None) -> Path:
    corpus_dir, annotation_dir = Path(corpus), Path(annotations)
    check = check_corpus(corpus_dir)
    if not check["valid"]:
        raise ValueError(f"Корпус не прошёл проверку: {check['error_count']} ошибок")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = run_id or f"{stamp}-{uuid.uuid4().hex[:8]}"
    run_dir = Path(output) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    rows = load_jsonl(corpus_dir / "manifest.jsonl")
    cases_path = corpus_dir / "cases.json"
    if cases_path.exists():
        for case in load_json(cases_path):
            validate_case(case)  # validation-only; never passed to analyzer
    annotation_path = annotation_dir / "expert_annotations.jsonl"
    annotations_rows = load_jsonl(annotation_path)
    for row in annotations_rows:
        validate_annotation(row)
    registry_path = annotation_dir / "feature_registry.json"
    registry = load_json(registry_path) if registry_path.exists() else {}
    analyzer = analyzer or ProductionValidationAnalyzer()
    raw = []
    for item in rows:
        text = (corpus_dir / item["text_path"]).read_text(encoding="utf-8")
        raw.append(analyzer.analyze(make_blind_document(item, text)))
    write_jsonl(run_dir / "raw_results.jsonl", raw)
    predictions = [candidate for result in raw for candidate in result.get("feature_candidates", [])]
    metrics = {
        "features": evaluate_features(predictions, annotations_rows, registry),
        "agreement": expert_agreement(annotations_rows),
    }
    for layer in ("theme", "style"):
        gold_path = annotation_dir / f"{layer}_annotations.jsonl"
        if gold_path.exists():
            predicted_labels = [{"document_id": row["document_id"],
                                 "labels": _selected_labels(row, layer)} for row in raw]
            metrics[layer] = evaluate_multilabel(
                predicted_labels, load_jsonl(gold_path), label_kind=layer)
    time_path = annotation_dir / "time_records.jsonl"
    if time_path.exists():
        metrics["time"] = evaluate_time(load_jsonl(time_path))
    repo_root = Path(__file__).resolve().parents[2]
    meta = {"run_id": run_id, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "mode": mode, "framework_version": VALIDATION_FRAMEWORK_VERSION,
            "git_commit": _git_commit(repo_root), "python_version": platform.python_version(),
            "synthetic_demo": all("synthetic demo" in row.get("notes", "").lower() for row in rows)}
    write_json(run_dir / "run_metadata.json", meta)
    write_json(run_dir / "corpus_check.json", check)
    write_json(run_dir / "metrics.json", metrics)
    write_json(run_dir / "config_snapshot.json", FROZEN_ENGINE_CONFIG)
    hashes = {
        "manifest": sha256_file(corpus_dir / "manifest.jsonl"),
        "annotations": sha256_file(annotation_path),
        "config_snapshot": sha256_file(run_dir / "config_snapshot.json"),
        "raw_results": sha256_file(run_dir / "raw_results.jsonl"),
        "metrics": sha256_file(run_dir / "metrics.json"),
    }
    write_json(run_dir / "hashes.json", hashes)
    write_reports(run_dir, meta, check, metrics)
    reports_dir = Path(output) / "reports"
    reports_dir.mkdir(exist_ok=True)
    (reports_dir / f"{run_id}.md").write_text(
        (run_dir / "report.md").read_text(encoding="utf-8"), encoding="utf-8")
    return run_dir


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Слепой корпусный прогон Автороведа")
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--annotations", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", required=True, choices=("pilot", "validation"))
    parser.add_argument("--synthetic-demo", action="store_true",
                        help="Использовать только для поставляемого демонстрационного корпуса")
    args = parser.parse_args(argv)
    analyzer = SyntheticDemoAnalyzer() if args.synthetic_demo else None
    run_dir = run_validation(args.corpus, args.annotations, args.output,
                             args.mode, analyzer=analyzer)
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
