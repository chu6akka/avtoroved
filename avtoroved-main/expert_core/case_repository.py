from __future__ import annotations

import base64
from dataclasses import fields, is_dataclass
import hashlib
import json
import os
from pathlib import Path
import secrets
import tempfile
from typing import Any, TypeVar, get_args, get_origin, get_type_hints
import uuid

from .models import AuditEvent, ExpertCase, TextObject, utc_now

MAGIC = b"AVEDCASE\x01"
T = TypeVar("T")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _convert(tp, value):
    if value is None:
        return None
    origin = get_origin(tp)
    if origin is list:
        return [_convert(get_args(tp)[0], x) for x in value]
    if origin is dict:
        kt, vt = get_args(tp)
        return {k: _convert(vt, v) for k, v in value.items()}
    if origin is not None and type(None) in get_args(tp):
        target = next(t for t in get_args(tp) if t is not type(None))
        return _convert(target, value)
    if isinstance(tp, type) and issubclass(tp, str) and hasattr(tp, "__members__"):
        return tp(value)
    if isinstance(tp, type) and is_dataclass(tp):
        hints = get_type_hints(tp)
        return tp(**{f.name: _convert(hints.get(f.name, Any), value[f.name]) for f in fields(tp) if f.name in value})
    return value


class CaseRepository:
    @staticmethod
    def create(title: str, method_profile: str, actor: str = "expert") -> ExpertCase:
        case = ExpertCase(str(uuid.uuid4()), title, method_profile)
        CaseRepository.append_audit(case, "case_created", actor, {"title": title, "profile": method_profile})
        return case

    @staticmethod
    def add_text(case: ExpertCase, obj: TextObject, actor: str = "expert") -> None:
        obj.source_sha256 = hashlib.sha256(obj.text.encode("utf-8")).hexdigest()
        case.objects.append(obj)
        CaseRepository.append_audit(case, "object_added", actor, {"id": obj.id, "sha256": obj.source_sha256})

    @staticmethod
    def append_audit(case: ExpertCase, event_type: str, actor: str, details: dict[str, Any]) -> AuditEvent:
        previous = case.audit[-1].hash if case.audit else "0" * 64
        body = {"sequence": len(case.audit) + 1, "timestamp": utc_now(), "event_type": event_type,
                "actor": actor, "details": details, "previous_hash": previous}
        digest = hashlib.sha256(_canonical(body)).hexdigest()
        event = AuditEvent(hash=digest, **body)
        case.audit.append(event)
        return event

    @staticmethod
    def verify_integrity(case: ExpertCase) -> bool:
        previous = "0" * 64
        for idx, event in enumerate(case.audit, 1):
            body = {"sequence": event.sequence, "timestamp": event.timestamp,
                    "event_type": event.event_type, "actor": event.actor,
                    "details": event.details, "previous_hash": event.previous_hash}
            if event.sequence != idx or event.previous_hash != previous:
                return False
            if hashlib.sha256(_canonical(body)).hexdigest() != event.hash:
                return False
            previous = event.hash
        return all(not o.source_sha256 or hashlib.sha256(o.text.encode("utf-8")).hexdigest() == o.source_sha256
                   for o in case.objects)

    @staticmethod
    def _key(password: str, salt: bytes) -> bytes:
        try:
            from argon2.low_level import Type, hash_secret_raw
        except ImportError as exc:
            raise RuntimeError("Для защищённых дел установите argon2-cffi") from exc
        if len(password) < 8:
            raise ValueError("Пароль дела должен содержать не менее 8 символов")
        return hash_secret_raw(password.encode("utf-8"), salt, 3, 65536, 4, 32, Type.ID)

    def save(self, case: ExpertCase, path: str | Path, password: str) -> None:
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as exc:
            raise RuntimeError("Для защищённых дел установите cryptography") from exc
        if not self.verify_integrity(case):
            raise ValueError("Нарушена целостность дела")
        path = Path(path)
        salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
        key = self._key(password, salt)
        payload = _canonical(case.to_dict())
        cipher = AESGCM(key).encrypt(nonce, payload, MAGIC + salt)
        data = MAGIC + salt + nonce + cipher
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data); fh.flush(); os.fsync(fh.fileno())
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def open(self, path: str | Path, password: str) -> ExpertCase:
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as exc:
            raise RuntimeError("Для защищённых дел установите cryptography") from exc
        data = Path(path).read_bytes()
        if not data.startswith(MAGIC) or len(data) < len(MAGIC) + 28:
            raise ValueError("Неизвестный или повреждённый формат дела")
        pos = len(MAGIC); salt = data[pos:pos+16]; nonce = data[pos+16:pos+28]
        try:
            plain = AESGCM(self._key(password, salt)).decrypt(nonce, data[pos+28:], MAGIC + salt)
        except Exception as exc:
            raise ValueError("Неверный пароль или нарушена целостность контейнера") from exc
        case = _convert(ExpertCase, json.loads(plain.decode("utf-8")))
        if not self.verify_integrity(case):
            raise ValueError("Нарушена целостность журнала или исходных объектов")
        return case
