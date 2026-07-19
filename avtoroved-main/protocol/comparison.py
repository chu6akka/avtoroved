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
from typing import Any, Optional

from protocol import db as protocol_db
from protocol import feature_map as fm

# ── Типы сопоставления ───────────────────────────────────────────────────────
MATCH_COINCIDENCE = "совпадение"
MATCH_DIFFERENCE = "различие"
MATCH_ONLY_A = "только_у_спорного"
MATCH_ONLY_B = "только_у_образца"
MATCH_TYPES = (MATCH_COINCIDENCE, MATCH_DIFFERENCE, MATCH_ONLY_A, MATCH_ONLY_B)

# ── Вердикты сопоставления ОБЩИХ признаков (степеней навыков) ────────────────
# «Выше в спорном» = степень навыка выше (ошибок МЕНЬШЕ) за пределами допуска.
GEN_EQUAL = "навык_совпадает"
GEN_HIGHER = "навык_выше_в_спорном"
GEN_LOWER = "навык_ниже_в_спорном"
GEN_TYPES = (GEN_EQUAL, GEN_HIGHER, GEN_LOWER)

# Допуски сопоставления степеней навыков, в ошибках на 200 словоформ
# (методические рекомендации СЭУ Минюста России, с. 19):
# грамматический и лексико-фразеологический — ±2, орфографический и
# пунктуационный — ±4.
SKILL_TOLERANCE = {
    "грамматический": 2.0,
    "лексико-фразеологический": 2.0,
    "орфографический": 4.0,
    "пунктуационный": 4.0,
}
# Решающие навыки правила Вула (2007, с. 38): орфография/пунктуация в правиле
# НЕ участвуют.
VUL_DECISIVE_SKILLS = ("грамматический", "лексико-фразеологический")

# ── Покатегорийные минимумы совпадающих признаков ────────────────────────────
# для категорического положительного вывода (Моисеева/Огорелков, 2021,
# с. 89–93); вероятный — половина с округлением вверх. Ключ разбивки:
# для языковых — подгруппа (орфографические и пунктуационные объединяются),
# для остальных групп — группа целиком.
CATEGORY_MIN_CATEGORICAL = {
    "смысловые": 3,
    "текстологические": 5,
    "языковые/лексические": 10,
    "языковые/стилистические": 10,
    "языковые/синтаксические": 10,
    "языковые/орфографические+пунктуационные": 5,
    "психолингвистические": 5,
}


def category_min_probable(n: int) -> int:
    """Порог вероятного вывода: половина категорического, округление вверх."""
    return (n + 1) // 2


def category_key(group: str, subgroup: str) -> str:
    """Ключ покатегорийной разбивки для позиции сопоставления."""
    g, s = group or "", subgroup or ""
    if g != "языковые":
        return g
    if s in ("орфографические", "пунктуационные"):
        return "языковые/орфографические+пунктуационные"
    return f"языковые/{s}" if s else "языковые"

# ── Уровни индивидуализации навыка (Рубцова 2007, с.11): НН < НС < НСВ ───────
LEVELS = ("НН", "НС", "НСВ")

# Методический порог высокоинформативных признаков для категорического
# положительного вывода (Рубцова 2007, с.85–86). Здесь — только справочно.
MIN_FEATURES_FOR_CONCLUSION = 20

STATUS_AUTO = "авто"
STATUS_CONFIRMED = "подтверждено"
STATUS_RESET = "сброшено"


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


def _parse_rate(value: Optional[str]) -> Optional[float]:
    """Достать «ошибок/200 словоформ» из value общего признака профиля."""
    import re as _re
    if not value:
        return None
    m = _re.search(r"([\d.,]+)\s*ошибок/200", value)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def skill_verdict(rate_a: Optional[float], rate_b: Optional[float],
                  skill: str) -> Optional[str]:
    """
    Вердикт сопоставления степени навыка пары по числовому rate
    (ошибок/200 словоформ) с допуском Минюста (с. 19).
    Меньше ошибок в спорном за пределами допуска → степень навыка ВЫШЕ.
    """
    if rate_a is None or rate_b is None:
        return None
    tol = SKILL_TOLERANCE.get(skill)
    if tol is None:
        return None
    diff = rate_b - rate_a          # >0 → в спорном ошибок меньше → навык выше
    if diff > tol:
        return GEN_HIGHER
    if diff < -tol:
        return GEN_LOWER
    return GEN_EQUAL


