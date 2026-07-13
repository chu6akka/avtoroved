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


def _mark_fit(pdb, pid, a, b):
    """Стадия пригодности проведена, ограничений нет (для категорических форм)."""
    for did in (a, b):
        pdb.save_suitability(pid, verdict="пригоден",
                             blocks_strong_conclusion=False, document_id=did,
                             flags=[], metrics={})
    pdb.save_suitability(pid, verdict="пригоден", blocks_strong_conclusion=False,
                         pair_doc_a=a, pair_doc_b=b, flags=[], metrics={})


def _confirmed_position(pdb, pid, a, b, label, match_type, level,
                        group="языковые", subgroup="п"):
    """Создать подтверждённую позицию сравнения напрямую."""
    key = cmp.position_key(a, b, group, subgroup or "", label)
    pdb.replace_auto_comparisons(pid, a, b, [{
        "position_key": key, "feature_key_a": "fa", "feature_key_b": "fb",
        "group_name": group, "subgroup": subgroup, "label": label,
        "value_a": "v", "value_b": "v", "fragment_a": None, "fragment_b": None,
        "match_type": match_type,
    }])
    pdb.record_comparison_decision(pid, a, b, key, "подтверждено",
                                   match_type=match_type, level=level)
    return key


# Представитель каждой корзины Огорелкова: (group_name, subgroup).
_BUCKET_REPR = {
    "смысловые": ("смысловые", "тематические"),
    "текстологические": ("текстологические", "архитектоника"),
    "языковые: лексические": ("языковые", "лексические"),
    "языковые: стилистические": ("языковые", "стилистические"),
    "языковые: синтаксические": ("языковые", "синтаксические"),
    cmp.BUCKET_ORTH_PUNCT: ("языковые", "пунктуационные"),
    "психолингвистические": ("психолингвистические", None),
}


def _fill_buckets(pdb, pid, a, b, thresholds, levels=("НН", "НС", "НСВ")):
    """Подтверждённые совпадения, добирающие каждую корзину до её порога."""
    i = 0
    for bucket, need in thresholds.items():
        group, sub = _BUCKET_REPR[bucket]
        for j in range(need):
            _confirmed_position(pdb, pid, a, b, f"С-{bucket}-{j}",
                                cmp.MATCH_COINCIDENCE, levels[i % len(levels)],
                                group=group, subgroup=sub)
            i += 1


# ── правило вывода: все ветки ────────────────────────────────────────────────
def test_no_positions_npv(pdb):
    pid, a, b = _setup_pair(pdb)
    form, reasons, bd = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_NPV
    assert bd["total_confirmed"] == 0


def test_nn_difference_categorical_negative(pdb):
    pid, a, b = _setup_pair(pdb)
    _mark_fit(pdb, pid, a, b)
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


def test_all_levels_thresholds_and_buckets_categorical_positive(pdb):
    """Категорический положительный: все уровни + ≥20 суммарно + корзины."""
    pid, a, b = _setup_pair(pdb)
    _mark_fit(pdb, pid, a, b)
    _fill_buckets(pdb, pid, a, b, cmp.THRESHOLDS_CATEGORICAL)
    form, _, bd = concl.recommend(pdb, pid, a, b)
    assert bd["total_coincidence"] >= cmp.MIN_FEATURES_FOR_CONCLUSION
    assert form == concl.FORM_POS_CATEGORICAL


def test_twenty_coincidences_one_group_not_categorical(pdb):
    """20 совпадений одной группы НЕ дают категорический — недобранные
    корзины Огорелкова перечислены в пояснении (критерий задачи)."""
    pid, a, b = _setup_pair(pdb)
    levels = ["НН", "НС", "НСВ"]
    for i in range(cmp.MIN_FEATURES_FOR_CONCLUSION):
        _confirmed_position(pdb, pid, a, b, f"С{i}", cmp.MATCH_COINCIDENCE,
                            levels[i % 3], group="языковые",
                            subgroup="лексические")
    form, reasons, _ = concl.recommend(pdb, pid, a, b)
    assert form != concl.FORM_POS_CATEGORICAL
    assert any("Покатегорийные минимумы" in r for r in reasons)
    assert any("психолингвистические" in r for r in reasons)


