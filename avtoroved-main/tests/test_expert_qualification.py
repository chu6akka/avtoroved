"""Спринт 3: evidence → экспертная квалификация → METHOD_FEATURE."""
from __future__ import annotations

import sqlite3

import pytest

from protocol import comparison as cmp
from protocol import db as protocol_db
from protocol import feature_map as fm
from protocol import feature_model as model
from protocol.expert_features import EvidenceLinkService, ExpertFeatureService
from protocol.methodological_guard import MethodologicalGuard
from tests.method_feature_helpers import qualified_feature


@pytest.fixture()
def case(tmp_path):
    pdb = protocol_db.ProtocolDB(str(tmp_path / "qualification.db"))
    pid = pdb.create_project("Дело")
    disputed = pdb.add_document(pid, "disputed.txt", protocol_db.ROLE_DISPUTED,
                                 file_sha256="d", word_count=500)
    sample = pdb.add_document(pid, "sample.txt", protocol_db.ROLE_SAMPLE,
                              file_sha256="s", word_count=500)
    return pdb, pid, disputed, sample


def _profile_rows(pdb, document_id):
    pdb.save_feature_candidates(document_id, [{
        "group_name": "языковые", "subgroup": "лексические",
        "kind": "кандидат_признак", "label": "Жаргонизм", "value": "«движуха»",
        "fragment": "эта движуха", "source": "test", "role": model.EVIDENCE,
        "source_kind": model.SOURCE_ENGINEERING, "candidate_uid": f"ev-{document_id}",
        "candidate_origin": model.CANDIDATE_ORIGIN_AUTO,
    }, {
        "group_name": "языковые", "subgroup": "лексические", "kind": "счётчик",
        "label": "TTR", "value": "0.5", "source": "test", "role": model.AUX_METRIC,
        "source_kind": model.SOURCE_ENGINEERING, "candidate_uid": f"aux-{document_id}",
    }, {
        "group_name": "языковые", "subgroup": "грамматический",
        "kind": "общий_признак", "label": "Грамматический навык",
        "value": "средняя · 2 ошибок/200 словоформ", "source": "test",
        "role": model.GENERAL_SKILL, "source_kind": model.SOURCE_METHOD,
        "candidate_uid": f"gen-{document_id}",
    }])
    return {row["candidate_uid"]: row for row in pdb.fetch_feature_candidates(document_id)}


def _created(pdb, pid, document_id, rationale="обоснование эксперта"):
    rows = _profile_rows(pdb, document_id)
    feature = ExpertFeatureService.create_from_registry(
        pdb, pid, document_id, "nn.smysl.political",
        [fm.candidate_key(rows[f"ev-{document_id}"])], rationale)
    return feature, rows


def _confirm(pdb, pid, document_id, feature, stability="STABLE",
             comparability="COMPARABLE"):
    ExpertFeatureService.confirm(
        pdb, pid, document_id, feature,
        expert_identification_value="высокая",
        expert_rationale="обоснование эксперта", stability_status=stability,
        opportunity_status="SUFFICIENT", comparability_status=comparability)
    return next(f for f in pdb.fetch_features(document_id=document_id)
                if f["candidate_key"] == fm.candidate_key(feature))


def test_01_evidence_links_to_method_feature(case):
    pdb, pid, did, _ = case
    feature, _ = _created(pdb, pid, did)
    assert len(EvidenceLinkService.current_links(pdb, fm.candidate_key(feature), did)) == 1


def test_02_aux_metric_cannot_be_linked_as_evidence(case):
    pdb, pid, did, _ = case
    feature, rows = _created(pdb, pid, did)
    with pytest.raises(ValueError, match="только EVIDENCE"):
        EvidenceLinkService.link(pdb, pid, did, feature, rows[f"aux-{did}"])


def test_03_general_skill_cannot_be_accepted_as_private_feature(case):
    pdb, pid, did, _ = case
    rows = _profile_rows(pdb, did)
    with pytest.raises(ValueError, match="METHOD_FEATURE"):
        fm.decide(pdb, pid, did, rows[f"gen-{did}"], fm.STATUS_ACCEPTED)


def test_04_unknown_method_feature_id_is_rejected(case):
    pdb, pid, did, _ = case
    rows = _profile_rows(pdb, did)
    with pytest.raises(ValueError, match="Неизвестный method_feature_id"):
        ExpertFeatureService.create_from_registry(
            pdb, pid, did, "unknown.feature", [fm.candidate_key(rows[f"ev-{did}"])], "x")


