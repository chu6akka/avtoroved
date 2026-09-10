"""Зашифрованное дело, строгая целостность и проверяемый журнал действий."""
from __future__ import annotations

import base64
import copy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
from typing import Any
from uuid import uuid4

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from authoroved_core.core.document import Document, sha256_bytes
from authoroved_core.core.models import AnalysisResult, Candidate, Metric, ReviewStatus, Span, Token


FORMAT_NAME = "authoroved-encrypted-case"
SCHEMA_VERSION = 1
AAD = b"authoroved-core:avedcase:v1"
GENESIS_HASH = "0" * 64


class CaseError(Exception):
    """Базовая ошибка работы с делом."""


class CasePasswordError(CaseError):
    """Неверный пароль либо повреждённый зашифрованный контейнер."""


class CaseIntegrityError(CaseError):
    """Внутренняя целостность дела нарушена."""


class CaseFormatError(CaseError):
    """Файл не является поддерживаемым делом Автороведа."""


@dataclass(frozen=True)
class AuditEntry:
    sequence: int
    timestamp: str
    event: str
    details: dict[str, Any]
    previous_hash: str
    entry_hash: str


@dataclass
class CaseData:
    case_id: str
    created_at: str
    updated_at: str
    materials: list[Document | None] = field(default_factory=lambda: [None, None])
    results: list[AnalysisResult | None] = field(default_factory=lambda: [None, None])
    current_slot: int = 0
    audit: list[AuditEntry] = field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _span(value: Span | None):
    return None if value is None else {"start": value.start, "end": value.end}


def _span_from(value) -> Span | None:
    return None if value is None else Span(int(value["start"]), int(value["end"]))


def _required_span(value) -> Span:
    span = _span_from(value)
    if span is None:
        raise CaseFormatError("В файле дела отсутствует обязательный диапазон текста.")
    return span


def _document(value: Document | None):
    if value is None:
        return None
    return {
        "id": value.id, "name": value.name, "text": value.text,
        "original_bytes": base64.b64encode(value.original_bytes).decode("ascii"),
        "file_sha256": value.file_sha256, "text_sha256": value.text_sha256,
        "encoding": value.encoding, "import_note": value.import_note,
    }


def _document_from(value) -> Document | None:
    if value is None:
        return None
    return Document(
        id=str(value["id"]), name=str(value["name"]), text=str(value["text"]),
        original_bytes=base64.b64decode(value["original_bytes"], validate=True),
        file_sha256=str(value["file_sha256"]), text_sha256=str(value["text_sha256"]),
        encoding=str(value["encoding"]), import_note=str(value["import_note"]),
    )


def _result(value: AnalysisResult | None):
    if value is None:
        return None
    return {
        "document_id": value.document_id,
        "tokens": [
            {
                "text": item.text, "lemma": item.lemma, "pos": item.pos,
                "feats": item.feats, "dependency": item.dependency, "head": item.head,
                "sentence": item.sentence, "index": item.index, "span": _span(item.span),
            } for item in value.tokens
        ],
        "candidates": [
            {
                "id": item.id, "document_id": item.document_id, "name": item.name,
                "category": item.category, "explanation": item.explanation,
                "fragment": item.fragment, "span": _span(item.span), "rule_id": item.rule_id,
                "replacements": list(item.replacements), "source": item.source,
                "status": item.status.value, "comment": item.comment,
            } for item in value.candidates
        ],
        "metrics": [
            {
                "name": item.name, "value": item.value, "explanation": item.explanation,
                "group": item.group, "spans": [_span(span) for span in item.spans],
            } for item in value.metrics
        ],
        "metadata": value.metadata,
        "errors": value.errors,
    }


def _result_from(value) -> AnalysisResult | None:
    if value is None:
        return None
    return AnalysisResult(
        document_id=str(value["document_id"]),
        tokens=[Token(
            text=str(item["text"]), lemma=str(item["lemma"]), pos=str(item["pos"]),
            feats=dict(item["feats"]), dependency=str(item["dependency"]),
            head=int(item["head"]), sentence=int(item["sentence"]),
            index=int(item["index"]), span=_span_from(item["span"]),
        ) for item in value["tokens"]],
        candidates=[Candidate(
            id=str(item["id"]), document_id=str(item["document_id"]), name=str(item["name"]),
            category=str(item["category"]), explanation=str(item["explanation"]),
            fragment=str(item["fragment"]), span=_required_span(item["span"]),
            rule_id=str(item["rule_id"]), replacements=tuple(item["replacements"]),
            source=str(item["source"]), status=ReviewStatus(item["status"]),
            comment=str(item["comment"]),
        ) for item in value["candidates"]],
        metrics=[Metric(
            name=str(item["name"]), value=str(item["value"]),
            explanation=str(item["explanation"]), group=str(item["group"]),
            spans=tuple(_required_span(span) for span in item["spans"]),
        ) for item in value["metrics"]],
        metadata=dict(value["metadata"]), errors=list(value["errors"]),
    )


