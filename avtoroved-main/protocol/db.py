"""
protocol/db.py — слой данных SQLite для экспертного протокола (Этап 1).

Хранит проекты, документы (спорные/образцы), слои текста, предложения, токены
и журнал действий. Стиль повторяет analyzer/query_history.py: модуль sqlite3,
CREATE TABLE IF NOT EXISTS, файл рядом с программой.

База по умолчанию: protocol.db в корне avtoroved-main (рядом с query_history.db
и corpus.db). Путь можно переопределить при создании ProtocolDB — это используют
тесты (временный файл) и позволит позже перейти на per-project базы.

Все временные метки — ISO 8601 (datetime.isoformat).

На этот срез реализованы таблицы: projects, documents, document_layers,
sentences, tokens, audit_log. Остальные таблицы целевой схемы
(feature_candidates, features, feature_occurrences, comparisons,
expert_decisions, reports) пока НЕ создаются — добавятся в следующих этапах
дополнением SCHEMA и новыми методами, без переделки существующих.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Iterable, Optional

# База по умолчанию — рядом с программой (как query_history.db / corpus.db).
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "protocol.db")

# Допустимые значения provenance (происхождение материала). Используются и в UI.
PROVENANCE_VALUES = (
    "рукопись",
    "печатная_машинка",
    "цифровой",
    "опубликованный",
    "расшифровка_устной_речи",
)

# Допустимые роли документа.
ROLE_DISPUTED = "спорный"
ROLE_SAMPLE = "образец"
ROLE_VALUES = (ROLE_DISPUTED, ROLE_SAMPLE)

# Типы слоёв текста.
LAYER_ORIGINAL = "original"
LAYER_CLEANED = "cleaned"
LAYER_NORMALIZED = "normalized"

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expert_name TEXT,
  program_version TEXT,
  note TEXT
);

CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id),
  filename TEXT NOT NULL,
  role TEXT NOT NULL,                 -- 'спорный' | 'образец'
  provenance TEXT,                    -- рукопись | печатная_машинка | цифровой | опубликованный | расшифровка_устной_речи
  genre TEXT,
  file_sha256 TEXT NOT NULL,
  imported_at TEXT NOT NULL,
  word_count INTEGER,
  note TEXT
);

CREATE TABLE IF NOT EXISTS document_layers (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES documents(id),
  layer_type TEXT NOT NULL,           -- 'original' | 'cleaned' | 'normalized'
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sentences (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES documents(id),
  idx INTEGER NOT NULL,
  start_char INTEGER,
  end_char INTEGER,
  text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tokens (
  id INTEGER PRIMARY KEY,
  sentence_id INTEGER NOT NULL REFERENCES sentences(id),
  idx INTEGER NOT NULL,
  text TEXT NOT NULL,
  lemma TEXT,
  pos TEXT,
  feats TEXT,
  start_char INTEGER,
  end_char INTEGER
);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY,
  project_id INTEGER REFERENCES projects(id),
  ts TEXT NOT NULL,
  action TEXT NOT NULL,
  details TEXT,
  program_version TEXT
);

CREATE TABLE IF NOT EXISTS suitability (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id),
  document_id INTEGER REFERENCES documents(id),   -- NULL = проверка пары
  pair_doc_a INTEGER REFERENCES documents(id),    -- для парной сопоставимости
  pair_doc_b INTEGER REFERENCES documents(id),
  verdict TEXT NOT NULL,        -- 'пригоден' | 'пригоден_с_ограничениями' | 'непригоден'
  flags TEXT,                   -- JSON-список красных флагов
  metrics TEXT,                 -- JSON: объём, доля цитат, повторов и т.п.
  blocks_strong_conclusion INTEGER NOT NULL DEFAULT 0,  -- 0/1
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feature_candidates (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES documents(id),
  group_name TEXT NOT NULL,     -- 'смысловые'|'текстологические'|'языковые'|'психолингвистические'
  subgroup TEXT,                -- 'лексические'|'стилистические'|'синтаксические'|'орфографические'|'пунктуационные'|...
  kind TEXT NOT NULL,           -- 'счётчик' | 'кандидат_признак'
  label TEXT NOT NULL,
  value TEXT,                   -- значение счётчика или описание признака
  fragment TEXT,                -- фрагмент текста, где проявился
  source TEXT,                  -- модуль-источник
  id_value TEXT,                -- метка идентификационной ценности: 'низкая'|'средняя'|'высокая'|''
  reliability TEXT DEFAULT '',  -- надёжность кандидата: 'низкая'|'средняя'|'высокая'|''
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feature_decisions (
  -- Append-only журнал решений эксперта по кандидатам признаков.
  -- Никогда не редактируется и не чистится: полная история для воспроизводимости.
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id),
  document_id INTEGER NOT NULL REFERENCES documents(id),
  candidate_key TEXT NOT NULL,   -- стабильный хэш содержимого кандидата (переживает пересборку профиля)
  status TEXT NOT NULL,          -- 'принят'|'отклонён'|'сомнителен'|'не_учитывать'|'сброшен'
  group_name TEXT, subgroup TEXT, label TEXT, value TEXT, fragment TEXT,
  source TEXT, reliability TEXT, auto_id_value TEXT,
  expert_id_value TEXT,          -- ид. ценность по оценке эксперта (может отличаться от авто)
  expert_note TEXT,
  decided_at TEXT NOT NULL,
  program_version TEXT
);

CREATE TABLE IF NOT EXISTS features (
  -- Текущее состояние карты признаков: последнее решение по каждому кандидату.
  -- Материализуется из feature_decisions; 'сброшен' удаляет строку отсюда.
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id),
  document_id INTEGER NOT NULL REFERENCES documents(id),
  candidate_key TEXT NOT NULL,
  status TEXT NOT NULL,
  group_name TEXT, subgroup TEXT, label TEXT, value TEXT, fragment TEXT,
  source TEXT, reliability TEXT, auto_id_value TEXT,
  expert_id_value TEXT, expert_note TEXT,
  decided_at TEXT NOT NULL,
  UNIQUE(document_id, candidate_key)
);

CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project_id);
CREATE INDEX IF NOT EXISTS idx_fc_document ON feature_candidates(document_id);
CREATE INDEX IF NOT EXISTS idx_fd_document ON feature_decisions(document_id);
CREATE INDEX IF NOT EXISTS idx_features_document ON features(document_id);
CREATE INDEX IF NOT EXISTS idx_features_project ON features(project_id);
CREATE INDEX IF NOT EXISTS idx_layers_document ON document_layers(document_id);
CREATE INDEX IF NOT EXISTS idx_sentences_document ON sentences(document_id);
CREATE INDEX IF NOT EXISTS idx_tokens_sentence ON tokens(sentence_id);
CREATE INDEX IF NOT EXISTS idx_audit_project ON audit_log(project_id);
CREATE INDEX IF NOT EXISTS idx_suitability_project ON suitability(project_id);
"""


