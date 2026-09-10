from hashlib import sha256

import pytest

from authoroved_core.core.document import Document
from authoroved_core.core.feature_models import (
    Applicability,
    ExpertFeatureStatus,
    FeatureObservation,
    MaterialConditions,
    SuitabilityStatus,
)
from authoroved_core.core.feature_registry import FeatureRegistry
from authoroved_core.core.suitability import FeatureComparisonService, SuitabilityService


def document(identifier: str, text: str) -> Document:
    data = text.encode("utf-8")
    digest = sha256(data).hexdigest()
    return Document(identifier, f"{identifier}.txt", text, data, digest, digest, "utf-8", "test")


def conditions(**changes):
    values = {
        "language": "русский", "independent_authorship": True,
        "genre": "личное сообщение", "period": "2026",
        "addressee": "частное лицо", "communicative_situation": "переписка",
    }
    values.update(changes)
    return MaterialConditions(**values)


def observation(feature_id: str, status=ExpertFeatureStatus.UNREVIEWED,
                applicability=Applicability.APPLICABLE):
    return FeatureObservation(
        feature_id=feature_id, raw_value={"count": 1}, normalized_value={"rate": 1.0},
        evidence=(), applicability=applicability, limitations=(), method_version="test",
        source=(), expert_status=status,
    )


def test_suitability_passes_only_when_all_conditions_are_explicit_and_comparable():
    registry = FeatureRegistry.load()
    service = SuitabilityService(registry)
    documents = [document("a", "Один текст"), document("b", "Другой текст")]

    passed = service.assess(documents, [conditions(), conditions()])
    unknown = service.assess(documents, [conditions(genre=None), conditions()])
    mismatch = service.assess(documents, [conditions(), conditions(genre="статья")])

    assert passed.status is SuitabilityStatus.PASSED
    assert passed.comparable and passed.allows_expert_synthesis
    assert unknown.status is SuitabilityStatus.REQUIRES_EXPERT
    assert not unknown.allows_expert_synthesis
    assert mismatch.status is SuitabilityStatus.BLOCKED
    assert not mismatch.comparable
    assert "жанру" in " ".join(mismatch.blocking_reasons)


def test_non_russian_or_non_independent_material_blocks_synthesis():
    service = SuitabilityService(FeatureRegistry.load())
    assessment = service.assess(
        [document("a", "Текст"), document("b", "Text")],
        [conditions(), conditions(language="английский", independent_authorship=False)],
    )

    assert assessment.status is SuitabilityStatus.BLOCKED
    assert not assessment.allows_expert_synthesis
    assert "русского языка" in " ".join(assessment.blocking_reasons)
    assert "самостоятельность" in " ".join(assessment.blocking_reasons)


def test_feature_comparison_ignores_unconfirmed_insufficient_and_groups_dependencies():
    registry = FeatureRegistry.load()
    suitability = SuitabilityService(registry).assess(
        [document("a", "Первый текст"), document("b", "Второй текст")],
        [conditions(), conditions()],
    )
    service = FeatureComparisonService(registry)
    first = [
        observation("LEX_001", ExpertFeatureStatus.CONFIRMED),
        observation("MOR_001", ExpertFeatureStatus.UNREVIEWED),
        observation("MOR_003", ExpertFeatureStatus.CONFIRMED, Applicability.INSUFFICIENT_DATA),
    ]
    second = [
        observation("LEX_001", ExpertFeatureStatus.CORRECTED),
        observation("MOR_001", ExpertFeatureStatus.CONFIRMED),
        observation("MOR_003", ExpertFeatureStatus.CONFIRMED),
    ]

    result = service.compare(first, second, suitability)

    assert result.allowed
    assert [pair.feature_id for pair in result.pairs] == ["LEX_001"]
    assert result.ignored_feature_ids == ("MOR_001", "MOR_003")
    assert result.dependency_groups == {"lexical_function_distribution": ("LEX_001",)}
    assert not hasattr(result, "score") and not hasattr(result, "verdict")


def test_failed_suitability_blocks_even_confirmed_observations():
    registry = FeatureRegistry.load()
    assessment = SuitabilityService(registry).assess(
        [document("a", "Первый"), document("b", "Второй")],
        [conditions(), conditions(genre="иной жанр")],
    )
    result = FeatureComparisonService(registry).compare(
        [observation("LEX_001", ExpertFeatureStatus.CONFIRMED)],
        [observation("LEX_001", ExpertFeatureStatus.CONFIRMED)],
        assessment,
    )

    assert not result.allowed
    assert not result.pairs
    assert result.ignored_feature_ids == ("LEX_001",)


def test_expert_correction_is_separate_from_machine_value():
    item = observation("LEX_001")
    machine_value = item.normalized_value

    item.review(ExpertFeatureStatus.CORRECTED, corrected_value={"rate": 2.0},
                comment="Исправлена ошибка разметки")

    assert item.normalized_value == machine_value
    assert item.expert_value == {"rate": 2.0}
    assert item.expert_comment == "Исправлена ошибка разметки"
    with pytest.raises(ValueError, match="значение эксперта"):
        observation("LEX_001").review(ExpertFeatureStatus.CORRECTED)
