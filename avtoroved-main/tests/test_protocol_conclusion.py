"""Тесты стадии 4: правило вывода (protocol/conclusion.py) и экспорт (report.py)."""
import json
import os

import pytest

from protocol import db as protocol_db
from protocol import comparison as cmp
from protocol import conclusion as concl
from protocol import feature_map as fm


@pytest.fixture()
def pdb(tmp_path):
    return protocol_db.ProtocolDB(str(tmp_path / "concl.db"))


def _setup_pair(pdb):
    pid = pdb.create_project("Дело", expert_name="Иванов И.И.")
    a = pdb.add_document(pid, "sporny.txt", protocol_db.ROLE_DISPUTED,
                         file_sha256="a", word_count=600)
    b = pdb.add_document(pid, "obrazec.txt", protocol_db.ROLE_SAMPLE,
                         file_sha256="b", word_count=600)
    return pid, a, b


def _confirmed_position(pdb, pid, a, b, label, match_type, level):
    """Создать подтверждённую позицию сравнения напрямую."""
    key = cmp.position_key(a, b, "языковые", "п", label)
    pdb.replace_auto_comparisons(pid, a, b, [{
        "position_key": key, "feature_key_a": "fa", "feature_key_b": "fb",
        "group_name": "языковые", "subgroup": "п", "label": label,
        "value_a": "v", "value_b": "v", "fragment_a": None, "fragment_b": None,
        "match_type": match_type,
    }])
    pdb.record_comparison_decision(pid, a, b, key, "подтверждено",
                                   match_type=match_type, level=level)
    return key


# ── правило вывода: все ветки ────────────────────────────────────────────────
def test_no_positions_npv(pdb):
    pid, a, b = _setup_pair(pdb)
    form, reasons, bd = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_NPV
    assert bd["total_confirmed"] == 0


def test_nn_difference_categorical_negative(pdb):
    pid, a, b = _setup_pair(pdb)
    _confirmed_position(pdb, pid, a, b, "Р1", cmp.MATCH_DIFFERENCE, "НН")
    form, reasons, _ = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_NEG_CATEGORICAL
    assert any("НН" in r for r in reasons)


def test_ns_nsv_difference_probable_negative(pdb):
    pid, a, b = _setup_pair(pdb)
    _confirmed_position(pdb, pid, a, b, "Р1", cmp.MATCH_DIFFERENCE, "НС")
    _confirmed_position(pdb, pid, a, b, "Р2", cmp.MATCH_DIFFERENCE, "НСВ")
    form, _, _ = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_NEG_PROBABLE


def test_only_confirmed_difference_wins_over_coincidences(pdb):
    pid, a, b = _setup_pair(pdb)
    _confirmed_position(pdb, pid, a, b, "С1", cmp.MATCH_COINCIDENCE, "НН")
    _confirmed_position(pdb, pid, a, b, "Р1", cmp.MATCH_ONLY_A, "НС")
    form, _, _ = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_NEG_PROBABLE     # только_у_* — различие


def test_all_levels_and_threshold_categorical_positive(pdb):
    pid, a, b = _setup_pair(pdb)
    levels = ["НН", "НС", "НСВ"]
    for i in range(cmp.MIN_FEATURES_FOR_CONCLUSION):
        _confirmed_position(pdb, pid, a, b, f"С{i}", cmp.MATCH_COINCIDENCE,
                            levels[i % 3])
    form, _, bd = concl.recommend(pdb, pid, a, b)
    assert bd["total_coincidence"] == cmp.MIN_FEATURES_FOR_CONCLUSION
    assert form == concl.FORM_POS_CATEGORICAL


def test_blocks_degrades_categorical_positive(pdb):
    pid, a, b = _setup_pair(pdb)
    levels = ["НН", "НС", "НСВ"]
    for i in range(cmp.MIN_FEATURES_FOR_CONCLUSION):
        _confirmed_position(pdb, pid, a, b, f"С{i}", cmp.MATCH_COINCIDENCE,
                            levels[i % 3])
    pdb.save_suitability(pid, verdict="пригоден_с_ограничениями",
                         blocks_strong_conclusion=True, document_id=a,
                         flags=[], metrics={})
    form, reasons, _ = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_POS_PROBABLE
    assert any("ЗАБЛОКИРОВАНА" in r for r in reasons)


def test_blocks_degrades_categorical_negative(pdb):
    pid, a, b = _setup_pair(pdb)
    _confirmed_position(pdb, pid, a, b, "Р", cmp.MATCH_DIFFERENCE, "НН")
    pdb.save_suitability(pid, verdict="пригоден_с_ограничениями",
                         blocks_strong_conclusion=True, document_id=b,
                         flags=[], metrics={})
    form, _, _ = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_NEG_PROBABLE


