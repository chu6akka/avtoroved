"""Единые ворота участия признака в строгом методическом комплексе."""
from __future__ import annotations

from protocol import feature_map as fm
from protocol import feature_model as model
from protocol.expert_features import EvidenceLinkService, ExpertFeatureService


class MethodologicalGuard:
    """Не формулирует вывод; проверяет происхождение и экспертную квалификацию."""

    @staticmethod
    def is_countable(pdb, feature, require_identification_value: bool = False) -> bool:
        if model.normalized_role(feature) != model.METHOD_FEATURE:
            return False
        if model.get_field(feature, "status", "") != fm.STATUS_ACCEPTED:
            return False
        if model.get_field(feature, "source_kind", "") != model.SOURCE_METHOD:
            return False
        if model.registered_method_feature(
                model.get_field(feature, "method_feature_id")) is None:
            return False
        key = model.get_field(feature, "candidate_key", "")
        document_id = model.get_field(feature, "document_id")
        if not key or document_id is None:
            return False
        qualification = ExpertFeatureService.current_qualification(pdb, key)
        if not (qualification.get("expert_rationale") or "").strip():
            return False
        if qualification.get("stability_status") not in ("STABLE", "NOT_APPLICABLE"):
            return False
        if qualification.get("comparability_status") != "COMPARABLE":
            return False
        if not EvidenceLinkService.linked_evidence(pdb, document_id, key):
            return False
        if require_identification_value and not (
                model.get_field(feature, "expert_identification_value", "")
                or model.get_field(feature, "expert_id_value", "")):
            return False
        return True

    @staticmethod
    def countable_features(pdb, document_id: int,
                           require_identification_value: bool = False) -> list:
        return [feature for feature in pdb.fetch_features(document_id=document_id)
                if MethodologicalGuard.is_countable(
                    pdb, feature, require_identification_value)]
