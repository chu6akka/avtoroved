"""Streaming scanner and first-pass reports for the Pilot 01 corpus."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.metadata
import json
import logging
from pathlib import Path
import re
import sqlite3
from statistics import median
from typing import Any, Iterable, Iterator

from .filtering import (
    ACCOUNT_RISK_RE,
    HARD_EXCLUSION_TERMS,
    PREFERRED_TAGS,
    FilterResult,
    assess_post,
    simhash_distance,
)


DATASET_ID = "IlyaGusev/pikabu"
DEFAULT_REVISION = "96466c289dfe2fd1ce8570f4d23c3c59737e2a76"
DATA_FILES = tuple(f"{index:02d}.jsonl.zst" for index in range(20))
REQUIRED_FIELDS = (
    "id", "title", "text_markdown", "timestamp", "author_id", "username",
    "url", "tags",
)


@dataclass(frozen=True)
class ScanConfig:
    output_dir: Path
    max_records: int = 250_000
    checkpoint_every: int = 2_000
    seed: int = 20260907
    revision: str = DEFAULT_REVISION
    top_authors: int = 30
    max_posts_per_author: int = 12
    resume: bool = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS scan_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS posts (
            source_post_id TEXT PRIMARY KEY,
            source_author_id TEXT NOT NULL,
            username TEXT NOT NULL,
            date TEXT NOT NULL,
            timestamp INTEGER,
            title TEXT NOT NULL,
            source_url TEXT NOT NULL,
            tags TEXT NOT NULL,
            word_count INTEGER NOT NULL,
            char_count INTEGER NOT NULL,
            russian_ratio REAL NOT NULL,
            quote_ratio REAL NOT NULL,
            markup_ratio REAL NOT NULL,
            content_type TEXT NOT NULL,
            priority_score INTEGER NOT NULL,
            flags TEXT NOT NULL,
            status TEXT NOT NULL,
            reasons TEXT NOT NULL,
            exact_text_sha256 TEXT NOT NULL,
            simhash TEXT NOT NULL,
            text_markdown TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_posts_author_status
            ON posts(source_author_id, status);
        CREATE INDEX IF NOT EXISTS idx_posts_status
            ON posts(status);
        CREATE INDEX IF NOT EXISTS idx_posts_hash
            ON posts(exact_text_sha256);
        """
    )
    return connection


def _meta_get(connection: sqlite3.Connection, key: str, default: str = "") -> str:
    row = connection.execute("SELECT value FROM scan_meta WHERE key = ?", (key,)).fetchone()
    return str(row[0]) if row else default


