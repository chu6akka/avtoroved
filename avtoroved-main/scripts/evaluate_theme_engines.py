"""DEVELOPMENT METRICS для V1/V2 на локальных тематических fixtures.

Это не научная валидация. По умолчанию V2 использует только локально
установленную embedding model; отсутствие зависимости/весов даёт честный
``REAL V2 EVALUATION NOT RUN`` без сетевой загрузки.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Callable, Iterable


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from analyzer import thematic_engine as legacy_theme  # noqa: E402
from analyzer.semantic_layers.embedding_backend import (  # noqa: E402
    DeterministicEmbeddingBackend,
    SentenceTransformerEmbeddingBackend,
)
from analyzer.semantic_layers.lexical_theme_evidence import (  # noqa: E402
    LazyRussianLemmatizer,
)
from analyzer.semantic_layers.theme_engine_v2 import (  # noqa: E402
    ThemeEngineV2,
    clear_prototype_embedding_cache,
)


_FIXTURE_DIR = _ROOT / "tests" / "fixtures" / "theme_v2"
_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+(?:[-'][A-Za-zА-Яа-яЁё0-9]+)*")


def load_fixtures(include_hard: bool = True) -> list[dict]:
    names = ["development.json"]
    if include_hard:
        names.append("hard_cases.json")
    fixtures: list[dict] = []
    for name in names:
        payload = json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))
        fixtures.extend(payload)
    return fixtures


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def calculate_metrics(fixtures: list[dict], predictions: list[set[str]],
                      dominant: list[str | None]) -> dict:
    total_tp = total_fp = total_fn = 0
    top1_correct = 0
    for fixture, predicted, predicted_dominant in zip(
            fixtures, predictions, dominant):
        expected = set(fixture["expected_themes"])
        total_tp += len(expected & predicted)
        total_fp += len(predicted - expected)
        total_fn += len(expected - predicted)
        if ((predicted_dominant in expected)
                or (predicted_dominant is None and not expected)):
            top1_correct += 1
    per_theme = calculate_per_theme(fixtures, predictions)
    micro_precision = _safe_ratio(total_tp, total_tp + total_fp)
    micro_recall = _safe_ratio(total_tp, total_tp + total_fn)
    micro_f1 = _safe_ratio(
        2 * micro_precision * micro_recall,
        micro_precision + micro_recall,
    )
    return {
        "top1_accuracy": round(_safe_ratio(top1_correct, len(fixtures)), 6),
        "micro_precision": round(micro_precision, 6),
        "micro_recall": round(micro_recall, 6),
        "micro_f1": round(micro_f1, 6),
        "macro_f1": round(
            sum(row["f1"] for row in per_theme.values()) / len(per_theme), 6),
        "average_labels_per_document": round(
            sum(len(predicted) for predicted in predictions) / len(fixtures), 6
        ) if fixtures else 0.0,
    }


def calculate_per_theme(fixtures: list[dict], predictions: list[set[str]]) -> dict:
    output: dict[str, dict] = {}
    for theme_id in legacy_theme.DOMAIN_META:
        tp = fp = fn = 0
        for fixture, predicted in zip(fixtures, predictions):
            expected = set(fixture["expected_themes"])
            tp += int(theme_id in expected and theme_id in predicted)
            fp += int(theme_id not in expected and theme_id in predicted)
            fn += int(theme_id in expected and theme_id not in predicted)
        precision = _safe_ratio(tp, tp + fp)
        recall = _safe_ratio(tp, tp + fn)
        f1 = _safe_ratio(2 * precision * recall, precision + recall)
        output[theme_id] = {
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "f1": round(f1, 6),
            "support": sum(
                theme_id in fixture["expected_themes"] for fixture in fixtures),
        }
    return output


def _run_v1(fixtures: list[dict]) -> tuple[list, list[set[str]], list[str | None], float]:
    started = time.perf_counter()
    lemmatize = LazyRussianLemmatizer()
    engine = legacy_theme.ThematicEngine()
    results: list = []
    predictions: list[set[str]] = []
    dominant: list[str | None] = []
    for fixture in fixtures:
        lemmas = [lemmatize(match.group())
                  for match in _WORD_RE.finditer(fixture["text"])]
        result = engine.analyze(lemmas)
        results.append(result)
        predictions.append({row.key for row in result.top_domains})
        dominant.append(result.top_domains[0].key if result.top_domains else None)
    return results, predictions, dominant, time.perf_counter() - started


def _run_v2(fixtures: list[dict], engine: ThemeEngineV2
            ) -> tuple[list, list[set[str]], list[str | None], str, str | None, float]:
    started = time.perf_counter()
    results: list = []
    predictions: list[set[str]] = []
    dominant: list[str | None] = []
    status = "ok"
    reason = None
    for fixture in fixtures:
        result = engine.analyze(fixture["text"])
        results.append(result)
        if result.status != "ok":
            status = result.status
            reason = result.reason
            break
        predictions.append({row.theme_id for row in result.selected_themes})
        dominant.append(
            result.dominant_theme.theme_id if result.dominant_theme else None)
    return (results, predictions, dominant, status, reason,
            time.perf_counter() - started)


def evaluate_detailed(fixtures: list[dict], backend=None) -> tuple[dict, list, list]:
    v1_results, v1_predictions, v1_dominant, v1_seconds = _run_v1(fixtures)
    backend = backend or SentenceTransformerEmbeddingBackend()
    v2_engine = ThemeEngineV2(embedding_backend=backend)
    (v2_results, v2_predictions, v2_dominant, v2_status, v2_reason,
     v2_seconds) = _run_v2(fixtures, v2_engine)

    output = {
        "label": "DEVELOPMENT METRICS — NOT SCIENTIFIC VALIDATION",
        "fixture_count": len(fixtures),
        "development_fixture_count": sum(
            not fixture["id"].startswith("hard_") for fixture in fixtures),
        "hard_case_count": sum(
            fixture["id"].startswith("hard_") for fixture in fixtures),
        "v1": calculate_metrics(fixtures, v1_predictions, v1_dominant),
        "v2": None,
        "v2_status": v2_status,
        "v2_reason": v2_reason,
        "backend": backend.model_info,
        "evaluation_runtime": {
            "v1_seconds": round(v1_seconds, 6),
            "v2_seconds": round(v2_seconds, 6),
        },
    }
    if v2_status == "ok":
        output["v2"] = calculate_metrics(
            fixtures, v2_predictions, v2_dominant)
        output["v2_per_theme"] = calculate_per_theme(fixtures, v2_predictions)
        if backend.model_info.get("test_only"):
            output["v2_label"] = "DETERMINISTIC TEST BACKEND METRICS"
        else:
            output["v2_label"] = "REAL LOCAL EMBEDDING DEVELOPMENT METRICS"
    else:
        output["v2_label"] = "REAL V2 EVALUATION NOT RUN"
    return output, v1_results, v2_results


def evaluate(fixtures: list[dict], backend=None) -> dict:
    report, _v1_results, _v2_results = evaluate_detailed(fixtures, backend)
    return report


def benchmark(fixtures: list[dict], backend_factory: Callable[[], object],
              process_cold_seconds: float | None = None) -> dict:
    _v1_results, _v1_predictions, _v1_dominant, v1_seconds = _run_v1(fixtures)
    clear_prototype_embedding_cache()
    engine = ThemeEngineV2(embedding_backend=backend_factory())
    (_cold_results, _cold_predictions, _cold_dominant, cold_status, cold_reason,
     cold_seconds) = _run_v2(fixtures, engine)
    if cold_status != "ok":
        return {
            "status": cold_status,
            "reason": cold_reason,
            "v1_total_seconds": round(v1_seconds, 6),
        }
    (_warm_results, _warm_predictions, _warm_dominant, warm_status, warm_reason,
     warm_seconds) = _run_v2(fixtures, engine)
    return {
        "status": warm_status,
        "reason": warm_reason,
        "v1_total_seconds": round(v1_seconds, 6),
        "v2_process_cold_total_seconds": (
            round(process_cold_seconds, 6)
            if process_cold_seconds is not None else None),
        "v2_reloaded_instance_seconds": round(cold_seconds, 6),
        "v2_warm_total_seconds": round(warm_seconds, 6),
        "v2_warm_mean_ms_per_document": round(
            warm_seconds * 1000 / len(fixtures), 3),
        "definition": (
            "process_cold=first evaluation in process; reloaded_instance=new "
            "model instance after libraries are warm; warm=same model instance+"
            "prototype cache"
        ),
    }


def _v1_label(result) -> str:
    dominant = result.top_domains[0].key if result.top_domains else "none"
    ranked = ", ".join(f"{row.key}:{row.cosine:.4f}" for row in result.top_domains)
    return f"dominant={dominant}; top=[{ranked}]"


def _v2_label(result, limit: int = 3) -> str:
    dominant = result.dominant_theme.theme_id if result.dominant_theme else "none"
    selected = ",".join(row.theme_id for row in result.selected_themes) or "none"
    ranked = ", ".join(
        f"{row.theme_id}:{row.combined_score:.4f}" for row in result.themes[:limit])
    return f"dominant={dominant}; selected=[{selected}]; ranked=[{ranked}]"


def _md(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def build_error_analysis(fixtures: list[dict], report: dict,
                         v1_results: list, v2_results: list) -> str:
    lines = [
        "# ThemeEngineV2 real development error analysis",
        "",
        "> DEVELOPMENT METRICS — NOT SCIENTIFIC VALIDATION. Thresholds, weights,",
        "> prototypes and fixtures were not tuned for this report.",
        "",
        "## Model",
        "",
        "```json",
        json.dumps(report["backend"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Aggregate metrics",
        "",
        "| Engine | top-1 | micro P | micro R | micro F1 | macro F1 |",
        "|---|---:|---:|---:|---:|---:|",
        (f"| V1 | {report['v1']['top1_accuracy']:.6f} | "
         f"{report['v1']['micro_precision']:.6f} | "
         f"{report['v1']['micro_recall']:.6f} | "
         f"{report['v1']['micro_f1']:.6f} | {report['v1']['macro_f1']:.6f} |"),
        (f"| REAL V2 | {report['v2']['top1_accuracy']:.6f} | "
         f"{report['v2']['micro_precision']:.6f} | "
         f"{report['v2']['micro_recall']:.6f} | "
         f"{report['v2']['micro_f1']:.6f} | {report['v2']['macro_f1']:.6f} |"),
        "",
        "## REAL V2 per-theme metrics",
        "",
        "| Theme | Precision | Recall | F1 | Support |",
        "|---|---:|---:|---:|---:|",
    ]
    for theme_id, row in report["v2_per_theme"].items():
        lines.append(
            f"| `{theme_id}` | {row['precision']:.6f} | {row['recall']:.6f} | "
            f"{row['f1']:.6f} | {row['support']} |")

    semantic_only: list[tuple[dict, object, object, int]] = []
    mixed: list[tuple[dict, object, object]] = []
    errors: list[tuple[dict, object, object, set[str], set[str], set[str]]] = []
    for fixture, v1_result, v2_result in zip(fixtures, v1_results, v2_results):
        expected = set(fixture["expected_themes"])
        v1_predicted = {row.key for row in v1_result.top_domains}
        v2_predicted = {row.theme_id for row in v2_result.selected_themes}
        if expected != v1_predicted or expected != v2_predicted:
            errors.append((fixture, v1_result, v2_result, expected,
                           v1_predicted, v2_predicted))
        if len(expected) == 1:
            expected_id = next(iter(expected))
            expected_row = next(
                row for row in v2_result.themes if row.theme_id == expected_id)
            max_unique = max(
                (evidence.lexical_unique_match_count
                 for evidence in expected_row.evidence), default=0)
            if max_unique < 2:
                semantic_only.append(
                    (fixture, v1_result, v2_result, max_unique))
        if len(expected) > 1:
            mixed.append((fixture, v1_result, v2_result))

    lines.extend([
        "",
        "## Semantic-only / weak-lexical cases",
        "",
        "Criterion: single expected theme and fewer than two unique lexical matches.",
        "",
        "| Fixture | Expected | Lexical unique | V1 | REAL V2 | Expected-theme scores |",
        "|---|---|---:|---|---|---|",
    ])
    for fixture, v1_result, v2_result, unique in semantic_only:
        expected_id = fixture["expected_themes"][0]
        row = next(item for item in v2_result.themes if item.theme_id == expected_id)
        lines.append(
            f"| `{fixture['id']}` | `{expected_id}` | {unique} | "
            f"{_md(_v1_label(v1_result))} | {_md(_v2_label(v2_result))} | "
            f"semantic={row.semantic_score:.4f}; lexical={row.lexical_score:.4f}; "
            f"coverage={row.coverage:.4f} |")

    lines.extend([
        "",
        "## Mixed-theme cases",
        "",
        "| Fixture | Expected | V1 | REAL V2 | Expected-theme coverage |",
        "|---|---|---|---|---|",
    ])
    for fixture, v1_result, v2_result in mixed:
        coverage = ", ".join(
            f"{theme_id}={next(row.coverage for row in v2_result.themes if row.theme_id == theme_id):.4f}"
            for theme_id in fixture["expected_themes"])
        lines.append(
            f"| `{fixture['id']}` | {_md(fixture['expected_themes'])} | "
            f"{_md(_v1_label(v1_result))} | {_md(_v2_label(v2_result))} | "
            f"{coverage} |")

    lines.extend([
        "",
        f"## Error fixtures ({len(errors)})",
        "",
    ])
    for fixture, v1_result, v2_result, expected, v1_predicted, v2_predicted in errors:
        lines.extend([
            f"### `{fixture['id']}`",
            "",
            f"- expected_themes: `{sorted(expected)}`",
            f"- V1 result: `{_v1_label(v1_result)}`; predicted `{sorted(v1_predicted)}`",
            f"- V2 predicted: `{sorted(v2_predicted)}`",
            "",
            "| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |",
            "|---:|---|---:|---:|---:|---:|---:|",
        ])
        for rank, row in enumerate(v2_result.themes, start=1):
            lines.append(
                f"| {rank} | `{row.theme_id}` | {row.combined_score:.6f} | "
                f"{row.semantic_score:.6f} | {row.lexical_score:.6f} | "
                f"{row.coverage:.6f} | {row.segment_support_count} |")
        lines.extend(["", "Top supporting segments:", ""])
        for row in v2_result.themes[:3]:
            supporting = sorted(
                row.evidence, key=lambda evidence: evidence.semantic_score,
                reverse=True)[:2]
            for evidence in supporting:
                fragment = _md(evidence.fragment[:220])
                lines.append(
                    f"- `{row.theme_id}` `{evidence.segment_id}` "
                    f"[{evidence.start}:{evidence.end}], semantic="
                    f"{evidence.semantic_score:.4f}, lexical="
                    f"{evidence.lexical_unique_match_count}: {fragment}")
        lines.append("")

    if report.get("benchmark"):
        lines.extend([
            "## Engineering benchmark",
            "",
            "```json",
            json.dumps(report["benchmark"], ensure_ascii=False, indent=2),
            "```",
            "",
        ])
    lines.extend([
        "## Interpretation",
        "",
        "V2 dominant-theme ranking and calibrated multi-label selection are reported",
        "separately. Scores remain engineering similarity/ranking values rather than",
        "probabilities; this small development corpus is not scientific validation.",
        "",
    ])
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--deterministic",
        action="store_true",
        help="использовать test-only hashing backend",
    )
    parser.add_argument(
        "--development-only",
        action="store_true",
        help="не включать hard cases",
    )
    parser.add_argument(
        "--benchmark", action="store_true",
        help="измерить cold/warm runtime на том же corpus",
    )
    parser.add_argument(
        "--error-report", type=Path,
        help="сохранить подробный Markdown error report",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    backend = (
        DeterministicEmbeddingBackend() if args.deterministic
        else SentenceTransformerEmbeddingBackend()
    )
    fixtures = load_fixtures(include_hard=not args.development_only)
    report, v1_results, v2_results = evaluate_detailed(fixtures, backend=backend)
    if args.benchmark:
        factory = (
            (lambda: DeterministicEmbeddingBackend()) if args.deterministic
            else (lambda: SentenceTransformerEmbeddingBackend())
        )
        report["benchmark"] = benchmark(
            fixtures, factory,
            process_cold_seconds=report["evaluation_runtime"]["v2_seconds"],
        )
    if args.error_report and report.get("v2") is not None:
        args.error_report.parent.mkdir(parents=True, exist_ok=True)
        args.error_report.write_text(
            build_error_analysis(fixtures, report, v1_results, v2_results),
            encoding="utf-8",
        )
        report["error_report"] = str(args.error_report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
