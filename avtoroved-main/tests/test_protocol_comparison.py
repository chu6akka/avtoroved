"""Тесты сравнительного исследования (protocol/comparison.py)."""
import json

import pytest

from protocol import db as protocol_db
from protocol import comparison as cmp
from protocol import feature_map as fm


@pytest.fixture()
def pdb(tmp_path):
    return protocol_db.ProtocolDB(str(tmp_path / "cmp.db"))


def _setup_pair(pdb):
    pid = pdb.create_project("Дело")
    doc_a = pdb.add_document(pid, "sporny.txt", protocol_db.ROLE_DISPUTED,
                             file_sha256="a", word_count=500)
    doc_b = pdb.add_document(pid, "obrazec.txt", protocol_db.ROLE_SAMPLE,
                             file_sha256="b", word_count=500)
    return pid, doc_a, doc_b


def _accept_feature(pdb, pid, did, label, subgroup="пунктуационные",
                    value="значение", status=fm.STATUS_ACCEPTED, key_suffix=""):
    """Утвердить признак напрямую через record_feature_decision."""
    key = f"key-{did}-{label}{key_suffix}"[:64]
    pdb.record_feature_decision(
        pid, did, key, status,
        snapshot={"group_name": "языковые", "subgroup": subgroup,
                  "label": label, "value": value, "fragment": f"фраг {label}",
                  "source": "PUNCT:TEST", "reliability": "средняя",
                  "id_value": "средняя"},
        expert_id_value="средняя")
    return key


# ── авто-сопоставление ───────────────────────────────────────────────────────
def test_auto_match_coincidence_and_only(pdb):
    pid, a, b = _setup_pair(pdb)
    _accept_feature(pdb, pid, a, "Общий признак")
    _accept_feature(pdb, pid, b, "Общий признак")
    _accept_feature(pdb, pid, a, "Только у спорного")
    _accept_feature(pdb, pid, b, "Только у образца")

    summary = cmp.auto_match(pdb, pid, a, b)
    assert summary["positions"] == 3
    rows = pdb.fetch_comparisons(a, b)
    types = {r["label"]: r["match_type"] for r in rows}
    assert types["Общий признак"] == cmp.MATCH_COINCIDENCE
    assert types["Только у спорного"] == cmp.MATCH_ONLY_A
    assert types["Только у образца"] == cmp.MATCH_ONLY_B
    assert all(r["status"] == cmp.STATUS_AUTO for r in rows)


def test_auto_match_only_accepted_features(pdb):
    pid, a, b = _setup_pair(pdb)
    _accept_feature(pdb, pid, a, "Принятый")
    _accept_feature(pdb, pid, a, "Отклонённый", status=fm.STATUS_REJECTED)
    _accept_feature(pdb, pid, a, "Сомнительный", status=fm.STATUS_DOUBTFUL)
    cmp.auto_match(pdb, pid, a, b)
    labels = {r["label"] for r in pdb.fetch_comparisons(a, b)}
    assert labels == {"Принятый"}      # сомнителен/отклонён — вне зачёта


def test_auto_match_logged(pdb):
    pid, a, b = _setup_pair(pdb)
    _accept_feature(pdb, pid, a, "П1")
    cmp.auto_match(pdb, pid, a, b)
    log = pdb.fetch_audit_log(pid)
    entry = next(r for r in log
                 if r["action"] == "сравнительное исследование: авто-сопоставление")
    d = json.loads(entry["details"])
    assert d["позиций_всего"] == 1


