"""
Тесты стадии 4: правило вывода (protocol/conclusion.py) и экспорт (report.py).

Правила: Рубцова 2007 (уровни, суммарный ≥20, с. 85) + Вул 2007 (решающее
правило по навыкам, с. 38; допуски Минюста, с. 19) + Моисеева/Огорелков 2021
(покатегорийные минимумы, с. 89–93).
"""
import json
import os

import pytest

from protocol import db as protocol_db
from protocol import comparison as cmp
from protocol import conclusion as concl


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


def _confirmed_position(pdb, pid, a, b, label, match_type, level,
                        group="языковые", subgroup="пунктуационные"):
    """Создать подтверждённую позицию сравнения напрямую."""
    key = cmp.position_key(a, b, group, subgroup, label)
    pdb.replace_auto_comparisons(pid, a, b, [{
        "position_key": key, "feature_key_a": "fa", "feature_key_b": "fb",
        "group_name": group, "subgroup": subgroup, "label": label,
        "value_a": "v", "value_b": "v", "fragment_a": None, "fragment_b": None,
        "match_type": match_type,
    }])
    pdb.record_comparison_decision(pid, a, b, key, "подтверждено",
                                   match_type=match_type, level=level)
    return key


# Категории покатегорийных порогов: (group, subgroup) для каждой.
_CATEGORY_SPECS = {
    "смысловые": ("смысловые", "тематические"),
    "текстологические": ("текстологические", "архитектоника"),
    "языковые/лексические": ("языковые", "лексические"),
    "языковые/стилистические": ("языковые", "стилистические"),
    "языковые/синтаксические": ("языковые", "синтаксические"),
    "языковые/орфографические+пунктуационные": ("языковые", "пунктуационные"),
    "психолингвистические": ("психолингвистические", None),
}


def _coincidence_set(pdb, pid, a, b, probable_only=False,
                     levels=("НН", "НС", "НСВ")):
    """
    Наполнить пару подтверждёнными совпадениями по ВСЕМ категориям:
    полные минимумы (категорические) либо половинные (вероятные).
    """
    n_created = 0
    for cat_key, (group, subgroup) in _CATEGORY_SPECS.items():
        need = cmp.CATEGORY_MIN_CATEGORICAL[cat_key]
        if probable_only:
            need = cmp.category_min_probable(need)
        for i in range(need):
            _confirmed_position(
                pdb, pid, a, b, f"{cat_key}-{i}", cmp.MATCH_COINCIDENCE,
                levels[n_created % len(levels)], group=group, subgroup=subgroup)
            n_created += 1
    return n_created


def _general_position(pdb, pid, a, b, skill, verdict,
                      rate_a=1.0, rate_b=6.0):
    """Позиция сопоставления общего признака (степени навыка)."""
    label = f"Общий признак: {skill} навык"
    key = cmp.position_key(a, b, "языковые", skill, label)
    pdb.replace_auto_comparisons(pid, a, b, [{
        "position_key": key, "feature_key_a": None, "feature_key_b": None,
        "group_name": "языковые", "subgroup": skill, "label": label,
        "value_a": f"высокая · {rate_a} ошибок/200 словоформ",
        "value_b": f"низкая · {rate_b} ошибок/200 словоформ",
        "fragment_a": None, "fragment_b": None, "match_type": verdict,
    }])
    return key


# ── допуски и вердикты навыков (Минюст, с. 19) ───────────────────────────────
def test_skill_verdict_tolerances():
    # Грамматический: допуск ±2 — в пределах → совпадает.
    assert cmp.skill_verdict(5.0, 6.0, "грамматический") == cmp.GEN_EQUAL
    # За пределами: в спорном ошибок меньше → навык ВЫШЕ.
    assert cmp.skill_verdict(2.0, 6.0, "грамматический") == cmp.GEN_HIGHER
    # В спорном ошибок больше → навык ниже.
    assert cmp.skill_verdict(9.0, 6.0, "грамматический") == cmp.GEN_LOWER
    # Орфографический: допуск ±4 — разница 3 в пределах.
    assert cmp.skill_verdict(1.0, 4.0, "орфографический") == cmp.GEN_EQUAL
    assert cmp.skill_verdict(1.0, 6.0, "орфографический") == cmp.GEN_HIGHER
    # Нет данных → None.
    assert cmp.skill_verdict(None, 5.0, "грамматический") is None


# ── правило Вула ─────────────────────────────────────────────────────────────
def test_vul_rule_fires_beyond_tolerance(pdb):
    """(а) Грамматический навык выше в спорном за пределами допуска →
    категорический отрицательный, орфография в правиле не участвует."""
    pid, a, b = _setup_pair(pdb)
    _general_position(pdb, pid, a, b, "грамматический", cmp.GEN_HIGHER)
    form, reasons, bd = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_NEG_CATEGORICAL
    assert bd["правило_Вула"] == ["грамматический"]
    assert any("Вул" in r for r in reasons)


def test_vul_rule_ignores_orthography(pdb):
    """Орфографический «выше в спорном» правило Вула НЕ запускает."""
    pid, a, b = _setup_pair(pdb)
    _general_position(pdb, pid, a, b, "орфографический", cmp.GEN_HIGHER)
    form, _, bd = concl.recommend(pdb, pid, a, b)
    assert bd["правило_Вула"] == []
    assert form != concl.FORM_NEG_CATEGORICAL