def general_positions(pdb: "protocol_db.ProtocolDB",
                      doc_a: int, doc_b: int) -> list[dict]:
    """
    Позиции сопоставления общих признаков (степеней навыков) пары.
    Берутся напрямую из профилей (kind='общий_признак'): по методике общие
    признаки сопоставляются всегда и через экспертный отбор не проходят.
    """
    from protocol.profile import KIND_GENERAL

    def _skills(document_id: int) -> dict[str, dict]:
        out = {}
        for c in pdb.fetch_feature_candidates(document_id):
            if c["kind"] == KIND_GENERAL and (c["subgroup"] or "") in SKILL_TOLERANCE:
                out[c["subgroup"]] = c
        return out

    sa, sb = _skills(doc_a), _skills(doc_b)
    positions: list[dict] = []
    for skill in SKILL_TOLERANCE:
        a, b = sa.get(skill), sb.get(skill)
        if a is None or b is None:
            continue
        verdict = skill_verdict(_parse_rate(a["value"]), _parse_rate(b["value"]), skill)
        if verdict is None:
            continue
        label = f"Общий признак: {skill} навык"
        positions.append({
            "position_key": position_key(doc_a, doc_b, "языковые", skill, label),
            "feature_key_a": None, "feature_key_b": None,
            "group_name": "языковые", "subgroup": skill, "label": label,
            "value_a": a["value"], "value_b": b["value"],
            "fragment_a": None, "fragment_b": None,
            "match_type": verdict,
        })
    return positions


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

    # Общие признаки (степени навыков) — сопоставляются всегда, с допусками
    # Минюста; вердикты идут отдельными позициями.
    gen_positions = general_positions(pdb, doc_a, doc_b)
    positions += gen_positions

    inserted, confirmed_kept = pdb.replace_auto_comparisons(
        project_id, doc_a, doc_b, positions)
    pdb.log_action(
        "сравнительное исследование: авто-сопоставление", project_id=project_id,
        details={"pair_doc_a": doc_a, "pair_doc_b": doc_b,
                 "позиций_всего": len(positions), "вставлено_авто": inserted,
                 "сохранено_подтверждённых": confirmed_kept,
                 "признаков_спорного": len(fa), "признаков_образца": len(fb),
                 "общих_признаков": {p["subgroup"]: p["match_type"]
                                     for p in gen_positions}},
        program_version=program_version)
    return {"positions": len(positions), "inserted_auto": inserted,
            "confirmed_kept": confirmed_kept,
            "general": {p["subgroup"]: p["match_type"] for p in gen_positions}}


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
    general: dict[str, str] = {}
    coincidence_by_category: dict[str, int] = {}
    for r in rows:
        if r["match_type"] in GEN_TYPES:
            # Общие признаки — отдельная секция, в счёт позиций/уровней не идут.
            general[r["subgroup"] or "?"] = r["match_type"]
            continue
        st[r["match_type"]] = st.get(r["match_type"], 0) + 1
        if r["status"] == STATUS_CONFIRMED:
            st["подтверждено"] += 1
            if r["level"]:
                st[f"уровень_{r['level']}"] += 1
            if r["match_type"] == MATCH_COINCIDENCE:
                key = category_key(r["group_name"], r["subgroup"])
                coincidence_by_category[key] = coincidence_by_category.get(key, 0) + 1

    st["общие_признаки"] = general
    st["порог_методики"] = MIN_FEATURES_FOR_CONCLUSION
    st["до_порога"] = max(0, MIN_FEATURES_FOR_CONCLUSION - st["подтверждено"])

    # Покатегорийная разбивка подтверждённых совпадений против обоих порогов
    # (Моисеева/Огорелков, 2021, с. 89–93). Суммарный ≥20 (Рубцова, с. 85)
    # сохраняется рядом — это дополнение, не замена.
    breakdown = {}
    for key, cat_min in CATEGORY_MIN_CATEGORICAL.items():
        have = coincidence_by_category.get(key, 0)
        breakdown[key] = {
            "есть": have,
            "мин_категорический": cat_min,
            "мин_вероятный": category_min_probable(cat_min),
            "категорический_ок": have >= cat_min,
            "вероятный_ок": have >= category_min_probable(cat_min),
        }
    st["разбивка_по_категориям"] = breakdown
    st["недобор_категорический"] = [k for k, v in breakdown.items()
                                    if not v["категорический_ок"]]
    st["недобор_вероятный"] = [k for k, v in breakdown.items()
                               if not v["вероятный_ок"]]

    st["blocks_strong_conclusion"] = pair_blocks_strong_conclusion(
        pdb, project_id, doc_a, doc_b)
    return st
