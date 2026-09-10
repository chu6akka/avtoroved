"""Офлайн-прогон Core по слепым парам Pilot 01 без оценки авторства."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
from time import perf_counter

from authoroved_core import __version__
from authoroved_core.core.analysis import AnalysisService
from authoroved_core.core.comparison import compare_results
from authoroved_core.core.document import load_document
from authoroved_core.nlp.settings import LocalSettings


def _check_spans(result, text_length: int) -> list[str]:
    issues = []
    collections = [
        ("токен", (token.span for token in result.tokens if token.span is not None)),
        ("кандидат", (candidate.span for candidate in result.candidates)),
        ("показатель", (span for metric in result.metrics for span in metric.spans)),
    ]
    for title, spans in collections:
        for span in spans:
            if span.start < 0 or span.end < span.start or span.end > text_length:
                issues.append(f"Некорректный диапазон ({title}): {span.start}:{span.end}")
    return issues


def _read_cases(corpus: Path, limit: int | None) -> list[tuple[str, Path, Path]]:
    table = corpus / "cases_public.csv"
    with table.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if limit is not None:
        rows = rows[:limit]
    return [
        (row["case_id"], corpus / row["document_a"], corpus / row["document_b"])
        for row in rows
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus", type=Path,
        default=Path("avtoroved-main/artifacts/pilot01_corpus"),
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--output", type=Path,
        default=Path("authoroved_core/artifacts/pilot01_engineering.json"),
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit должен быть положительным числом")

    network_attempts: list[str] = []

    def forbid_network(sock, address):
        network_attempts.append(str(address))
        raise RuntimeError("Сетевые соединения запрещены во время пилотного прогона")

    socket.socket.connect = forbid_network
    socket.socket.connect_ex = forbid_network

    service = AnalysisService(LocalSettings.load())
    cases = _read_cases(args.corpus, args.limit)
    started = perf_counter()
    case_reports = []
    failures = []
    for case_id, first_path, second_path in cases:
        case_started = perf_counter()
        try:
            documents = [load_document(first_path), load_document(second_path)]
            results = [service.analyze(document) for document in documents]
            comparison = compare_results(results[0], results[1])
            issues = [message for result in results for message in result.errors]
            for document, result in zip(documents, results):
                issues.extend(_check_spans(result, len(document.text)))
            if not comparison.metrics:
                issues.append("Сопоставление не содержит измеримых показателей.")
            if hasattr(comparison, "score") or hasattr(comparison, "verdict"):
                issues.append("Обнаружена запрещённая автоматическая оценка авторства.")
            status = "пройдено" if not issues else "ошибка"
            report = {
                "case_id": case_id,
                "status": status,
                "documents": [
                    {
                        "name": document.name,
                        "sha256": document.file_sha256,
                        "characters": len(document.text),
                        "tokens": len(result.tokens),
                        "metrics": len(result.metrics),
                        "candidates": len(result.candidates),
                    }
                    for document, result in zip(documents, results)
                ],
                "comparison_metrics": len(comparison.metrics),
                "accepted_observations": len(comparison.accepted_groups),
                "limitations": list(comparison.limitations),
                "issues": issues,
                "seconds": round(perf_counter() - case_started, 3),
            }
            case_reports.append(report)
            if issues:
                failures.append(case_id)
            print(f"{case_id}: {status} · {report['seconds']} с", flush=True)
        except Exception as exc:
            failures.append(case_id)
            case_reports.append({
                "case_id": case_id,
                "status": "сбой",
                "issues": [f"{type(exc).__name__}: {exc}"],
                "seconds": round(perf_counter() - case_started, 3),
            })
            print(f"{case_id}: сбой · {type(exc).__name__}: {exc}", flush=True)

    report = {
        "kind": "инженерный офлайн-пилот без оценки авторства",
        "program_version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus": str(args.corpus),
        "cases_requested": len(cases),
        "cases_passed": len(cases) - len(failures),
        "cases_failed": failures,
        "python_network_attempts": network_attempts,
        "total_seconds": round(perf_counter() - started, 3),
        "cases": case_reports,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "cases_requested", "cases_passed", "cases_failed",
        "python_network_attempts", "total_seconds",
    )}, ensure_ascii=False), flush=True)
    if failures or network_attempts:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
