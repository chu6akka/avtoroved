"""Approved-corpus finalization for Pilot 01.

This module writes source texts and study bookkeeping only.  It does not import
or execute any Authoroved analyzer.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
from statistics import median
from typing import Any, Iterable

from .scanner import DATASET_ID, DEFAULT_REVISION, _author_rows, _connect, _write_csv


SEED = 20260907
PUBLIC_CASE_FIELDS = ["case_id", "document_a", "document_b"]
GOLD_CASE_FIELDS = ["case_id", "document_a", "document_b", "expected_relation"]
MANIFEST_FIELDS = [
    "document_id", "author_code", "source", "source_post_id", "date", "title",
    "source_url", "word_count", "char_count", "raw_path", "analysis_path",
    "raw_sha256", "analysis_sha256", "split", "is_reserve", "content_type",
    "tags", "selection_notes",
]


@dataclass(frozen=True)
class SelectedDocument:
    document_id: str
    author_code: str
    source_author_id: str
    username: str
    source_post_id: str
    date: str
    title: str
    source_url: str
    word_count: int
    char_count: int
    content_type: str
    tags: str
    raw_path: str
    analysis_path: str
    raw_sha256: str
    analysis_sha256: str
    is_reserve: bool


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def pseudonym_codes(count: int) -> list[str]:
    if count < 1 or count > 999:
        raise ValueError("author count must be between 1 and 999")
    return [f"A{index:03d}" for index in range(1, count + 1)]


def _read_selected_rows(connection, author_id: str) -> list[Any]:
    rows = connection.execute(
        """
        SELECT * FROM posts
        WHERE source_author_id = ? AND status = 'candidate'
        ORDER BY date BETWEEN '2017-01-01' AND '2021-12-31' DESC,
                 priority_score DESC, word_count BETWEEN 350 AND 650 DESC,
                 date, source_post_id
        """,
        (author_id,),
    ).fetchall()
    clean: list[Any] = []
    for row in rows:
        username = str(row["username"] or "").strip()
        text = str(row["text_markdown"] or "")
        # A literal source username in a text would disclose the blind mapping.
        if len(username) >= 4 and username.casefold() in text.casefold():
            continue
        clean.append(row)
        if len(clean) == 6:
            break
    return clean


def _write_exact_text(path: Path, text: str) -> str:
    payload = text.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return sha256_bytes(payload)


def choose_different_pairs(
    documents: list[SelectedDocument],
    seed: int = SEED,
) -> list[tuple[SelectedDocument, SelectedDocument]]:
    """Pair each supplied document once, preferring similar word counts."""
    if len(documents) % 2:
        raise ValueError("an even number of documents is required")
    rng = random.Random(seed)
    remaining = list(documents)
    rng.shuffle(remaining)
    pairs: list[tuple[SelectedDocument, SelectedDocument]] = []
    while remaining:
        left = remaining.pop()
        choices = [
            (abs(left.word_count - right.word_count), index, right)
            for index, right in enumerate(remaining)
            if right.author_code != left.author_code
        ]
        if not choices:
            raise ValueError("cannot create different-author pairs without document reuse")
        _, index, right = min(choices, key=lambda item: (item[0], item[2].document_id))
        remaining.pop(index)
        pairs.append((left, right))
    return pairs


def _ensure_final_targets_absent(root: Path) -> None:
    targets = [
        root / "source_authors_private.csv", root / "authors_public.csv",
        root / "manifest.csv", root / "processing_log.csv",
        root / "cases_public.csv", root / "cases_gold_private.csv",
        root / "raw", root / "analysis", root / "reserve_raw",
        root / "reserve_analysis", root / "blind",
    ]
    existing = [str(path) for path in targets if path.exists()]
    if existing:
        raise FileExistsError("final corpus targets already exist: " + ", ".join(existing))


MAX_AUTHORS = 200


def finalize_approved_corpus(
    root: Path,
    author_count: int = 15,
    seed: int = SEED,
    case_author_count: int | None = None,
) -> dict[str, Any]:
    """Собрать утверждённую выборку и слепые пары.

    `case_author_count` — сколько авторов участвует в парах; по умолчанию 10,
    как в Pilot 01. Пар «тот же автор» получается ровно столько же, поскольку с
    каждого автора берётся одна пара: пары от одного автора построены из одних
    и тех же текстов и независимыми наблюдениями не являются, поэтому объём
    выборки считается по авторам, а не по парам.
    """
    if author_count < 10 or author_count > MAX_AUTHORS:
        raise ValueError(f"требуется от 10 до {MAX_AUTHORS} авторов")
    case_author_count = 10 if case_author_count is None else case_author_count
    if case_author_count < 2 or case_author_count > author_count:
        raise ValueError("авторов в парах не может быть больше, чем отобрано")
    database = root / ".scan_state.sqlite3"
    if not database.exists():
        raise FileNotFoundError(f"scan state is missing: {database}")
    _ensure_final_targets_absent(root)

    connection = _connect(database)
    try:
        authors = [row for row in _author_rows(connection) if row["eligible_six_clean"]]
        if len(authors) < author_count:
            raise RuntimeError(f"only {len(authors)} authors have six clean documents")
        authors = authors[:author_count]
        codes = pseudonym_codes(author_count)
        selected: list[SelectedDocument] = []
        private_rows = []
        public_author_rows = []

        for rank, (author, code) in enumerate(zip(authors, codes), 1):
            source_author_id = str(author["source_author_id"])
            rows = _read_selected_rows(connection, source_author_id)
            if len(rows) < 6:
                raise RuntimeError(
                    f"{source_author_id} has fewer than six blind-safe clean documents"
                )
            private_rows.append({
                "author_code": code,
                "source_author_id": source_author_id,
                "username": author["username"],
                "profile_url_if_available": f"https://pikabu.ru/@{author['username']}" if author["username"] else "",
            })
            author_docs: list[SelectedDocument] = []
            for index, row in enumerate(rows, 1):
                reserve = index > 4
                suffix = f"R{index - 4:02d}" if reserve else f"T{index:02d}"
                document_id = f"{code}_{suffix}"
                raw_dir = "reserve_raw" if reserve else "raw"
                analysis_dir = "reserve_analysis" if reserve else "analysis"
                raw_rel = f"{raw_dir}/{document_id}.txt"
                analysis_rel = f"{analysis_dir}/{document_id}.txt"
                text = str(row["text_markdown"])
                raw_hash = _write_exact_text(root / raw_rel, text)
                # No linguistic or typographic normalization is applied in Pilot 01.
                analysis_hash = _write_exact_text(root / analysis_rel, text)
                doc = SelectedDocument(
                    document_id=document_id,
                    author_code=code,
                    source_author_id=source_author_id,
                    username=str(row["username"]),
                    source_post_id=str(row["source_post_id"]),
                    date=str(row["date"]),
                    title=str(row["title"]),
                    source_url=str(row["source_url"]),
                    word_count=int(row["word_count"]),
                    char_count=int(row["char_count"]),
                    content_type=str(row["content_type"]),
                    tags=str(row["tags"]),
                    raw_path=raw_rel,
                    analysis_path=analysis_rel,
                    raw_sha256=raw_hash,
                    analysis_sha256=analysis_hash,
                    is_reserve=reserve,
                )
                author_docs.append(doc)
                selected.append(doc)
            public_author_rows.append({
                "author_code": code,
                "main_docs_count": 4,
                "reserve_docs_count": 2,
                "first_date": min(doc.date for doc in author_docs),
                "last_date": max(doc.date for doc in author_docs),
                "median_words": median(doc.word_count for doc in author_docs),
                "source": "Pikabu",
                "status": "APPROVED_FOR_PILOT_01",
            })

        _write_csv(
            root / "source_authors_private.csv",
            ["author_code", "source_author_id", "username", "profile_url_if_available"],
            private_rows,
        )
        _write_csv(
            root / "authors_public.csv",
            [
                "author_code", "main_docs_count", "reserve_docs_count", "first_date",
                "last_date", "median_words", "source", "status",
            ],
            public_author_rows,
        )
        manifest_rows = []
        for doc in selected:
            manifest_rows.append({
                "document_id": doc.document_id,
                "author_code": doc.author_code,
                "source": "Pikabu",
                "source_post_id": doc.source_post_id,
                "date": doc.date,
                "title": doc.title,
                "source_url": doc.source_url,
                "word_count": doc.word_count,
                "char_count": doc.char_count,
                "raw_path": doc.raw_path,
                "analysis_path": doc.analysis_path,
                "raw_sha256": doc.raw_sha256,
                "analysis_sha256": doc.analysis_sha256,
                "split": "PILOT",
                "is_reserve": str(doc.is_reserve).lower(),
                "content_type": doc.content_type,
                "tags": doc.tags,
                "selection_notes": "manual shortlist approved; deterministic clean-candidate selection",
            })
        _write_csv(root / "manifest.csv", MANIFEST_FIELDS, manifest_rows)
        _write_csv(
            root / "processing_log.csv",
            ["document_id", "operation", "details", "before_chars", "after_chars"],
            [],
        )
        case_summary = _write_cases(root, selected, seed, case_author_count)
        _write_templates(root, case_summary["public_rows"])
        _write_final_selection_report(root, authors, selected)
        _write_final_readme(root, author_count, len(selected), seed, case_author_count)
        verification = validate_manifest(root)
        metadata = {
            "dataset_id": DATASET_ID,
            "dataset_revision": DEFAULT_REVISION,
            "finalized_at_utc": datetime.now(timezone.utc).isoformat(),
            "seed": seed,
            "author_count": author_count,
            "case_author_count": case_author_count,
            "main_document_count": sum(not doc.is_reserve for doc in selected),
            "reserve_document_count": sum(doc.is_reserve for doc in selected),
            "case_count": len(case_summary["public_rows"]),
            "raw_equals_analysis": all(doc.raw_sha256 == doc.analysis_sha256 for doc in selected),
            "manifest_verification": verification,
            "authoroved_analysis_run": False,
        }
        (root / "reports" / "finalization.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return metadata
    finally:
        connection.close()


def _write_cases(
    root: Path,
    selected: list[SelectedDocument],
    seed: int,
    case_author_count: int = 10,
) -> dict[str, Any]:
    main = [doc for doc in selected if not doc.is_reserve]
    by_author: dict[str, list[SelectedDocument]] = {}
    for doc in main:
        by_author.setdefault(doc.author_code, []).append(doc)
    pilot_authors = sorted(by_author)[:case_author_count]
    public_rows = []
    gold_rows = []
    case_number = 1

    for author_code in pilot_authors:
        docs = sorted(by_author[author_code], key=lambda item: item.document_id)
        public, gold = _write_blind_case(root, case_number, docs[0], docs[1], "SAME")
        public_rows.append(public)
        gold_rows.append(gold)
        case_number += 1

    different_pool = []
    for author_code in pilot_authors:
        docs = sorted(by_author[author_code], key=lambda item: item.document_id)
        different_pool.extend(docs[2:4])
    for left, right in choose_different_pairs(different_pool, seed):
        public, gold = _write_blind_case(root, case_number, left, right, "DIFFERENT")
        public_rows.append(public)
        gold_rows.append(gold)
        case_number += 1

    _write_csv(root / "cases_public.csv", PUBLIC_CASE_FIELDS, public_rows)
    _write_csv(root / "cases_gold_private.csv", GOLD_CASE_FIELDS, gold_rows)
    return {"public_rows": public_rows, "gold_rows": gold_rows}


def _write_blind_case(
    root: Path,
    number: int,
    left: SelectedDocument,
    right: SelectedDocument,
    relation: str,
) -> tuple[dict[str, str], dict[str, str]]:
    case_id = f"CASE_{number:03d}"
    case_dir = root / "blind" / case_id
    case_dir.mkdir(parents=True, exist_ok=False)
    left_public = f"blind/{case_id}/TEXT_A.txt"
    right_public = f"blind/{case_id}/TEXT_B.txt"
    (root / left_public).write_bytes((root / left.analysis_path).read_bytes())
    (root / right_public).write_bytes((root / right.analysis_path).read_bytes())
    public = {"case_id": case_id, "document_a": left_public, "document_b": right_public}
    gold = {
        "case_id": case_id,
        "document_a": left.document_id,
        "document_b": right.document_id,
        "expected_relation": relation,
    }
    return public, gold


def _write_templates(root: Path, public_cases: list[dict[str, str]]) -> None:
    time_rows = []
    for order, case in enumerate(public_cases, 1):
        for mode in ("MANUAL", "ASSISTED"):
            for stage in ("SUITABILITY", "SEPARATE_ANALYSIS", "COMPARISON", "ASSESSMENT", "REPORT"):
                time_rows.append({
                    "case_id": case["case_id"], "expert_id": "", "mode": mode,
                    "stage": stage, "start_time": "", "end_time": "",
                    "duration_seconds": "", "session_order": order, "notes": "",
                })
    _write_csv(
        root / "time_motion_template.csv",
        [
            "case_id", "expert_id", "mode", "stage", "start_time", "end_time",
            "duration_seconds", "session_order", "notes",
        ],
        time_rows,
    )
    annotation_rows = []
    for case in public_cases:
        for label in ("TEXT_A", "TEXT_B"):
            annotation_rows.append({
                "case_id": case["case_id"], "document_id": label, "expert_id": "",
                "feature_id": "", "feature_group": "", "program_detected": "",
                "expert_confirmed": "", "expert_rejected": "",
                "expert_added_manually": "", "notes": "",
            })
    _write_csv(
        root / "feature_annotation_template.csv",
        [
            "case_id", "document_id", "expert_id", "feature_id", "feature_group",
            "program_detected", "expert_confirmed", "expert_rejected",
            "expert_added_manually", "notes",
        ],
        annotation_rows,
    )
    _write_csv(
        root / "rerun_reproducibility_template.csv",
        ["document_id", "run_id", "result_sha256", "notes"],
        [],
    )


def validate_manifest(root: Path) -> dict[str, Any]:
    with (root / "manifest.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    errors = []
    seen_ids = set()
    for row in rows:
        document_id = row["document_id"]
        if document_id in seen_ids:
            errors.append(f"duplicate_document_id:{document_id}")
        seen_ids.add(document_id)
        for kind in ("raw", "analysis"):
            path = root / row[f"{kind}_path"]
            if not path.is_file():
                errors.append(f"missing_{kind}:{document_id}")
            elif sha256_file(path) != row[f"{kind}_sha256"]:
                errors.append(f"hash_mismatch_{kind}:{document_id}")
    return {"valid": not errors, "document_count": len(rows), "errors": errors}


def _write_final_selection_report(root: Path, authors: list[dict[str, Any]], documents: list[SelectedDocument]) -> None:
    by_author: dict[str, list[SelectedDocument]] = {}
    for doc in documents:
        by_author.setdefault(doc.author_code, []).append(doc)
    lines = ["# Pilot 01 — утверждённая выборка", ""]
    for author, code in zip(authors, sorted(by_author)):
        lines.extend([
            f"## {code}", "",
            f"- source author id: `{author['source_author_id']}`",
            f"- username: `{author['username']}`",
            f"- чистых постов в первичном проходе: {author['clean_count']}",
            f"- риски первичного routing: `{author['author_risks'] or 'none'}`",
            f"- причина включения: ручное одобрение shortlist; доступны 4 основных и 2 резервных независимых кандидата",
            "",
        ])
        for doc in sorted(by_author[code], key=lambda item: item.document_id):
            role = "reserve" if doc.is_reserve else "main"
            lines.append(
                f"- `{doc.document_id}` ({role}): {doc.date}; {doc.word_count} слов; "
                f"{doc.source_url}; `{doc.content_type}`"
            )
        lines.append("")
    (root / "reports" / "selection_report.md").write_text("\n".join(lines), encoding="utf-8")


def _write_final_readme(root: Path, author_count: int, document_count: int, seed: int,
                        case_author_count: int = 10) -> None:
    text = f"""# Pilot 01 — исследовательский корпус

