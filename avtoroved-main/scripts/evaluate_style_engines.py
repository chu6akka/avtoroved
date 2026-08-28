"""DEVELOPMENT evaluator for production StyleEngineV1 and shadow V2."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Iterable


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from analyzer import senti_engine  # noqa: E402
from analyzer.semantic_layers.style_detectors import STYLE_LABELS  # noqa: E402
from analyzer.semantic_layers.style_engine import StyleEngine  # noqa: E402
from analyzer.semantic_layers.style_engine_v2 import StyleEngineV2  # noqa: E402


_FIXTURE_DIR = _ROOT / "tests" / "fixtures" / "style_v2"
_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+")


def load_fixtures() -> list[dict]:
    fixtures: list[dict] = []
    for name in ("clear.json", "hard_cases.json"):
        fixtures.extend(json.loads((_FIXTURE_DIR / name).read_text("utf-8")))
    return fixtures


def _ratio(a: int, b: int) -> float:
    return a / b if b else 0.0


def calculate_metrics(fixtures: list[dict], predictions: list[set[str]],
                      dominant: list[str | None]) -> dict:
    tp = fp = fn = top1 = 0
    for fixture, predicted, first in zip(fixtures, predictions, dominant):
        expected = set(fixture["expected_styles"])
        tp += len(expected & predicted)
        fp += len(predicted - expected)
        fn += len(expected - predicted)
        top1 += int((first in expected) or (first is None and not expected))
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = _ratio(2 * precision * recall, precision + recall)
    per_style = calculate_per_style(fixtures, predictions)
    mixed = [index for index, fixture in enumerate(fixtures)
             if len(fixture["expected_styles"]) > 1]
    mixed_expected = sum(len(fixtures[index]["expected_styles"]) for index in mixed)
    mixed_hits = sum(len(set(fixtures[index]["expected_styles"])
                         & predictions[index]) for index in mixed)
    return {
        "top1_accuracy": round(_ratio(top1, len(fixtures)), 6),
        "micro_precision": round(precision, 6),
        "micro_recall": round(recall, 6),
        "micro_f1": round(f1, 6),
        "macro_f1": round(sum(row["f1"] for row in per_style.values())
                          / len(per_style), 6),
        "average_selected_styles": round(
            sum(len(row) for row in predictions) / len(fixtures), 6),
        "abstention_count": sum(not row for row in predictions),
        "mixed_case_recall": round(_ratio(mixed_hits, mixed_expected), 6),
    }


def calculate_per_style(fixtures: list[dict], predictions: list[set[str]]) -> dict:
    output = {}
    for style_id in STYLE_LABELS:
        tp = fp = fn = 0
        for fixture, predicted in zip(fixtures, predictions):
            expected = set(fixture["expected_styles"])
            tp += int(style_id in expected and style_id in predicted)
            fp += int(style_id not in expected and style_id in predicted)
            fn += int(style_id in expected and style_id not in predicted)
        precision = _ratio(tp, tp + fp)
        recall = _ratio(tp, tp + fn)
        output[style_id] = {
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "f1": round(_ratio(2 * precision * recall, precision + recall), 6),
            "support": sum(style_id in fixture["expected_styles"]
                           for fixture in fixtures),
        }
    return output


def _legacy_metrics(text: str) -> dict:
    lengths = [len(_WORD_RE.findall(sentence)) for sentence in
               re.split(r"[.!?]+", text) if _WORD_RE.findall(sentence)]
    return {"дополнительно": {"Средняя длина предложения (слов)": (
        sum(lengths) / len(lengths) if lengths else 0.0)}}


def evaluate(fixtures: list[dict] | None = None) -> dict:
    fixtures = fixtures or load_fixtures()
    v1_engine = StyleEngine()
    v2_engine = StyleEngineV2()
    sentiment = senti_engine.get()
    sentiment.load()

    v1_results = []
    v1_dominant: list[str | None] = []
    started = time.perf_counter()
    for fixture in fixtures:
        result = v1_engine.analyze(fixture["text"])
        v1_results.append(result)
        label = v1_engine.leading_style(_legacy_metrics(fixture["text"]), result)
        v1_dominant.append(
            "conversational" if label == "разговорно-сниженный" else None)
    v1_seconds = time.perf_counter() - started

    v2_results = []
    v2_predictions: list[set[str]] = []
    v2_dominant: list[str | None] = []
    started = time.perf_counter()
    for fixture, stratification in zip(fixtures, v1_results):
        sentiment_result = sentiment.analyze(fixture["text"])
        result = v2_engine.analyze(
            fixture["text"], stratification_result=stratification,
            sentiment_result=sentiment_result)
        v2_results.append(result)
        v2_predictions.append({row.style_id for row in result.selected_styles})
        v2_dominant.append(
            result.leading_style.style_id if result.leading_style else None)
    v2_seconds = time.perf_counter() - started

    v1_correct = sum(
        dominant in fixture["expected_styles"]
        or (dominant is None and not fixture["expected_styles"])
        for fixture, dominant in zip(fixtures, v1_dominant))
    report = {
        "label": "DEVELOPMENT METRICS — NOT SCIENTIFIC VALIDATION",
        "fixture_count": len(fixtures),
        "clear_count": sum(not fixture["id"].startswith("hard_")
                           for fixture in fixtures),
        "hard_count": sum(fixture["id"].startswith("hard_")
                          for fixture in fixtures),
        "v1": {"top1_accuracy": round(_ratio(v1_correct, len(fixtures)), 6)},
        "v2": calculate_metrics(fixtures, v2_predictions, v2_dominant),
        "v2_per_style": calculate_per_style(fixtures, v2_predictions),
        "runtime": {
            "v1_total_seconds": round(v1_seconds, 6),
            "v2_total_seconds": round(v2_seconds, 6),
            "v2_mean_ms_per_document": round(v2_seconds * 1000 / len(fixtures), 3),
            "parsed_document_reused": False,
            "stanza_started_by_v2": False,
            "note": "Evaluator supplies existing V1 stratification; no parsed tokens were available.",
        },
        "hard_cases": [
            {
                "id": fixture["id"],
                "expected": fixture["expected_styles"],
                "selected": sorted(predicted),
                "leading": dominant,
            }
            for fixture, predicted, dominant in zip(
                fixtures, v2_predictions, v2_dominant)
            if fixture["id"].startswith("hard_")
        ],
    }
    return report


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = evaluate()
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
