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
    c.execute("""
        CREATE TABLE IF NOT EXISTS strat_annotations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            text_hash   TEXT    NOT NULL,
            lemma       TEXT    NOT NULL,
            surface     TEXT    DEFAULT '',
            layer       TEXT    NOT NULL,
            verdict     TEXT    NOT NULL,
            context     TEXT    DEFAULT '',
            position    INTEGER DEFAULT 0,
            note        TEXT    DEFAULT '',
            created_at  TEXT    NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_dictionary (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            word        TEXT    NOT NULL COLLATE NOCASE,
            category    TEXT    NOT NULL DEFAULT 'норма',
            note        TEXT    DEFAULT '',
            created_at  TEXT    NOT NULL,
            UNIQUE(word, category)
        )
    """)
    c.commit()
    return c


# ── Аннотации стратификации ───────────────────────────────────────────────────

def save_strat_annotation(text_hash: str, lemma: str, surface: str,
                          layer: str, verdict: str, context: str = "",
                          position: int = 0, note: str = "") -> None:
    """Сохранить (или заменить) аннотацию эксперта для конкретного слова в тексте."""
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        with _conn() as c:
            c.execute(
                "DELETE FROM strat_annotations WHERE text_hash=? AND lemma=? AND layer=?",
                (text_hash, lemma, layer),
            )
            c.execute(
                "INSERT INTO strat_annotations "
                "(text_hash, lemma, surface, layer, verdict, context, position, note, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (text_hash, lemma, surface, layer, verdict, context, position, note, ts),
            )
    except Exception:
        pass


def remove_strat_annotation(text_hash: str, lemma: str, layer: str) -> None:
    """Удалить аннотацию (снять пометку)."""
    try:
        with _conn() as c:
            c.execute(
                "DELETE FROM strat_annotations WHERE text_hash=? AND lemma=? AND layer=?",
                (text_hash, lemma, layer),
            )
    except Exception:
        pass


def get_strat_exclusions(text_hash: str) -> set:
    """Вернуть множество (lemma, layer) помеченных как 'exclude' для данного текста."""
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT lemma, layer FROM strat_annotations "
                "WHERE text_hash=? AND verdict='exclude'",
                (text_hash,),
            ).fetchall()
        return {(r[0], r[1]) for r in rows}
    except Exception:
        return set()


def get_strat_annotation_verdict(text_hash: str, lemma: str, layer: str) -> Optional[str]:
    """Вернуть вердикт аннотации или None если не аннотировано."""
    try:
        with _conn() as c:
            row = c.execute(
                "SELECT verdict FROM strat_annotations "
                "WHERE text_hash=? AND lemma=? AND layer=?",
                (text_hash, lemma, layer),
            ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def get_all_strat_annotations() -> List[dict]:
    """Все аннотации — для просмотра в разделе обучения."""
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT id, text_hash, lemma, surface, layer, verdict, context, note, created_at "
                "FROM strat_annotations ORDER BY id DESC"
            ).fetchall()
        keys = ["id", "text_hash", "lemma", "surface", "layer",
                "verdict", "context", "note", "created_at"]
        return [dict(zip(keys, r)) for r in rows]
    except Exception:
        return []


def delete_strat_annotation_by_id(ann_id: int) -> None:
    try:
        with _conn() as c:
            c.execute("DELETE FROM strat_annotations WHERE id=?", (ann_id,))
    except Exception:
        pass


def get_strat_annotation_stats() -> dict:
    """Статистика аннотаций для UI (кнопка «Обучить фильтр»)."""
    try:
        with _conn() as c:
            total = c.execute(
                "SELECT COUNT(*) FROM strat_annotations").fetchone()[0]
            rows = c.execute(
                "SELECT verdict, COUNT(*) FROM strat_annotations GROUP BY verdict"
            ).fetchall()
        counts = {v: n for v, n in rows}
        return {
            "total": total,
            "exclude_count": counts.get("exclude", 0),
            "confirm_count": counts.get("confirm", 0),
        }
    except Exception:
        return {"total": 0, "exclude_count": 0, "confirm_count": 0}