def test_nn_ns_only_probable_positive(pdb):
    pid, a, b = _setup_pair(pdb)
    _confirmed_position(pdb, pid, a, b, "С1", cmp.MATCH_COINCIDENCE, "НН")
    _confirmed_position(pdb, pid, a, b, "С2", cmp.MATCH_COINCIDENCE, "НС")
    form, reasons, _ = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_POS_PROBABLE
    assert any("НСВ" in r for r in reasons)     # указана недостающая ступень


def test_below_threshold_probable_positive(pdb):
    pid, a, b = _setup_pair(pdb)
    for i, lv in enumerate(("НН", "НС", "НСВ")):
        _confirmed_position(pdb, pid, a, b, f"С{i}", cmp.MATCH_COINCIDENCE, lv)
    form, reasons, _ = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_POS_PROBABLE
    assert any("порог" in r.lower() for r in reasons)


# ── фиксация вывода экспертом ────────────────────────────────────────────────
def test_decide_matching_recommendation(pdb):
    pid, a, b = _setup_pair(pdb)
    _confirmed_position(pdb, pid, a, b, "Р", cmp.MATCH_DIFFERENCE, "НН")
    out = concl.decide(pdb, pid, a, b, concl.FORM_NEG_CATEGORICAL,
                       program_version="5.0")
    assert out["form"] == out["recommended"]
    row = pdb.fetch_conclusion(a, b)
    assert row["form"] == concl.FORM_NEG_CATEGORICAL
    snap = json.loads(row["stats_snapshot"])
    assert snap["difference"]["НН"] == 1


def test_decide_disagreement_requires_justification(pdb):
    pid, a, b = _setup_pair(pdb)
    _confirmed_position(pdb, pid, a, b, "Р", cmp.MATCH_DIFFERENCE, "НН")
    with pytest.raises(ValueError, match="обоснование"):
        concl.decide(pdb, pid, a, b, concl.FORM_NPV)
    # С обоснованием — можно.
    concl.decide(pdb, pid, a, b, concl.FORM_NPV,
                 justification="Объём образца методически недостаточен.")
    assert pdb.fetch_conclusion(a, b)["form"] == concl.FORM_NPV


def test_decide_append_only_history(pdb):
    pid, a, b = _setup_pair(pdb)
    _confirmed_position(pdb, pid, a, b, "Р", cmp.MATCH_DIFFERENCE, "НН")
    concl.decide(pdb, pid, a, b, concl.FORM_NEG_CATEGORICAL)
    concl.decide(pdb, pid, a, b, concl.FORM_NEG_PROBABLE, justification="осторожность")
    assert pdb.fetch_conclusion(a, b)["form"] == concl.FORM_NEG_PROBABLE
    assert len(pdb.fetch_conclusion_decisions(a, b)) == 2
    actions = [r["action"] for r in pdb.fetch_audit_log(pid)]
    assert actions.count("зафиксирован вывод по паре") == 2


def test_invalid_form(pdb):
    pid, a, b = _setup_pair(pdb)
    with pytest.raises(ValueError):
        concl.decide(pdb, pid, a, b, "может_быть")


# ── экспорт заключения ───────────────────────────────────────────────────────
def test_export_requires_fixed_conclusion(pdb, tmp_path):
    from protocol.report import export_conclusion_docx
    pid, a, b = _setup_pair(pdb)
    with pytest.raises(ValueError, match="не зафиксирован"):
        export_conclusion_docx(pdb, pid, a, b, str(tmp_path / "x.docx"))


def test_export_creates_docx_and_registers(pdb, tmp_path):
    from protocol.report import export_conclusion_docx
    pid, a, b = _setup_pair(pdb)
    _confirmed_position(pdb, pid, a, b, "С1", cmp.MATCH_COINCIDENCE, "НН")
    concl.decide(pdb, pid, a, b, concl.FORM_POS_PROBABLE, program_version="5.0")

    fp = str(tmp_path / "заключение.docx")
    summary = export_conclusion_docx(
        pdb, pid, a, b, fp,
        header={"expert_name": "Иванов И.И.", "case_number": "1/2026",
                "questions": "Кто автор?"},
        program_version="5.0")
    assert os.path.exists(fp)
    assert summary["sha256"] and len(summary["sha256"]) == 64

    # Файл читается python-docx и содержит ключевые разделы.
    from docx import Document
    text = "\n".join(p.text for p in Document(fp).paragraphs)
    assert "ЗАКЛЮЧЕНИЕ ЭКСПЕРТА" in text
    assert "ИССЛЕДОВАНИЕ" in text
    assert "ВЫВОДЫ" in text
    assert "Вероятный положительный" in text

    # Зарегистрирован в reports + журнал.
    reports = pdb.fetch_reports(pid)
    assert len(reports) == 1
    assert reports[0]["file_sha256"] == summary["sha256"]
    actions = [r["action"] for r in pdb.fetch_audit_log(pid)]
    assert "экспортировано заключение" in actions
