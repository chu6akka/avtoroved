"""
protocol/conclusion.py — стадия 4: оценка результатов и вывод (Рубцова 2007).

Авто-рекомендация формы вывода по правилу методики (с.85–86) поверх
ПОДТВЕРЖДЁННЫХ экспертом позиций сравнительного исследования:

  • различие на уровне НН            → категорический отрицательный;
  • различия на НС и/или НСВ         → вероятный отрицательный;
  • совпадения на всех трёх уровнях, нет значимых различий и
    ≥ MIN_FEATURES_FOR_CONCLUSION признаков → категорический положительный;
  • совпадения только на НН и НС     → вероятный положительный;
  • данных недостаточно              → НПВ (не представляется возможным).

Флаг blocks_strong_conclusion из стадии пригодности ДЕГРАДИРУЕТ категорические
формы до вероятных. Рекомендация — только подсказка: форму вывода фиксирует
эксперт; несогласие с рекомендацией требует письменного обоснования.
Решения хранятся append-only (conclusion_decisions) + текущее (conclusions).
"""
from __future__ import annotations

from typing import Any, Optional

from protocol import db as protocol_db
from protocol import comparison as cmp

# ── Формы вывода ─────────────────────────────────────────────────────────────
FORM_POS_CATEGORICAL = "категорический_положительный"
FORM_POS_PROBABLE = "вероятный_положительный"
FORM_NEG_CATEGORICAL = "категорический_отрицательный"
FORM_NEG_PROBABLE = "вероятный_отрицательный"
FORM_NPV = "НПВ"    # решить вопрос не представляется возможным

FORMS = (FORM_POS_CATEGORICAL, FORM_POS_PROBABLE,
         FORM_NEG_CATEGORICAL, FORM_NEG_PROBABLE, FORM_NPV)

FORM_LABELS = {
    FORM_POS_CATEGORICAL: "Категорический положительный (тексты написаны одним лицом)",
    FORM_POS_PROBABLE: "Вероятный положительный (вероятно, одним лицом)",
    FORM_NEG_CATEGORICAL: "Категорический отрицательный (разными лицами)",
    FORM_NEG_PROBABLE: "Вероятный отрицательный (вероятно, разными лицами)",
    FORM_NPV: "Не представляется возможным (НПВ)",
}

# Типы позиций, считающиеся различием при подтверждении экспертом.
_DIFF_TYPES = (cmp.MATCH_DIFFERENCE, cmp.MATCH_ONLY_A, cmp.MATCH_ONLY_B)


def _level_breakdown(pdb: "protocol_db.ProtocolDB",
                     doc_a: int, doc_b: int) -> dict:
    """Подтверждённые позиции пары: совпадения/различия по уровням НН/НС/НСВ."""
    coin = {lv: 0 for lv in cmp.LEVELS}
    diff = {lv: 0 for lv in cmp.LEVELS}
    coin_nolevel = diff_nolevel = 0
    total_confirmed = 0
    for r in pdb.fetch_comparisons(doc_a, doc_b):
        if r["status"] != cmp.STATUS_CONFIRMED:
            continue
        total_confirmed += 1
        lv = r["level"] or ""
        if r["match_type"] == cmp.MATCH_COINCIDENCE:
            if lv in coin:
                coin[lv] += 1
            else:
                coin_nolevel += 1
        elif r["match_type"] in _DIFF_TYPES:
            if lv in diff:
                diff[lv] += 1
            else:
                diff_nolevel += 1
    return {
        "coincidence": coin, "difference": diff,
        "coincidence_nolevel": coin_nolevel, "difference_nolevel": diff_nolevel,
        "total_confirmed": total_confirmed,
        "total_coincidence": sum(coin.values()) + coin_nolevel,
        "total_difference": sum(diff.values()) + diff_nolevel,
    }


