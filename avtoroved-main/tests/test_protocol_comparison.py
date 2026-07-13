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


# ── блокировка категорического вывода и статистика ───────────────────────────
def test_blocks_strong_conclusion_from_pair_and_docs(pdb):
    pid, a, b = _setup_pair(pdb)
    assert cmp.pair_blocks_strong_conclusion(pdb, pid, a, b) is False
    pdb.save_suitability(pid, verdict="пригоден_с_ограничениями",
                         blocks_strong_conclusion=True, document_id=a,
                         flags=[], metrics={})
    assert cmp.pair_blocks_strong_conclusion(pdb, pid, a, b) is True


# ── общие признаки: сопоставление с допусками (Минюст, с. 19) ────────────────
from protocol import profile as prof


def _add_general(pdb, did, skill, rate, level="средняя", reliability=""):
    pdb.save_feature_candidates(did, [{
        "group_name": "языковые", "subgroup": skill, "kind": prof.KIND_GENERAL,
        "label": f"{prof.GENERAL_LABEL_PREFIX}{skill} навык",
        "value": prof.GENERAL_VALUE_FMT.format(level=level, rate=rate,
                                               count=int(rate)),
        "fragment": None, "source": "errors.scale", "id_value": "",
        "reliability": reliability}])


def test_parse_general_rate():
    assert cmp.parse_general_rate("средняя · 5.0 ош./200 сл. · уникальных 5") == 5.0
    assert cmp.parse_general_rate("высокая · 0.0 ош./200 сл. · уникальных 0") == 0.0
    assert cmp.parse_general_rate("что-то другое") is None
    assert cmp.parse_general_rate(None) is None


def test_general_verdicts_tolerance(pdb):
    """В допуске → совпадает; за допуском → выше/ниже в спорном (по ошибкам)."""
    pid, a, b = _setup_pair(pdb)
    _add_general(pdb, a, "грамматический", 1.0)         # |1-2.5|=1.5 ≤ 2
    _add_general(pdb, b, "грамматический", 2.5)
    _add_general(pdb, a, "лексико-фразеологический", 0.5)  # 0.5 vs 4.0 → выше
    _add_general(pdb, b, "лексико-фразеологический", 4.0)
    _add_general(pdb, a, "орфографический", 6.0)        # 6 vs 1 → ниже (>4)
    _add_general(pdb, b, "орфографический", 1.0)
    _add_general(pdb, a, "пунктуационный", 3.0)         # |3-6|=3 ≤ 4 → совпадает
    _add_general(pdb, b, "пунктуационный", 6.0)

    v = cmp.general_skill_verdicts(pdb, a, b)
    assert v["грамматический"]["verdict"] == cmp.GENERAL_VERDICT_EQUAL
    assert v["лексико-фразеологический"]["verdict"] == cmp.GENERAL_VERDICT_HIGHER_A
    assert v["лексико-фразеологический"]["delta"] == -3.5
    assert v["орфографический"]["verdict"] == cmp.GENERAL_VERDICT_LOWER_A
    assert v["пунктуационный"]["verdict"] == cmp.GENERAL_VERDICT_EQUAL


def test_general_verdicts_missing_side_skipped(pdb):
    pid, a, b = _setup_pair(pdb)
    _add_general(pdb, a, "грамматический", 1.0)
    v = cmp.general_skill_verdicts(pdb, a, b)
    assert v == {}


def test_auto_match_adds_general_positions(pdb):
    """Общие признаки попадают в comparisons как авто-черновики с вердиктом."""
    pid, a, b = _setup_pair(pdb)
    _add_general(pdb, a, "грамматический", 0.5)
    _add_general(pdb, b, "грамматический", 4.0)     # различие (выше в спорном)
    _add_general(pdb, a, "пунктуационный", 2.0)
    _add_general(pdb, b, "пунктуационный", 3.0)     # совпадает

    summary = cmp.auto_match(pdb, pid, a, b)
    assert summary["positions"] == 2
    assert set(summary["general_verdicts"]) == {"грамматический", "пунктуационный"}
    rows = {r["label"]: r for r in pdb.fetch_comparisons(a, b)}
    gram = rows[f"{prof.GENERAL_LABEL_PREFIX}грамматический навык"]
    assert gram["match_type"] == cmp.MATCH_DIFFERENCE
    assert gram["status"] == cmp.STATUS_AUTO
    punct = rows[f"{prof.GENERAL_LABEL_PREFIX}пунктуационный навык"]
    assert punct["match_type"] == cmp.MATCH_COINCIDENCE
    # Журнал: вердикты записаны.
    log = pdb.fetch_audit_log(pid)
    details = json.loads(log[0]["details"])
    assert details["общие_признаки"]["грамматический"]["вердикт"] == \
        cmp.GENERAL_VERDICT_HIGHER_A


