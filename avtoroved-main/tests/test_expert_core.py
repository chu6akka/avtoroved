from __future__ import annotations

import json
import zipfile

import pytest

from expert_core import (
    CaseRepository, ComparisonService, DecisionGuard, ExpertReview,
    FeatureExtractionService, GenderDiagnosticService, MethodProfile,
    ReportService, SuitabilityService,
)
from expert_core.models import (
    DifferenceQualification, ExpertStatus, TextObject, TextRole, VerdictType,
)


BASE = "В соответствии с договорённостью автор подробно рассматривает обстоятельства дела и формулирует вывод. "


def objects(good=True):
    disputed = TextObject("Q1", "Спорный", BASE * 25, TextRole.DISPUTED, genre="письмо",
                          independent_authorship=True, compilation_suspected=False)
    sample_count = 260 if good else 5
    samples = [TextObject("S1", "Образец", BASE * sample_count, TextRole.FREE_SAMPLE, genre="письмо",
                          independent_authorship=True, compilation_suspected=False)]
    return disputed, samples


def test_profiles_are_valid_and_versioned():
    for name in ("mvd_2007", "minjust"):
        profile = MethodProfile.bundled(name)
        assert profile.version and profile.features
        assert all(f.source and f.page for f in profile.features)


def test_suitability_blocks_insufficient_samples():
    profile = MethodProfile.bundled("mvd_2007")
    disputed, samples = objects(good=False)
    result = SuitabilityService().assess([disputed, *samples], profile)
    assert not result.suitable
    assert {i.code for i in result.issues} >= {"insufficient_sample_volume"}


def test_numeric_comparison_uses_values_and_sample_range():
    profile = MethodProfile.bundled("mvd_2007")
    disputed, samples = objects()
    extractor = FeatureExtractionService()
    obs = {o.id: extractor.analyze_object(o, profile) for o in [disputed, *samples]}
    comparison = ComparisonService().compare(disputed, samples, obs, profile)
    assert comparison.features
    assert all(f.sample_min is not None for f in comparison.features if f.outcome != "not_assessable")


def test_program_does_not_restrict_expert_form_from_unreviewed_features():
    profile = MethodProfile.bundled("mvd_2007")
    disputed, samples = objects()
    all_objects = [disputed, *samples]
    suitability = SuitabilityService().assess(all_objects, profile)
    extractor = FeatureExtractionService()
    obs = {o.id: extractor.analyze_object(o, profile) for o in all_objects}
    comparison = ComparisonService().compare(disputed, samples, obs, profile)
    allowed, reasons = DecisionGuard().allowed_verdicts(suitability, comparison, obs[disputed.id], profile)
    assert allowed == set(VerdictType)
    assert reasons


def test_difference_requires_reasoned_qualification():
    profile = MethodProfile.bundled("mvd_2007")
    disputed, samples = objects()
    extractor = FeatureExtractionService()
    obs = {o.id: extractor.analyze_object(o, profile) for o in [disputed, *samples]}
    comparison = ComparisonService().compare(disputed, samples, obs, profile)
    feature = next((f for f in comparison.features if f.outcome == "difference"), None)
    if feature is None:
        feature = comparison.features[0]
        feature.outcome = "difference"
    with pytest.raises(ValueError):
        ExpertReview.explain(feature, DifferenceQualification.INSIGNIFICANT, "")
    ExpertReview.explain(feature, DifferenceQualification.INSIGNIFICANT, "Вариативность подтверждена образцами")
    assert feature.expert_status is ExpertStatus.CONFIRMED


def test_encrypted_case_roundtrip_and_tamper_detection(tmp_path):
    repo = CaseRepository()
    case = repo.create("Контрольное дело", "mvd_2007")
    disputed, _ = objects()
    repo.add_text(case, disputed)
    path = tmp_path / "case.avedcase"
    repo.save(case, path, "correct horse battery")
    assert "Контрольное дело".encode("utf-8") not in path.read_bytes()
    loaded = repo.open(path, "correct horse battery")
    assert loaded.title == case.title and repo.verify_integrity(loaded)
    damaged = bytearray(path.read_bytes()); damaged[-1] ^= 1; path.write_bytes(damaged)
    with pytest.raises(ValueError):
        repo.open(path, "correct horse battery")


def test_gender_result_is_research_only_and_not_exportable():
    obj = TextObject("Q1", "Текст", BASE * 5, TextRole.DISPUTED, genre="письмо")
    result = GenderDiagnosticService().analyze(obj)
    assert result.applicability.research_only
    assert not result.exportable_as_evidence
    assert result.conclusion.startswith("НПВ")


def test_verification_package_excludes_text_by_default(tmp_path):
    repo = CaseRepository(); case = repo.create("Дело", "mvd_2007")
    disputed, _ = objects(); repo.add_text(case, disputed)
    path = tmp_path / "verify.zip"
    ReportService().export_verification_package(case, path)
    with zipfile.ZipFile(path) as zf:
        assert "manifest.json" in zf.namelist()
        assert "SHA256SUMS.txt" in zf.namelist()
        assert not any(n.startswith("texts/") for n in zf.namelist())
        assert json.loads(zf.read("manifest.json"))["source_texts_included"] is False