def test_05_expert_candidate_comes_from_registry(case):
    pdb, pid, did, _ = case
    rows = _profile_rows(pdb, did)
    feature = ExpertFeatureService.create_from_registry(
        pdb, pid, did, "nn.smysl.political",
        [fm.candidate_key(rows[f"ev-{did}"])], "обоснование",
        program_version="3.0-test")
    registry = model.registered_method_feature(feature["method_feature_id"])
    assert feature["label"] == registry["label"]
    assert feature["created_at"] and feature["program_version"] == "3.0-test"
    assert feature["source"] == registry["source"]
    assert feature["candidate_origin"] == model.CANDIDATE_ORIGIN_EXPERT


def test_06_creation_does_not_set_expert_identification_value(case):
    pdb, pid, did, _ = case
    feature, _ = _created(pdb, pid, did)
    assert feature["expert_identification_value"] is None
    assert feature["id_value"] in (None, "")


def test_07_expert_candidate_survives_profile_rebuild(case):
    pdb, pid, did, _ = case
    feature, _ = _created(pdb, pid, did)
    pdb.clear_feature_candidates(did)
    remaining = pdb.fetch_feature_candidates(did)
    assert [row["candidate_uid"] for row in remaining] == [feature["candidate_uid"]]


def test_08_auto_candidates_are_rebuilt_as_before(case):
    pdb, _pid, did, _ = case
    _profile_rows(pdb, did)
    pdb.clear_feature_candidates(did)
    assert pdb.fetch_feature_candidates(did) == []
    assert len(_profile_rows(pdb, did)) == 3


def test_09_link_unlink_history_is_append_only(case):
    pdb, pid, did, _ = case
    feature, rows = _created(pdb, pid, did)
    fk, ek = fm.candidate_key(feature), fm.candidate_key(rows[f"ev-{did}"])
    EvidenceLinkService.unlink(pdb, pid, did, fk, ek, "снято")
    EvidenceLinkService.link(pdb, pid, did, feature, rows[f"ev-{did}"], "возвращено")
    assert [row["action"] for row in EvidenceLinkService.history(pdb, fk)] == [
        "LINK", "UNLINK", "LINK"]


def test_10_duplicate_active_link_is_rejected(case):
    pdb, pid, did, _ = case
    feature, rows = _created(pdb, pid, did)
    with pytest.raises(ValueError, match="уже активна"):
        EvidenceLinkService.link(pdb, pid, did, feature, rows[f"ev-{did}"])


def test_11_method_feature_without_evidence_cannot_be_confirmed(case):
    pdb, pid, did, _ = case
    _profile_rows(pdb, did)
    candidate = {
        "group_name": "смысловые", "subgroup": "тематические",
        "kind": "кандидат_признак", "label": "Политическая направленность текста",
        "source": "методика", "source_kind": model.SOURCE_METHOD,
        "role": model.METHOD_FEATURE, "method_feature_id": "nn.smysl.political",
        "candidate_origin": model.CANDIDATE_ORIGIN_EXPERT, "candidate_uid": "no-evidence",
    }
    pdb.save_feature_candidates(did, [candidate])
    saved = next(r for r in pdb.fetch_feature_candidates(did)
                 if r["candidate_uid"] == "no-evidence")
    with pytest.raises(ValueError, match="связанное EVIDENCE"):
        _confirm(pdb, pid, did, saved)


def test_12_confirmation_requires_rationale(case):
    pdb, pid, did, _ = case
    feature, _ = _created(pdb, pid, did)
    with pytest.raises(ValueError, match="мотивировка"):
        ExpertFeatureService.confirm(
            pdb, pid, did, feature, expert_rationale="", stability_status="STABLE",
            comparability_status="COMPARABLE")


def test_13_not_assessed_stability_is_not_countable(case):
    pdb, pid, did, _ = case
    feature, _ = _created(pdb, pid, did)
    fm.decide(pdb, pid, did, feature, fm.STATUS_ACCEPTED,
              expert_note="обоснование", expert_identification_value="высокая")
    state = pdb.fetch_features(document_id=did)[0]
    assert MethodologicalGuard.is_countable(pdb, state) is False


