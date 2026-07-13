"""
protocol/comparison.py — стадия «сравнительное исследование» (Рубцова 2007).

Сопоставляет ПРИНЯТЫЕ экспертом признаки (таблица features, статус «принят»)
пары спорный↔образец. Автоматика даёт только черновик: признаки с одинаковым
содержательным ключом (группа, подгруппа, наименование) в обоих текстах —
черновик «совпадение», признак в одном тексте — «только_у_…». Классификацию
(совпадение/различие) и уровень индивидуализации НН/НС/НСВ подтверждает
эксперт; его решения хранятся append-only (comparison_decisions) + текущее
состояние (comparisons) и переживают пересборку авто-позиций.

Вывода об авторстве здесь НЕТ — правило вывода (порог ≥20 признаков,
различие на НН → категорический отрицательный и т.д., с.85–86) применяется
на следующей стадии. Здесь только подготовка и учёт данных для него.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Optional

from protocol import db as protocol_db
from protocol import feature_map as fm
from protocol import profile as prof

# ── Типы сопоставления ───────────────────────────────────────────────────────
MATCH_COINCIDENCE = "совпадение"
MATCH_DIFFERENCE = "различие"
MATCH_ONLY_A = "только_у_спорного"
MATCH_ONLY_B = "только_у_образца"
MATCH_TYPES = (MATCH_COINCIDENCE, MATCH_DIFFERENCE, MATCH_ONLY_A, MATCH_ONLY_B)

# ── Уровни индивидуализации навыка (Рубцова 2007, с.11): НН < НС < НСВ ───────
LEVELS = ("НН", "НС", "НСВ")

# Методический порог высокоинформативных признаков для категорического
# положительного вывода (Рубцова 2007, с.85–86). Здесь — только справочно.
MIN_FEATURES_FOR_CONCLUSION = 20

STATUS_AUTO = "авто"
STATUS_CONFIRMED = "подтверждено"
STATUS_RESET = "сброшено"

# ── Общие признаки: допуски сопоставления степеней навыков ───────────────────
# Допуск — по числу ошибок на 200 словоформ (методика СЭУ Минюста, с. 19
# [сверить]): ±2 для грамматического и лексико-фразеологического, ±4 для
# орфографического и пунктуационного. Сопоставление общих признаков идёт на
# уровне НН; общий уровень грамотности с допуском не сопоставляется (справочен).
GENERAL_TOLERANCE = {
    "грамматический": 2.0,
    "лексико-фразеологический": 2.0,
    "орфографический": 4.0,
    "пунктуационный": 4.0,
}

GENERAL_VERDICT_EQUAL = "совпадает"
GENERAL_VERDICT_HIGHER_A = "выше_в_спорном"   # ошибок меньше → навык выше
GENERAL_VERDICT_LOWER_A = "ниже_в_спорном"

# Формат value общего признака — profile.GENERAL_VALUE_FMT.
_GENERAL_RATE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*ош\./200")

# ── Покатегорийные пороги подтверждённых совпадений ──────────────────────────
# Моисеева/Огорелков 2021, с. 89–93 [сверить]. Дополнение к суммарному порогу
# ≥20 (Рубцова, с. 85), не замена. Грамматические и общие признаки в корзины
# не входят — учитываются только в суммарном счётчике.
BUCKET_ORTH_PUNCT = "языковые: орфографические+пунктуационные"
THRESHOLDS_CATEGORICAL = {
    "смысловые": 3,
    "текстологические": 5,
    "языковые: лексические": 10,
    "языковые: стилистические": 10,
    "языковые: синтаксические": 10,
    BUCKET_ORTH_PUNCT: 5,
    "психолингвистические": 5,
}
# Вероятный вывод — половина категорических порогов, округление вверх.
THRESHOLDS_PROBABLE = {k: math.ceil(v / 2) for k, v in THRESHOLDS_CATEGORICAL.items()}

_LINGUISTIC_SUBGROUP_BUCKET = {
    prof.SUB_LEXICAL: "языковые: лексические",
    prof.SUB_STYLISTIC: "языковые: стилистические",
    prof.SUB_SYNTACTIC: "языковые: синтаксические",
    prof.SUB_ORTHOGRAPHIC: BUCKET_ORTH_PUNCT,
    prof.SUB_PUNCTUATION: BUCKET_ORTH_PUNCT,
}


def position_key(doc_a: int, doc_b: int, group: str, subgroup: str, label: str) -> str:
    """Стабильный ключ позиции сопоставления пары."""
    payload = f"{doc_a}|{doc_b}|{group or ''}|{subgroup or ''}|{label or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _accepted_features(pdb: "protocol_db.ProtocolDB", document_id: int) -> dict:
    """
    Принятые признаки документа, сгруппированные по содержательному ключу
    (group, subgroup, label). Несколько признаков с одним ключом объединяются
    (значения/фрагменты через « ; »).
    """
    by_key: dict[tuple, dict] = {}
    for f in pdb.fetch_features(document_id=document_id):
        if f["status"] != fm.STATUS_ACCEPTED:
            continue
        k = (f["group_name"] or "", f["subgroup"] or "", f["label"] or "")
        slot = by_key.setdefault(k, {"feature_key": f["candidate_key"],
                                     "values": [], "fragments": []})
        if f["value"]:
            slot["values"].append(f["value"])
        if f["fragment"]:
            slot["fragments"].append(f["fragment"])
    return by_key


def parse_general_rate(value: Optional[str]) -> Optional[float]:
    """Число ошибок на 200 словоформ из value общего признака."""
    if not value:
        return None
    m = _GENERAL_RATE_RE.search(value)
    return float(m.group(1).replace(",", ".")) if m else None


def general_skill_verdicts(pdb: "protocol_db.ProtocolDB",
                           doc_a: int, doc_b: int) -> dict[str, dict]:
    """
    Сопоставление общих признаков пары по 4 навыкам с допусками Минюста.
    Читает feature_candidates (kind='общий_признак') обоих документов —
    карту признаков общие признаки минуют. Возвращает
    {навык: {verdict, rate_a, rate_b, delta, tolerance,
             value_a, value_b, reliability_a, reliability_b}}.
    """
    def _generals(did: int) -> dict[str, Any]:
        return {c["subgroup"]: c for c in pdb.fetch_feature_candidates(did)
                if c["kind"] == prof.KIND_GENERAL}

    ga, gb = _generals(doc_a), _generals(doc_b)
    out: dict[str, dict] = {}
    for skill, tol in GENERAL_TOLERANCE.items():
        a, b = ga.get(skill), gb.get(skill)
        if a is None or b is None:
            continue
        rate_a, rate_b = parse_general_rate(a["value"]), parse_general_rate(b["value"])
        if rate_a is None or rate_b is None:
            continue
        delta = round(rate_a - rate_b, 1)
        if abs(delta) <= tol:
            verdict = GENERAL_VERDICT_EQUAL
        elif rate_a < rate_b:      # в спорном ошибок меньше → навык выше
            verdict = GENERAL_VERDICT_HIGHER_A
        else:
            verdict = GENERAL_VERDICT_LOWER_A
        out[skill] = {
            "verdict": verdict, "rate_a": rate_a, "rate_b": rate_b,
            "delta": delta, "tolerance": tol,
            "value_a": a["value"], "value_b": b["value"],
            "reliability_a": a["reliability"] or "",
            "reliability_b": b["reliability"] or "",
        }
    return out


def bucket_of(group_name: Optional[str], subgroup: Optional[str]) -> Optional[str]:
    """Корзина Огорелкова для позиции; None — только в суммарный счётчик."""
    g = group_name or ""
    if g in ("смысловые", "текстологические", "психолингвистические"):
        return g
    if g == "языковые":
        return _LINGUISTIC_SUBGROUP_BUCKET.get(subgroup or "")
    return None


def bucket_breakdown(pdb: "protocol_db.ProtocolDB",
                     doc_a: int, doc_b: int) -> list[dict]:
    """
    Подтверждённые СОВПАДЕНИЯ пары по корзинам Огорелкова: сколько набрано,
    пороги категорического/вероятного вывода и их достижение.
    """
    counts = {b: 0 for b in THRESHOLDS_CATEGORICAL}
    for r in pdb.fetch_comparisons(doc_a, doc_b):
        if r["status"] != STATUS_CONFIRMED or r["match_type"] != MATCH_COINCIDENCE:
            continue
        b = bucket_of(r["group_name"], r["subgroup"])
        if b:
            counts[b] += 1
    return [{
        "bucket": b,
        "confirmed": counts[b],
        "threshold_categorical": THRESHOLDS_CATEGORICAL[b],
        "threshold_probable": THRESHOLDS_PROBABLE[b],
        "meets_categorical": counts[b] >= THRESHOLDS_CATEGORICAL[b],
        "meets_probable": counts[b] >= THRESHOLDS_PROBABLE[b],
    } for b in THRESHOLDS_CATEGORICAL]


def auto_match(
    pdb: "protocol_db.ProtocolDB",
    project_id: int,
    doc_a: int,
    doc_b: int,
    program_version: Optional[str] = None,
) -> dict:
    """
    Автоматическое сопоставление принятых признаков пары (черновик).
    Пересборка идемпотентна: авто-позиции перестраиваются, подтверждённые
    экспертом позиции не трогаются. Пишет итог в audit_log.
    """
    fa = _accepted_features(pdb, doc_a)
    fb = _accepted_features(pdb, doc_b)

    positions: list[dict] = []
    for k in sorted(set(fa) | set(fb)):
        group, subgroup, label = k
        a, b = fa.get(k), fb.get(k)
        if a and b:
            mtype = MATCH_COINCIDENCE
        elif a:
            mtype = MATCH_ONLY_A
        else:
            mtype = MATCH_ONLY_B
        positions.append({
            "position_key": position_key(doc_a, doc_b, group, subgroup, label),
            "feature_key_a": a["feature_key"] if a else None,
            "feature_key_b": b["feature_key"] if b else None,
            "group_name": group, "subgroup": subgroup or None, "label": label,
            "value_a": " ; ".join(a["values"]) if a else None,
            "value_b": " ; ".join(b["values"]) if b else None,
            "fragment_a": " ; ".join(a["fragments"]) if a else None,
            "fragment_b": " ; ".join(b["fragments"]) if b else None,
            "match_type": mtype,
        })

    # Общие признаки (степени навыков): сопоставляются автоматически с
    # допусками Минюста, минуя карту признаков — черновик «совпадение» или
    # «различие» по вердикту, дельта видна в value обеих сторон.
    gsv = general_skill_verdicts(pdb, doc_a, doc_b)
    for skill in sorted(gsv):
        v = gsv[skill]
        label = f"{prof.GENERAL_LABEL_PREFIX}{skill} навык"
        positions.append({
            "position_key": position_key(doc_a, doc_b, prof.GROUP_LINGUISTIC,
                                         skill, label),
            "feature_key_a": None, "feature_key_b": None,
            "group_name": prof.GROUP_LINGUISTIC, "subgroup": skill,
            "label": label,
            "value_a": v["value_a"], "value_b": v["value_b"],
            "fragment_a": None, "fragment_b": None,
            "match_type": (MATCH_COINCIDENCE
                           if v["verdict"] == GENERAL_VERDICT_EQUAL
                           else MATCH_DIFFERENCE),
        })

    inserted, confirmed_kept = pdb.replace_auto_comparisons(
        project_id, doc_a, doc_b, positions)
    pdb.log_action(
        "сравнительное исследование: авто-сопоставление", project_id=project_id,
        details={"pair_doc_a": doc_a, "pair_doc_b": doc_b,
                 "позиций_всего": len(positions), "вставлено_авто": inserted,
                 "сохранено_подтверждённых": confirmed_kept,
                 "признаков_спорного": len(fa), "признаков_образца": len(fb),
                 "общие_признаки": {s: {"вердикт": v["verdict"],
                                        "дельта": v["delta"],
                                        "допуск": v["tolerance"]}
                                    for s, v in gsv.items()}},
        program_version=program_version)
    return {"positions": len(positions), "inserted_auto": inserted,
            "confirmed_kept": confirmed_kept, "general_verdicts": gsv}


def decide(
    pdb: "protocol_db.ProtocolDB",
    project_id: int,
    doc_a: int,
    doc_b: int,
    pos_key: str,
    match_type: Optional[str] = None,
    level: str = "",
    expert_note: str = "",
    program_version: Optional[str] = None,
) -> None:
    """Подтвердить позицию: тип (совпадение/различие), уровень НН/НС/НСВ, примечание."""
    if match_type is not None and match_type not in MATCH_TYPES:
        raise ValueError(f"Недопустимый тип сопоставления: {match_type}")
    if level and level not in LEVELS:
        raise ValueError(f"Недопустимый уровень: {level}")
    pdb.record_comparison_decision(
        project_id, doc_a, doc_b, pos_key, STATUS_CONFIRMED,
        match_type=match_type, level=level, expert_note=expert_note,
        program_version=program_version)
    pdb.log_action(
        "сравнение: позиция подтверждена", project_id=project_id,
        details={"pair_doc_a": doc_a, "pair_doc_b": doc_b,
                 "position_key": pos_key, "тип": match_type,
                 "уровень": level or None, "примечание": expert_note or None},
        program_version=program_version)


def reset(
    pdb: "protocol_db.ProtocolDB",
    project_id: int,
    doc_a: int,
    doc_b: int,
    pos_key: str,
    program_version: Optional[str] = None,
) -> None:
    """Снять подтверждение позиции (история решений сохраняется)."""
    pdb.record_comparison_decision(
        project_id, doc_a, doc_b, pos_key, STATUS_RESET,
        program_version=program_version)
    pdb.log_action(
        "сравнение: позиция сброшена", project_id=project_id,
        details={"pair_doc_a": doc_a, "pair_doc_b": doc_b, "position_key": pos_key},
        program_version=program_version)


def pair_blocks_strong_conclusion(pdb: "protocol_db.ProtocolDB",
                                  project_id: int, doc_a: int, doc_b: int) -> bool:
    """
    Заблокирован ли категорический вывод для пары: смотрим строки suitability
    самой пары и обоих документов (любой blocks_strong_conclusion=1 → блок).
    """
    for r in pdb.fetch_suitability(project_id):
        hit_pair = (r["pair_doc_a"] == doc_a and r["pair_doc_b"] == doc_b)
        hit_doc = r["document_id"] in (doc_a, doc_b)
        if (hit_pair or hit_doc) and r["blocks_strong_conclusion"]:
            return True
    return False


def stats(pdb: "protocol_db.ProtocolDB", project_id: int,
          doc_a: int, doc_b: int) -> dict:
    """
    Сводка по паре: позиции по типам/статусам, подтверждённые по уровням,
    справочный порог ≥20 и блокировка категорического вывода.
    """
    rows = pdb.fetch_comparisons(doc_a, doc_b)
    st: dict = {"всего": len(rows), "подтверждено": 0}
    for t in MATCH_TYPES:
        st[t] = 0
    for lv in LEVELS:
        st[f"уровень_{lv}"] = 0
    for r in rows:
        st[r["match_type"]] = st.get(r["match_type"], 0) + 1
        if r["status"] == STATUS_CONFIRMED:
            st["подтверждено"] += 1
            if r["level"]:
                st[f"уровень_{r['level']}"] += 1
    st["порог_методики"] = MIN_FEATURES_FOR_CONCLUSION
    st["до_порога"] = max(0, MIN_FEATURES_FOR_CONCLUSION - st["подтверждено"])
    st["blocks_strong_conclusion"] = pair_blocks_strong_conclusion(
        pdb, project_id, doc_a, doc_b)
    st["общие_признаки"] = general_skill_verdicts(pdb, doc_a, doc_b)
    st["разбивка_по_группам"] = bucket_breakdown(pdb, doc_a, doc_b)
    return st
