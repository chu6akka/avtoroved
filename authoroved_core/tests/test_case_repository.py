import json
import os
from dataclasses import replace

import pytest

from authoroved_core.core.case_repository import (
    CaseIntegrityError, CasePasswordError, CaseRepository,
)
from authoroved_core.core.document import load_document
from authoroved_core.core.models import AnalysisResult, Candidate, Metric, ReviewStatus, Span, Token


@pytest.fixture
def repository():
    return CaseRepository(memory_cost_kib=8192, time_cost=1, parallelism=1)


def populated_case(repository, tmp_path):
    source = tmp_path / "Исходный.txt"
    source.write_bytes("Он пришол.\r\n".encode("utf-8"))
    document = load_document(source)
    candidate = Candidate(
        "candidate", document.id, "Орфография", "Орфография", "Проверить",
        "пришол", Span(3, 9), "RULE", ("пришёл",), status=ReviewStatus.ACCEPTED,
        comment="Подтверждено экспертом",
    )
    result = AnalysisResult(
        document.id,
        tokens=[Token("Он", "он", "PRON", {"Case": "Nom"}, "nsubj", 2, 0, 1, Span(0, 2))],
        candidates=[candidate],
        metrics=[Metric("Слова", "2", "Подсчёт", "Количественные показатели")],
        metadata={"stanza": {"version": "test"}}, errors=[],
    )
    case = repository.create()
    case.materials[0] = document
    case.results[0] = result
    repository.record(case, "document_imported", {
        "slot": 1, "name": document.name, "file_sha256": document.file_sha256,
    })
    repository.record(case, "candidate_reviewed", {
        "document_id": document.id, "candidate_id": candidate.id,
        "from": "new", "to": "accepted",
    })
    return case


def test_encrypted_case_roundtrip_preserves_sources_results_and_audit(repository, tmp_path):
    case = populated_case(repository, tmp_path)
    target = tmp_path / "Дело.avedcase"

    repository.save(target, case, "надёжный пароль")
    raw = target.read_bytes()
    restored = repository.open(target, "надёжный пароль")

    assert "Он пришол".encode("utf-8") not in raw
    assert "Подтверждено экспертом".encode("utf-8") not in raw
    assert restored.materials == case.materials
    assert restored.results == case.results
    assert restored.audit[-1].event == "case_saved"
    repository.verify_integrity(restored)


def test_wrong_password_and_ciphertext_tampering_are_rejected(repository, tmp_path):
    target = tmp_path / "case.avedcase"
    repository.save(target, populated_case(repository, tmp_path), "правильный")
    with pytest.raises(CasePasswordError):
        repository.open(target, "неправильный")

    envelope = json.loads(target.read_text(encoding="utf-8"))
    ciphertext = envelope["ciphertext"]
    envelope["ciphertext"] = ("A" if ciphertext[0] != "A" else "B") + ciphertext[1:]
    target.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(CasePasswordError):
        repository.open(target, "правильный")


def test_document_and_audit_mutation_fail_integrity(repository, tmp_path):
    case = populated_case(repository, tmp_path)
    original = case.materials[0]
    case.materials[0] = replace(original, text=original.text + "подмена")
    with pytest.raises(CaseIntegrityError, match="извлечённого текста"):
        repository.verify_integrity(case)

    case.materials[0] = original
    case.audit[1] = replace(case.audit[1], event="forged")
    with pytest.raises(CaseIntegrityError, match="цепочка журнала"):
        repository.verify_integrity(case)


def test_failed_atomic_replace_keeps_previous_case(repository, tmp_path, monkeypatch):
    target = tmp_path / "case.avedcase"
    case = populated_case(repository, tmp_path)
    repository.save(target, case, "пароль")
    previous = target.read_bytes()
    repository.record(case, "candidate_reviewed", {"to": "rejected"})

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        repository.save(target, case, "пароль")

    assert target.read_bytes() == previous
    assert not list(tmp_path.glob(".*.tmp"))


def test_saved_file_uses_declared_crypto_and_fresh_randomness(repository, tmp_path):
    case = populated_case(repository, tmp_path)
    first, second = tmp_path / "one.avedcase", tmp_path / "two.avedcase"
    repository.save(first, case, "пароль")
    repository.save(second, case, "пароль")
    first_envelope = json.loads(first.read_text(encoding="utf-8"))
    second_envelope = json.loads(second.read_text(encoding="utf-8"))

    assert first_envelope["kdf"]["name"] == "argon2id"
    assert first_envelope["cipher"]["name"] == "AES-256-GCM"
    assert first_envelope["kdf"]["salt"] != second_envelope["kdf"]["salt"]
    assert first_envelope["cipher"]["nonce"] != second_envelope["cipher"]["nonce"]
