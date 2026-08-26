"""Экспертная квалификация METHOD_FEATURE и связи с EVIDENCE."""
from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from protocol import db as protocol_db
from protocol import feature_map as fm
from protocol import feature_model as model

LINK = "LINK"
UNLINK = "UNLINK"

STABILITY_STATUSES = (
    "NOT_ASSESSED", "STABLE", "UNSTABLE", "INSUFFICIENT_DATA", "NOT_APPLICABLE",
)
OPPORTUNITY_STATUSES = (
    "NOT_ASSESSED", "SUFFICIENT", "INSUFFICIENT", "NOT_APPLICABLE",
)
COMPARABILITY_STATUSES = (
    "NOT_ASSESSED", "COMPARABLE", "LIMITED", "NOT_COMPARABLE",
)


def _field(item: Any, name: str, default=None):
    return model.get_field(item, name, default)


def _candidate_by_key(pdb: "protocol_db.ProtocolDB", document_id: int,
                      key: str):
    for candidate in pdb.fetch_feature_candidates(document_id):
        if fm.candidate_key(candidate) == key:
            return candidate
    return None


def _validate_document(pdb: "protocol_db.ProtocolDB", project_id: int,
                       document_id: int) -> None:
    document = pdb.get_document(document_id)
    if document is None or document["project_id"] != project_id:
        raise ValueError("Документ не принадлежит указанному проекту")


class EvidenceLinkService:
    """Append-only LINK/UNLINK между наблюдением и методическим признаком."""

    @staticmethod
    def current_links(pdb: "protocol_db.ProtocolDB", feature_candidate_key: str,
                      document_id: Optional[int] = None) -> list:
        events = pdb.fetch_evidence_link_events(feature_candidate_key, document_id)
        latest = {}
        for event in events:
            latest[event["evidence_candidate_key"]] = event
        return [event for event in latest.values() if event["action"] == LINK]

    @staticmethod
    def history(pdb: "protocol_db.ProtocolDB", feature_candidate_key: str,
                document_id: Optional[int] = None) -> list:
        return pdb.fetch_evidence_link_events(feature_candidate_key, document_id)

    @staticmethod
    def link(pdb: "protocol_db.ProtocolDB", project_id: int, document_id: int,
             feature: Any, evidence: Any, expert_note: str = "",
             program_version: Optional[str] = None) -> int:
        _validate_document(pdb, project_id, document_id)
        if model.normalized_role(feature) != model.METHOD_FEATURE:
            raise ValueError("Целью evidence-связи может быть только METHOD_FEATURE")
        if model.normalized_role(evidence) != model.EVIDENCE:
            raise ValueError("Источником evidence-связи может быть только EVIDENCE")
        if _field(feature, "document_id") != document_id:
            raise ValueError("METHOD_FEATURE принадлежит другому документу")
        if _field(evidence, "document_id") != document_id:
            raise ValueError("EVIDENCE принадлежит другому документу")
        feature_key = fm.candidate_key(feature)
        evidence_key = fm.candidate_key(evidence)
        if _candidate_by_key(pdb, document_id, feature_key) is None:
            raise ValueError("METHOD_FEATURE отсутствует в профиле документа")
        if _candidate_by_key(pdb, document_id, evidence_key) is None:
            raise ValueError("EVIDENCE отсутствует в профиле документа")
        active = {r["evidence_candidate_key"] for r in
                  EvidenceLinkService.current_links(pdb, feature_key, document_id)}
        if evidence_key in active:
            raise ValueError("Такая evidence-связь уже активна")
        event_id = pdb.append_evidence_link_event(
            project_id, document_id, feature_key, evidence_key, LINK,
            expert_note=expert_note, program_version=program_version)
        pdb.log_action(
            "evidence: LINK", project_id=project_id,
            details={"document_id": document_id, "feature_key": feature_key,
                     "evidence_key": evidence_key, "примечание": expert_note or None},
            program_version=program_version)
        return event_id

    @staticmethod
    def unlink(pdb: "protocol_db.ProtocolDB", project_id: int, document_id: int,
               feature_candidate_key: str, evidence_candidate_key: str,
               expert_note: str = "", program_version: Optional[str] = None) -> int:
        _validate_document(pdb, project_id, document_id)
        active = {r["evidence_candidate_key"] for r in
                  EvidenceLinkService.current_links(
                      pdb, feature_candidate_key, document_id)}
        if evidence_candidate_key not in active:
            raise ValueError("Активная evidence-связь не найдена")
        event_id = pdb.append_evidence_link_event(
            project_id, document_id, feature_candidate_key, evidence_candidate_key,
            UNLINK, expert_note=expert_note, program_version=program_version)
        pdb.log_action(
            "evidence: UNLINK", project_id=project_id,
            details={"document_id": document_id,
                     "feature_key": feature_candidate_key,
                     "evidence_key": evidence_candidate_key,
                     "примечание": expert_note or None},
            program_version=program_version)
        return event_id

    @staticmethod
    def linked_evidence(pdb: "protocol_db.ProtocolDB", document_id: int,
                        feature_candidate_key: str) -> list:
        rows = []
        for event in EvidenceLinkService.current_links(
                pdb, feature_candidate_key, document_id):
            evidence = _candidate_by_key(
                pdb, document_id, event["evidence_candidate_key"])
            if evidence is not None and model.normalized_role(evidence) == model.EVIDENCE:
                rows.append(evidence)
        return rows