def _meta_set(connection: sqlite3.Connection, key: str, value: Any) -> None:
    connection.execute(
        "INSERT INTO scan_meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


def dataset_urls(revision: str = DEFAULT_REVISION) -> list[str]:
    base = f"https://huggingface.co/datasets/{DATASET_ID}/resolve/{revision}"
    return [f"{base}/{name}" for name in DATA_FILES]


def iter_dataset_rows(revision: str = DEFAULT_REVISION) -> Iterator[dict[str, Any]]:
    """Read the official shards lazily; no complete shard or dataset is retained."""
    from datasets import load_dataset

    stream = load_dataset(
        "json",
        data_files={"train": dataset_urls(revision)},
        split="train",
        streaming=True,
    )
    yield from stream


def inspect_dataset_schema(revision: str = DEFAULT_REVISION) -> dict[str, Any]:
    from datasets import load_dataset
    from huggingface_hub import HfApi

    info = HfApi().dataset_info(DATASET_ID, revision=revision)
    stream = load_dataset(
        "json",
        data_files={"train": [dataset_urls(revision)[0]]},
        split="train",
        streaming=True,
    )
    first = next(iter(stream))
    observed = {key: _describe_value(value) for key, value in first.items()}
    declared = None
    if info.card_data is not None:
        card = info.card_data.to_dict()
        declared = card.get("dataset_info")
    return {
        "dataset_id": DATASET_ID,
        "requested_revision": revision,
        "resolved_revision": info.sha,
        "captured_at_utc": _utc_now(),
        "files": [item.rfilename for item in info.siblings],
        "declared_dataset_info": declared,
        "observed_fields": observed,
        "required_fields": {
            field: {"present": field in first, "observed_type": observed.get(field)}
            for field in REQUIRED_FIELDS
        },
        "library_versions": library_versions(),
    }


def _describe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _describe_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return {"type": "list", "item": _describe_value(value[0]) if value else "unknown"}
    return type(value).__name__


def library_versions() -> dict[str, str]:
    names = ("datasets", "huggingface-hub", "pyarrow", "zstandard")
    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def _near_duplicate_reason(
    connection: sqlite3.Connection,
    author_id: str,
    result: FilterResult,
) -> str:
    exact = connection.execute(
        "SELECT source_post_id FROM posts WHERE exact_text_sha256 = ? LIMIT 1",
        (result.exact_text_sha256,),
    ).fetchone()
    if exact:
        return f"exact_duplicate_of:{exact[0]}"
    rows = connection.execute(
        "SELECT source_post_id, simhash FROM posts "
        "WHERE source_author_id = ? AND status != 'rejected' "
        "ORDER BY priority_score DESC LIMIT 100",
        (author_id,),
    )
    for row in rows:
        if simhash_distance(result.simhash, row["simhash"]) <= 3:
            return f"near_duplicate_of:{row['source_post_id']}"
    return ""


def _insert_post(connection: sqlite3.Connection, row: dict[str, Any], result: FilterResult) -> None:
    author_id = str(row.get("author_id") or "")
    status = result.status
    reasons = list(result.rejection_reasons)
    flags = list(result.flags)
    if status != "rejected":
        duplicate = _near_duplicate_reason(connection, author_id, result)
        if duplicate:
            status = "rejected"
            reasons.append(duplicate)
            if "possible_repost" not in flags:
                flags.append("possible_repost")

    connection.execute(
        """
        INSERT OR IGNORE INTO posts(
            source_post_id, source_author_id, username, date, timestamp, title,
            source_url, tags, word_count, char_count, russian_ratio, quote_ratio,
            markup_ratio, content_type, priority_score, flags, status, reasons,
            exact_text_sha256, simhash, text_markdown
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(row.get("id") or ""), author_id, str(row.get("username") or ""),
            result.date, row.get("timestamp"), str(row.get("title") or ""),
            str(row.get("url") or ""), _json(row.get("tags") or []),
            result.word_count, result.char_count, result.russian_ratio,
            result.quote_ratio, result.markup_ratio, result.content_type,
            result.priority_score, "|".join(flags), status, "|".join(reasons),
            result.exact_text_sha256, result.simhash,
            str(row.get("text_markdown") or ""),
        ),
    )


def _write_checkpoint(config: ScanConfig, connection: sqlite3.Connection) -> None:
    checkpoint = {
        "dataset_id": DATASET_ID,
        "revision": config.revision,
        "records_scanned": int(_meta_get(connection, "records_scanned", "0")),
        "seed": config.seed,
        "updated_at_utc": _utc_now(),
        "complete": _meta_get(connection, "complete", "false") == "true",
    }
    _atomic_json(config.output_dir / "checkpoint.json", checkpoint)


def _atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".new")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def scan(config: ScanConfig) -> dict[str, Any]:
    output = config.output_dir
    if output.exists() and not config.resume and any(output.iterdir()):
        raise FileExistsError(
            f"{output} is not empty; pass --resume or choose a new output directory"
        )
    output.mkdir(parents=True, exist_ok=True)
    (output / "reports").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(output / "scan.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )

    schema_path = output / "reports" / "dataset_schema.json"
    if not schema_path.exists():
        schema = inspect_dataset_schema(config.revision)
        missing = [name for name, item in schema["required_fields"].items() if not item["present"]]
        if missing:
            raise RuntimeError(f"dataset schema is missing required fields: {missing}")
        _atomic_json(schema_path, schema)

    connection = _connect(output / ".scan_state.sqlite3")
    try:
        previous = int(_meta_get(connection, "records_scanned", "0"))
        stored_revision = _meta_get(connection, "revision")
        if stored_revision and stored_revision != config.revision:
            raise RuntimeError("checkpoint revision differs from requested dataset revision")
        _meta_set(connection, "revision", config.revision)
        _meta_set(connection, "seed", config.seed)
        _meta_set(connection, "started_at_utc", _meta_get(connection, "started_at_utc", _utc_now()))
        _meta_set(connection, "complete", "false")
        connection.commit()

        scanned = previous
        stream = iter_dataset_rows(config.revision)
        for index, row in enumerate(stream):
            if index < previous:
                continue
            if scanned >= config.max_records:
                break
            _insert_post(connection, row, assess_post(row))
            scanned += 1
            if scanned % config.checkpoint_every == 0:
                _meta_set(connection, "records_scanned", scanned)
                connection.commit()
                _write_checkpoint(config, connection)
                logging.info("scanned %d records", scanned)
        _meta_set(connection, "records_scanned", scanned)
        _meta_set(connection, "complete", "true")
        _meta_set(connection, "finished_at_utc", _utc_now())
        connection.commit()
        _write_checkpoint(config, connection)
        result = export_first_pass(config, connection)
        logging.info("first pass complete: %s", result)
        return result
    except KeyboardInterrupt:
        _meta_set(connection, "records_scanned", locals().get("scanned", 0))
        connection.commit()
        _write_checkpoint(config, connection)
        logging.warning("scan interrupted; checkpoint saved")
        raise
    finally:
        connection.close()


def export_existing(config: ScanConfig) -> dict[str, Any]:
    """Regenerate first-pass reports from a saved checkpoint without network I/O."""
    database = config.output_dir / ".scan_state.sqlite3"
    if not database.exists():
        raise FileNotFoundError(f"scan state does not exist: {database}")
    connection = _connect(database)
    try:
        return export_first_pass(config, connection)
    finally:
        connection.close()


def _author_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT source_author_id, MAX(username) AS username,
               SUM(status = 'candidate') AS clean_count,
               SUM(status = 'review') AS review_count,
               COUNT(*) AS retained_count,
               MIN(CASE WHEN status != 'rejected' THEN date END) AS first_date,
               MAX(CASE WHEN status != 'rejected' THEN date END) AS last_date,
               AVG(CASE WHEN status != 'rejected' THEN word_count END) AS mean_words,
               SUM(CASE WHEN status = 'candidate' AND date BETWEEN '2017-01-01' AND '2021-12-31' THEN 1 ELSE 0 END) AS preferred_period_count,
               SUM(CASE WHEN status = 'candidate' THEN priority_score ELSE 0 END) AS priority_total
        FROM posts
        GROUP BY source_author_id
        HAVING clean_count > 0 OR review_count > 0
        """
    ).fetchall()
    output: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        counts = [
            int(value[0]) for value in connection.execute(
                "SELECT word_count FROM posts WHERE source_author_id = ? "
                "AND status != 'rejected' ORDER BY word_count",
                (row["source_author_id"],),
            )
        ]
        item["median_words"] = median(counts) if counts else 0
        item["eligible_six_clean"] = int(item["clean_count"]) >= 6
        evidence_rows = connection.execute(
            "SELECT tags, text_markdown FROM posts WHERE source_author_id = ? AND status = 'candidate'",
            (row["source_author_id"],),
        ).fetchall()
        preferred_count = 0
        own_count = 0
        first_person_count = 0
        first_person_re = re.compile(
            r"\b(?:я|мне|меня|мной|мой|моя|моё|мои|мы|нам|нас|наш|наша|наше|наши)\b",
            re.IGNORECASE,
        )
        for evidence in evidence_rows:
            tags = {str(tag).strip().lower() for tag in json.loads(evidence["tags"])}
            preferred_count += bool(tags & PREFERRED_TAGS)
            own_count += bool(tags & {"моё", "мое"})
            first_person_count += len(first_person_re.findall(evidence["text_markdown"])) >= 3
        clean_count = int(item["clean_count"])
        review_count = int(item["review_count"])
        risks: list[str] = []
        if preferred_count == 0:
            risks.append("no_preferred_tags_observed")
        if clean_count and first_person_count / clean_count < 0.25:
            risks.append("low_first_person_signal")
        if review_count and review_count / (clean_count + review_count) >= 0.30:
            risks.append("high_flagged_share")
        if ACCOUNT_RISK_RE.search(str(item["username"])):
            risks.append("organizational_username")
        if "no_preferred_tags_observed" in risks and "low_first_person_signal" in risks:
            risks.append("possible_content_aggregator")
        item["preferred_tag_posts"] = preferred_count
        item["own_tag_posts"] = own_count
        item["first_person_posts"] = first_person_count
        item["author_risks"] = "|".join(risks)
        item["risk_count"] = len(risks)
        output.append(item)
    return sorted(
        output,
        key=lambda item: (
            not item["eligible_six_clean"],
            item["risk_count"],
            -(item["preferred_tag_posts"] + item["first_person_posts"]),
            -int(item["clean_count"]),
            -int(item["preferred_period_count"]),
            str(item["source_author_id"]),
        ),
    )


def _selected_posts(
    connection: sqlite3.Connection,
    author_ids: Iterable[str],
    per_author: int,
) -> list[sqlite3.Row]:
    selected: list[sqlite3.Row] = []
    for author_id in author_ids:
        rows = connection.execute(
            """
            SELECT * FROM posts
            WHERE source_author_id = ? AND status IN ('candidate', 'review')
            ORDER BY status = 'candidate' DESC,
                     date BETWEEN '2017-01-01' AND '2021-12-31' DESC,
                     priority_score DESC, word_count BETWEEN 350 AND 650 DESC,
                     date, source_post_id
            LIMIT ?
            """,
            (author_id, per_author),
        ).fetchall()
        selected.extend(rows)
    return selected


def _preview(text: str, limit: int = 500) -> str:
    compact = " ".join((text or "").split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".new")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def export_first_pass(config: ScanConfig, connection: sqlite3.Connection) -> dict[str, Any]:
    _refresh_priority_scores(connection)
    _apply_account_risk_updates(connection)
    authors = _author_rows(connection)
    shortlist = authors[: max(50, config.top_authors)]
    top30 = shortlist[: config.top_authors]
    author_ids = [str(row["source_author_id"]) for row in top30]
    posts = _selected_posts(connection, author_ids, config.max_posts_per_author)

    _write_csv(
        config.output_dir / "authors_shortlist_private.csv",
        [
            "rank", "source_author_id", "username", "clean_count", "review_count",
            "retained_count", "first_date", "last_date", "mean_words",
            "median_words", "preferred_period_count", "preferred_tag_posts",
            "own_tag_posts", "first_person_posts", "author_risks",
            "eligible_six_clean",
        ],
        ({"rank": index, **row} for index, row in enumerate(shortlist, 1)),
    )
    candidate_fields = [
        "author_rank", "source_author_id", "username", "source_post_id", "date",
        "title", "source_url", "word_count", "char_count", "content_type", "tags",
        "priority_score", "status", "flags", "selection_status", "text_preview",
    ]
    rank_by_author = {author_id: index for index, author_id in enumerate(author_ids, 1)}
    candidate_rows = []
    for row in posts:
        item = dict(row)
        item["author_rank"] = rank_by_author[item["source_author_id"]]
        item["selection_status"] = "MANUAL_REVIEW_REQUIRED"
        item["text_preview"] = _preview(item.pop("text_markdown"))
        candidate_rows.append(item)
    _write_csv(config.output_dir / "posts_candidates.csv", candidate_fields, candidate_rows)

    review_rows = []
    for author_id in author_ids:
        flagged_posts = connection.execute(
            "SELECT * FROM posts WHERE source_author_id = ? AND status = 'review' "
            "ORDER BY priority_score DESC, date, source_post_id",
            (author_id,),
        ).fetchall()
        for row in flagged_posts:
            item = dict(row)
            item["author_rank"] = rank_by_author[item["source_author_id"]]
            item["selection_status"] = "DO_NOT_SELECT_WITHOUT_MANUAL_APPROVAL"
            item["text_preview"] = _preview(item.pop("text_markdown"))
            item["review_reason"] = item["flags"] or "low_confidence"
            review_rows.append(item)
    _write_csv(
        config.output_dir / "review_needed.csv",
        candidate_fields + ["review_reason", "review_decision", "review_notes"],
        review_rows,
    )

    rejected = connection.execute(
        "SELECT source_author_id, username, source_post_id, date, title, source_url, "
        "word_count, reasons AS rejection_reasons, flags FROM posts "
        "WHERE status = 'rejected' ORDER BY source_post_id"
    )
    _write_csv(
        config.output_dir / "rejected_posts.csv",
        [
            "source_author_id", "username", "source_post_id", "date", "title",
            "source_url", "word_count", "rejection_reasons", "flags",
        ],
        (dict(row) for row in rejected),
    )

    stats = _filtering_stats(connection, authors)
    _atomic_json(config.output_dir / "reports" / "filtering_stats.json", stats)
    (config.output_dir / "reports" / "scan_report.md").write_text(
        _render_scan_report(config, stats, shortlist), encoding="utf-8"
    )
    (config.output_dir / "reports" / "selection_report.md").write_text(
        _render_selection_placeholder(top30, candidate_rows), encoding="utf-8"
    )
    (config.output_dir / "README.md").write_text(
        _render_readme(config, stats), encoding="utf-8"
    )
    return {
        "records_scanned": stats["records_scanned"],
        "authors_with_six_clean": stats["authors_with_6_clean_candidates"],
        "shortlist_authors": len(top30),
        "candidate_posts_exported": len(candidate_rows),
        "review_posts_exported": len(review_rows),
    }


def _apply_account_risk_updates(connection: sqlite3.Connection) -> None:
    """Apply account-name risk routing to checkpoints created by older scanner code."""
    rows = connection.execute(
        "SELECT source_post_id, username, flags, status FROM posts WHERE status != 'rejected'"
    ).fetchall()
    for row in rows:
        if not ACCOUNT_RISK_RE.search(str(row["username"])):
            continue
        flags = [flag for flag in str(row["flags"]).split("|") if flag]
        for flag in ("commercial_account", "suspicious_authorship"):
            if flag not in flags:
                flags.append(flag)
        connection.execute(
            "UPDATE posts SET status = 'review', flags = ? WHERE source_post_id = ?",
            ("|".join(flags), row["source_post_id"]),
        )
    connection.commit()


def _refresh_priority_scores(connection: sqlite3.Connection) -> None:
    """Keep stored ranking aligned with the exact, documented preference list."""
    rows = connection.execute(
        "SELECT source_post_id, tags, date, word_count, flags FROM posts"
    ).fetchall()
    for row in rows:
        tags = {str(tag).strip().lower() for tag in json.loads(row["tags"])}
        score = 5 if tags & {"моё", "мое"} else 0
        score += min(4, 2 * len(tags & PREFERRED_TAGS))
        if "2017-01-01" <= str(row["date"]) <= "2021-12-31":
            score += 3
        if 350 <= int(row["word_count"]) <= 650:
            score += 1
        flags = [flag for flag in str(row["flags"]).split("|") if flag]
        score -= 2 * len(flags)
        connection.execute(
            "UPDATE posts SET priority_score = ? WHERE source_post_id = ?",
            (score, row["source_post_id"]),
        )
    connection.commit()


def _filtering_stats(connection: sqlite3.Connection, authors: list[dict[str, Any]]) -> dict[str, Any]:
    scanned = int(_meta_get(connection, "records_scanned", "0"))
    status_counts = {
        row["status"]: int(row["count"])
        for row in connection.execute("SELECT status, COUNT(*) AS count FROM posts GROUP BY status")
    }
    reason_counts: dict[str, int] = {}
    for row in connection.execute("SELECT reasons FROM posts WHERE reasons != ''"):
        for reason in str(row[0]).split("|"):
            if reason in HARD_EXCLUSION_TERMS:
                reason = "excluded_tag:" + reason
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    date_row = connection.execute(
        "SELECT MIN(date), MAX(date) FROM posts WHERE date != ''"
    ).fetchone()
    unique_authors = connection.execute(
        "SELECT COUNT(DISTINCT source_author_id) FROM posts WHERE source_author_id != ''"
    ).fetchone()[0]
    length_pass = connection.execute(
        "SELECT COUNT(*) FROM posts WHERE word_count BETWEEN 300 AND 700"
    ).fetchone()[0]
    date_pass = connection.execute(
        "SELECT COUNT(*) FROM posts WHERE date BETWEEN '2017-01-01' AND '2021-12-31'"
    ).fetchone()[0]
    bins = {}
    for label, low, high in (
        ("0-99", 0, 99), ("100-299", 100, 299), ("300-499", 300, 499),
        ("500-700", 500, 700), ("701-999", 701, 999), ("1000+", 1000, 10**9),
    ):
        bins[label] = connection.execute(
            "SELECT COUNT(*) FROM posts WHERE word_count BETWEEN ? AND ?", (low, high)
        ).fetchone()[0]
    return {
        "dataset_id": DATASET_ID,
        "dataset_revision": _meta_get(connection, "revision"),
        "records_scanned": scanned,
        "date_min": date_row[0] or "",
        "date_max": date_row[1] or "",
        "unique_authors": int(unique_authors),
        "length_300_700": int(length_pass),
        "date_2017_2021": int(date_pass),
        "status_counts": status_counts,
        "rejection_reason_counts": dict(sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))),
        "length_distribution": bins,
        "authors_with_4_clean_candidates": sum(int(row["clean_count"]) >= 4 for row in authors),
        "authors_with_6_clean_candidates": sum(int(row["clean_count"]) >= 6 for row in authors),
        "generated_at_utc": _utc_now(),
        "library_versions": library_versions(),
    }


