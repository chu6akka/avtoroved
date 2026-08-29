"""Минимальная офлайн-проверка контрактов без новой зависимости jsonschema."""
from __future__ import annotations

from datetime import datetime

from .constants import EXPECTED_RELATIONS, SAMPLE_TYPES, SUBSETS


class SchemaError(ValueError):
    pass


def _required(row: dict, fields: set[str], kind: str) -> None:
    missing = sorted(fields - row.keys())
    if missing:
        raise SchemaError(f"{kind}: отсутствуют поля: {', '.join(missing)}")


def validate_corpus_item(row: dict) -> None:
    fields = {"document_id", "author_id_pseudonymous", "sample_type", "genre",
              "source_type", "creation_context", "year_or_period", "word_count",
              "character_count", "known_author", "disputed_or_reference",
              "pair_group_id", "notes", "subset", "text_path", "input_sha256"}
    _required(row, fields, "corpus_item")
    if row["sample_type"] not in SAMPLE_TYPES or row["subset"] not in SUBSETS:
        raise SchemaError("corpus_item: недопустимый sample_type/subset")
    if not isinstance(row["known_author"], bool):
        raise SchemaError("corpus_item: known_author должен быть bool")
    if not isinstance(row["word_count"], int) or row["word_count"] < 0:
        raise SchemaError("corpus_item: некорректный word_count")
    digest = row["input_sha256"]
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise SchemaError("corpus_item: некорректный SHA256")


def validate_case(row: dict) -> None:
    _required(row, {"case_id", "disputed_document_ids",
                    "reference_document_ids", "expected_relation"}, "case")
    if row["expected_relation"] not in EXPECTED_RELATIONS:
        raise SchemaError("case: недопустимое expected_relation")
    if not row["disputed_document_ids"] or not row["reference_document_ids"]:
        raise SchemaError("case: обе стороны должны содержать документы")


def validate_annotation(row: dict) -> None:
    _required(row, {"annotation_id", "document_id", "method_feature_id",
                    "present", "accepted", "offsets", "expert_id_pseudonymous",
                    "comment", "timestamp"}, "expert_annotation")
    if row["present"] not in (True, False, "uncertain"):
        raise SchemaError("expert_annotation: present=true/false/uncertain")
    if not isinstance(row["accepted"], bool):
        raise SchemaError("expert_annotation: accepted должен быть bool")
    datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))


def validate_time_record(row: dict) -> None:
    _required(row, {"case_id", "expert_id_pseudonymous", "mode", "stage",
                    "start", "end", "duration_seconds", "notes",
                    "session_order"}, "time_record")
    if row["mode"] not in ("MANUAL", "ASSISTED"):
        raise SchemaError("time_record: mode")
    if row["duration_seconds"] < 0 or row["session_order"] < 1:
        raise SchemaError("time_record: duration/session_order")