def test_14_unstable_feature_is_not_countable(case):
    pdb, pid, did, _ = case
    feature, _ = _created(pdb, pid, did)
    state = _confirm(pdb, pid, did, feature, stability="UNSTABLE")
    assert MethodologicalGuard.is_countable(pdb, state) is False


def test_15_not_comparable_feature_is_not_countable(case):
    pdb, pid, did, _ = case
    feature, _ = _created(pdb, pid, did)
    state = _confirm(pdb, pid, did, feature, comparability="NOT_COMPARABLE")
    assert MethodologicalGuard.is_countable(pdb, state) is False


def test_16_fully_qualified_feature_is_countable(case):
    pdb, pid, did, _ = case
    feature, _ = _created(pdb, pid, did)
    state = _confirm(pdb, pid, did, feature)
    assert MethodologicalGuard.is_countable(pdb, state, True) is True


@pytest.mark.parametrize("role", [model.AUX_METRIC, model.EVIDENCE])
def test_17_18_non_method_roles_do_not_enter_strict_comparison(case, role):
    pdb, pid, a, b = case
    for did in (a, b):
        pdb.record_feature_decision(
            pid, did, f"{role}-{did}", fm.STATUS_ACCEPTED,
            {"group_name": "языковые", "subgroup": "лексические",
             "label": role, "value": "x", "role": role,
             "source_kind": model.SOURCE_ENGINEERING})
    assert cmp.auto_match(pdb, pid, a, b)["positions"] == 0


def test_19_general_skill_remains_available_to_vula(case):
    pdb, pid, a, b = case
    for did, rate in ((a, 1), (b, 6)):
        pdb.save_feature_candidates(did, [{
            "group_name": "языковые", "subgroup": "грамматический",
            "kind": "общий_признак", "label": "Грамматический навык",
            "value": f"средняя · {rate} ошибок/200 словоформ", "source": "test",
            "role": model.GENERAL_SKILL, "source_kind": model.SOURCE_METHOD,
        }])
    summary = cmp.auto_match(pdb, pid, a, b)
    assert summary["general"]["грамматический"] == cmp.GEN_HIGHER
    assert cmp.stats(pdb, pid, a, b)["всего"] == 0


def test_20_absence_without_sufficient_opportunity_is_not_confirmed(case):
    pdb, pid, a, b = case
    qualified_feature(pdb, pid, a, "Только A")
    cmp.auto_match(pdb, pid, a, b)
    row = pdb.fetch_comparisons(a, b)[0]
    with pytest.raises(ValueError, match="SUFFICIENT"):
        cmp.decide(pdb, pid, a, b, row["position_key"],
                   match_type=cmp.MATCH_ONLY_A,
                   difference_qualification="SUBSTANTIAL", expert_note="различие")


def test_21_absence_with_sufficient_opportunity_can_be_confirmed(case):
    pdb, pid, a, b = case
    qualified_feature(pdb, pid, a, "Только A")
    cmp.auto_match(pdb, pid, a, b)
    row = pdb.fetch_comparisons(a, b)[0]
    cmp.decide(pdb, pid, a, b, row["position_key"], match_type=cmp.MATCH_ONLY_A,
               difference_qualification="SUBSTANTIAL", opportunity_status="SUFFICIENT",
               expert_note="в образце была достаточная возможность проявления")
    assert pdb.fetch_comparisons(a, b)[0]["status"] == cmp.STATUS_CONFIRMED


def test_22_difference_without_qualification_is_not_confirmed(case):
    pdb, pid, a, b = case
    qualified_feature(pdb, pid, a, "П")
    qualified_feature(pdb, pid, b, "П")
    cmp.auto_match(pdb, pid, a, b)
    row = pdb.fetch_comparisons(a, b)[0]
    with pytest.raises(ValueError, match="квалификации"):
        cmp.decide(pdb, pid, a, b, row["position_key"],
                   match_type=cmp.MATCH_DIFFERENCE, expert_note="различается")


@pytest.mark.parametrize("qualification", ["SUBSTANTIAL", "EXPLAINED_BY_GENRE"])
def test_23_24_qualified_difference_is_stored(case, qualification):
    pdb, pid, a, b = case
    qualified_feature(pdb, pid, a, "П")
    qualified_feature(pdb, pid, b, "П")
    cmp.auto_match(pdb, pid, a, b)
    row = pdb.fetch_comparisons(a, b)[0]
    cmp.decide(pdb, pid, a, b, row["position_key"],
               match_type=cmp.MATCH_DIFFERENCE,
               difference_qualification=qualification,
               opportunity_status="SUFFICIENT", expert_note="мотивировка различия")
    assert pdb.fetch_comparisons(a, b)[0]["difference_qualification"] == qualification