def _render_scan_report(
    config: ScanConfig,
    stats: dict[str, Any],
    shortlist: list[dict[str, Any]],
) -> str:
    reasons = "\n".join(
        f"- `{reason}`: {count}" for reason, count in list(stats["rejection_reason_counts"].items())[:20]
    ) or "- нет"
    lengths = "\n".join(
        f"- {label}: {count}" for label, count in stats["length_distribution"].items()
    )
    author_lines = [
        "| # | author_id | username | clean | review | preferred tags | first-person | dates | risks | >=6 clean |",
        "|---:|---:|---|---:|---:|---:|---:|---|---|:---:|",
    ]
    for index, row in enumerate(shortlist[:50], 1):
        username = str(row["username"]).replace("|", "\\|")
        author_lines.append(
            f"| {index} | {row['source_author_id']} | {username} | {row['clean_count']} | "
            f"{row['review_count']} | {row['preferred_tag_posts']} | {row['first_person_posts']} | "
            f"{row['first_date']} — {row['last_date']} | {row['author_risks'] or 'none'} | "
            f"{'yes' if row['eligible_six_clean'] else 'no'} |"
        )
    return f"""# Pilot 01 — отчёт потокового сканирования

Статус: **ПЕРВИЧНЫЙ ПРОХОД / ТРЕБУЕТСЯ РУЧНОЕ ПОДТВЕРЖДЕНИЕ**. Финальный корпус и pilot cases не созданы.

## Источник и воспроизводимость

- Датасет: `{DATASET_ID}`
- Ревизия: `{stats['dataset_revision']}`
- Фактически просмотрено: **{stats['records_scanned']}** из заявленных 6 907 622 записей
- Режим: потоковый reader Hugging Face `datasets` для `.jsonl.zst`; полный датасет не скачивался и не удерживался в RAM
- Seed для последующего детерминированного формирования cases: `{config.seed}`
- Наблюдаемый диапазон дат: {stats['date_min']} — {stats['date_max']}
- Уникальных непустых author_id: {stats['unique_authors']}

Точная заявленная и наблюдаемая схема сохранена в `dataset_schema.json`.

## Первичная фильтрация

- Постов объёмом 300–700 слов: {stats['length_300_700']}
- Постов за 2017–2021 годы: {stats['date_2017_2021']}
- Чистых кандидатов: {stats['status_counts'].get('candidate', 0)}
- Направлено на ручную проверку: {stats['status_counts'].get('review', 0)}
- Отбраковано: {stats['status_counts'].get('rejected', 0)}
- Авторов с минимум 4 чистыми кандидатами: {stats['authors_with_4_clean_candidates']}
- Авторов с минимум 6 чистыми кандидатами: {stats['authors_with_6_clean_candidates']}

Дата является предпочтением, а не жёстким исключением. Жанровая метка используется только как metadata.

## Распределение объёма

{lengths}

## Основные причины отбраковки

{reasons}

## TOP-50 авторов-кандидатов

Идентификаторы в этом локальном отчёте являются исходными и не должны попадать в последующий blind workflow.

{chr(10).join(author_lines)}

## Методологическое ограничение

Материалы Pikabu являются публично доступным исследовательским корпусом пользовательских текстов. Принадлежность нескольких публикаций одному автору определяется по платформенному `author_id`. Это не является процессуально удостоверенным авторством конкретного физического лица и не приравнивается к свободным образцам письменной речи в судебно-экспертном смысле. Корпус используется для пилотной апробации устойчивости программного конвейера, обнаружения и систематизации признаков, воспроизводимости, экспертного workflow и оценки трудозатрат. Pilot 01 нельзя использовать для заявления о точности установления автора программой.
"""