def test_vul_rule_not_fires_within_tolerance(pdb):
    """(а) В пределах допуска вердикт «совпадает» — правило не срабатывает."""
    pid, a, b = _setup_pair(pdb)
    _general_position(pdb, pid, a, b, "лексико-фразеологический", cmp.GEN_EQUAL,
                      rate_a=5.0, rate_b=6.0)
    form, _, bd = concl.recommend(pdb, pid, a, b)
    assert bd["правило_Вула"] == []
    assert form != concl.FORM_NEG_CATEGORICAL


def test_vul_rule_degrades_with_blocks(pdb):
    pid, a, b = _setup_pair(pdb)
    _general_position(pdb, pid, a, b, "грамматический", cmp.GEN_HIGHER)
    pdb.save_suitability(pid, verdict="пригоден_с_ограничениями",
                         blocks_strong_conclusion=True, document_id=a,
                         flags=[], metrics={})
    form, reasons, _ = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_NEG_PROBABLE
    assert any("ЗАБЛОКИРОВАНА" in r for r in reasons)


# ── правило Рубцовой: базовые ветки ──────────────────────────────────────────
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


def test_blocks_degrades_categorical_negative(pdb):
    pid, a, b = _setup_pair(pdb)
    _confirmed_position(pdb, pid, a, b, "Р", cmp.MATCH_DIFFERENCE, "НН")
    pdb.save_suitability(pid, verdict="пригоден_с_ограничениями",
                         blocks_strong_conclusion=True, document_id=b,
                         flags=[], metrics={})
    form, _, _ = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_NEG_PROBABLE


# ── покатегорийные пороги Огорелкова (2021, с. 89–93) ────────────────────────
def test_full_categorical_positive(pdb):
    """Все уровни + суммарный ≥20 + ВСЕ покатегорийные минимумы → категорический."""
    pid, a, b = _setup_pair(pdb)
    n = _coincidence_set(pdb, pid, a, b, probable_only=False)
    assert n >= cmp.MIN_FEATURES_FOR_CONCLUSION
    form, reasons, _ = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_POS_CATEGORICAL
    assert any("покатегорийные" in r.lower() for r in reasons)


def test_one_group_20_coincidences_not_categorical(pdb):
    """(б) 20 совпадений ОДНОЙ группы не дают категорический положительный."""
    pid, a, b = _setup_pair(pdb)
    levels = ["НН", "НС", "НСВ"]
    for i in range(20):
        _confirmed_position(pdb, pid, a, b, f"С{i}", cmp.MATCH_COINCIDENCE,
                            levels[i % 3], group="языковые", subgroup="лексические")
    form, reasons, _ = concl.recommend(pdb, pid, a, b)
    assert form != concl.FORM_POS_CATEGORICAL
    # Недобранные группы перечислены.
    assert any("смысловые" in r for r in reasons)


def test_half_thresholds_probable_positive(pdb):
    """Половинные минимумы во всех категориях → вероятный положительный."""
    pid, a, b = _setup_pair(pdb)
    _coincidence_set(pdb, pid, a, b, probable_only=True)
    form, reasons, _ = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_POS_PROBABLE


def test_sparse_coincidences_npv(pdb):
    """Совпадения лишь в одной категории и мало — понижение до НПВ."""
    pid, a, b = _setup_pair(pdb)
    for i, lv in enumerate(("НН", "НС", "НСВ")):
        _confirmed_position(pdb, pid, a, b, f"С{i}", cmp.MATCH_COINCIDENCE, lv)
    form, reasons, _ = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_NPV
    assert any("НПВ" in r for r in reasons)


def test_blocks_degrades_full_categorical(pdb):
    pid, a, b = _setup_pair(pdb)
    _coincidence_set(pdb, pid, a, b, probable_only=False)
    pdb.save_suitability(pid, verdict="пригоден_с_ограничениями",
                         blocks_strong_conclusion=True, document_id=a,
                         flags=[], metrics={})
    form, reasons, _ = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_POS_PROBABLE
    assert any("ЗАБЛОКИРОВАНА" in r for r in reasons)


def test_missing_level_not_categorical(pdb):
    """Полные категории, но уровни только НН и НС → вероятный (упомянут НСВ)."""
    pid, a, b = _setup_pair(pdb)
    _coincidence_set(pdb, pid, a, b, probable_only=False, levels=("НН", "НС"))
    form, reasons, _ = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_POS_PROBABLE
    assert any("НСВ" in r for r in reasons)


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
    concl.decide(pdb, pid, a, b, concl.FORM_NPV,
                 justification="Демонстрационный экспорт.", program_version="5.0")

    fp = str(tmp_path / "заключение.docx")
    summary = export_conclusion_docx(
        pdb, pid, a, b, fp,
        header={"expert_name": "Иванов И.И.", "case_number": "1/2026",
                "questions": "Кто автор?"},
        program_version="5.0")
    assert os.path.exists(fp)
    assert summary["sha256"] and len(summary["sha256"]) == 64

    from docx import Document
    text = "\n".join(p.text for p in Document(fp).paragraphs)
    assert "ЗАКЛЮЧЕНИЕ ЭКСПЕРТА" in text
    assert "ИССЛЕДОВАНИЕ" in text
    assert "ВЫВОДЫ" in text

    reports = pdb.fetch_reports(pid)
    assert len(reports) == 1
    assert reports[0]["file_sha256"] == summary["sha256"]
    actions = [r["action"] for r in pdb.fetch_audit_log(pid)]
    assert "экспортировано заключение" in actions