def recommend(pdb: "protocol_db.ProtocolDB", project_id: int,
              doc_a: int, doc_b: int) -> tuple[str, list[str], dict]:
    """
    Авто-рекомендация формы вывода по правилу Рубцовой (с.85–86).
    Возвращает (форма, обоснование по пунктам, breakdown-словарь).
    """
    bd = _level_breakdown(pdb, doc_a, doc_b)
    blocks = cmp.pair_blocks_strong_conclusion(pdb, project_id, doc_a, doc_b)
    bd["blocks_strong_conclusion"] = blocks
    reasons: list[str] = []
    coin, diff = bd["coincidence"], bd["difference"]

    if bd["total_confirmed"] == 0:
        reasons.append("Нет ни одной подтверждённой экспертом позиции сравнения — "
                       "оценка результатов невозможна.")
        return FORM_NPV, reasons, bd

    # 1) Различие на НН — самый сильный сигнал (с.85).
    if diff["НН"] > 0:
        reasons.append(f"Выявлены различия на уровне НН (набор норм): {diff['НН']} — "
                       "по методике это основание категорического отрицательного вывода.")
        form = FORM_NEG_CATEGORICAL
        if blocks:
            reasons.append("Категорическая форма ЗАБЛОКИРОВАНА стадией пригодности "
                           "(blocks_strong_conclusion=1) — форма понижена до вероятной.")
            form = FORM_NEG_PROBABLE
        return form, reasons, bd

    # 2) Различия на НС/НСВ (или без уровня) → вероятный отрицательный.
    if bd["total_difference"] > 0:
        parts = [f"НС: {diff['НС']}", f"НСВ: {diff['НСВ']}"]
        if bd["difference_nolevel"]:
            parts.append(f"без уровня: {bd['difference_nolevel']}")
        reasons.append("Выявлены различия (" + ", ".join(parts) + ") при отсутствии "
                       "различий на НН — вероятный отрицательный вывод.")
        return FORM_NEG_PROBABLE, reasons, bd

    # 3) Только совпадения.
    all_levels = all(coin[lv] > 0 for lv in cmp.LEVELS)
    enough = bd["total_coincidence"] >= cmp.MIN_FEATURES_FOR_CONCLUSION
    reasons.append(
        f"Значимых различий не выявлено; совпадений {bd['total_coincidence']} "
        f"(НН: {coin['НН']}, НС: {coin['НС']}, НСВ: {coin['НСВ']}"
        + (f", без уровня: {bd['coincidence_nolevel']}" if bd["coincidence_nolevel"] else "")
        + ").")

    if all_levels and enough:
        reasons.append(f"Совпадения на всех трёх уровнях и достигнут методический порог "
                       f"≥{cmp.MIN_FEATURES_FOR_CONCLUSION} — категорический положительный вывод.")
        form = FORM_POS_CATEGORICAL
        if blocks:
            reasons.append("Категорическая форма ЗАБЛОКИРОВАНА стадией пригодности — "
                           "форма понижена до вероятной.")
            form = FORM_POS_PROBABLE
        return form, reasons, bd

    if not all_levels:
        missing = [lv for lv in cmp.LEVELS if coin[lv] == 0]
        reasons.append(f"Совпадения не охватывают все уровни (нет: {', '.join(missing)}) — "
                       "категорическая форма недоступна, вероятный положительный вывод.")
    if not enough:
        reasons.append(f"Порог ≥{cmp.MIN_FEATURES_FOR_CONCLUSION} не достигнут "
                       f"({bd['total_coincidence']}) — категорическая форма недоступна.")
    return FORM_POS_PROBABLE, reasons, bd


def decide(
    pdb: "protocol_db.ProtocolDB",
    project_id: int,
    doc_a: int,
    doc_b: int,
    form: str,
    justification: str = "",
    program_version: Optional[str] = None,
) -> dict:
    """
    Зафиксировать форму вывода. Если форма отличается от авто-рекомендации,
    обоснование обязательно. Пишет append-only + audit_log.
    """
    if form not in FORMS:
        raise ValueError(f"Недопустимая форма вывода: {form}")
    rec_form, rec_reasons, bd = recommend(pdb, project_id, doc_a, doc_b)
    if form != rec_form and not justification.strip():
        raise ValueError(
            "Форма вывода отличается от рекомендации методики "
            f"({rec_form}) — требуется письменное обоснование эксперта.")
    pdb.record_conclusion(
        project_id, doc_a, doc_b, form,
        justification=justification, recommended_form=rec_form,
        stats_snapshot=bd, program_version=program_version)
    pdb.log_action(
        "зафиксирован вывод по паре", project_id=project_id,
        details={"pair_doc_a": doc_a, "pair_doc_b": doc_b,
                 "форма": form, "рекомендация": rec_form,
                 "совпадение_с_рекомендацией": form == rec_form,
                 "обоснование": justification or None},
        program_version=program_version)
    return {"form": form, "recommended": rec_form, "breakdown": bd}