def _render_selection_placeholder(
    authors: list[dict[str, Any]],
    posts: list[dict[str, Any]],
) -> str:
    by_author: dict[str, list[dict[str, Any]]] = {}
    for post in posts:
        by_author.setdefault(str(post["source_author_id"]), []).append(post)
    lines = [
        "# Pilot 01 — shortlist для ручной проверки",
        "",
        "Ни один автор или документ пока не выбран окончательно. Коды `A001…` намеренно не присвоены.",
        "",
    ]
    for index, author in enumerate(authors, 1):
        author_id = str(author["source_author_id"])
        lines.extend([
            f"## Кандидат {index:02d}: source author {author_id} / {author['username']}",
            "",
            f"Чистых кандидатов: {author['clean_count']}; на проверке: {author['review_count']}; "
            f"наблюдаемые даты: {author['first_date']} — {author['last_date']}.",
            f"Автоматические риски автора: `{author['author_risks'] or 'none'}`. Это только routing для ручной проверки, не автороведческий признак.",
            "",
        ])
        for post in by_author.get(author_id, []):
            lines.append(
                f"- `{post['source_post_id']}` — {post['date']}, {post['word_count']} слов, "
                f"{post['content_type']}, status `{post['status']}`, flags `{post['flags'] or 'none'}`; "
                f"{post['source_url']}"
            )
        lines.append("")
    lines.extend([
        "## Требуемое решение",
        "",
        "Нужно вручную проверить исходные страницы, самостоятельность постов, признаки репоста/перевода, характер аккаунта и предложенный набор документов. Финальные авторы, RAW/ANALYSIS, хэши, псевдонимы и cases заблокированы до явного подтверждения.",
        "",
    ])
    return "\n".join(lines)


