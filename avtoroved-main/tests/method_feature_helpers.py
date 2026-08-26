"""Тестовые фабрики квалифицированных признаков протокола."""
from __future__ import annotations

import hashlib

from protocol import feature_map as fm
from protocol import feature_model as model
from protocol.expert_features import EvidenceLinkService, ExpertFeatureService


def qualified_feature(pdb, project_id, document_id, label,
                      group="языковые", subgroup="лексические", value="значение",
                      status=fm.STATUS_ACCEPTED, expert_value="средняя", suffix=""):
    token = hashlib.sha256(
        f"{document_id}|{group}|{subgroup}|{label}|{suffix}".encode("utf-8")
    ).hexdigest()[:12]
    evidence_uid = f"test-evidence-{token}"
    feature_uid = f"test-feature-{token}"
    pdb.save_feature_candidates(document_id, [{
        "group_name": group, "subgroup": subgroup, "kind": "кандидат_признак",
        "label": f"Evidence: {label}", "value": value, "fragment": f"фраг {label}",
        "source": "test", "candidate_origin": model.CANDIDATE_ORIGIN_AUTO,
        "candidate_uid": evidence_uid, "role": model.EVIDENCE,
        "source_kind": model.SOURCE_ENGINEERING, "id_value": "", "reliability": "",
    }, {
        "group_name": group, "subgroup": subgroup, "kind": "кандидат_признак",
        "label": label, "value": value, "fragment": f"фраг {label}",
        "source": "Рубцова и др., Комплексная методика ЭКЦ МВД, 2007",
        "source_section": "с. 86", "candidate_origin": model.CANDIDATE_ORIGIN_EXPERT,
        "candidate_uid": feature_uid, "role": model.METHOD_FEATURE,
        "source_kind": model.SOURCE_METHOD,
        "method_feature_id": "nn.smysl.political",
        "method_reference_informativeness": "низкая",
        "expert_identification_value": None, "id_value": "", "reliability": "",
    }])
    rows = {row["candidate_uid"]: row for row in
            pdb.fetch_feature_candidates(document_id)}
    evidence, feature = rows[evidence_uid], rows[feature_uid]
    if status == fm.STATUS_ACCEPTED:
        EvidenceLinkService.link(
            pdb, project_id, document_id, feature, evidence, "тестовое основание")
        ExpertFeatureService.confirm(
            pdb, project_id, document_id, feature,
            expert_identification_value=expert_value,
            expert_rationale="мотивированная тестовая квалификация",
            stability_status="STABLE", opportunity_status="SUFFICIENT",
            comparability_status="COMPARABLE")
    else:
        fm.decide(pdb, project_id, document_id, feature, status)
    return fm.candidate_key(feature)