# ── решения эксперта ─────────────────────────────────────────────────────────
def test_decide_confirms_with_level(pdb):
    pid, a, b = _setup_pair(pdb)
    _accept_feature(pdb, pid, a, "П")
    _accept_feature(pdb, pid, b, "П")
    cmp.auto_match(pdb, pid, a, b)
    pos = pdb.fetch_comparisons(a, b)[0]

    cmp.decide(pdb, pid, a, b, pos["position_key"],
               match_type=cmp.MATCH_COINCIDENCE, level="НС",
               expert_note="устойчиво", program_version="5.0")
    row = pdb.fetch_comparisons(a, b)[0]
    assert row["status"] == cmp.STATUS_CONFIRMED
    assert row["level"] == "НС"
    assert row["expert_note"] == "устойчиво"
    assert len(pdb.fetch_comparison_decisions(a, b)) == 1


def test_decide_can_reclassify_type(pdb):
    """Эксперт может переквалифицировать авто-«совпадение» в «различие»."""
    pid, a, b = _setup_pair(pdb)
    _accept_feature(pdb, pid, a, "П")
    _accept_feature(pdb, pid, b, "П")
    cmp.auto_match(pdb, pid, a, b)
    pos = pdb.fetch_comparisons(a, b)[0]
    cmp.decide(pdb, pid, a, b, pos["position_key"],
               match_type=cmp.MATCH_DIFFERENCE, level="НН")
    row = pdb.fetch_comparisons(a, b)[0]
    assert row["match_type"] == cmp.MATCH_DIFFERENCE
    assert row["level"] == "НН"


def test_reset_returns_to_auto_keeps_history(pdb):
    pid, a, b = _setup_pair(pdb)
    _accept_feature(pdb, pid, a, "П")
    cmp.auto_match(pdb, pid, a, b)
    pos = pdb.fetch_comparisons(a, b)[0]
    cmp.decide(pdb, pid, a, b, pos["position_key"],
               match_type=cmp.MATCH_ONLY_A, level="НСВ")
    cmp.reset(pdb, pid, a, b, pos["position_key"])
    row = pdb.fetch_comparisons(a, b)[0]
    assert row["status"] == cmp.STATUS_AUTO
    assert row["level"] == ""
    assert len(pdb.fetch_comparison_decisions(a, b)) == 2   # история append-only


def test_invalid_level_and_type(pdb):
    pid, a, b = _setup_pair(pdb)
    with pytest.raises(ValueError):
        cmp.decide(pdb, pid, a, b, "k", match_type="похожесть")
    with pytest.raises(ValueError):
        cmp.decide(pdb, pid, a, b, "k", match_type=cmp.MATCH_COINCIDENCE, level="НХ")


# ── идемпотентность пересборки ───────────────────────────────────────────────
def test_rematch_preserves_confirmed(pdb):
    pid, a, b = _setup_pair(pdb)
    _accept_feature(pdb, pid, a, "П")
    _accept_feature(pdb, pid, b, "П")
    cmp.auto_match(pdb, pid, a, b)
    pos = pdb.fetch_comparisons(a, b)[0]
    cmp.decide(pdb, pid, a, b, pos["position_key"],
               match_type=cmp.MATCH_COINCIDENCE, level="НСВ")
    # Новый принятый признак + пересборка.
    _accept_feature(pdb, pid, a, "Новый")
    summary = cmp.auto_match(pdb, pid, a, b)
    rows = {r["label"]: r for r in pdb.fetch_comparisons(a, b)}
    assert len(rows) == 2
    assert rows["П"]["status"] == cmp.STATUS_CONFIRMED     # подтверждение выжило
    assert rows["П"]["level"] == "НСВ"
    assert rows["Новый"]["status"] == cmp.STATUS_AUTO
    assert summary["confirmed_kept"] == 1


# ── общие признаки: сопоставление степеней навыков ───────────────────────────
def _general_candidate(pdb, did, skill, rate):
    pdb.save_feature_candidates(did, [{
        "group_name": "языковые", "subgroup": skill, "kind": "общий_признак",
        "label": f"Степень развития: {skill} навык",
        "value": f"средняя · {rate} ошибок/200 словоформ",
        "fragment": None, "source": "errors.skills",
        "id_value": "высокая", "reliability": "",
    }])


