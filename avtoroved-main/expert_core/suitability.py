from __future__ import annotations

import re

from .method_profile import MethodProfile
from .models import SuitabilityIssue, SuitabilityResult, TextObject, TextRole

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+")


class SuitabilityService:
    @staticmethod
    def word_count(text: str) -> int:
        return len(_WORD_RE.findall(text))

    @staticmethod
    def _cyrillic_ratio(text: str) -> float:
        letters = [c for c in text if c.isalpha()]
        if not letters:
            return 0.0
        return sum("а" <= c.lower() <= "я" or c.lower() == "ё" for c in letters) / len(letters)

    def assess(self, objects: list[TextObject], profile: MethodProfile) -> SuitabilityResult:
        cfg = profile.suitability
        min_disputed = int(cfg.get("min_disputed_words", 100))
        min_sample = int(cfg.get("min_sample_words", 100))
        min_ratio = float(cfg.get("min_sample_ratio", 10.0))
        counts = {obj.id: self.word_count(obj.text) for obj in objects}
        issues: list[SuitabilityIssue] = []
        disputed = [o for o in objects if o.role is TextRole.DISPUTED]
        samples = [o for o in objects if o.role.is_sample]
        if not disputed:
            issues.append(SuitabilityIssue("no_disputed", "Не представлен спорный текст"))
        if not samples:
            issues.append(SuitabilityIssue("no_samples", "Не представлены сравнительные образцы"))
        for obj in objects:
            minimum = min_disputed if obj.role is TextRole.DISPUTED else min_sample
            if counts[obj.id] < minimum:
                issues.append(SuitabilityIssue(
                    "insufficient_object_volume",
                    f"Объём объекта {counts[obj.id]} слов меньше минимума {minimum}",
                    object_id=obj.id,
                ))
            if self._cyrillic_ratio(obj.text) < float(cfg.get("min_cyrillic_ratio", 0.5)):
                issues.append(SuitabilityIssue("not_russian", "Недостаточная доля кириллицы", object_id=obj.id))
            if obj.independent_authorship is False:
                issues.append(SuitabilityIssue("not_independent", "Несамостоятельное составление текста", object_id=obj.id))
            if obj.compilation_suspected is True:
                issues.append(SuitabilityIssue("compilation", "Имеются признаки компиляции", object_id=obj.id))
        dw = sum(counts[o.id] for o in disputed)
        sw = sum(counts[o.id] for o in samples)
        ratio = sw / dw if dw else 0.0
        if disputed and samples and ratio < min_ratio:
            issues.append(SuitabilityIssue(
                "insufficient_sample_volume",
                f"Соотношение объёма образцов к спорному тексту ×{ratio:.1f}, требуется не менее ×{min_ratio:g}",
            ))
        disp_genres = {o.genre for o in disputed if o.genre}
        sample_genres = {o.genre for o in samples if o.genre}
        if disp_genres and sample_genres and not disp_genres.intersection(sample_genres):
            issues.append(SuitabilityIssue("genre_mismatch", "Жанры спорного текста и образцов несопоставимы"))
        return SuitabilityResult(
            suitable=not any(i.blocking for i in issues), issues=issues,
            object_word_counts=counts, sample_to_disputed_ratio=round(ratio, 3),
            method_version=f"{profile.id}:{profile.version}",
        )