def clear_strat_annotations() -> None:
    try:
        with _conn() as c:
            c.execute("DELETE FROM strat_annotations")
    except Exception:
        pass


# ── Пользовательский словарь (LT false-positive filter + engine injection) ────

# Стилистические пласты (ключи = LAYER_META из stratification_engine)
STRAT_LAYER_LABELS: Dict[str, str] = {
    "literary_standard":  "Книжная / нейтральная",
    "colloquial_reduced": "Разговорно-сниженная",
    "vernacular":         "Просторечие",
    "general_jargon":     "Общий жаргон",
    "youth_jargon":       "Молодёжный жаргон",
    "drug_jargon":        "Наркотический жаргон",
    "criminal_jargon":    "Криминальный жаргон",
    "archaic":            "Архаизмы",
    "dialectal":          "Диалектизмы",
    "euphemistic":        "Эвфемизмы",
    "obscene":            "Обсценная лексика",
}

# Тематические домены (ключи = "domain:<domain_key>", domain_key = DOMAIN_META)
THEMATIC_DOMAIN_LABELS: Dict[str, str] = {
    "domain:law":       "Юридическая / правовая",
    "domain:medicine":  "Медицинская / фармацевтика",
    "domain:it":        "IT / цифровые технологии",
    "domain:economics": "Экономика / финансы",
    "domain:military":  "Военная / силовые структуры",
    "domain:science":   "Научная / академическая",
    "domain:religion":  "Религиозная / духовная",
    "domain:politics":  "Политическая / государственная",
    "domain:sports":    "Спортивная / физкультура",
    "domain:everyday":  "Бытовая / разговорная",
}


def add_to_user_dict(word: str, category: str = "literary_standard", note: str = "") -> None:
    """Добавить слово в словарь (или заменить существующее для той же категории)."""
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        with _conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO user_dictionary (word, category, note, created_at) "
                "VALUES (?, ?, ?, ?)",
                (word.strip(), category, note, ts),
            )
    except Exception:
        pass


def remove_from_user_dict(word_id: int) -> None:
    try:
        with _conn() as c:
            c.execute("DELETE FROM user_dictionary WHERE id=?", (word_id,))
    except Exception:
        pass


def get_user_dict_words() -> set:
    """Вернуть множество слов (нижний регистр) для быстрой фильтрации LT-ошибок."""
    try:
        with _conn() as c:
            rows = c.execute("SELECT word FROM user_dictionary").fetchall()
        return {r[0].lower() for r in rows}
    except Exception:
        return set()


def get_user_dict_all() -> List[dict]:
    """Все записи словаря для управления в UI."""
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT id, word, category, note, created_at "
                "FROM user_dictionary ORDER BY word ASC"
            ).fetchall()
        keys = ["id", "word", "category", "note", "created_at"]
        return [dict(zip(keys, r)) for r in rows]
    except Exception:
        return []


def clear_user_dict() -> None:
    try:
        with _conn() as c:
            c.execute("DELETE FROM user_dictionary")
    except Exception:
        pass


def get_user_strat_words() -> Dict[str, List[str]]:
    """Вернуть {layer_key: [слова]} для инъекции в стратификатор."""
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT word, category FROM user_dictionary"
            ).fetchall()
        result: Dict[str, List[str]] = {}
        for word, cat in rows:
            if cat in STRAT_LAYER_LABELS:
                result.setdefault(cat, []).append(word.lower().strip())
        return result
    except Exception:
        return {}


def get_user_domain_words() -> Dict[str, List[str]]:
    """Вернуть {domain_key: [слова]} для инъекции в тематический движок."""
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT word, category FROM user_dictionary"
            ).fetchall()
        result: Dict[str, List[str]] = {}
        for word, cat in rows:
            if cat in THEMATIC_DOMAIN_LABELS:
                domain_key = cat[len("domain:"):]   # "domain:law" → "law"
                result.setdefault(domain_key, []).append(word.lower().strip())
        return result
    except Exception:
        return {}


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
