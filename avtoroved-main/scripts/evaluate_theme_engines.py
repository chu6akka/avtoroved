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
from pathlib import Path
from typing import Iterable


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
from analyzer.semantic_layers.theme_engine_v2 import ThemeEngineV2  # noqa: E402


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
    theme_ids = tuple(legacy_theme.DOMAIN_META)
    total_tp = total_fp = total_fn = 0
    per_theme_f1: list[float] = []
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
    for theme_id in theme_ids:
        tp = fp = fn = 0
        for fixture, predicted in zip(fixtures, predictions):
            expected = set(fixture["expected_themes"])
            tp += int(theme_id in expected and theme_id in predicted)
            fp += int(theme_id not in expected and theme_id in predicted)
            fn += int(theme_id in expected and theme_id not in predicted)
        precision = _safe_ratio(tp, tp + fp)
        recall = _safe_ratio(tp, tp + fn)
        per_theme_f1.append(
            _safe_ratio(2 * precision * recall, precision + recall))
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
        "macro_f1": round(sum(per_theme_f1) / len(per_theme_f1), 6),
    }


def evaluate(fixtures: list[dict], backend=None) -> dict:
    lemmatize = LazyRussianLemmatizer()
    v1_engine = legacy_theme.ThematicEngine()
    v1_predictions: list[set[str]] = []
    v1_dominant: list[str | None] = []
    for fixture in fixtures:
        lemmas = [lemmatize(match.group())
                  for match in _WORD_RE.finditer(fixture["text"])]
        result = v1_engine.analyze(lemmas)
        v1_predictions.append({row.key for row in result.top_domains})
        v1_dominant.append(result.top_domains[0].key if result.top_domains else None)

    backend = backend or SentenceTransformerEmbeddingBackend()
    v2_engine = ThemeEngineV2(embedding_backend=backend)
    v2_predictions: list[set[str]] = []
    v2_dominant: list[str | None] = []
    v2_status = "ok"
    v2_reason = None
    for fixture in fixtures:
        result = v2_engine.analyze(fixture["text"])
        if result.status != "ok":
            v2_status = result.status
            v2_reason = result.reason
            break
        v2_predictions.append({
            row.theme_id for row in result.themes
            if row.segment_support_count > 0
        })
        v2_dominant.append(
            result.dominant_theme.theme_id if result.dominant_theme else None)

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
    }
    if v2_status == "ok":
        output["v2"] = calculate_metrics(
            fixtures, v2_predictions, v2_dominant)
        if backend.model_info.get("test_only"):
            output["v2_label"] = "DETERMINISTIC TEST BACKEND METRICS"
        else:
            output["v2_label"] = "REAL LOCAL EMBEDDING DEVELOPMENT METRICS"
    else:
        output["v2_label"] = "REAL V2 EVALUATION NOT RUN"
    return output


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
    args = parser.parse_args(list(argv) if argv is not None else None)
    backend = (
        DeterministicEmbeddingBackend() if args.deterministic
        else SentenceTransformerEmbeddingBackend()
    )
    report = evaluate(
        load_fixtures(include_hard=not args.development_only), backend=backend)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
