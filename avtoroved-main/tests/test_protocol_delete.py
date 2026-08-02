"""Тесты удаления материалов и проектов (protocol/db.py)."""
import json

import pytest

from protocol import db as protocol_db
from protocol import comparison as cmp
from protocol import conclusion as concl
from protocol import feature_map as fm


@pytest.fixture()
def pdb(tmp_path):
    return protocol_db.ProtocolDB(str(tmp_path / "del.db"))


def _full_case(pdb):
    """Проект с парой документов и данными всех стадий."""
    pid = pdb.create_project("Дело", expert_name="Иванов")
    a = pdb.add_document(pid, "sporny.txt", protocol_db.ROLE_DISPUTED,
                         file_sha256="a" * 64, word_count=500)
    b = pdb.add_document(pid, "obrazec.txt", protocol_db.ROLE_SAMPLE,
                         file_sha256="b" * 64, word_count=500)
    for did in (a, b):
        pdb.save_layers(did, {protocol_db.LAYER_CLEANED: "Текст материала."})
        pdb.save_parsed(did, [{"idx": 0, "start_char": 0, "end_char": 10,
                               "text": "Текст материала.",
                               "tokens": [{"idx": 0, "text": "Текст"},
                                          {"idx": 1, "text": "материала"}]}])
        pdb.save_feature_candidates(did, [{
            "group_name": "языковые", "subgroup": "лексические",
            "kind": "кандидат_признак", "label": "П", "value": "v",
            "fragment": "ф", "source": "s", "id_value": "средняя",
            "reliability": ""}])
        pdb.save_suitability(pid, verdict="пригоден", blocks_strong_conclusion=False,
                             document_id=did, flags=[], metrics={})
        pdb.save_ogorelkov_result(pdb.get_document(did)["file_sha256"],
                                  "d" * 64, 100, {"categories": {}}, label="x")
    # Решение эксперта по признаку.
    cand = pdb.fetch_feature_candidates(a)[0]
    fm.decide(pdb, pid, a, cand, fm.STATUS_ACCEPTED, expert_id_value="высокая")
    # Пара: сравнение и вывод.
    key = cmp.position_key(a, b, "языковые", "лексические", "П")
    pdb.replace_auto_comparisons(pid, a, b, [{
        "position_key": key, "feature_key_a": "x", "feature_key_b": "y",
        "group_name": "языковые", "subgroup": "лексические", "label": "П",
        "value_a": "v", "value_b": "v", "fragment_a": None, "fragment_b": None,
        "match_type": cmp.MATCH_COINCIDENCE}])
    pdb.record_comparison_decision(pid, a, b, key, "подтверждено",
                                   match_type=cmp.MATCH_COINCIDENCE, level="НС")
    concl.decide(pdb, pid, a, b, concl.FORM_NPV, justification="тест")
    pdb.record_report(pid, "отчёт.docx", "c" * 64, pair_doc_a=a, pair_doc_b=b)
    return pid, a, b


# ── удаление материала ───────────────────────────────────────────────────────
def test_delete_document_cascades(pdb):
    pid, a, b = _full_case(pdb)
    preview = pdb.document_deletion_preview(a)
    assert preview["предложений"] == 1 and preview["токенов"] == 2
    assert preview["кандидатов признаков"] == 1
    assert preview["позиций сравнения"] == 1

    summary = pdb.delete_document(a, program_version="5.0")
    assert summary["filename"] == "sporny.txt"

    # Сам материал и все производные сняты.
    assert pdb.get_document(a) is None
    assert pdb.count_sentences(a) == 0 and pdb.count_tokens(a) == 0
    assert pdb.get_layer(a, protocol_db.LAYER_CLEANED) is None
    assert pdb.fetch_feature_candidates(a) == []
    assert pdb.fetch_features(document_id=a) == []
    assert pdb.fetch_comparisons(a, b) == []
    assert pdb.fetch_conclusion(a, b) is None
    assert not [r for r in pdb.fetch_suitability(pid) if r["document_id"] == a]

    # Второй материал не пострадал.
    assert pdb.get_document(b) is not None
    assert pdb.count_sentences(b) == 1
    assert len(pdb.fetch_feature_candidates(b)) == 1

    # Факт удаления зафиксирован в журнале проекта.
    entry = next(r for r in pdb.fetch_audit_log(pid) if r["action"] == "удалён материал")
    details = json.loads(entry["details"])
    assert details["filename"] == "sporny.txt"
    assert details["удалено"]["токенов"] == 2


