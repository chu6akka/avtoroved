from __future__ import annotations

import json
from pathlib import Path

import pytest

from validation.agreement import expert_agreement
from validation.analyzer import SyntheticDemoAnalyzer
from validation.check_corpus import check_corpus
from validation.constants import FROZEN_ENGINE_CONFIG
from validation.evaluate_features import evaluate_features, resolve_detection_gold
from validation.evaluate_labels import evaluate_multilabel
from validation.evaluate_time import evaluate_time
from validation.io import canonical_json, sha256_bytes
from validation.models import make_blind_document
from validation.run import run_validation
from validation.schema import (SchemaError, validate_annotation, validate_case,
                               validate_corpus_item, validate_time_record)

ROOT = Path(__file__).resolve().parents[1]
DEMO_CORPUS = ROOT / "validation" / "corpus" / "demo"
DEMO_ANNOTATIONS = ROOT / "validation" / "annotations" / "demo"


def test_frozen_theme_configuration():
    assert FROZEN_ENGINE_CONFIG["theme"]["selection_floor"] == .44
    assert FROZEN_ENGINE_CONFIG["theme"]["revision"] == "e8ed3b0"


def test_frozen_style_configuration():
    assert FROZEN_ENGINE_CONFIG["style"]["configuration"] == "F_HYBRID"
    assert FROZEN_ENGINE_CONFIG["style"]["weak_signal_threshold"] == .14


def test_canonical_json_is_stable():
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})


def test_sha256_known_value():
    assert sha256_bytes(b"abc").startswith("ba7816bf")


def test_demo_corpus_passes_quality_control():
    assert check_corpus(DEMO_CORPUS)["valid"]