Статус: утверждённая выборка для пилотной апробации. Включено {author_count} авторов, {document_count} исходных документов: по четыре основных и два резервных на автора. Pilot cases используют первых {case_author_count} авторов и основные документы; резервные тексты в cases не входят. Seed: `{seed}`.

`raw/` и `reserve_raw/` содержат точный UTF-8 текст поля `text_markdown` без добавления завершающего перевода строки. `analysis/` и `reserve_analysis/` в этой версии байтово совпадают с RAW: языковая и техническая нормализация не выполнялась. Поэтому `processing_log.csv` содержит только заголовок.

`source_authors_private.csv` и `cases_gold_private.csv` являются служебными. Их нельзя публиковать или передавать в blind workflow. Эксперту передаются только `cases_public.csv`, соответствующий каталог `blind/`, шаблоны разметки и замера времени.

## Методологическое ограничение

Материалы Pikabu являются публично доступным исследовательским корпусом пользовательских текстов. Принадлежность нескольких публикаций одному автору определяется по платформенному `author_id`. Это не является процессуально удостоверенным авторством конкретного физического лица и не приравнивается к свободным образцам письменной речи в судебно-экспертном смысле.

Корпус используется для пилотной апробации устойчивости программного конвейера, обнаружения и систематизации признаков, воспроизводимости, экспертного workflow и оценки трудозатрат. Pilot 01 нельзя использовать для заявления о точности установления автора программой. Поля или метрики `same_author_probability`, `same_author_score`, `program_conclusion` и accuracy установления автора не формируются.
"""
    (root / "README.md").write_text(text, encoding="utf-8")
