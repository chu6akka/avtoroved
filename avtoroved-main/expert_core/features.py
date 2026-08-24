from __future__ import annotations

from collections import Counter
import re

from .method_profile import MethodProfile
from .models import Evidence, ExpertStatus, FeatureObservation, TextObject
from .suitability import SuitabilityService

_WORD_RE = re.compile(r"[А-Яа-яЁёA-Za-z]+")
_SENT_RE = re.compile(r"[^.!?]+[.!?]?", re.S)


class FeatureExtractionService:
    """Проверяемый базовый набор; неподдерживаемые признаки остаются экспертными."""

    def analyze_object(self, obj: TextObject, profile: MethodProfile) -> list[FeatureObservation]:
        words = [w.lower() for w in _WORD_RE.findall(obj.text)]
        sentences = [s for s in _SENT_RE.findall(obj.text) if _WORD_RE.search(s)]
        counts = Counter(words)
        values = {
            "stats.word_count": float(len(words)),
            "stats.ttr": len(counts) / len(words) if words else 0.0,
            "stats.hapax_ratio": sum(v == 1 for v in counts.values()) / len(counts) if counts else 0.0,
            "stats.avg_sentence_words": len(words) / len(sentences) if sentences else 0.0,
        }
        out: list[FeatureObservation] = []
        for rule in profile.features:
            if rule.extractor not in values:
                continue
            wc = SuitabilityService.word_count(obj.text)
            limitations = []
            applicable = "applicable"
            if wc < rule.min_words:
                applicable = "insufficient_material"
                limitations.append(f"Требуется не менее {rule.min_words} слов")
            out.append(FeatureObservation(
                feature_id=rule.id, value=values[rule.extractor], unit=rule.unit,
                method_version=f"{profile.id}:{profile.version}",
                source=f"{rule.source}, {rule.page}", applicability=applicable,
                expert_status=ExpertStatus.UNREVIEWED, limitations=limitations,
                stable=wc >= max(rule.min_words, 200), dependency_group=rule.dependency_group,
                origin="auto" if rule.method == "auto" else "assisted",
            ))
        return out
