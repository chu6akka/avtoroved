"""
analyzer/corpus_manager.py — Накопление корпуса текстов в SQLite.

Каждый проанализированный текст сохраняется в corpus.db.
Корпус используется LearningBackend для дообучения моделей.

Таблица corpus_texts:
  id, ts, text, lemmas_json, domain, word_count
"""
from __future__ import annotations
import sqlite3
import json
import datetime
import os
from typing import List, Optional, Tuple

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "corpus.db")

MIN_WORDS_FOR_TRAINING = 500    # минимум слов для первого обучения
MIN_TEXTS_FOR_TRAINING = 3      # минимум текстов


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH)
    c.execute("""
        CREATE TABLE IF NOT EXISTS corpus_texts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT    NOT NULL,
            text        TEXT    NOT NULL,
            lemmas_json TEXT    NOT NULL,
            domain      TEXT    DEFAULT '',
            word_count  INTEGER DEFAULT 0
        )
    """)
    c.commit()
    return c


# ── Запись ───────────────────────────────────────────────────────────────────

def add_text(text: str, lemmas: List[str], domain: str = "") -> None:
    """Добавить текст и его леммы в корпус."""
    if not text or not lemmas:
        return
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        with _conn() as c:
            c.execute(
                "INSERT INTO corpus_texts (ts, text, lemmas_json, domain, word_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (ts, text, json.dumps(lemmas, ensure_ascii=False),
                 domain, len(lemmas)),
            )
    except Exception:
        pass


# ── Чтение ───────────────────────────────────────────────────────────────────

def get_all_lemma_sentences() -> List[List[str]]:
    """
    Вернуть все тексты как списки лемм (одна строка = один текст).
    Используется для обучения FastText/LDA.
    """
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT lemmas_json FROM corpus_texts ORDER BY id"
            ).fetchall()
        return [json.loads(r[0]) for r in rows if r[0]]
    except Exception:
        return []


def get_recent_lemma_sentences(limit: int = 100) -> List[List[str]]:
    """Последние N текстов — для инкрементального дообучения."""
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT lemmas_json FROM corpus_texts ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(r[0]) for r in rows if r[0]]
    except Exception:
        return []


# ── Статистика ────────────────────────────────────────────────────────────────

def stats() -> dict:
    """Статистика корпуса для UI."""
    try:
        with _conn() as c:
            total_texts = c.execute(
                "SELECT COUNT(*) FROM corpus_texts").fetchone()[0]
            total_words = c.execute(
                "SELECT COALESCE(SUM(word_count),0) FROM corpus_texts").fetchone()[0]
            last_ts = c.execute(
                "SELECT ts FROM corpus_texts ORDER BY id DESC LIMIT 1").fetchone()
        return {
            "total_texts": total_texts,
            "total_words": int(total_words),
            "last_added": last_ts[0] if last_ts else "—",
            "ready_for_training": (
                total_words >= MIN_WORDS_FOR_TRAINING
                and total_texts >= MIN_TEXTS_FOR_TRAINING
            ),
            "words_needed": max(0, MIN_WORDS_FOR_TRAINING - int(total_words)),
        }
    except Exception:
        return {
            "total_texts": 0, "total_words": 0,
            "last_added": "—", "ready_for_training": False,
            "words_needed": MIN_WORDS_FOR_TRAINING,
        }


def total_words() -> int:
    try:
        with _conn() as c:
            return c.execute(
                "SELECT COALESCE(SUM(word_count),0) FROM corpus_texts"
            ).fetchone()[0]
    except Exception:
        return 0


def clear() -> None:
    """Очистить весь корпус (с подтверждением из UI)."""
    try:
        with _conn() as c:
            c.execute("DELETE FROM corpus_texts")
    except Exception:
        pass