def test_25_experimental_method_feature_is_not_countable(case):
    pdb, pid, did, _ = case
    feature, _ = _created(pdb, pid, did)
    with pdb._connect() as conn:
        conn.execute("UPDATE feature_candidates SET source_kind='EXPERIMENTAL' "
                     "WHERE candidate_uid=?", (feature["candidate_uid"],))
    feature = next(r for r in pdb.fetch_feature_candidates(did)
                   if r["candidate_uid"] == feature["candidate_uid"])
    state = _confirm(pdb, pid, did, feature)
    assert MethodologicalGuard.is_countable(pdb, state) is False


def test_26_disputed_texts_are_compared_separately(case):
    pdb, pid, a1, sample = case
    a2 = pdb.add_document(pid, "disputed-2.txt", protocol_db.ROLE_DISPUTED,
                          file_sha256="d2", word_count=500)
    for did in (a1, a2, sample):
        qualified_feature(pdb, pid, did, "П")
    cmp.auto_match(pdb, pid, a1, sample)
    cmp.auto_match(pdb, pid, a2, sample)
    assert len(pdb.fetch_comparisons(a1, sample)) == 1
    assert len(pdb.fetch_comparisons(a2, sample)) == 1
    assert pdb.fetch_comparisons(a1, sample)[0]["pair_doc_a"] != \
        pdb.fetch_comparisons(a2, sample)[0]["pair_doc_a"]


def test_27_old_sqlite_schema_gets_sprint3_columns(tmp_path):
    path = str(tmp_path / "migration.db")
    pdb = protocol_db.ProtocolDB(path)
    with sqlite3.connect(path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(feature_candidates)")}
        cmp_cols = {row[1] for row in conn.execute("PRAGMA table_info(comparisons)")}
    assert {"candidate_origin", "candidate_uid", "source_section", "program_version"} <= cols
    assert {"difference_qualification", "opportunity_status"} <= cmp_cols


def test_28_existing_project_reopens(case):
    pdb, pid, _a, _b = case
    reopened = protocol_db.ProtocolDB(pdb.path)
    assert reopened.get_project(pid)["name"] == "Дело"


def test_29_feature_decisions_remain_append_only(case):
    pdb, pid, did, _ = case
    feature, _ = _created(pdb, pid, did)
    _confirm(pdb, pid, did, feature)
    ExpertFeatureService.reject(pdb, pid, did, feature, "пересмотр")
    assert [row["status"] for row in pdb.fetch_feature_decisions(did)] == [
        fm.STATUS_REJECTED, fm.STATUS_ACCEPTED]


def test_30_stability_observations_are_descriptive_only(case):
    pdb, pid, _a, sample = case
    feature, _ = _created(pdb, pid, sample)
    rows = ExpertFeatureService.stability_observations(
        pdb, pid, feature["method_feature_id"])
    assert rows[0]["document_id"] == sample
    assert rows[0]["evidence_count"] == 1
    assert "stability_status" not in rows[0]


def test_31_stability_summary_has_metadata_and_interval(tmp_path):
    pdb = protocol_db.ProtocolDB(str(tmp_path / "stability.db"))
    pid = pdb.create_project("Дело")
    first = pdb.add_document(
        pid, "sample-1.txt", protocol_db.ROLE_SAMPLE, file_sha256="s1",
        genre="письмо", document_date="2024-01-01",
        communicative_situation="частная переписка", word_count=500)
    second = pdb.add_document(
        pid, "sample-2.txt", protocol_db.ROLE_SAMPLE, file_sha256="s2",
        genre="письмо", document_date="2024-02-01",
        communicative_situation="частная переписка", word_count=1000)
    for did in (first, second):
        _created(pdb, pid, did)
    summary = ExpertFeatureService.stability_summary(
        pdb, pid, "nn.smysl.political")
    assert summary["sample_count"] == 2
    assert summary["normalized_frequency_interval"] == {"min": 1.0, "max": 2.0}
    assert summary["observations"][0]["document_date"] == "2024-01-01"
    assert summary["observations"][0]["communicative_situation"] == "частная переписка"
