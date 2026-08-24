from __future__ import annotations

from .method_profile import MethodProfile
from .models import (
    ComparedFeature, ComparisonResult, DifferenceQualification, ExpertDecision,
    ExpertStatus, FeatureObservation, SuitabilityResult, VerdictType,
)


class DecisionGuard:
    def allowed_verdicts(
        self, suitability: SuitabilityResult | None, comparison: ComparisonResult | None,
        observations: list[FeatureObservation], profile: MethodProfile,
    ) -> tuple[set[VerdictType], list[str]]:
        all_forms = set(VerdictType)
        if not suitability or not suitability.suitable:
            return all_forms, ["Материалы не прошли проверку пригодности; форму вывода оценивает эксперт"]
        if comparison is None:
            return all_forms, ["Сравнительное исследование не выполнено; форму вывода оценивает эксперт"]
        reasons: list[str] = []
        unqualified = [f for f in comparison.features if f.outcome == "difference" and f.qualification is None]
        if unqualified:
            reasons.append("Не все различия получили экспертную квалификацию")
        confirmed = [o for o in observations if o.eligible_for_synthesis]
        if not confirmed:
            reasons.append("Нет подтверждённых экспертом признаков")
        return all_forms, reasons


class ExpertReview:
    @staticmethod
    def confirm(observation: FeatureObservation) -> None:
        observation.expert_status = ExpertStatus.CONFIRMED

    @staticmethod
    def reject(observation: FeatureObservation, reason: str) -> None:
        observation.expert_status = ExpertStatus.REJECTED
        observation.limitations.append(reason)

    @staticmethod
    def explain(feature: ComparedFeature, qualification: DifferenceQualification, explanation: str) -> None:
        if feature.outcome != "difference":
            raise ValueError("Квалифицировать можно только различающийся признак")
        if not explanation.strip():
            raise ValueError("Необходимо мотивированное объяснение")
        feature.qualification = qualification
        feature.explanation = explanation.strip()
        feature.expert_status = ExpertStatus.CONFIRMED

    @staticmethod
    def decide(verdict: VerdictType, rationale: str, expert_name: str,
               allowed: set[VerdictType] | None = None) -> ExpertDecision:
        # allowed оставлен только для совместимости API; форма не сравнивается
        # с программной рекомендацией или автоматически вычисленным допуском.
        if not rationale.strip() or not expert_name.strip():
            raise ValueError("Требуются мотивировка и имя эксперта")
        return ExpertDecision(verdict, rationale.strip(), expert_name.strip())
