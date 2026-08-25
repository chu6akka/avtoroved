"""Тесты карты признаков (protocol/feature_map.py): отбор кандидатов экспертом."""
import json

import pytest

from protocol import db as protocol_db
from protocol import feature_map as fm
from protocol import feature_model as model


@pytest.fixture()
def pdb(tmp_path):
    return protocol_db.ProtocolDB(str(tmp_path / "fmap.db"))


def _make_candidate(pdb, pid, did, label="Пунктуационная: запятая",
                    value="лишняя запятая · требует проверки",
                    reliability="средняя"):
    pdb.save_feature_candidates(did, [{
        "group_name": "языковые", "subgroup": "пунктуационные",
        "kind": "кандидат_признак", "label": label, "value": value,
        "fragment": "текст , фрагмент", "source": "PUNCT:TEST",
        "role": model.METHOD_FEATURE, "source_kind": model.SOURCE_METHOD,
        "method_feature_id": "test.punctuation.comma",
        "method_reference_informativeness": "средняя",
        "detection_reliability": reliability,
        "id_value": "", "reliability": reliability,
    }])
    return pdb.fetch_feature_candidates(did)[-1]


def _setup(pdb):
    pid = pdb.create_project("Дело")
    did = pdb.add_document(pid, "d.txt", protocol_db.ROLE_SAMPLE,
                           file_sha256="h", word_count=100)
    return pid, did


# ── стабильный ключ ──────────────────────────────────────────────────────────
def test_candidate_key_stable_across_rebuild(pdb):
    pid, did = _setup(pdb)
    c1 = _make_candidate(pdb, pid, did)
    key1 = fm.candidate_key(c1)
    # Пересборка профиля: clear + insert, содержимое то же — ключ стабилен.
    pdb.clear_feature_candidates(did)
    c2 = _make_candidate(pdb, pid, did)
    assert fm.candidate_key(c2) == key1


def test_candidate_key_changes_with_content(pdb):
    pid, did = _setup(pdb)
    c1 = _make_candidate(pdb, pid, did)
    pdb.clear_feature_candidates(did)
    c2 = _make_candidate(pdb, pid, did, value="другое описание")
    assert fm.candidate_key(c1) != fm.candidate_key(c2)


# ── решения: журнал append-only + текущее состояние ──────────────────────────
def test_decide_writes_decision_and_feature(pdb):
    pid, did = _setup(pdb)
    cand = _make_candidate(pdb, pid, did)
    key = fm.decide(pdb, pid, did, cand, fm.STATUS_ACCEPTED,
                    expert_id_value="высокая", expert_note="устойчивый навык",
                    program_version="5.0")
    feats = pdb.fetch_features(document_id=did)
    assert len(feats) == 1
    f = feats[0]
    assert f["candidate_key"] == key
    assert f["status"] == fm.STATUS_ACCEPTED
    assert f["expert_id_value"] == "высокая"
    assert f["expert_identification_value"] == "высокая"
    assert f["expert_note"] == "устойчивый навык"
    assert f["auto_id_value"] == ""
    assert f["method_reference_informativeness"] == "средняя"
    # История.
    hist = pdb.fetch_feature_decisions(did)
    assert len(hist) == 1


def test_last_decision_wins_history_grows(pdb):
    pid, did = _setup(pdb)
    cand = _make_candidate(pdb, pid, did)
    fm.decide(pdb, pid, did, cand, fm.STATUS_DOUBTFUL)
    fm.decide(pdb, pid, did, cand, fm.STATUS_REJECTED)
    feats = pdb.fetch_features(document_id=did)
    assert len(feats) == 1                       # текущее состояние — одна строка
    assert feats[0]["status"] == fm.STATUS_REJECTED
    hist = pdb.fetch_feature_decisions(did)
    assert len(hist) == 2                        # история append-only, обе записи
    assert [h["status"] for h in hist] == [fm.STATUS_REJECTED, fm.STATUS_DOUBTFUL]


def test_reset_clears_state_keeps_history(pdb):
    pid, did = _setup(pdb)
    cand = _make_candidate(pdb, pid, did)
    fm.decide(pdb, pid, did, cand, fm.STATUS_ACCEPTED, expert_id_value="средняя")
    fm.decide(pdb, pid, did, cand, fm.STATUS_RESET)
    assert pdb.fetch_features(document_id=did) == []      # решение снято
    assert len(pdb.fetch_feature_decisions(did)) == 2     # история сохранена