def test_blocks_degrades_categorical_positive(pdb):
    pid, a, b = _setup_pair(pdb)
    _fill_buckets(pdb, pid, a, b, cmp.THRESHOLDS_CATEGORICAL)
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
    """Половинные корзины добраны, но совпадения лишь на НН и НС —
    вероятный положительный с указанием недостающей ступени."""
    pid, a, b = _setup_pair(pdb)
    _fill_buckets(pdb, pid, a, b, cmp.THRESHOLDS_PROBABLE, levels=("НН", "НС"))
    form, reasons, _ = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_POS_PROBABLE
    assert any("НСВ" in r for r in reasons)     # указана недостающая ступень


def test_below_probable_buckets_npv(pdb):
    """Совпадений мало (половинные корзины не добраны) → НПВ с перечнем."""
    pid, a, b = _setup_pair(pdb)
    for i, lv in enumerate(("НН", "НС", "НСВ")):
        _confirmed_position(pdb, pid, a, b, f"С{i}", cmp.MATCH_COINCIDENCE, lv)
    form, reasons, _ = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_NPV
    assert any("половинные" in r for r in reasons)
    assert any("текстологические" in r for r in reasons)


# ── гейты стадийности ────────────────────────────────────────────────────────
def test_no_suitability_blocks_categorical(pdb):
    """Стадия пригодности не проводилась → категорическая форма недоступна,
    в пояснении — прямое указание провести стадию."""
    pid, a, b = _setup_pair(pdb)
    _fill_buckets(pdb, pid, a, b, cmp.THRESHOLDS_CATEGORICAL)
    form, reasons, bd = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_POS_PROBABLE
    assert bd["suitability_done"] is False
    assert any("НЕ ПРОВОДИЛАСЬ" in r for r in reasons)


def test_unfit_document_forces_npv(pdb):
    """Непригодный объект → НПВ, а не смягчённая форма."""
    pid, a, b = _setup_pair(pdb)
    _fill_buckets(pdb, pid, a, b, cmp.THRESHOLDS_CATEGORICAL)
    pdb.save_suitability(pid, verdict="непригоден",
                         blocks_strong_conclusion=True, document_id=b,
                         flags=[], metrics={})
    form, reasons, _ = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_NPV
    assert any("непригодным" in r for r in reasons)


def test_unfit_beats_vul_rule(pdb):
    """Непригодность важнее правила Вула: сравнивать нечего → НПВ."""
    pid, a, b = _setup_pair(pdb)
    # Данные для правила Вула есть...
    pdb.save_feature_candidates(a, [{
        "group_name": "языковые", "subgroup": "грамматический",
        "kind": "общий_признак", "label": "Общий признак: грамматический навык",
        "value": "высокая · 0.5 ош./200 сл. · уникальных 0", "fragment": None,
        "source": "errors.scale", "id_value": "", "reliability": ""}])
    pdb.save_feature_candidates(b, [{
        "group_name": "языковые", "subgroup": "грамматический",
        "kind": "общий_признак", "label": "Общий признак: грамматический навык",
        "value": "низкая · 7.0 ош./200 сл. · уникальных 7", "fragment": None,
        "source": "errors.scale", "id_value": "", "reliability": ""}])
    # ...но образец непригоден.
    pdb.save_suitability(pid, verdict="непригоден",
                         blocks_strong_conclusion=True, document_id=b,
                         flags=[], metrics={})
    form, _, _ = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_NPV


# ── решающее правило Вула (Минюст с.19; Вул 2007 с.38) ───────────────────────
from protocol import profile as prof


