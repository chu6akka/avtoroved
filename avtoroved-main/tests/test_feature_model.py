"""Регрессии методической нормализации ролей элементов профиля."""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from protocol import comparison as cmp
from protocol import db as protocol_db
from protocol import feature_map as fm
from protocol import feature_model as model
from protocol import profile as pf


def _pair(tmp_path):
    pdb = protocol_db.ProtocolDB(str(tmp_path / "roles.db"))
    pid = pdb.create_project("Дело")
    a = pdb.add_document(pid, "a.txt", protocol_db.ROLE_DISPUTED,
                         file_sha256="a", word_count=500)
    b = pdb.add_document(pid, "b.txt", protocol_db.ROLE_SAMPLE,
                         file_sha256="b", word_count=500)
    return pdb, pid, a, b


def _candidate(role, label="П", subgroup="лексические"):
    return {
        "group_name": "языковые", "subgroup": subgroup,
        "kind": "кандидат_признак", "label": label, "value": "x",
        "fragment": "фрагмент", "source": "test", "role": role,
        "source_kind": model.SOURCE_METHOD if role == model.METHOD_FEATURE
        else model.SOURCE_ENGINEERING,
        "method_feature_id": "test.method" if role == model.METHOD_FEATURE else None,
        "method_reference_informativeness": "средняя" if role == model.METHOD_FEATURE else None,
        "expert_identification_value": None, "detection_reliability": "средняя",
        "id_value": "", "reliability": "средняя",
    }


def _record(pdb, pid, did, role, label="П", status=fm.STATUS_ACCEPTED):
    cand = _candidate(role, label)
    pdb.record_feature_decision(
        pid, did, f"{did}-{role}-{label}", status, cand,
        expert_id_value="высокая" if role == model.METHOD_FEATURE else "")


class _Domain:
    def __init__(self, key, cosine=0.42):
        self.key = key
        self.label = key
        self.cosine = cosine
        self.match_count = 5
        self.examples = ["пример"]


def test_01_ttr_is_aux_metric():
    rows = pf.lexical_candidates(
        {"дополнительно": {"Лексическое разнообразие (TTR)": 0.55}}, None)
    assert rows[0]["role"] == model.AUX_METRIC


def test_02_mean_sentence_length_is_aux_metric():
    rows = pf.textological_candidates(
        {"дополнительно": {"Средняя длина предложения (слов)": 12.5}}, "Текст.")
    row = next(r for r in rows if r["label"].startswith("Средняя длина предложения"))
    assert row["role"] == model.AUX_METRIC


def test_03_pos_is_morphological_aux_metric():
    rows = pf.syntactic_candidates(
        {"частоты": {"Существительное": {"коэффициент": 0.4, "количество": 4}}},
        "Текст.")
    pos = next(r for r in rows if r["label"].startswith("Доля POS"))
    assert (pos["group_name"], pos["subgroup"], pos["role"]) == (
        pf.GROUP_LINGUISTIC, pf.SUB_MORPHOLOGICAL, model.AUX_METRIC)


def test_04_word_count_not_in_method_feature_count(tmp_path):
    pdb, _pid, a, _b = _pair(tmp_path)
    rows = pf.textological_candidates({"дополнительно": {"Всего слов": 123}}, "Текст")
    pdb.save_feature_candidates(a, rows)
    assert fm.stats(fm.candidates_with_state(pdb, a))["всего"] == 0


def test_05_single_jargon_token_is_evidence_not_high_method_feature():
    token = SimpleNamespace(surface="движуха", lemma="движуха", layer="common_jargon",
                            context="эта движуха")
    strat = SimpleNamespace(tokens=[token])
    row = pf.lexical_marker_candidates(strat)[0]
    assert row["role"] == model.EVIDENCE
    assert row["method_feature_id"] is None and row["id_value"] == ""


def test_06_rare_token_gets_no_expert_identification_value():
    token = SimpleNamespace(surface="движуха", lemma="движуха", layer="common_jargon",
                            context="эта движуха")
    freq = SimpleNamespace(lookup=lambda _lemma: (99999, 0.01, "rare"))
    row = pf.lexical_marker_candidates(SimpleNamespace(tokens=[token]), freq)[0]
    assert "99999" in row["value"]
    assert row["expert_identification_value"] is None and row["id_value"] == ""


