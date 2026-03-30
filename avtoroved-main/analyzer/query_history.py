"""
analyzer/query_history.py — История грамматических запросов (SQLite).

Хранит все выполненные POS-паттерн запросы с результатами.
База данных: query_history.db рядом с программой.
"""
from __future__ import annotations
import sqlite3
import datetime
import os
from typing import List, Tuple

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "query_history.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_history (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ts            TEXT    NOT NULL,
            pattern       TEXT    NOT NULL,
            result_count  INTEGER DEFAULT 0,
            text_snippet  TEXT    DEFAULT ''
        )
    """)
    conn.commit()
    return conn


def add(pattern: str, result_count: int, text_snippet: str = "") -> None:
    """Записать выполненный запрос в историю."""
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        snippet = text_snippet[:80].replace("\n", " ") if text_snippet else ""
        with _get_conn() as conn:
            conn.execute(
                "INSERT INTO query_history (ts, pattern, result_count, text_snippet) "
                "VALUES (?, ?, ?, ?)",
                (ts, pattern.strip(), result_count, snippet),
            )
    except Exception:
        pass  # история не критична


def get_recent(limit: int = 100) -> List[Tuple]:
    """
    Вернуть последние N записей.
    Формат: [(id, ts, pattern, result_count), ...]
    """
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT id, ts, pattern, result_count FROM query_history "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return rows
    except Exception:
        return []


def get_unique_patterns(limit: int = 50) -> List[str]:
    """
    Уникальные паттерны (последние по времени) для выпадающего списка.
    """
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT pattern FROM query_history "
                "GROUP BY pattern ORDER BY MAX(id) DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []


def clear() -> None:
    """Очистить всю историю запросов."""
    try:
        with _get_conn() as conn:
            conn.execute("DELETE FROM query_history")
    except Exception:
        pass


def total_count() -> int:
    """Общее количество записей в истории."""
    try:
        with _get_conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM query_history").fetchone()[0]
    except Exception:
        return 0
