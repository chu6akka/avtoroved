import sqlite3

from protocol import comparison as cmp
from protocol import db as protocol_db
from protocol import feature_map as fm


def _pair(pdb):
    pid = pdb.create_project("Дело")
    a = pdb.add_document(pid, "a.txt", protocol_db.ROLE_DISPUTED,
                         file_sha256="a", word_count=500)
    b = pdb.add_document(pid, "b.txt", protocol_db.ROLE_SAMPLE,
                         file_sha256="b", word_count=500)
    return pid, a, b


def test_feature_map_value_is_reference_not_comparison_decision(tmp_path):
    pdb = protocol_db.ProtocolDB(str(tmp_path / "case.db"))
    pid, a, b = _pair(pdb)
    for doc in (a, b):
        pdb.save_feature_candidates(doc, [{
            "group_name": "смысловые", "subgroup": "тематические",
            "kind": "кандидат_признак", "label": "устойчивая тема",
            "value": "x", "source": "test", "id_value": "средняя",
        }])
        candidate = pdb.fetch_feature_candidates(doc)[0]
        fm.decide(pdb, pid, doc, candidate, fm.STATUS_ACCEPTED,
                  expert_id_value="высокая")
    cmp.auto_match(pdb, pid, a, b)
    row = pdb.fetch_comparisons(a, b)[0]
    assert "высокая" in row["source_expert_id_value"]
    assert row["identification_value"] == ""
    cmp.decide(pdb, pid, a, b, row["position_key"],
               match_type=cmp.MATCH_COINCIDENCE, level="НС",
               identification_value="средняя")
    assert pdb.fetch_comparisons(a, b)[0]["identification_value"] == "средняя"


def test_old_sqlite_schema_migrates_without_data_loss(tmp_path):
    path = str(tmp_path / "old.db")
    # Создаём базу старой версией схемы приложения, затем удаляем только новые
    # колонки через явную старую форму таблиц.
    pdb = protocol_db.ProtocolDB(path)
    pid, a, b = _pair(pdb)
    key = cmp.position_key(a, b, "смысловые", "", "старый признак")
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE comparisons")
        conn.execute("DROP TABLE comparison_decisions")
        conn.executescript("""
            CREATE TABLE comparisons (
              id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL,
              pair_doc_a INTEGER NOT NULL, pair_doc_b INTEGER NOT NULL,
              position_key TEXT NOT NULL, feature_key_a TEXT, feature_key_b TEXT,
              group_name TEXT, subgroup TEXT, label TEXT, value_a TEXT, value_b TEXT,
              fragment_a TEXT, fragment_b TEXT, match_type TEXT NOT NULL,
              level TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'авто',
              expert_note TEXT, created_at TEXT NOT NULL, decided_at TEXT,
              UNIQUE(pair_doc_a, pair_doc_b, position_key));
            CREATE TABLE comparison_decisions (
              id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL,
              pair_doc_a INTEGER NOT NULL, pair_doc_b INTEGER NOT NULL,
              position_key TEXT NOT NULL, match_type TEXT, level TEXT,
              expert_note TEXT, status TEXT NOT NULL, decided_at TEXT NOT NULL,
              program_version TEXT);
        """)
        conn.execute(
            "INSERT INTO comparisons(project_id,pair_doc_a,pair_doc_b,position_key,"
            "group_name,label,match_type,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (pid, a, b, key, "смысловые", "старый признак", "совпадение", "2026"))
    migrated = protocol_db.ProtocolDB(path)
    row = migrated.fetch_comparisons(a, b)[0]
    assert row["label"] == "старый признак"
    assert row["source_expert_id_value"] == ""
    assert row["identification_value"] == ""
    with sqlite3.connect(path) as conn:
        decision_cols = {r[1] for r in conn.execute(
            "PRAGMA table_info(comparison_decisions)")}
    assert "identification_value" in decision_cols