def test_07_two_emoji_do_not_get_high_identification_value():
    rows = pf.internet_candidates("🙂 тест 🙂")
    emoji = next(r for r in rows if r["label"] == "Эмодзи")
    assert "×2" in emoji["value"]
    assert emoji["expert_identification_value"] is None and emoji["id_value"] == ""


def test_08_internet_marker_is_experimental():
    rows = pf.internet_candidates("тест :) тест :)")
    assert rows and all(r["source_kind"] == model.SOURCE_EXPERIMENTAL for r in rows)


def test_09_arbitrary_thematic_domain_is_not_method_feature():
    row = pf.semantic_candidates(SimpleNamespace(top_domains=[_Domain("technology")]))[0]
    assert row["role"] == model.AUX_METRIC and row["method_feature_id"] is None


def test_10_registered_political_theme_is_method_feature_candidate():
    row = pf.semantic_candidates(SimpleNamespace(top_domains=[_Domain("politics")]))[0]
    assert row["role"] == model.METHOD_FEATURE
    assert row["method_feature_id"] == "nn.smysl.political"
    assert row["method_reference_informativeness"] == "низкая"


def test_11_cosine_changes_detection_reliability_not_identification_value():
    weak = pf.semantic_candidates(SimpleNamespace(top_domains=[_Domain("politics", 0.18)]))[0]
    strong = pf.semantic_candidates(SimpleNamespace(top_domains=[_Domain("politics", 0.42)]))[0]
    assert weak["detection_reliability"] == "низкая"
    assert strong["detection_reliability"] == "средняя"
    assert weak["expert_identification_value"] is strong["expert_identification_value"] is None


def test_12_language_tool_severity_is_not_expert_value():
    err = SimpleNamespace(
        error_type="Грамматическая", subtype="согласование", fragment="ошибка",
        description="описание", context="контекст", significance="высокая",
        severity="high", rule_ref="LT:TEST", source="LanguageTool")
    row = pf.error_candidates([err], False, reliabilities=["высокая"])[0]
    assert row["detection_reliability"] == "высокая"
    assert row["expert_identification_value"] is None and row["id_value"] == ""


def test_13_function_word_ratio_is_not_expert_value():
    result = {"categories": {"частицы": {
        "total_count": 5, "total_ipm": 5000.0, "total_ipm_rnc": 1000.0,
        "total_ratio": 5.0, "used": 1, "total_lemmas": 1,
        "lemmas": {"не": {"count": 5, "ipm_text": 5000.0,
                             "ipm_rnc": 1000.0, "ratio": 5.0}},
    }}}
    rows = pf.ogorelkov_candidates(result)
    assert {r["role"] for r in rows} == {model.AUX_METRIC, model.EVIDENCE}
    assert all(r["expert_identification_value"] is None for r in rows)


def test_14_general_skill_not_in_private_feature_count(tmp_path):
    pdb, pid, a, b = _pair(tmp_path)
    for did, rate in ((a, 1.0), (b, 6.0)):
        row = _candidate(model.GENERAL_SKILL, "Степень развития: грамматический навык",
                         "грамматический")
        row["kind"] = "общий_признак"
        row["value"] = f"средняя · {rate} ошибок/200 словоформ"
        pdb.save_feature_candidates(did, [row])
    cmp.auto_match(pdb, pid, a, b)
    stats = cmp.stats(pdb, pid, a, b)
    assert stats["всего"] == 0
    assert stats["общие_признаки"]["грамматический"] == cmp.GEN_HIGHER


def test_15_evidence_not_in_category_counts(tmp_path):
    pdb, pid, a, b = _pair(tmp_path)
    _record(pdb, pid, a, model.EVIDENCE)
    _record(pdb, pid, b, model.EVIDENCE)
    cmp.auto_match(pdb, pid, a, b)
    assert cmp.stats(pdb, pid, a, b)["всего"] == 0


def test_16_aux_metric_not_in_category_counts(tmp_path):
    pdb, pid, a, b = _pair(tmp_path)
    _record(pdb, pid, a, model.AUX_METRIC)
    _record(pdb, pid, b, model.AUX_METRIC)
    cmp.auto_match(pdb, pid, a, b)
    assert cmp.stats(pdb, pid, a, b)["всего"] == 0