def _now() -> str:
    """Текущая метка времени в ISO 8601 (до секунд)."""
    return datetime.now().isoformat(timespec="seconds")


class ProtocolDB:
    """
    Тонкая обёртка над SQLite для экспертного протокола.

    Соединение открывается на каждую операцию (как в query_history.py) — это
    безопасно при работе из фонового QThread импорта, где база может вызываться
    из другого потока, чем UI.
    """

    def __init__(self, path: str = DEFAULT_DB_PATH):
        self.path = path
        self.init_db()

    # ── соединение / инициализация ──────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Создать таблицы и индексы, если их ещё нет; домигрировать старые базы."""
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            # Миграция: колонка reliability появилась после создания ранних баз.
            cols = {r["name"] for r in conn.execute(
                "PRAGMA table_info(feature_candidates)").fetchall()}
            if "reliability" not in cols:
                conn.execute(
                    "ALTER TABLE feature_candidates ADD COLUMN reliability TEXT DEFAULT ''")

    # ── проекты ─────────────────────────────────────────────────────────────
    def create_project(
        self,
        name: str,
        expert_name: Optional[str] = None,
        program_version: Optional[str] = None,
        note: Optional[str] = None,
    ) -> int:
        """Создать проект и вернуть его id."""
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO projects (name, created_at, expert_name, program_version, note) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, _now(), expert_name, program_version, note),
            )
            return int(cur.lastrowid)

    def fetch_projects(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM projects ORDER BY id DESC"
            ).fetchall()

    def get_project(self, project_id: int) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()

    # ── документы ───────────────────────────────────────────────────────────
    def add_document(
        self,
        project_id: int,
        filename: str,
        role: str,
        file_sha256: str,
        provenance: Optional[str] = None,
        genre: Optional[str] = None,
        word_count: Optional[int] = None,
        note: Optional[str] = None,
    ) -> int:
        """Зарегистрировать документ в проекте и вернуть его id."""
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO documents "
                "(project_id, filename, role, provenance, genre, file_sha256, imported_at, word_count, note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (project_id, filename, role, provenance, genre,
                 file_sha256, _now(), word_count, note),
            )
            return int(cur.lastrowid)

    def fetch_documents(self, project_id: int) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM documents WHERE project_id = ? ORDER BY id",
                (project_id,),
            ).fetchall()

    def get_document(self, document_id: int) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM documents WHERE id = ?", (document_id,)
            ).fetchone()

    # ── слои текста ─────────────────────────────────────────────────────────
    def save_layer(self, document_id: int, layer_type: str, content: str) -> int:
        """Сохранить один слой текста (original/cleaned/normalized)."""
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO document_layers (document_id, layer_type, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (document_id, layer_type, content, _now()),
            )
            return int(cur.lastrowid)

    def save_layers(self, document_id: int, layers: dict[str, str]) -> None:
        """Сохранить несколько слоёв сразу: {layer_type: content}."""
        ts = _now()
        rows = [(document_id, lt, content, ts) for lt, content in layers.items()]
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO document_layers (document_id, layer_type, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )

    def get_layer(self, document_id: int, layer_type: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT content FROM document_layers "
                "WHERE document_id = ? AND layer_type = ? ORDER BY id DESC LIMIT 1",
                (document_id, layer_type),
            ).fetchone()
        return row["content"] if row else None

    # ── предложения и токены ────────────────────────────────────────────────
    def save_parsed(self, document_id: int, sentences: list[dict[str, Any]]) -> tuple[int, int]:
        """
        Сохранить разбор документа: предложения и их токены за одну транзакцию.

        Формат: sentences = [
            {"idx": int, "start_char": int|None, "end_char": int|None, "text": str,
             "tokens": [
                 {"idx": int, "text": str, "lemma": str|None, "pos": str|None,
                  "feats": str|None, "start_char": int|None, "end_char": int|None},
                 ...
             ]},
            ...
        ]
        Возвращает (число_предложений, число_токенов).
        """
        n_sent = 0
        n_tok = 0
        with self._connect() as conn:
            for sent in sentences:
                cur = conn.execute(
                    "INSERT INTO sentences (document_id, idx, start_char, end_char, text) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (document_id, sent["idx"], sent.get("start_char"),
                     sent.get("end_char"), sent["text"]),
                )
                sentence_id = int(cur.lastrowid)
                n_sent += 1
                tok_rows = [
                    (sentence_id, t["idx"], t["text"], t.get("lemma"), t.get("pos"),
                     t.get("feats"), t.get("start_char"), t.get("end_char"))
                    for t in sent.get("tokens", [])
                ]
                if tok_rows:
                    conn.executemany(
                        "INSERT INTO tokens "
                        "(sentence_id, idx, text, lemma, pos, feats, start_char, end_char) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        tok_rows,
                    )
                    n_tok += len(tok_rows)
        return n_sent, n_tok

    def count_sentences(self, document_id: int) -> int:
        with self._connect() as conn:
            return int(conn.execute(
                "SELECT COUNT(*) FROM sentences WHERE document_id = ?",
                (document_id,),
            ).fetchone()[0])

    def count_tokens(self, document_id: int) -> int:
        with self._connect() as conn:
            return int(conn.execute(
                "SELECT COUNT(*) FROM tokens t "
                "JOIN sentences s ON t.sentence_id = s.id "
                "WHERE s.document_id = ?",
                (document_id,),
            ).fetchone()[0])

    # ── журнал действий ─────────────────────────────────────────────────────
    def log_action(
        self,
        action: str,
        project_id: Optional[int] = None,
        details: Optional[dict] = None,
        program_version: Optional[str] = None,
    ) -> int:
        """Записать строку в журнал действий. details сериализуется в JSON."""
        details_json = json.dumps(details, ensure_ascii=False) if details else None
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO audit_log (project_id, ts, action, details, program_version) "
                "VALUES (?, ?, ?, ?, ?)",
                (project_id, _now(), action, details_json, program_version),
            )
            return int(cur.lastrowid)

    def fetch_audit_log(self, project_id: Optional[int] = None) -> list[sqlite3.Row]:
        with self._connect() as conn:
            if project_id is None:
                return conn.execute(
                    "SELECT * FROM audit_log ORDER BY id DESC"
                ).fetchall()
            return conn.execute(
                "SELECT * FROM audit_log WHERE project_id = ? ORDER BY id DESC",
                (project_id,),
            ).fetchall()

    # ── пригодность (стадия оценки пригодности) ──────────────────────────────
    def clear_suitability(self, project_id: int) -> None:
        """Удалить все оценки пригодности проекта (перед пересчётом)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM suitability WHERE project_id = ?", (project_id,))

    def save_suitability(
        self,
        project_id: int,
        verdict: str,
        blocks_strong_conclusion: bool,
        document_id: Optional[int] = None,
        pair_doc_a: Optional[int] = None,
        pair_doc_b: Optional[int] = None,
        flags: Optional[list] = None,
        metrics: Optional[dict] = None,
    ) -> int:
        """Сохранить одну оценку пригодности (по документу или по паре)."""
        flags_json = json.dumps(flags, ensure_ascii=False) if flags is not None else None
        metrics_json = json.dumps(metrics, ensure_ascii=False) if metrics is not None else None
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO suitability "
                "(project_id, document_id, pair_doc_a, pair_doc_b, verdict, flags, metrics, "
                " blocks_strong_conclusion, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (project_id, document_id, pair_doc_a, pair_doc_b, verdict,
                 flags_json, metrics_json, 1 if blocks_strong_conclusion else 0, _now()),
            )
            return int(cur.lastrowid)

    def fetch_suitability(self, project_id: int) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM suitability WHERE project_id = ? ORDER BY id",
                (project_id,),
            ).fetchall()

    # ── кандидаты признаков (раздельное исследование) ────────────────────────
    def clear_feature_candidates(self, document_id: int) -> None:
        """Удалить профиль документа (перед пересборкой)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM feature_candidates WHERE document_id = ?",
                         (document_id,))

    def save_feature_candidates(self, document_id: int, candidates: list[dict]) -> int:
        """
        Сохранить элементы профиля документа. Каждый элемент:
        {group_name, subgroup, kind, label, value, fragment, source, id_value}.
        Возвращает число записанных строк.
        """
        ts = _now()
        rows = [
            (document_id, c["group_name"], c.get("subgroup"), c["kind"],
             c["label"], c.get("value"), c.get("fragment"), c.get("source"),
             c.get("id_value", ""), c.get("reliability", ""), ts)
            for c in candidates
        ]
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO feature_candidates "
                "(document_id, group_name, subgroup, kind, label, value, fragment, "
                " source, id_value, reliability, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def fetch_feature_candidates(self, document_id: int) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM feature_candidates WHERE document_id = ? ORDER BY id",
                (document_id,),
            ).fetchall()

    # ── карта признаков: решения эксперта ────────────────────────────────────
    def record_feature_decision(
        self,
        project_id: int,
        document_id: int,
        candidate_key: str,
        status: str,
        snapshot: dict,
        expert_id_value: str = "",
        expert_note: str = "",
        program_version: Optional[str] = None,
    ) -> int:
        """
        Записать решение эксперта: строка ВСЕГДА добавляется в append-only
        журнал feature_decisions, а таблица features обновляется до текущего
        состояния (последнее решение по ключу; статус 'сброшен' удаляет строку).
        snapshot — содержимое кандидата: {group_name, subgroup, label, value,
        fragment, source, reliability, id_value}.
        """
        ts = _now()
        snap = (
            snapshot.get("group_name"), snapshot.get("subgroup"),
            snapshot.get("label"), snapshot.get("value"),
            snapshot.get("fragment"), snapshot.get("source"),
            snapshot.get("reliability"), snapshot.get("id_value"),
        )
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO feature_decisions "
                "(project_id, document_id, candidate_key, status, group_name, subgroup, "
                " label, value, fragment, source, reliability, auto_id_value, "
                " expert_id_value, expert_note, decided_at, program_version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (project_id, document_id, candidate_key, status, *snap,
                 expert_id_value, expert_note, ts, program_version),
            )
            decision_id = int(cur.lastrowid)
            # Материализация текущего состояния.
            conn.execute(
                "DELETE FROM features WHERE document_id = ? AND candidate_key = ?",
                (document_id, candidate_key))
            if status != "сброшен":
                conn.execute(
                    "INSERT INTO features "
                    "(project_id, document_id, candidate_key, status, group_name, subgroup, "
                    " label, value, fragment, source, reliability, auto_id_value, "
                    " expert_id_value, expert_note, decided_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (project_id, document_id, candidate_key, status, *snap,
                     expert_id_value, expert_note, ts),
                )
        return decision_id

    def fetch_features(self, document_id: Optional[int] = None,
                       project_id: Optional[int] = None) -> list[sqlite3.Row]:
        """Текущее состояние карты признаков (по документу или по проекту)."""
        with self._connect() as conn:
            if document_id is not None:
                return conn.execute(
                    "SELECT * FROM features WHERE document_id = ? ORDER BY id",
                    (document_id,)).fetchall()
            return conn.execute(
                "SELECT * FROM features WHERE project_id = ? ORDER BY id",
                (project_id,)).fetchall()

    def fetch_feature_decisions(self, document_id: int) -> list[sqlite3.Row]:
        """Полная история решений по документу (append-only, новые сверху)."""
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM feature_decisions WHERE document_id = ? ORDER BY id DESC",
                (document_id,)).fetchall()
