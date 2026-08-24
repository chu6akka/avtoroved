from __future__ import annotations

from statistics import mean

from .method_profile import MethodProfile
from .models import ComparedFeature, ComparisonResult, FeatureObservation, TextObject, TextRole


class ComparisonService:
    def compare(
        self, disputed: TextObject, samples: list[TextObject],
        observations: dict[str, list[FeatureObservation]], profile: MethodProfile,
        sample_subject_id: str = "samples",
    ) -> ComparisonResult:
        if disputed.role is not TextRole.DISPUTED:
            raise ValueError("Первый объект должен быть спорным текстом")
        if not samples or any(not s.role.is_sample for s in samples):
            raise ValueError("Требуется хотя бы один сравнительный образец")
        dmap = {o.feature_id: o for o in observations.get(disputed.id, [])}
        smaps = [{o.feature_id: o for o in observations.get(s.id, [])} for s in samples]
        result: list[ComparedFeature] = []
        limitations: list[str] = []
        for rule in profile.features:
            d = dmap.get(rule.id)
            sv = [m[rule.id] for m in smaps if rule.id in m]
            if not d or not sv:
                continue
            numeric = isinstance(d.value, (int, float)) and all(isinstance(v.value, (int, float)) for v in sv)
            if not numeric or rule.tolerance is None:
                result.append(ComparedFeature(
                    rule.id, disputed.id, sample_subject_id, "not_assessable",
                    disputed_value=d.value, explanation="Требуется экспертное качественное сопоставление",
                    dependency_group=rule.dependency_group,
                ))
                continue
            nums = [float(v.value) for v in sv]
            avg = mean(nums)
            base = max(abs(float(d.value)), abs(avg), 1e-9)
            rel = abs(float(d.value) - avg) / base
            stable_samples = sum(bool(v.stable) for v in sv)
            outcome = "match" if rel <= rule.tolerance else "difference"
            if stable_samples < max(1, len(samples) // 2 + len(samples) % 2):
                outcome = "not_assessable"
                limitations.append(f"{rule.id}: недостаточная устойчивость в образцах")
            result.append(ComparedFeature(
                feature_id=rule.id, disputed_object_id=disputed.id,
                sample_subject_id=sample_subject_id, outcome=outcome,
                disputed_value=d.value, sample_mean=avg, sample_min=min(nums), sample_max=max(nums),
                relative_difference=rel, tolerance=rule.tolerance,
                dependency_group=rule.dependency_group,
            ))
        return ComparisonResult(disputed.id, sample_subject_id, result, sorted(set(limitations)))