def _case(value: CaseData) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": value.case_id,
        "created_at": value.created_at,
        "updated_at": value.updated_at,
        "current_slot": value.current_slot,
        "materials": [_document(item) for item in value.materials],
        "results": [_result(item) for item in value.results],
        "audit": [asdict(item) for item in value.audit],
    }


def _case_from(value: dict[str, Any]) -> CaseData:
    if value.get("schema_version") != SCHEMA_VERSION:
        raise CaseFormatError("Версия файла дела не поддерживается.")
    materials = [_document_from(item) for item in value["materials"]]
    results = [_result_from(item) for item in value["results"]]
    if len(materials) != 2 or len(results) != 2:
        raise CaseFormatError("В деле должна быть пара мест для исследуемых текстов.")
    return CaseData(
        case_id=str(value["case_id"]), created_at=str(value["created_at"]),
        updated_at=str(value["updated_at"]), materials=materials, results=results,
        current_slot=int(value["current_slot"]),
        audit=[AuditEntry(**item) for item in value["audit"]],
    )


class CaseRepository:
    def __init__(self, *, memory_cost_kib: int = 65536, time_cost: int = 3,
                 parallelism: int = 4):
        self.memory_cost_kib = memory_cost_kib
        self.time_cost = time_cost
        self.parallelism = parallelism

    def create(self) -> CaseData:
        timestamp = _now()
        value = CaseData(str(uuid4()), timestamp, timestamp)
        self.record(value, "case_created", {})
        return value

    def record(self, case: CaseData, event: str, details: dict[str, Any]) -> AuditEntry:
        previous = case.audit[-1].entry_hash if case.audit else GENESIS_HASH
        payload = {
            "sequence": len(case.audit) + 1,
            "timestamp": _now(),
            "event": event,
            "details": copy.deepcopy(details),
            "previous_hash": previous,
        }
        entry = AuditEntry(**payload, entry_hash=sha256(_canonical(payload)).hexdigest())
        case.audit.append(entry)
        case.updated_at = entry.timestamp
        return entry

    def verify_integrity(self, case: CaseData) -> None:
        issues = []
        if not case.case_id:
            issues.append("Отсутствует идентификатор дела.")
        if case.current_slot not in {0, 1}:
            issues.append("Некорректен номер активного текста.")
        if not case.audit or case.audit[0].event != "case_created":
            issues.append("Отсутствует начальная запись журнала.")
        previous = GENESIS_HASH
        for expected, entry in enumerate(case.audit, 1):
            payload = {
                "sequence": entry.sequence, "timestamp": entry.timestamp,
                "event": entry.event, "details": entry.details,
                "previous_hash": entry.previous_hash,
            }
            calculated = sha256(_canonical(payload)).hexdigest()
            if entry.sequence != expected or entry.previous_hash != previous or entry.entry_hash != calculated:
                issues.append(f"Нарушена цепочка журнала в записи {expected}.")
            previous = entry.entry_hash
        if case.audit and case.updated_at != case.audit[-1].timestamp:
            issues.append("Время изменения дела не соответствует журналу.")
        for index, (document, result) in enumerate(zip(case.materials, case.results), 1):
            if document is None:
                if result is not None:
                    issues.append(f"У текста {index} есть результат без исходного документа.")
                continue
            if sha256_bytes(document.original_bytes) != document.file_sha256:
                issues.append(f"Не совпадает контрольная сумма файла текста {index}.")
            if sha256_bytes(document.text.encode("utf-8")) != document.text_sha256:
                issues.append(f"Не совпадает контрольная сумма извлечённого текста {index}.")
            if result is None:
                continue
            if result.document_id != document.id:
                issues.append(f"Результат текста {index} относится к другому документу.")
            for token in result.tokens:
                if token.span is not None and (
                    not token.span.valid_for(document.text)
                    or document.text[token.span.start:token.span.end] != token.text
                ):
                    issues.append(f"Некорректен диапазон слова в тексте {index}.")
            for candidate in result.candidates:
                if candidate.document_id != document.id or not candidate.span.valid_for(document.text):
                    issues.append(f"Некорректен кандидат {candidate.id} текста {index}.")
                elif document.text[candidate.span.start:candidate.span.end] != candidate.fragment:
                    issues.append(f"Не совпадает фрагмент кандидата {candidate.id} текста {index}.")
            for metric in result.metrics:
                if any(not span.valid_for(document.text) for span in metric.spans):
                    issues.append(f"Некорректен диапазон показателя «{metric.name}» текста {index}.")
        if issues:
            raise CaseIntegrityError(" ".join(issues))

    def save(self, path: str | Path, case: CaseData, password: str) -> Path:
        if not password:
            raise ValueError("Пароль не может быть пустым.")
        path = Path(path)
        working = copy.deepcopy(case)
        self.record(working, "case_saved", {"file_name": path.name})
        self.verify_integrity(working)
        salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
        key = self._derive(password, salt, self.memory_cost_kib, self.time_cost, self.parallelism)
        ciphertext = AESGCM(key).encrypt(nonce, _canonical(_case(working)), AAD)
        envelope = {
            "format": FORMAT_NAME, "version": SCHEMA_VERSION,
            "kdf": {
                "name": "argon2id", "salt": base64.b64encode(salt).decode("ascii"),
                "memory_cost_kib": self.memory_cost_kib, "time_cost": self.time_cost,
                "parallelism": self.parallelism, "length": 32,
            },
            "cipher": {"name": "AES-256-GCM", "nonce": base64.b64encode(nonce).decode("ascii")},
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(_canonical(envelope))
                stream.flush()
                os.fsync(stream.fileno())
            verified = self._read(temporary, password)
            self.verify_integrity(verified)
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
        case.audit = working.audit
        case.updated_at = working.updated_at
        return path

    def open(self, path: str | Path, password: str) -> CaseData:
        case = self._read(Path(path), password)
        self.verify_integrity(case)
        return case

    def _read(self, path: Path, password: str) -> CaseData:
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            if envelope.get("format") != FORMAT_NAME or envelope.get("version") != SCHEMA_VERSION:
                raise CaseFormatError("Файл не является делом Автороведа поддерживаемой версии.")
            kdf, cipher = envelope["kdf"], envelope["cipher"]
            if kdf.get("name") != "argon2id" or cipher.get("name") != "AES-256-GCM":
                raise CaseFormatError("Формат защиты файла дела не поддерживается.")
            memory = int(kdf["memory_cost_kib"])
            time_cost = int(kdf["time_cost"])
            parallelism = int(kdf["parallelism"])
            if not (8192 <= memory <= 1048576 and 1 <= time_cost <= 10 and 1 <= parallelism <= 16):
                raise CaseFormatError("Параметры защиты файла дела некорректны.")
            salt = base64.b64decode(kdf["salt"], validate=True)
            nonce = base64.b64decode(cipher["nonce"], validate=True)
            ciphertext = base64.b64decode(envelope["ciphertext"], validate=True)
            if len(salt) != 16 or len(nonce) != 12 or int(kdf.get("length", 0)) != 32:
                raise CaseFormatError("Параметры защиты файла дела некорректны.")
            key = self._derive(password, salt, memory, time_cost, parallelism)
            plaintext = AESGCM(key).decrypt(nonce, ciphertext, AAD)
            return _case_from(json.loads(plaintext.decode("utf-8")))
        except CaseError:
            raise
        except InvalidTag as exc:
            raise CasePasswordError("Неверный пароль либо файл дела повреждён.") from exc
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeError) as exc:
            raise CaseFormatError("Файл дела повреждён или имеет неверный формат.") from exc

    @staticmethod
    def _derive(password: str, salt: bytes, memory: int, time_cost: int,
                parallelism: int) -> bytes:
        return hash_secret_raw(
            secret=password.encode("utf-8"), salt=salt, time_cost=time_cost,
            memory_cost=memory, parallelism=parallelism, hash_len=32, type=Type.ID,
        )