def test_invalid_status_rejected(pdb):
    pid, did = _setup(pdb)
    cand = _make_candidate(pdb, pid, did)
    with pytest.raises(ValueError):
        fm.decide(pdb, pid, did, cand, "одобрен-наверное")


# ── решения переживают пересборку профиля ────────────────────────────────────
def test_decisions_survive_profile_rebuild(pdb):
    pid, did = _setup(pdb)
    cand = _make_candidate(pdb, pid, did)
    fm.decide(pdb, pid, did, cand, fm.STATUS_ACCEPTED, expert_id_value="высокая")
    # Пересборка профиля.
    pdb.clear_feature_candidates(did)
    _make_candidate(pdb, pid, did)     # тот же кандидат, новый id
    pairs = fm.candidates_with_state(pdb, did)
    assert len(pairs) == 1
    cand2, feat = pairs[0]
    assert feat is not None
    assert feat["status"] == fm.STATUS_ACCEPTED   # решение не потерялось


def test_changed_candidate_returns_to_undecided(pdb):
    pid, did = _setup(pdb)
    cand = _make_candidate(pdb, pid, did)
    fm.decide(pdb, pid, did, cand, fm.STATUS_ACCEPTED)
    pdb.clear_feature_candidates(did)
    _make_candidate(pdb, pid, did, value="изменённое содержание")
    pairs = fm.candidates_with_state(pdb, did)
    _c, feat = pairs[0]
    assert feat is None    # содержание изменилось → решение не применяется


# ── выборка и статистика ─────────────────────────────────────────────────────
def test_candidates_with_state_excludes_counters(pdb):
    pid, did = _setup(pdb)
    _make_candidate(pdb, pid, did)
    pdb.save_feature_candidates(did, [{
        "group_name": "языковые", "subgroup": "лексические",
        "kind": "счётчик", "label": "TTR", "value": "0.5",
        "fragment": None, "source": "metrics", "id_value": "", "reliability": "",
        "role": model.AUX_METRIC, "source_kind": model.SOURCE_ENGINEERING,
    }])
    pairs = fm.candidates_with_state(pdb, did)
    assert len(pairs) == 1     # счётчик не попал в карту признаков


def test_non_method_feature_cannot_be_accepted(pdb):
    pid, did = _setup(pdb)
    pdb.save_feature_candidates(did, [{
        "group_name": "языковые", "subgroup": "лексические",
        "kind": "кандидат_признак", "label": "единичная лексема", "value": "x",
        "source": "detector", "role": model.EVIDENCE,
        "source_kind": model.SOURCE_ENGINEERING,
    }])
    cand = pdb.fetch_feature_candidates(did)[0]
    with pytest.raises(ValueError, match="METHOD_FEATURE"):
        fm.decide(pdb, pid, did, cand, fm.STATUS_ACCEPTED)


def test_stats(pdb):
    pid, did = _setup(pdb)
    c1 = _make_candidate(pdb, pid, did, label="К1")
    _make_candidate(pdb, pid, did, label="К2")
    fm.decide(pdb, pid, did, c1, fm.STATUS_DOUBTFUL)
    st = fm.stats(fm.candidates_with_state(pdb, did))
    assert st["всего"] == 2
    assert st["решено"] == 1
    assert st["нерешённые"] == 1
    assert st[fm.STATUS_DOUBTFUL] == 1


# ── журнал действий ──────────────────────────────────────────────────────────
def test_decision_logged_in_audit(pdb):
    pid, did = _setup(pdb)
    cand = _make_candidate(pdb, pid, did)
    fm.decide(pdb, pid, did, cand, fm.STATUS_ACCEPTED,
              expert_id_value="высокая", program_version="5.0")
    log = pdb.fetch_audit_log(pid)
    entry = next(r for r in log if r["action"] == f"признак: {fm.STATUS_ACCEPTED}")
    details = json.loads(entry["details"])
    assert details["candidate_key"]
    assert details["ид_ценность_эксперта"] == "высокая"
    assert entry["program_version"] == "5.0"