def _add_general(pdb, did, skill, rate, level="средняя"):
    pdb.save_feature_candidates(did, [{
        "group_name": "языковые", "subgroup": skill, "kind": prof.KIND_GENERAL,
        "label": f"{prof.GENERAL_LABEL_PREFIX}{skill} навык",
        "value": prof.GENERAL_VALUE_FMT.format(level=level, rate=rate,
                                               count=int(rate)),
        "fragment": None, "source": "errors.scale", "id_value": "",
        "reliability": ""}])


def test_vul_rule_grammar_higher_fires_categorical_negative(pdb):
    """Грамматический навык в спорном выше допуска ±2 → категорический
    отрицательный, в пояснении — навык и дельта."""
    pid, a, b = _setup_pair(pdb)
    _mark_fit(pdb, pid, a, b)
    _add_general(pdb, a, "грамматический", 0.5)
    _add_general(pdb, b, "грамматический", 4.0)
    form, reasons, bd = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_NEG_CATEGORICAL
    assert any("Вула" in r and "грамматический" in r for r in reasons)
    assert bd["general_verdicts"]["грамматический"] == cmp.GENERAL_VERDICT_HIGHER_A


def test_vul_rule_within_tolerance_does_not_fire(pdb):
    """Разница в пределах допуска ±2 → правило не срабатывает."""
    pid, a, b = _setup_pair(pdb)
    _add_general(pdb, a, "грамматический", 2.0)
    _add_general(pdb, b, "грамматический", 3.5)
    form, reasons, _ = concl.recommend(pdb, pid, a, b)
    assert form != concl.FORM_NEG_CATEGORICAL
    assert not any("Вула" in r for r in reasons)


def test_vul_rule_ignores_orthographic_and_punctuation(pdb):
    """Орфографический/пунктуационный навыки в правиле не участвуют."""
    pid, a, b = _setup_pair(pdb)
    _add_general(pdb, a, "орфографический", 0.0)
    _add_general(pdb, b, "орфографический", 9.0)     # выше в спорном, за ±4
    _add_general(pdb, a, "пунктуационный", 0.0)
    _add_general(pdb, b, "пунктуационный", 9.0)
    form, reasons, _ = concl.recommend(pdb, pid, a, b)
    assert form != concl.FORM_NEG_CATEGORICAL
    assert not any("Вула" in r for r in reasons)


def test_vul_rule_lexical_lower_does_not_fire(pdb):
    """Навык в спорном НИЖЕ образца — основания для правила нет."""
    pid, a, b = _setup_pair(pdb)
    _add_general(pdb, a, "лексико-фразеологический", 8.0)
    _add_general(pdb, b, "лексико-фразеологический", 1.0)
    form, reasons, _ = concl.recommend(pdb, pid, a, b)
    assert not any("Вула" in r for r in reasons)


def test_vul_rule_degrades_when_blocked(pdb):
    pid, a, b = _setup_pair(pdb)
    _add_general(pdb, a, "лексико-фразеологический", 0.5)
    _add_general(pdb, b, "лексико-фразеологический", 5.0)
    pdb.save_suitability(pid, verdict="пригоден_с_ограничениями",
                         blocks_strong_conclusion=True, document_id=b,
                         flags=[], metrics={})
    form, reasons, _ = concl.recommend(pdb, pid, a, b)
    assert form == concl.FORM_NEG_PROBABLE
    assert any("Вула" in r for r in reasons)
    assert any("ЗАБЛОКИРОВАНА" in r for r in reasons)


# ── фиксация вывода экспертом ────────────────────────────────────────────────
def test_decide_matching_recommendation(pdb):
    pid, a, b = _setup_pair(pdb)
    _mark_fit(pdb, pid, a, b)
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
    _mark_fit(pdb, pid, a, b)
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
    concl.decide(pdb, pid, a, b, concl.FORM_POS_PROBABLE,
                 justification="Тестовая фиксация вопреки рекомендации.",
                 program_version="5.0")

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
    concl.decide(pdb, pid, a, b, concl.FORM_POS_PROBABLE,
                 justification="Тестовая фиксация вопреки рекомендации.",
                 program_version="5.0")

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