def test_auto_match_general_positions(pdb):
    """Общие признаки пары сопоставляются с допусками Минюста (с. 19)."""
    pid, a, b = _setup_pair(pdb)
    _general_candidate(pdb, a, "грамматический", 1.0)   # в спорном ошибок меньше
    _general_candidate(pdb, b, "грамматический", 6.0)   # разница 5 > допуск 2
    _general_candidate(pdb, a, "орфографический", 3.0)
    _general_candidate(pdb, b, "орфографический", 5.0)  # разница 2 ≤ допуск 4

    summary = cmp.auto_match(pdb, pid, a, b)
    assert summary["general"]["грамматический"] == cmp.GEN_HIGHER
    assert summary["general"]["орфографический"] == cmp.GEN_EQUAL

    st = cmp.stats(pdb, pid, a, b)
    assert st["общие_признаки"]["грамматический"] == cmp.GEN_HIGHER
    # Общие признаки не попадают в счёт обычных позиций.
    assert st["всего"] == 2 and st[cmp.MATCH_COINCIDENCE] == 0


def test_stats_category_breakdown(pdb):
    """Разбивка подтверждённых совпадений по категориям Огорелкова."""
    pid, a, b = _setup_pair(pdb)
    for i in range(3):
        _accept_feature(pdb, pid, a, f"П{i}", subgroup="лексические")
        _accept_feature(pdb, pid, b, f"П{i}", subgroup="лексические")
    cmp.auto_match(pdb, pid, a, b)
    for r in pdb.fetch_comparisons(a, b):
        cmp.decide(pdb, pid, a, b, r["position_key"],
                   match_type=cmp.MATCH_COINCIDENCE, level="НС",
                   identification_value="высокая")
    st = cmp.stats(pdb, pid, a, b)
    bl = st["разбивка_по_категориям"]["языковые/лексические"]
    assert bl["есть"] == 3
    assert bl["мин_категорический"] == 10 and bl["категорический_ок"] is False
    assert bl["мин_вероятный"] == 5
    assert "языковые/лексические" in st["недобор_категорический"]
    # Суммарный порог Рубцовой сохраняется рядом.
    assert st["порог_методики"] == cmp.MIN_FEATURES_FOR_CONCLUSION


# ── блокировка категорического вывода и статистика ───────────────────────────
def test_blocks_strong_conclusion_from_pair_and_docs(pdb):
    pid, a, b = _setup_pair(pdb)
    assert cmp.pair_blocks_strong_conclusion(pdb, pid, a, b) is False
    pdb.save_suitability(pid, verdict="пригоден_с_ограничениями",
                         blocks_strong_conclusion=True, document_id=a,
                         flags=[], metrics={})
    assert cmp.pair_blocks_strong_conclusion(pdb, pid, a, b) is True


def test_stats_levels_and_threshold(pdb):
    pid, a, b = _setup_pair(pdb)
    for i in range(3):
        _accept_feature(pdb, pid, a, f"П{i}")
        _accept_feature(pdb, pid, b, f"П{i}")
    cmp.auto_match(pdb, pid, a, b)
    rows = pdb.fetch_comparisons(a, b)
    cmp.decide(pdb, pid, a, b, rows[0]["position_key"],
               match_type=cmp.MATCH_COINCIDENCE, level="НН",
               identification_value="высокая")
    cmp.decide(pdb, pid, a, b, rows[1]["position_key"],
               match_type=cmp.MATCH_COINCIDENCE, level="НСВ",
               identification_value="высокая")
    st = cmp.stats(pdb, pid, a, b)
    assert st["всего"] == 3
    assert st["подтверждено"] == 2
    assert st["уровень_НН"] == 1
    assert st["уровень_НСВ"] == 1
    assert st["до_порога"] == cmp.MIN_FEATURES_FOR_CONCLUSION - 2
    assert st["blocks_strong_conclusion"] is False
