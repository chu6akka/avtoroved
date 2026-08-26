"""
protocol/feature_map.py — карта признаков: экспертный отбор кандидатов.

Центральный элемент протокола: эксперт просматривает кандидатов признаков
(feature_candidates, построенные раздельным исследованием) и выносит решения.
Сравнительного исследования здесь НЕТ — только отбор.

Хранение (по требованию заказчика):
  • feature_decisions — append-only журнал ВСЕХ решений (история не правится);
  • features          — текущее состояние: последнее решение по кандидату.

Привязка решения к кандидату — через стабильный ключ candidate_key
(хэш содержимого), а не через id строки: пересборка профиля делает clear+insert
и меняет id, но содержательно тот же кандидат сохраняет ключ, поэтому решения
эксперта переживают пересборку. Если кандидат изменился по содержанию —
ключ другой, и он честно возвращается в «нерешённые».
"""
from __future__ import annotations

import hashlib
from typing import Any, Optional

from protocol import db as protocol_db
from protocol import feature_model as model

# ── Статусы решений ──────────────────────────────────────────────────────────
STATUS_ACCEPTED = "принят"
STATUS_REJECTED = "отклонён"
STATUS_DOUBTFUL = "сомнителен"
STATUS_IGNORED = "не_учитывать"
STATUS_RESET = "сброшен"          # служебный: снимает решение (только в истории)

# Статусы, которые эксперт выставляет из UI.
DECISION_STATUSES = (STATUS_ACCEPTED, STATUS_REJECTED, STATUS_DOUBTFUL, STATUS_IGNORED)

# Значения идентификационной ценности, доступные эксперту при принятии.
ID_VALUES = ("низкая", "средняя", "высокая")


def candidate_key(candidate: Any) -> str:
    """
    Стабильный ключ кандидата: sha256 от содержательных полей.
    candidate — sqlite3.Row или dict с полями feature_candidates.
    """
    def g(field: str) -> str:
        try:
            v = candidate[field]
        except (KeyError, IndexError, TypeError):
            v = None
        return str(v) if v is not None else ""

    # Экспертный кандидат имеет стабильный UID и не теряет решения при
    # уточнении отображаемого текста/мотивировки. AUTO-кандидаты сохраняют
    # прежний содержательный hash.
    uid = g("candidate_uid")
    if uid:
        return uid
    payload = "|".join((
        g("document_id"), g("group_name"), g("subgroup"),
        g("label"), g("value"), g("fragment"),
    ))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _snapshot(candidate: Any) -> dict:
    def g(field: str):
        try:
            return candidate[field]
        except (KeyError, IndexError, TypeError):
            return None
    return {
        "group_name": g("group_name"), "subgroup": g("subgroup"),
        "label": g("label"), "value": g("value"), "fragment": g("fragment"),
        "source": g("source"), "source_section": g("source_section"),
        "reliability": g("reliability"),
        "id_value": g("id_value"),
        "candidate_origin": g("candidate_origin") or model.CANDIDATE_ORIGIN_AUTO,
        "candidate_uid": g("candidate_uid"),
        "role": model.normalized_role(candidate),
        "source_kind": g("source_kind"),
        "method_feature_id": g("method_feature_id"),
        "method_reference_informativeness": g("method_reference_informativeness"),
        "detection_reliability": g("detection_reliability") or g("reliability"),
    }


def decide(
    pdb: "protocol_db.ProtocolDB",
    project_id: int,
    document_id: int,
    candidate: Any,
    status: str,
    expert_id_value: str = "",
    expert_identification_value: Optional[str] = None,
    expert_note: str = "",
    program_version: Optional[str] = None,
) -> str:
    """
    Вынести решение по кандидату (или STATUS_RESET — снять решение).
    Возвращает candidate_key. Пишет в feature_decisions/features и в audit_log.
    """
    if status not in DECISION_STATUSES + (STATUS_RESET,):
        raise ValueError(f"Недопустимый статус решения: {status}")
    role = model.normalized_role(candidate)
    if status == STATUS_ACCEPTED and role != model.METHOD_FEATURE:
        raise ValueError("Принять как идентификационный признак можно только METHOD_FEATURE")
    expert_value = (expert_identification_value
                    if expert_identification_value is not None else expert_id_value)
    if expert_value and expert_value not in ID_VALUES:
        raise ValueError(f"Недопустимая экспертная идентификационная ценность: {expert_value}")
    key = candidate_key(candidate)
    snap = _snapshot(candidate)
    pdb.record_feature_decision(
        project_id, document_id, key, status, snap,
        expert_id_value=expert_value, expert_note=expert_note,
        program_version=program_version)
    pdb.log_action(
        f"признак: {status}", project_id=project_id,
        details={"document_id": document_id, "candidate_key": key,
                 "label": snap["label"],
                 "role": role,
                 "ид_ценность_эксперта": expert_value or None,
                 "примечание": expert_note or None},
        program_version=program_version)
    return key


def candidates_with_state(pdb: "protocol_db.ProtocolDB",
                          document_id: int) -> list[tuple[Any, Optional[Any]]]:
    """
    Только METHOD_FEATURE-кандидаты вместе с текущим решением. Метрики,
    evidence и общие навыки доступны в раздельном исследовании, но не могут
    быть случайно приняты как идентификационный признак.
    """
    state = {f["candidate_key"]: f for f in pdb.fetch_features(document_id=document_id)}
    out = []
    for c in pdb.fetch_feature_candidates(document_id):
        if model.normalized_role(c) != model.METHOD_FEATURE:
            continue
        # Подавленные фильтром сырые срабатывания хранятся для
        # воспроизводимости, но кандидатами для принятия не являются.
        if (c["reliability"] or "") == "подавлен":
            continue
        out.append((c, state.get(candidate_key(c))))
    return out


def stats(pairs: list[tuple[Any, Optional[Any]]]) -> dict:
    """Прогресс отбора: {'всего', 'решено', 'нерешённые', по статусам…}."""
    st: dict = {"всего": len(pairs), "решено": 0}
    for s in DECISION_STATUSES:
        st[s] = 0
    for _c, f in pairs:
        if f is not None:
            st["решено"] += 1
            if f["status"] in st:
                st[f["status"]] += 1
    st["нерешённые"] = st["всего"] - st["решено"]
    return st
