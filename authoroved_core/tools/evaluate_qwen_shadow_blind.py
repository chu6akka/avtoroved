"""Замер теневых признаков на неразмеченном корпусе Pilot 01.

Fixtures из `qwen_shadow_dev.json` использовались при настройке формулировок,
поэтому числа на них не являются оценкой признаков. Этот инструмент работает по
текстам, которых в настройке не было, и измеряет то, что можно измерить без
ручной разметки:

* частоту срабатывания каждого признака;
* нарушения собственных исключений признака, проверяемые детерминированно;
* лист для экспертного разбора со всеми кандидатами и их окружением.

Полнота здесь не измеряется: неизвестно, сколько реализаций признака в корпусе
на самом деле. Инструмент ничего не фильтрует и не подтверждает — проверки
нужны для замера, а не для отсечения кандидатов.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import re
from time import perf_counter

from authoroved_core.core.qwen_shadow import QwenShadowService
from authoroved_core.nlp.qwen_local import LlamaCppLocalProvider, LocalQwenConfig
from authoroved_core.nlp.qwen_server import LocalQwenServer, QwenServerSettings, file_sha256


DEFAULT_CORPUS = Path("avtoroved-main/artifacts/pilot01_corpus")
NARROW_PROFILES = ("phonetic_imitation", "internet_lexicon")
CORPUS_SAMPLE_SEED = 20260917

LATIN = re.compile(r"[A-Za-z]")
TRIPLED_LETTER = re.compile(r"(\w)\1\1", re.UNICODE)
REPEATED_PUNCTUATION = re.compile(r"([!?.])\1")


def iter_corpus_documents(root: Path) -> list[tuple[str, str]]:
    """Тексты blind-каталога в устойчивом порядке: blind/CASE_XXX/TEXT_?.txt."""
    blind = Path(root) / "blind"
    if not blind.is_dir():
        raise FileNotFoundError(
            f"Не найден каталог {blind}. Укажите корень корпуса через --corpus."
        )
    documents = []
    for path in sorted(blind.glob("*/TEXT_*.txt")):
        documents.append((f"{path.parent.name}/{path.name}", path.read_text(encoding="utf-8")))
    if not documents:
        raise FileNotFoundError(f"В {blind} нет файлов TEXT_*.txt.")
    return documents


def exclusion_violations(feature_id: str, quote: str) -> tuple[str, ...]:
    """Нарушения, проверяемые без модели и без ручной разметки.

    Правила, выведенные из исключений GRA_103 и LEX_201, изъяты вместе с самими
    признаками. Осталась проверка, не привязанная к признаку и описавшая главный
    отказ замера: цитата длиннее одного слова встретилась в 20 случаях из 25,
    то есть модель выделяла фрагмент текста, а не реализацию признака.
    """
    found = []
    if len(quote.split()) > 1:
        found.append("цитата не является отдельным словом")
    return tuple(found)


def _context(text: str, start: int, end: int, width: int = 45) -> str:
    left = text[max(0, start - width):start]
    right = text[end:end + width]
    return f"…{left}[{text[start:end]}]{right}…".replace("\n", " ")


def evaluate_blind(service: QwenShadowService, documents, profile_ids):
    """Прогон профилей по корпусу. Возвращает отчёт и лист для эксперта."""
    started = perf_counter()
    rows, per_feature, statuses = [], {}, {}
    runs = 0
    for document_id, text in documents:
        for run in service.analyze(text, tuple(profile_ids)):
            runs += 1
            statuses[run.status.value] = statuses.get(run.status.value, 0) + 1
            for candidate in run.candidates:
                span = candidate.evidence.span
                violations = exclusion_violations(candidate.feature_id, candidate.evidence.quote)
                stats = per_feature.setdefault(
                    candidate.feature_id, {"candidates": 0, "violations": 0},
                )
                stats["candidates"] += 1
                stats["violations"] += bool(violations)
                rows.append({
                    "document_id": document_id,
                    "profile_id": run.profile_id,
                    "feature_id": candidate.feature_id,
                    "quote": candidate.evidence.quote,
                    "start": span.start,
                    "end": span.end,
                    "context": _context(text, span.start, span.end),
                    "machine_violations": "; ".join(violations),
                    "expert_verdict": "",
                })
    report = {
        "kind": "Qwen shadow measurement on unlabelled Pilot 01 texts; not authorship validation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "documents": len(documents),
        "profiles": list(profile_ids),
        "runs": runs,
        "total_seconds": round(perf_counter() - started, 3),
        "statuses": statuses,
        "candidates": len(rows),
        "per_feature": per_feature,
        "note": (
            "Полнота не измеряется: корпус не размечен. Нарушения исключений "
            "проверены детерминированно и являются нижней оценкой числа ложных "
            "срабатываний; остальные кандидаты требуют решения эксперта."
        ),
    }
    return report, rows


def _write_review_sheet(path: Path, rows) -> None:
    fields = ["document_id", "profile_id", "feature_id", "quote", "start", "end",
              "context", "machine_violations", "expert_verdict"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--limit", type=int, default=40,
                        help="сколько текстов взять; 0 — весь корпус")
    parser.add_argument("--profiles", nargs="+", default=list(NARROW_PROFILES))
    parser.add_argument("--output", type=Path,
                        default=Path("authoroved_core/artifacts/qwen_shadow_blind.json"))
    parser.add_argument("--review", type=Path,
                        default=Path("authoroved_core/artifacts/qwen_shadow_blind_review.csv"))
    parser.add_argument("--port", type=int, default=8089)
    args = parser.parse_args()

    documents = iter_corpus_documents(args.corpus)
    if args.limit:
        # Фиксированный seed: та же выборка при повторном запуске.
        documents = random.Random(CORPUS_SAMPLE_SEED).sample(
            documents, min(args.limit, len(documents)),
        )
        documents.sort()

    settings = QwenServerSettings(args.runtime.resolve(), args.model.resolve(), port=args.port)
    server = LocalQwenServer(settings, Path("authoroved_core/.local/qwen/llama-server.log"))
    model_hash = file_sha256(settings.model)
    runtime_version = server.version()
    with server:
        provider = LlamaCppLocalProvider(LocalQwenConfig(
            endpoint=server.endpoint, model_name=settings.model.name,
            model_sha256=model_hash, runtime_version=runtime_version,
            api_key=server.api_key,
        ))
        report, rows = evaluate_blind(QwenShadowService(provider), documents, args.profiles)

    report["model_name"] = settings.model.name
    report["model_sha256"] = model_hash
    report["runtime_version"] = runtime_version
    report["corpus"] = str(args.corpus)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_review_sheet(args.review, rows)
    print(json.dumps({key: report[key] for key in (
        "documents", "runs", "candidates", "per_feature", "total_seconds",
    )}, ensure_ascii=False))


if __name__ == "__main__":
    main()
