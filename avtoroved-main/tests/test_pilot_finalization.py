from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

from pilot_corpus.finalize import (
    SelectedDocument,
    choose_different_pairs,
    pseudonym_codes,
    sha256_bytes,
    validate_manifest,
)
from pilot_corpus.scanner import _write_csv


def _document(author: int, number: int, words: int) -> SelectedDocument:
    return SelectedDocument(
        document_id=f"A{author:03d}_T{number:02d}", author_code=f"A{author:03d}",
        source_author_id=str(author), username=f"u{author}", source_post_id=str(number),
        date="2020-01-01", title="", source_url="", word_count=words,
        char_count=words * 5, content_type="narrative", tags="[]",
        raw_path="", analysis_path="", raw_sha256="", analysis_sha256="",
        is_reserve=False,
    )


def test_pseudonymization_is_deterministic_and_contains_no_source_id():
    assert pseudonym_codes(3) == ["A001", "A002", "A003"]


def test_exact_byte_hash_is_deterministic_and_newline_sensitive():
    payload = "Текст".encode("utf-8")
    assert sha256_bytes(payload) == sha256_bytes(payload)
    assert sha256_bytes(payload) != sha256_bytes(payload + b"\n")


def test_different_pair_builder_uses_each_document_once_and_never_same_author():
    documents = [_document(author, number, 300 + author * 10 + number) for author in range(1, 6) for number in (3, 4)]
    pairs = choose_different_pairs(documents, seed=17)
    flattened = [doc.document_id for pair in pairs for doc in pair]
    assert len(pairs) == 5
    assert len(flattened) == len(set(flattened)) == 10
    assert all(left.author_code != right.author_code for left, right in pairs)
    assert pairs == choose_different_pairs(documents, seed=17)


def test_manifest_validation_accepts_exact_bytes_and_rejects_change(tmp_path: Path):
    raw = tmp_path / "raw" / "A001_T01.txt"
    analysis = tmp_path / "analysis" / "A001_T01.txt"
    raw.parent.mkdir()
    analysis.parent.mkdir()
    payload = "Исходный текст".encode("utf-8")
    raw.write_bytes(payload)
    analysis.write_bytes(payload)
    digest = sha256_bytes(payload)
    _write_csv(
        tmp_path / "manifest.csv",
        ["document_id", "raw_path", "analysis_path", "raw_sha256", "analysis_sha256"],
        [{
            "document_id": "A001_T01", "raw_path": "raw/A001_T01.txt",
            "analysis_path": "analysis/A001_T01.txt", "raw_sha256": digest,
            "analysis_sha256": digest,
        }],
    )
    assert validate_manifest(tmp_path)["valid"]
    analysis.write_bytes(payload + b"!")
    result = validate_manifest(tmp_path)
    assert not result["valid"]
    assert result["errors"] == ["hash_mismatch_analysis:A001_T01"]