def test_delete_document_removes_ogorelkov_by_sha(pdb):
    pid, a, b = _full_case(pdb)
    sha = "a" * 64
    assert pdb.fetch_ogorelkov_results(sha)
    pdb.delete_document(a)
    assert pdb.fetch_ogorelkov_results(sha) == []      # хеш больше не используется
    assert pdb.fetch_ogorelkov_results("b" * 64)       # чужой расчёт цел


def test_delete_document_keeps_shared_ogorelkov(pdb):
    """Тот же файл импортирован дважды — расчёт по хешу остаётся."""
    pid = pdb.create_project("Дело")
    sha = "e" * 64
    d1 = pdb.add_document(pid, "f.txt", protocol_db.ROLE_SAMPLE, file_sha256=sha)
    pdb.add_document(pid, "f-копия.txt", protocol_db.ROLE_SAMPLE, file_sha256=sha)
    pdb.save_ogorelkov_result(sha, "d" * 64, 10, {"categories": {}})
    pdb.delete_document(d1)
    assert pdb.fetch_ogorelkov_results(sha)


def test_delete_missing_document(pdb):
    with pytest.raises(ValueError):
        pdb.delete_document(999)


# ── удаление проекта ─────────────────────────────────────────────────────────
def test_delete_project_cascades_and_logs(pdb):
    pid, a, b = _full_case(pdb)
    other = pdb.create_project("Другое дело")
    other_doc = pdb.add_document(other, "x.txt", protocol_db.ROLE_SAMPLE,
                                 file_sha256="f" * 64)

    preview = pdb.project_deletion_preview(pid)
    assert preview["документов"] == 2 and preview["записей журнала"] > 0

    summary = pdb.delete_project(pid, program_version="5.0")
    assert summary["name"] == "Дело"

    # Проект, его материалы и журнал сняты.
    assert pdb.get_project(pid) is None
    assert pdb.fetch_documents(pid) == []
    assert pdb.fetch_audit_log(pid) == []
    assert pdb.fetch_suitability(pid) == []
    assert pdb.fetch_reports(pid) == []

    # Соседний проект не затронут.
    assert pdb.get_project(other) is not None
    assert len(pdb.fetch_documents(other)) == 1
    assert pdb.get_document(other_doc) is not None

    # След об удалении остался в общем журнале (вне проекта).
    entry = next(r for r in pdb.fetch_audit_log(None) if r["action"] == "удалён проект")
    details = json.loads(entry["details"])
    assert details["name"] == "Дело"
    assert details["удалено"]["документов"] == 2
    assert entry["project_id"] is None


def test_delete_project_no_orphans(pdb):
    """После удаления проекта в БД не остаётся висячих записей его данных."""
    pid, a, b = _full_case(pdb)
    pdb.delete_project(pid)
    with pdb._connect() as conn:
        for table, col in (("documents", "project_id"),
                           ("suitability", "project_id"),
                           ("comparisons", "project_id"),
                           ("conclusions", "project_id"),
                           ("features", "project_id")):
            n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?",
                             (pid,)).fetchone()[0]
            assert n == 0, f"остались записи в {table}"
        # Разметка удалённых документов тоже снята.
        for table, col in (("sentences", "document_id"),
                           ("document_layers", "document_id"),
                           ("feature_candidates", "document_id")):
            n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} IN (?, ?)",
                             (a, b)).fetchone()[0]
            assert n == 0, f"остались записи в {table}"
        assert conn.execute("SELECT COUNT(*) FROM tokens").fetchone()[0] == 0


def test_delete_missing_project(pdb):
    with pytest.raises(ValueError):
        pdb.delete_project(4242)