def _render_readme(config: ScanConfig, stats: dict[str, Any]) -> str:
    return f"""# Pilot 01 corpus — первичный shortlist

Текущий каталог содержит только результаты первого потокового прохода и материалы для ручной проверки. Финальный корпус, псевдонимы `A001…`, RAW/ANALYSIS-файлы, manifest и pilot cases ещё не созданы.

## Воспроизведение первого прохода

Из каталога `avtoroved-main`:

```powershell
.venv\\Scripts\\python.exe -m pip install -r requirements-pilot01.txt
.venv\\Scripts\\python.exe scripts\\prepare_pilot01.py --output artifacts\\pilot01_corpus --max-records {stats['records_scanned']} --checkpoint-every 5000
```

Продолжение прерванного сканирования выполняется с `--resume`. Повторная выгрузка отчётов из локальной контрольной точки без сети — с `--export-only`. Существующий непустой каталог без `--resume` не перезаписывается.

## Что проверять вручную

Откройте `posts_candidates.csv`, `review_needed.csv` и ссылки на исходные публикации. Для каждого автора необходимо подтвердить, что аккаунт не является коллективным/коммерческим, тексты самостоятельны, не являются переводами, репостами или частями одной серии и действительно дают минимум четыре основных и два резервных независимых документа.

## Методологическое ограничение

Материалы Pikabu являются публично доступным исследовательским корпусом пользовательских текстов. Принадлежность публикаций одному автору определяется только по платформенному `author_id`. Это не является процессуально удостоверенным авторством физического лица и не приравнивается к свободным образцам письменной речи в судебно-экспертном смысле.

Pilot 01 предназначен только для апробации устойчивости конвейера, обнаружения и систематизации признаков, воспроизводимости, экспертного workflow и оценки трудозатрат. Его нельзя использовать для заявления о точности установления автора программой.
"""