# ── объяснимые различия ──────────────────────────────────────────────────────
def test_explained_difference_requires_note(pdb):
    pid, a, b = _setup_pair(pdb)
    _accept_feature(pdb, pid, a, "П1")
    cmp.auto_match(pdb, pid, a, b)
    key = pdb.fetch_comparisons(a, b)[0]["position_key"]
    with pytest.raises(ValueError, match="пояснения"):
        cmp.decide(pdb, pid, a, b, key, match_type=cmp.MATCH_ONLY_A,
                   explained=True)
    with pytest.raises(ValueError, match="различие"):
        cmp.decide(pdb, pid, a, b, key, match_type=cmp.MATCH_COINCIDENCE,
                   expert_note="жанр", explained=True)
    cmp.decide(pdb, pid, a, b, key, match_type=cmp.MATCH_ONLY_A, level="НС",
               expert_note="объясняется жанровыми условиями", explained=True)
    row = pdb.fetch_comparisons(a, b)[0]
    assert row["explained"] == 1 and row["status"] == cmp.STATUS_CONFIRMED


def test_reset_clears_explained(pdb):
    pid, a, b = _setup_pair(pdb)
    _accept_feature(pdb, pid, a, "П1")
    cmp.auto_match(pdb, pid, a, b)
    key = pdb.fetch_comparisons(a, b)[0]["position_key"]
    cmp.decide(pdb, pid, a, b, key, match_type=cmp.MATCH_ONLY_A,
               expert_note="жанр", explained=True)
    cmp.reset(pdb, pid, a, b, key)
    row = pdb.fetch_comparisons(a, b)[0]
    assert row["explained"] == 0 and row["status"] == cmp.STATUS_AUTO


# ── корзины Огорелкова ───────────────────────────────────────────────────────
def test_bucket_of_mapping():
    assert cmp.bucket_of("смысловые", None) == "смысловые"
    assert cmp.bucket_of("языковые", "лексические") == "языковые: лексические"
    assert cmp.bucket_of("языковые", "орфографические") == cmp.BUCKET_ORTH_PUNCT
    assert cmp.bucket_of("языковые", "пунктуационные") == cmp.BUCKET_ORTH_PUNCT
    assert cmp.bucket_of("языковые", "грамматические") is None   # только в сумму
    assert cmp.bucket_of("языковые", "грамматический") is None   # общий признак


def test_bucket_breakdown_counts_confirmed_coincidences(pdb):
    pid, a, b = _setup_pair(pdb)
    for i in range(3):
        _accept_feature(pdb, pid, a, f"Л{i}", subgroup="лексические")
        _accept_feature(pdb, pid, b, f"Л{i}", subgroup="лексические")
    cmp.auto_match(pdb, pid, a, b)
    rows = pdb.fetch_comparisons(a, b)
    # Подтверждаем 2 из 3 как совпадения; третью — как различие.
    cmp.decide(pdb, pid, a, b, rows[0]["position_key"],
               match_type=cmp.MATCH_COINCIDENCE, level="НН")
    cmp.decide(pdb, pid, a, b, rows[1]["position_key"],
               match_type=cmp.MATCH_COINCIDENCE, level="НС")
    cmp.decide(pdb, pid, a, b, rows[2]["position_key"],
               match_type=cmp.MATCH_DIFFERENCE, level="НС")
    bd = {row["bucket"]: row for row in cmp.bucket_breakdown(pdb, a, b)}
    lex = bd["языковые: лексические"]
    assert lex["confirmed"] == 2                    # различие не считается
    assert lex["threshold_categorical"] == 10
    assert lex["threshold_probable"] == 5
    assert lex["meets_categorical"] is False
    st = cmp.stats(pdb, pid, a, b)
    assert "разбивка_по_группам" in st and "общие_признаки" in st


def test_stats_levels_and_threshold(pdb):
    pid, a, b = _setup_pair(pdb)
    for i in range(3):
        _accept_feature(pdb, pid, a, f"П{i}")
        _accept_feature(pdb, pid, b, f"П{i}")
    cmp.auto_match(pdb, pid, a, b)
    rows = pdb.fetch_comparisons(a, b)
    cmp.decide(pdb, pid, a, b, rows[0]["position_key"],
               match_type=cmp.MATCH_COINCIDENCE, level="НН")
    cmp.decide(pdb, pid, a, b, rows[1]["position_key"],
               match_type=cmp.MATCH_COINCIDENCE, level="НСВ")
    st = cmp.stats(pdb, pid, a, b)
    assert st["всего"] == 3
    assert st["подтверждено"] == 2
    assert st["уровень_НН"] == 1
    assert st["уровень_НСВ"] == 1
    assert st["до_порога"] == cmp.MIN_FEATURES_FOR_CONCLUSION - 2
    assert st["blocks_strong_conclusion"] is False