def test_17_accepted_method_feature_is_in_method_count(tmp_path):
    pdb, pid, a, b = _pair(tmp_path)
    _record(pdb, pid, a, model.METHOD_FEATURE)
    _record(pdb, pid, b, model.METHOD_FEATURE)
    cmp.auto_match(pdb, pid, a, b)
    assert cmp.stats(pdb, pid, a, b)["всего"] == 1


def test_18_profile_never_sets_expert_identification_value_automatically():
    rows = []
    rows += pf.textological_candidates({"дополнительно": {"Всего слов": 10}}, "Текст")
    rows += pf.semantic_candidates(SimpleNamespace(top_domains=[_Domain("politics")]))
    rows += pf.internet_candidates("лол лол :) :)")
    assert rows and all(r["expert_identification_value"] is None for r in rows)


def test_19_old_sqlite_feature_tables_migrate(tmp_path):
    path = str(tmp_path / "old-features.db")
    pdb = protocol_db.ProtocolDB(path)
    pid = pdb.create_project("Старое дело")
    did = pdb.add_document(pid, "old.txt", protocol_db.ROLE_SAMPLE,
                           file_sha256="old", word_count=20)
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE feature_decisions")
        conn.execute("DROP TABLE features")
        conn.execute("DROP TABLE feature_candidates")
        conn.executescript("""
            CREATE TABLE feature_candidates (
              id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL,
              group_name TEXT NOT NULL, subgroup TEXT, kind TEXT NOT NULL,
              label TEXT NOT NULL, value TEXT, fragment TEXT, source TEXT,
              id_value TEXT, reliability TEXT DEFAULT '', created_at TEXT NOT NULL);
            CREATE TABLE feature_decisions (
              id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, document_id INTEGER NOT NULL,
              candidate_key TEXT NOT NULL, status TEXT NOT NULL, group_name TEXT, subgroup TEXT,
              label TEXT, value TEXT, fragment TEXT, source TEXT, reliability TEXT,
              auto_id_value TEXT, expert_id_value TEXT, expert_note TEXT,
              decided_at TEXT NOT NULL, program_version TEXT);
            CREATE TABLE features (
              id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, document_id INTEGER NOT NULL,
              candidate_key TEXT NOT NULL, status TEXT NOT NULL, group_name TEXT, subgroup TEXT,
              label TEXT, value TEXT, fragment TEXT, source TEXT, reliability TEXT,
              auto_id_value TEXT, expert_id_value TEXT, expert_note TEXT, decided_at TEXT NOT NULL,
              UNIQUE(document_id, candidate_key));
        """)
        conn.execute(
            "INSERT INTO feature_candidates(document_id,group_name,kind,label,id_value,created_at) "
            "VALUES(?,?,?,?,?,?)", (did, "языковые", "счётчик", "TTR", "", "2026"))
    migrated = protocol_db.ProtocolDB(path)
    row = migrated.fetch_feature_candidates(did)[0]
    assert row["label"] == "TTR" and row["role"] == ""
    with sqlite3.connect(path) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(feature_candidates)")}
    assert {"role", "source_kind", "method_feature_id",
            "expert_identification_value", "detection_reliability"} <= cols


def test_20_feature_decision_audit_is_append_only(tmp_path):
    pdb, pid, a, _b = _pair(tmp_path)
    cand = _candidate(model.METHOD_FEATURE)
    pdb.save_feature_candidates(a, [cand])
    saved = pdb.fetch_feature_candidates(a)[0]
    fm.decide(pdb, pid, a, saved, fm.STATUS_DOUBTFUL)
    fm.decide(pdb, pid, a, saved, fm.STATUS_ACCEPTED,
              expert_identification_value="средняя")
    history = pdb.fetch_feature_decisions(a)
    assert [r["status"] for r in history] == [fm.STATUS_ACCEPTED, fm.STATUS_DOUBTFUL]
    assert history[0]["expert_identification_value"] == "средняя"


def test_method_registry_is_valid_and_unique():
    rows = model.load_method_registry()
    assert rows and len({r["id"] for r in rows}) == len(rows)
