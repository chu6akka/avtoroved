"""Запускает реальный локальный Qwen по малому теневому корпусу."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter

from authoroved_core.core.qwen_shadow import QwenShadowService
from authoroved_core.core.qwen_theme import QwenThemeService
from authoroved_core.nlp.qwen_local import LlamaCppLocalProvider, LocalQwenConfig
from authoroved_core.nlp.qwen_server import (
    LocalQwenServer, QwenServerSettings, file_sha256,
)


DEFAULT_FIXTURES = Path(__file__).parents[1] / "tests" / "fixtures" / "qwen_shadow_dev.json"
DEFAULT_THEME_FIXTURES = Path(__file__).parents[1] / "tests" / "fixtures" / "qwen_theme_dev.json"


def _candidate(item):
    return {
        "feature_id": item.feature_id,
        "quote": item.evidence.quote,
        "start": item.evidence.span.start,
        "end": item.evidence.span.end,
    }


def _candidate_evidence(item):
    return {
        "quote": item.quote,
        "start": item.span.start,
        "end": item.span.end,
    }


def evaluate(endpoint: str, fixtures_path: Path, theme_fixtures_path: Path,
             output_path: Path, *,
             model_name: str, model_hash: str, runtime_version: str,
             repeatability_trials: int = 3, api_key: str = ""):
    fixtures = json.loads(fixtures_path.read_text(encoding="utf-8"))
    provider = LlamaCppLocalProvider(LocalQwenConfig(
        endpoint=endpoint, model_name=model_name, model_sha256=model_hash,
        runtime_version=runtime_version, api_key=api_key,
    ))
    service = QwenShadowService(provider)
    theme_service = QwenThemeService(provider)
    cases = []
    started = perf_counter()
    for fixture in fixtures:
        runs = service.analyze(fixture["text"])
        case_runs = []
        for run in runs:
            detected = sorted({item.feature_id for item in run.candidates})
            case_runs.append({
                "profile_id": run.profile_id,
                "profile_version": run.profile_version,
                "status": run.status.value,
                "detected_feature_ids": detected,
                "candidates": [_candidate(item) for item in run.candidates],
                "raw_response": run.raw_response,
                "provider_metadata": run.provider_metadata,
                "rejection_reason": run.rejection_reason,
                "expert_use_allowed": run.expert_use_allowed,
                "matches_expected_set": (
                    run.status.value != "SYSTEM_REJECTED"
                    and detected == sorted(fixture["expected_feature_ids"])
                ),
            })
        cases.append({
            "fixture_id": fixture["id"],
            "expected_feature_ids": fixture["expected_feature_ids"],
            "runs": case_runs,
        })
    repeated = []
    if fixtures and repeatability_trials > 0:
        fixture = fixtures[0]
        for _ in range(repeatability_trials):
            run = service.analyze(fixture["text"], ("internet_communication",))[0]
            repeated.append({
                "status": run.status.value,
                "detected_feature_ids": sorted({item.feature_id for item in run.candidates}),
                "raw_response": run.raw_response,
            })
    candidate_sets = [item["detected_feature_ids"] for item in repeated]
    raw_responses = [item["raw_response"] for item in repeated]
    theme_cases = []
    theme_fixtures = json.loads(theme_fixtures_path.read_text(encoding="utf-8"))
    for fixture in theme_fixtures:
        run = theme_service.analyze(fixture["text"])
        labels = [item.label for item in run.candidates]
        searchable = " ".join(labels).casefold()
        expected_terms = [item.casefold() for item in fixture["expected_any_terms"]]
        theme_cases.append({
            "fixture_id": fixture["id"],
            "status": run.status.value,
            "labels": labels,
            "candidates": [{
                "label": item.label,
                "evidence": [_candidate_evidence(value) for value in item.evidence],
            } for item in run.candidates],
            "raw_response": run.raw_response,
            "rejection_reason": run.rejection_reason,
            "expert_use_allowed": run.expert_use_allowed,
            "matches_expected_concept": (
                bool(expected_terms) and any(term in searchable for term in expected_terms)
            ),
        })
    repeated_themes = []
    if theme_fixtures and repeatability_trials > 0:
        fixture = theme_fixtures[0]
        for _ in range(repeatability_trials):
            run = theme_service.analyze(fixture["text"])
            repeated_themes.append({
                "status": run.status.value,
                "labels": [item.label for item in run.candidates],
                "raw_response": run.raw_response,
            })
    report = {
        "kind": "Qwen shadow engineering evaluation; not authorship validation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_name": model_name,
        "model_sha256": model_hash,
        "runtime_version": runtime_version,
        "fixture_sha256": file_sha256(fixtures_path),
        "theme_fixture_sha256": file_sha256(theme_fixtures_path),
        "total_seconds": round(perf_counter() - started, 3),
        "runs": sum(len(item["runs"]) for item in cases),
        "system_rejections": sum(
            run["status"] == "SYSTEM_REJECTED" for item in cases for run in item["runs"]
        ),
        "exact_expected_sets": sum(
            run["matches_expected_set"] for item in cases for run in item["runs"]
        ),
        "repeatability": {
            "fixture_id": fixtures[0]["id"] if fixtures else None,
            "profile_id": "internet_communication" if fixtures else None,
            "trials": repeatability_trials if fixtures else 0,
            "candidate_sets_identical": len({json.dumps(item) for item in candidate_sets}) <= 1,
            "raw_responses_identical": len(set(raw_responses)) <= 1,
            "runs": repeated,
        },
        "theme_runs": len(theme_cases),
        "theme_system_rejections": sum(
            item["status"] == "SYSTEM_REJECTED" for item in theme_cases
        ),
        "theme_expected_concepts": sum(
            item["matches_expected_concept"] for item in theme_cases
        ),
        "theme_repeatability": {
            "fixture_id": theme_fixtures[0]["id"] if theme_fixtures else None,
            "trials": repeatability_trials if theme_fixtures else 0,
            "labels_identical": len({
                json.dumps(item["labels"], ensure_ascii=False) for item in repeated_themes
            }) <= 1,
            "raw_responses_identical": len({
                item["raw_response"] for item in repeated_themes
            }) <= 1,
            "runs": repeated_themes,
        },
        "theme_cases": theme_cases,
        "cases": cases,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "model_name", "total_seconds", "runs", "system_rejections", "exact_expected_sets",
        "theme_runs", "theme_system_rejections", "theme_expected_concepts",
    )}, ensure_ascii=False))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--theme-fixtures", type=Path, default=DEFAULT_THEME_FIXTURES)
    parser.add_argument("--output", type=Path,
                        default=Path("authoroved_core/artifacts/qwen_shadow_evaluation.json"))
    parser.add_argument("--port", type=int, default=8089)
    parser.add_argument("--repeatability-trials", type=int, default=3)
    args = parser.parse_args()
    settings = QwenServerSettings(args.runtime.resolve(), args.model.resolve(), port=args.port)
    server = LocalQwenServer(settings, Path("authoroved_core/.local/qwen/llama-server.log"))
    model_hash = file_sha256(settings.model)
    runtime_version = server.version()
    with server:
        evaluate(server.endpoint, args.fixtures, args.theme_fixtures, args.output,
                 model_name=settings.model.name, model_hash=model_hash,
                 runtime_version=runtime_version,
                 repeatability_trials=args.repeatability_trials,
                 api_key=server.api_key)


if __name__ == "__main__":
    main()