def test_demo_is_development_only():
    rows = [json.loads(line) for line in (DEMO_CORPUS / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {row["subset"] for row in rows} == {"DEVELOPMENT"}


def test_blind_document_excludes_gold_and_author():
    item = json.loads((DEMO_CORPUS / "manifest.jsonl").read_text(encoding="utf-8").splitlines()[0])
    blind = make_blind_document(item, "текст")
    assert not hasattr(blind, "author_id_pseudonymous")
    assert not hasattr(blind, "expected_relation")
    assert not hasattr(blind, "gold")


def test_case_schema_accepts_unknown_relation():
    validate_case({"case_id": "C", "disputed_document_ids": ["D1"],
                   "reference_document_ids": ["D2"], "expected_relation": "UNKNOWN"})


def test_case_schema_rejects_invalid_relation():
    with pytest.raises(SchemaError):
        validate_case({"case_id": "C", "disputed_document_ids": ["D1"],
                       "reference_document_ids": ["D2"], "expected_relation": "YES"})


def test_annotation_keeps_detection_and_acceptance_separate():
    row = {"annotation_id": "A", "document_id": "D", "method_feature_id": "F",
           "present": True, "accepted": False, "offsets": [],
           "expert_id_pseudonymous": "E001", "comment": "", "timestamp": "2026-01-01T00:00:00Z"}
    validate_annotation(row)
    assert row["present"] is True and row["accepted"] is False


def test_consensus_gold():
    rows = [{"document_id": "D", "method_feature_id": "F", "present": True, "accepted": value}
            for value in (True, False)]
    gold, _ = resolve_detection_gold(rows)
    assert gold[("D", "F")]["gold_source"] == "CONSENSUS"


def test_adjudication_overrides_conflict():
    rows = [{"document_id": "D", "method_feature_id": "F", "present": True,
             "accepted": True, "adjudicated_present": False},
            {"document_id": "D", "method_feature_id": "F", "present": False, "accepted": False}]
    gold, _ = resolve_detection_gold(rows)
    assert gold[("D", "F")]["present"] is False


def test_expert_only_is_not_false_negative():
    result = evaluate_features([], [{"document_id": "D", "method_feature_id": "F",
                                     "present": True, "accepted": True}],
                               {"F": {"group": "semantic", "automation_level": "EXPERT_ONLY"}})
    assert result["features"][0]["status"] == "not_automated_by_design"
    assert "fn" not in result["features"][0]


def test_candidate_metrics_are_separate():
    result = evaluate_features(
        [{"document_id": "D", "method_feature_id": "F"}],
        [{"document_id": "D", "method_feature_id": "F", "present": True, "accepted": False}],
        {"F": {"group": "lexical", "automation_level": "CANDIDATE_ONLY"}}, minimum_support=1)
    assert result["features"][0]["metric_scope"] == "candidate_detection"


def test_insufficient_support_is_marked():
    result = evaluate_features([], [], {"F": {"group": "lexical", "automation_level": "AUTO"}})
    assert result["features"][0]["status"] == "insufficient_support"


def test_theme_multilabel_metrics():
    result = evaluate_multilabel([{"document_id": "D", "labels": ["a"]}],
                                 [{"document_id": "D", "labels": ["a", "b"]}], label_kind="theme")
    assert result["top1_accuracy"] == 1 and result["mixed_label_recall"] == 1
    assert result["top1_micro_f1"] == 1


def test_style_abstention_and_focus_rows():
    result = evaluate_multilabel([{"document_id": "D", "labels": []}],
                                 [{"document_id": "D", "labels": ["publicistic"]}], label_kind="style")
    assert result["abstention_rate"] == 1
    assert "publicistic" in result["focus_styles"]


def test_segment_transition_metric():
    gold = [{"document_id": "D", "segment_id": "1", "labels": ["a"]},
            {"document_id": "D", "segment_id": "2", "labels": ["b"]}]
    assert evaluate_multilabel(gold, gold, label_kind="theme")["segment_transition_recall"] == 1


def test_agreement_and_kappa_available():
    rows = []
    for doc, value in (("D1", True), ("D2", False)):
        for expert in ("E001", "E002"):
            rows.append({"document_id": doc, "method_feature_id": "F",
                         "expert_id_pseudonymous": expert, "present": value})
    assert expert_agreement(rows)["percent_agreement"] == 100


def test_time_uses_only_paired_records():
    base = {"case_id": "C", "expert_id_pseudonymous": "E001", "stage": "FEATURE_MAP",
            "start": "2026-01-01T00:00:00Z", "end": "2026-01-01T00:01:00Z",
            "notes": "", "session_order": 1}
    records = [{**base, "mode": "MANUAL", "duration_seconds": 60},
               {**base, "mode": "ASSISTED", "duration_seconds": 40, "session_order": 2},
               {**base, "case_id": "C2", "mode": "MANUAL", "duration_seconds": 50}]
    result = evaluate_time(records)
    assert result["aggregate"]["mean_saved_seconds"] == 20
    assert len(result["unmatched"]) == 1


def test_time_schema_requires_session_order():
    with pytest.raises(SchemaError):
        validate_time_record({})


def test_synthetic_demo_runner_is_immutable_and_hashed(tmp_path):
    run_dir = run_validation(DEMO_CORPUS, DEMO_ANNOTATIONS, tmp_path, "pilot",
                             analyzer=SyntheticDemoAnalyzer(), run_id="demo-run")
    assert (run_dir / "hashes.json").is_file()
    assert (run_dir / "feature_metrics.csv").is_file()
    with pytest.raises(FileExistsError):
        run_validation(DEMO_CORPUS, DEMO_ANNOTATIONS, tmp_path, "pilot",
                       analyzer=SyntheticDemoAnalyzer(), run_id="demo-run")


def test_analyzer_receives_no_hidden_fields(tmp_path):
    class Spy:
        def analyze(self, document):
            assert set(vars(document)).isdisjoint({"author_id_pseudonymous", "expected_relation", "gold"})
            return {"document_id": document.document_id, "theme": {}, "style": {}, "feature_candidates": []}
    run_validation(DEMO_CORPUS, DEMO_ANNOTATIONS, tmp_path, "pilot", analyzer=Spy(), run_id="blind")
