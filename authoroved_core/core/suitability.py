"""Ворота пригодности и сопоставимости без скрытых числовых нормативов."""
from __future__ import annotations

from collections import defaultdict
import re

from authoroved_core.core.document import Document
from authoroved_core.core.feature_models import (
    Applicability,
    ExpertFeatureStatus,
    FeatureComparison,
    FeatureObservation,
    FeaturePair,
    MaterialConditions,
    SuitabilityAssessment,
    SuitabilityStatus,
)
from authoroved_core.core.feature_registry import FeatureRegistry


RUSSIAN_LABELS = {"ru", "rus", "russian", "русский", "русский язык"}
WORD_RE = re.compile(r"[^\W\d_]+(?:[-’'][^\W\d_]+)*", re.UNICODE)


class SuitabilityService:
    """Фиксирует экспертные условия; не угадывает жанр или авторство по тексту."""

    def __init__(self, registry: FeatureRegistry):
        self.registry = registry

    def assess(self, documents: list[Document],
               conditions: list[MaterialConditions]) -> SuitabilityAssessment:
        if len(documents) not in {1, 2} or len(documents) != len(conditions):
            raise ValueError("Нужно передать условия для каждого из одного или двух материалов.")

        blocking = []
        questions = []
        limitations = [
            "Общий норматив минимального объёма в профиле не установлен.",
            "Автоматические измерения допустимы и при блокировке, но в экспертный синтез не переносятся.",
        ]
        word_counts = tuple(len(WORD_RE.findall(document.text)) for document in documents)

        for index, (document, value) in enumerate(zip(documents, conditions), 1):
            if not document.text.strip():
                blocking.append(f"Текст {index}: материал пуст.")
            if value.language is None:
                questions.append(f"Текст {index}: эксперт должен подтвердить язык материала.")
            elif value.language.strip().casefold() not in RUSSIAN_LABELS:
                blocking.append(f"Текст {index}: профиль предназначен для русского языка.")
            if value.independent_authorship is None:
                questions.append(f"Текст {index}: не подтверждена самостоятельность составления.")
            elif value.independent_authorship is False:
                blocking.append(f"Текст {index}: самостоятельность составления не подтверждена.")
            for attribute, title in (
                ("genre", "жанр"), ("period", "время создания"),
                ("addressee", "адресат"),
                ("communicative_situation", "коммуникативная ситуация"),
            ):
                if not getattr(value, attribute):
                    questions.append(f"Текст {index}: эксперт должен указать {title}.")

        comparable = len(documents) == 1
        if len(documents) == 2:
            comparable = True
            for attribute, title in (
                ("genre", "жанру"), ("period", "времени создания"),
                ("addressee", "адресату"),
                ("communicative_situation", "коммуникативной ситуации"),
            ):
                first, second = getattr(conditions[0], attribute), getattr(conditions[1], attribute)
                if not first or not second:
                    comparable = False
                elif first.strip().casefold() != second.strip().casefold():
                    comparable = False
                    blocking.append(f"Материалы не подтверждены как сопоставимые по {title}.")

        if blocking:
            status = SuitabilityStatus.BLOCKED
        elif questions or not comparable:
            status = SuitabilityStatus.REQUIRES_EXPERT
        else:
            status = SuitabilityStatus.PASSED
        return SuitabilityAssessment(
            status=status,
            language=_summary(conditions, "language"),
            volume_words=word_counts,
            independent_authorship=_bool_summary(conditions),
            genre=_summary(conditions, "genre"),
            period=_summary(conditions, "period"),
            addressee=_summary(conditions, "addressee"),
            communicative_situation=_summary(conditions, "communicative_situation"),
            comparable=comparable,
            blocking_reasons=tuple(blocking), expert_questions=tuple(questions),
            limitations=tuple(limitations),
        )


def _summary(values: list[MaterialConditions], attribute: str) -> str:
    items = [getattr(value, attribute) or "не указано" for value in values]
    return " / ".join(items)


def _bool_summary(values: list[MaterialConditions]) -> str:
    labels = {True: "подтверждена", False: "не подтверждена", None: "не проверена"}
    return " / ".join(labels[value.independent_authorship] for value in values)


class FeatureComparisonService:
    """Передаёт в сопоставление лишь подтверждённые и применимые наблюдения."""

    def __init__(self, registry: FeatureRegistry):
        self.registry = registry

    def compare(self, first: list[FeatureObservation], second: list[FeatureObservation],
                suitability: SuitabilityAssessment) -> FeatureComparison:
        all_ids = sorted({item.feature_id for item in first + second})
        if not suitability.allows_expert_synthesis:
            return FeatureComparison(
                allowed=False, ignored_feature_ids=tuple(all_ids),
                reasons=tuple(suitability.blocking_reasons + suitability.expert_questions)
                or ("Пригодность и сопоставимость материалов не подтверждены.",),
            )
        first_map = {item.feature_id: item for item in first}
        second_map = {item.feature_id: item for item in second}
        pairs = []
        ignored = []
        groups: dict[str, list[str]] = defaultdict(list)
        for feature_id in all_ids:
            left, right = first_map.get(feature_id), second_map.get(feature_id)
            definition = self.registry.get(feature_id)
            if (left is None or right is None
                    or left.applicability is not Applicability.APPLICABLE
                    or right.applicability is not Applicability.APPLICABLE
                    or left.expert_status not in {ExpertFeatureStatus.CONFIRMED, ExpertFeatureStatus.CORRECTED}
                    or right.expert_status not in {ExpertFeatureStatus.CONFIRMED, ExpertFeatureStatus.CORRECTED}):
                ignored.append(feature_id)
                continue
            pairs.append(FeaturePair(feature_id, left, right, definition.dependency_group))
            groups[definition.dependency_group].append(feature_id)
        return FeatureComparison(
            allowed=True, pairs=tuple(pairs), ignored_feature_ids=tuple(ignored),
            dependency_groups={key: tuple(value) for key, value in sorted(groups.items())},
            reasons=("Зависимые показатели сгруппированы и не считаются независимыми доказательствами.",),
        )