class ExpertFeatureService:
    """Создание и квалификация признака экспертом в существующем feature pipeline."""

    @staticmethod
    def current_qualification(pdb: "protocol_db.ProtocolDB",
                              candidate_key: str) -> dict:
        events = pdb.fetch_feature_qualification_events(candidate_key)
        if not events:
            return {
                "expert_rationale": "", "stability_status": "NOT_ASSESSED",
                "opportunity_status": "NOT_ASSESSED",
                "comparability_status": "NOT_ASSESSED", "expert_note": "",
                "action": "",
            }
        return dict(events[-1])

    @staticmethod
    def history(pdb: "protocol_db.ProtocolDB", candidate_key: str) -> list:
        return pdb.fetch_feature_qualification_events(candidate_key)

    @staticmethod
    def _record_qualification(
        pdb: "protocol_db.ProtocolDB", project_id: int, document_id: int,
        candidate_key: str, action: str, *, expert_rationale: Optional[str] = None,
        stability_status: Optional[str] = None,
        opportunity_status: Optional[str] = None,
        comparability_status: Optional[str] = None, expert_note: str = "",
        program_version: Optional[str] = None,
    ) -> int:
        current = ExpertFeatureService.current_qualification(pdb, candidate_key)
        rationale = (current["expert_rationale"] if expert_rationale is None
                     else expert_rationale.strip())
        stability = stability_status or current["stability_status"]
        opportunity = opportunity_status or current["opportunity_status"]
        comparability = comparability_status or current["comparability_status"]
        if stability not in STABILITY_STATUSES:
            raise ValueError(f"Недопустимый статус устойчивости: {stability}")
        if opportunity not in OPPORTUNITY_STATUSES:
            raise ValueError(f"Недопустимый статус возможности проявления: {opportunity}")
        if comparability not in COMPARABILITY_STATUSES:
            raise ValueError(f"Недопустимый статус сопоставимости: {comparability}")
        event_id = pdb.append_feature_qualification_event(
            project_id, document_id, candidate_key, action,
            expert_rationale=rationale, stability_status=stability,
            opportunity_status=opportunity, comparability_status=comparability,
            expert_note=expert_note, program_version=program_version)
        pdb.log_action(
            f"квалификация признака: {action}", project_id=project_id,
            details={"document_id": document_id, "candidate_key": candidate_key,
                     "мотивировка": rationale or None, "устойчивость": stability,
                     "возможность_проявления": opportunity,
                     "сопоставимость": comparability,
                     "примечание": expert_note or None},
            program_version=program_version)
        return event_id

    @staticmethod
    def create_from_registry(
        pdb: "protocol_db.ProtocolDB", project_id: int, document_id: int,
        method_feature_id: str, evidence_candidate_keys: list[str],
        expert_rationale: str, program_version: Optional[str] = None,
    ):
        _validate_document(pdb, project_id, document_id)
        registry = model.registered_method_feature(method_feature_id)
        if registry is None:
            raise ValueError("Неизвестный method_feature_id; выберите признак из registry")
        if not expert_rationale.strip():
            raise ValueError("Для экспертного кандидата требуется мотивировка")
        if not evidence_candidate_keys:
            raise ValueError("Выберите хотя бы одно EVIDENCE")
        evidence_rows = []
        for key in dict.fromkeys(evidence_candidate_keys):
            evidence = _candidate_by_key(pdb, document_id, key)
            if evidence is None:
                raise ValueError(f"EVIDENCE отсутствует: {key}")
            if model.normalized_role(evidence) != model.EVIDENCE:
                raise ValueError("В основание можно включать только EVIDENCE")
            evidence_rows.append(evidence)

        uid = f"expert-{uuid4().hex}"
        candidate = {
            "group_name": registry["group"], "subgroup": registry["subgroup"],
            "kind": "кандидат_признак", "label": registry["label"],
            "value": "Экспертно квалифицированный кандидат",
            "fragment": None, "source": registry["source"],
            "source_section": registry["source_section"],
            "candidate_origin": model.CANDIDATE_ORIGIN_EXPERT,
            "candidate_uid": uid, "program_version": program_version,
            "role": model.METHOD_FEATURE,
            "source_kind": model.SOURCE_METHOD,
            "method_feature_id": registry["id"],
            "method_reference_informativeness": registry["reference_informativeness"],
            "expert_identification_value": None, "detection_reliability": "",
            "id_value": "", "reliability": "",
        }
        pdb.save_feature_candidates(document_id, [candidate])
        saved = next(c for c in pdb.fetch_feature_candidates(document_id)
                     if c["candidate_uid"] == uid)
        key = fm.candidate_key(saved)
        ExpertFeatureService._record_qualification(
            pdb, project_id, document_id, key, "CREATE",
            expert_rationale=expert_rationale, program_version=program_version)
        for evidence in evidence_rows:
            EvidenceLinkService.link(
                pdb, project_id, document_id, saved, evidence,
                expert_note="Основание экспертного кандидата",
                program_version=program_version)
        pdb.log_action(
            "создан экспертный METHOD_FEATURE", project_id=project_id,
            details={"document_id": document_id, "candidate_uid": uid,
                     "method_feature_id": method_feature_id,
                     "evidence_count": len(evidence_rows)},
            program_version=program_version)
        return saved

    @staticmethod
    def explain(pdb, project_id, document_id, candidate, expert_rationale,
                program_version=None):
        return ExpertFeatureService._record_qualification(
            pdb, project_id, document_id, fm.candidate_key(candidate), "EXPLAIN",
            expert_rationale=expert_rationale, program_version=program_version)

    @staticmethod
    def assess_stability(pdb, project_id, document_id, candidate, status,
                         expert_note="", program_version=None):
        return ExpertFeatureService._record_qualification(
            pdb, project_id, document_id, fm.candidate_key(candidate),
            "ASSESS_STABILITY", stability_status=status, expert_note=expert_note,
            program_version=program_version)

    @staticmethod
    def assess_opportunity(pdb, project_id, document_id, candidate, status,
                           expert_note="", program_version=None):
        return ExpertFeatureService._record_qualification(
            pdb, project_id, document_id, fm.candidate_key(candidate),
            "ASSESS_OPPORTUNITY", opportunity_status=status, expert_note=expert_note,
            program_version=program_version)

    @staticmethod
    def assess_comparability(pdb, project_id, document_id, candidate, status,
                             expert_note="", program_version=None):
        return ExpertFeatureService._record_qualification(
            pdb, project_id, document_id, fm.candidate_key(candidate),
            "ASSESS_COMPARABILITY", comparability_status=status,
            expert_note=expert_note, program_version=program_version)

    @staticmethod
    def confirm(
        pdb: "protocol_db.ProtocolDB", project_id: int, document_id: int,
        candidate: Any, expert_identification_value: str = "",
        expert_rationale: str = "", stability_status: str = "NOT_ASSESSED",
        opportunity_status: str = "NOT_ASSESSED",
        comparability_status: str = "NOT_ASSESSED",
        program_version: Optional[str] = None,
    ) -> str:
        registry = model.registered_method_feature(_field(candidate, "method_feature_id"))
        if registry is None:
            raise ValueError("METHOD_FEATURE отсутствует в method registry")
        if not EvidenceLinkService.current_links(
                pdb, fm.candidate_key(candidate), document_id):
            raise ValueError("Для принятия требуется хотя бы одно связанное EVIDENCE")
        if not expert_rationale.strip():
            raise ValueError("Для принятия требуется мотивировка эксперта")
        if stability_status == "NOT_ASSESSED":
            raise ValueError("Устойчивость должна быть явно оценена")
        if comparability_status == "NOT_ASSESSED":
            raise ValueError("Сопоставимость должна быть явно оценена")
        ExpertFeatureService._record_qualification(
            pdb, project_id, document_id, fm.candidate_key(candidate), "CONFIRM",
            expert_rationale=expert_rationale, stability_status=stability_status,
            opportunity_status=opportunity_status,
            comparability_status=comparability_status,
            program_version=program_version)
        return fm.decide(
            pdb, project_id, document_id, candidate, fm.STATUS_ACCEPTED,
            expert_identification_value=expert_identification_value,
            expert_note=expert_rationale, program_version=program_version)

    @staticmethod
    def reject(pdb, project_id, document_id, candidate, explanation="",
               program_version=None):
        if explanation:
            ExpertFeatureService.explain(
                pdb, project_id, document_id, candidate, explanation, program_version)
        return fm.decide(pdb, project_id, document_id, candidate, fm.STATUS_REJECTED,
                         expert_note=explanation, program_version=program_version)

    @staticmethod
    def mark_doubtful(pdb, project_id, document_id, candidate, explanation="",
                      program_version=None):
        if explanation:
            ExpertFeatureService.explain(
                pdb, project_id, document_id, candidate, explanation, program_version)
        return fm.decide(pdb, project_id, document_id, candidate, fm.STATUS_DOUBTFUL,
                         expert_note=explanation, program_version=program_version)

    @staticmethod
    def stability_observations(pdb: "protocol_db.ProtocolDB", project_id: int,
                               method_feature_id: str) -> list[dict]:
        """Справочные проявления по образцам; экспертный verdict не вычисляется."""
        result = []
        for document in pdb.fetch_documents(project_id):
            if document["role"] != protocol_db.ROLE_SAMPLE:
                continue
            for candidate in pdb.fetch_feature_candidates(document["id"]):
                if candidate["method_feature_id"] != method_feature_id:
                    continue
                links = EvidenceLinkService.linked_evidence(
                    pdb, document["id"], fm.candidate_key(candidate))
                words = document["word_count"] or 0
                result.append({
                    "document_id": document["id"], "filename": document["filename"],
                    "genre": document["genre"],
                    "document_date": document["document_date"],
                    "communicative_situation": document["communicative_situation"],
                    "evidence_count": len(links),
                    "per_1000_words": (len(links) * 1000 / words) if words else None,
                })
        return result

    @staticmethod
    def stability_summary(pdb: "protocol_db.ProtocolDB", project_id: int,
                          method_feature_id: str) -> dict:
        """Справочный интервал вариативности без автоматического verdict."""
        observations = ExpertFeatureService.stability_observations(
            pdb, project_id, method_feature_id)
        frequencies = [row["per_1000_words"] for row in observations
                       if row["per_1000_words"] is not None]
        interval = None
        if frequencies:
            interval = {"min": min(frequencies), "max": max(frequencies)}
        return {
            "observations": observations,
            "normalized_frequency_interval": interval,
            "sample_count": len(observations),
        }
