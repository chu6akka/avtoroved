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


# ── экспорт отчёта исследования ──────────────────────────────────────────────
def test_export_without_fixed_conclusion_uses_live_recommendation(pdb, tmp_path):
    """Отчёт — вставляемый фрагмент: экспортируется и до фиксации вывода,
    стадия 4 тогда содержит живую рекомендацию методики."""
    from protocol.report import export_research_docx
    pid, a, b = _setup_pair(pdb)
    _confirmed_position(pdb, pid, a, b, "Р1", cmp.MATCH_DIFFERENCE, "НН")

    fp = str(tmp_path / "отчет.docx")
    summary = export_research_docx(pdb, pid, a, b, fp, program_version="5.0")
    assert summary["form"] is None

    from docx import Document
    text = "\n".join(p.text for p in Document(fp).paragraphs)
    assert "Рекомендация по правилу методики" in text
    assert "зафиксирована форма вывода" not in text


def test_export_creates_docx_and_registers(pdb, tmp_path):
    from protocol.report import export_research_docx
    pid, a, b = _setup_pair(pdb)
    _confirmed_position(pdb, pid, a, b, "С1", cmp.MATCH_COINCIDENCE, "НН")
    concl.decide(pdb, pid, a, b, concl.FORM_POS_PROBABLE, program_version="5.0")

    fp = str(tmp_path / "отчет.docx")
    summary = export_research_docx(pdb, pid, a, b, fp, program_version="5.0")
    assert os.path.exists(fp)
    assert summary["sha256"] and len(summary["sha256"]) == 64
    assert summary["form"] == concl.FORM_POS_PROBABLE

    # Вставляемая исследовательская часть: есть стадии, нет титула и ВЫВОДОВ.
    from docx import Document
    text = "\n".join(p.text for p in Document(fp).paragraphs)
    assert "ИССЛЕДОВАНИЕ" in text
    assert "Объекты исследования" in text
    assert "4. Оценка результатов" in text
    assert "Вероятный положительный" in text          # зафиксированная форма
    assert "ЗАКЛЮЧЕНИЕ ЭКСПЕРТА" not in text
    assert "ВЫВОДЫ" not in text
    assert "Перед экспертом поставлены вопросы" not in text

    # Зарегистрирован в reports + журнал.
    reports = pdb.fetch_reports(pid)
    assert len(reports) == 1
    assert reports[0]["file_sha256"] == summary["sha256"]
    actions = [r["action"] for r in pdb.fetch_audit_log(pid)]
    assert "экспортирован отчёт исследования" in actions


def test_export_illustrates_positions_by_group(pdb, tmp_path):
    """Стадия 3: позиции сгруппированы по группам признаков, каждая
    иллюстрирована значениями и фрагментами из обоих текстов."""
    from protocol.report import export_research_docx
    pid, a, b = _setup_pair(pdb)
    pdb.replace_auto_comparisons(pid, a, b, [
        {"position_key": cmp.position_key(a, b, "языковые", "лексические", "Жаргонизм"),
         "feature_key_a": "fa1", "feature_key_b": "fb1",
         "group_name": "языковые", "subgroup": "лексические",
         "label": "Жаргонизм «движуха»",
         "value_a": "3 употребления", "value_b": "2 употребления",
         "fragment_a": "вся эта движуха вокруг дела",
         "fragment_b": "опять началась движуха",
         "match_type": cmp.MATCH_COINCIDENCE},
        {"position_key": cmp.position_key(a, b, "смысловые", "", "Тема"),
         "feature_key_a": "fa2", "feature_key_b": "fb2",
         "group_name": "смысловые", "subgroup": "",
         "label": "Доминирующая тема: право",
         "value_a": "право", "value_b": "право",
         "fragment_a": None, "fragment_b": None,
         "match_type": cmp.MATCH_COINCIDENCE},
    ])
    for grp, sub, lbl in (("языковые", "лексические", "Жаргонизм"),
                          ("смысловые", "", "Тема")):
        pdb.record_comparison_decision(
            pid, a, b, cmp.position_key(a, b, grp, sub, lbl), "подтверждено",
            match_type=cmp.MATCH_COINCIDENCE, level="НС",
            expert_note="устойчиво в обоих текстах")
    concl.decide(pdb, pid, a, b, concl.FORM_POS_PROBABLE, program_version="5.0")

    fp = str(tmp_path / "отчет.docx")
    export_research_docx(pdb, pid, a, b, fp, program_version="5.0")

    from docx import Document
    document = Document(fp)
    headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
    # Группы идут в методическом порядке: смысловые раньше языковых.
    assert "3.1. Признаки: смысловые" in headings
    assert "3.2. Признаки: языковые" in headings
    cells = "\n".join(c.text for t in document.tables
                      for row in t.rows for c in row.cells)
    assert "«вся эта движуха вокруг дела»" in cells      # иллюстрация спорного
    assert "«опять началась движуха»" in cells           # иллюстрация образца
    assert "3 употребления" in cells and "2 употребления" in cells
    assert "уровень НС" in cells
    assert "устойчиво в обоих текстах" in cells
    assert "Жаргонизм «движуха» (лексические)" in cells


def test_shorten_fragment_cuts_on_word_boundary():
    from protocol.report import _shorten_fragment, _FRAGMENT_LIMIT
    short = "короткая цитата"
    assert _shorten_fragment(short) == short
    long = "слово " * 80
    out = _shorten_fragment(long)
    assert len(out) <= _FRAGMENT_LIMIT + 1
    assert out.endswith("…") and not out.endswith(" …")
