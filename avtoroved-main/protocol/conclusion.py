"""
protocol/conclusion.py — стадия 4: оценка результатов и вывод (Рубцова 2007).

Авто-рекомендация формы вывода поверх ПОДТВЕРЖДЁННЫХ экспертом позиций
сравнительного исследования и объективных общих признаков:

  • решающее правило Вула: грамматический и/или лексико-фразеологический
    навык в спорном тексте ВЫШЕ, чем в образце, за пределами допуска
    → категорический отрицательный [Минюст, с. 19; Вул 2007, с. 38];
    орфографический и пунктуационный навыки в правиле НЕ участвуют
    (ненадёжны при автокоррекции цифровых текстов);
  • различие на уровне НН            → категорический отрицательный;
  • различия на НС и/или НСВ         → вероятный отрицательный;
  • совпадения на всех трёх уровнях, ≥ MIN_FEATURES_FOR_CONCLUSION
    признаков суммарно И покатегорийные минимумы Огорелкова
    → категорический положительный;
  • половинные покатегорийные пороги → вероятный положительный;
  • пороги не добраны / данных нет   → НПВ (не представляется возможным).

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
    su = cmp.pair_suitability_status(pdb, project_id, doc_a, doc_b)
    # Стадийность: непроведённая пригодность блокирует категорические формы
    # так же, как ограничения из проведённой стадии.
    blocks = su["blocks"] or not su["has_rows"]
    bd["blocks_strong_conclusion"] = blocks
    bd["suitability_done"] = su["has_rows"]
    gsv = cmp.general_skill_verdicts(pdb, doc_a, doc_b)
    buckets = cmp.bucket_breakdown(pdb, doc_a, doc_b)
    bd["general_verdicts"] = {s: v["verdict"] for s, v in gsv.items()}
    bd["buckets"] = buckets
    reasons: list[str] = []
    coin, diff = bd["coincidence"], bd["difference"]

    # 00) Непригодный объект: исследование по паре не проводится (методика —
    # непригодность основания для НПВ, а не для смягчения формы).
    if su["unfit"]:
        reasons.append("Объект пары признан непригодным на стадии пригодности — "
                       "идентификационное исследование по паре не проводится, "
                       "вывод: не представляется возможным.")
        return FORM_NPV, reasons, bd
    if not su["has_rows"]:
        reasons.append("Стадия оценки пригодности по паре НЕ ПРОВОДИЛАСЬ — "
                       "категорические формы недоступны до её проведения "
                       "(вкладка «Пригодность»).")

    # 0) Решающее правило Вула [Минюст, с. 19; Вул 2007, с. 38]: степень
    # развития грамматического и/или лексико-фразеологического навыка в
    # спорном тексте выше, чем в образце, за пределами допуска. Работает по
    # объективным общим признакам, подтверждения позиций не требует.
    # Орфографический и пунктуационный навыки не участвуют (автокоррекция).
    vul_hits = [(s, gsv[s]) for s in ("грамматический", "лексико-фразеологический")
                if s in gsv and gsv[s]["verdict"] == cmp.GENERAL_VERDICT_HIGHER_A]
    if vul_hits:
        for skill, v in vul_hits:
            reasons.append(
                f"Решающее правило Вула: {skill} навык в спорном тексте выше, "
                f"чем в образце ({v['rate_a']} против {v['rate_b']} ошибок на "
                f"200 словоформ; дельта {v['delta']}, допуск ±{v['tolerance']:g}) "
                f"— основание категорического отрицательного вывода "
                f"[Минюст, с. 19; Вул 2007, с. 38].")
        form = FORM_NEG_CATEGORICAL
        if blocks:
            reasons.append("Категорическая форма ЗАБЛОКИРОВАНА стадией пригодности "
                           "(blocks_strong_conclusion=1) — форма понижена до вероятной.")
            form = FORM_NEG_PROBABLE
        return form, reasons, bd

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

    # 3) Только совпадения: суммарный порог Рубцовой (с.85) + покатегорийные
    # минимумы Огорелкова (2021, с. 89–93 [сверить]) — дополнение, не замена.
    all_levels = all(coin[lv] > 0 for lv in cmp.LEVELS)
    enough = bd["total_coincidence"] >= cmp.MIN_FEATURES_FOR_CONCLUSION
    buckets_categorical = all(b["meets_categorical"] for b in buckets)
    buckets_probable = all(b["meets_probable"] for b in buckets)
    reasons.append(
        f"Значимых различий не выявлено; совпадений {bd['total_coincidence']} "
        f"(НН: {coin['НН']}, НС: {coin['НС']}, НСВ: {coin['НСВ']}"
        + (f", без уровня: {bd['coincidence_nolevel']}" if bd["coincidence_nolevel"] else "")
        + ").")

    if all_levels and enough and buckets_categorical:
        reasons.append(f"Совпадения на всех трёх уровнях, достигнуты методический порог "
                       f"≥{cmp.MIN_FEATURES_FOR_CONCLUSION} и покатегорийные минимумы "
                       f"— категорический положительный вывод.")
        form = FORM_POS_CATEGORICAL
        if blocks:
            reasons.append("Категорическая форма ЗАБЛОКИРОВАНА стадией пригодности — "
                           "форма понижена до вероятной.")
            form = FORM_POS_PROBABLE
        return form, reasons, bd

    if not all_levels:
        missing = [lv for lv in cmp.LEVELS if coin[lv] == 0]
        reasons.append(f"Совпадения не охватывают все уровни (нет: {', '.join(missing)}) — "
                       "категорическая форма недоступна.")
    if not enough:
        reasons.append(f"Порог ≥{cmp.MIN_FEATURES_FOR_CONCLUSION} не достигнут "
                       f"({bd['total_coincidence']}) — категорическая форма недоступна.")
    if not buckets_categorical:
        short = [f"{b['bucket']}: {b['confirmed']}/{b['threshold_categorical']}"
                 for b in buckets if not b["meets_categorical"]]
        reasons.append("Покатегорийные минимумы категорического вывода не достигнуты "
                       "(Моисеева/Огорелков): " + "; ".join(short) + ".")

    if buckets_probable:
        return FORM_POS_PROBABLE, reasons, bd

    short_prob = [f"{b['bucket']}: {b['confirmed']}/{b['threshold_probable']}"
                  for b in buckets if not b["meets_probable"]]
    reasons.append("Не достигнуты и половинные покатегорийные пороги вероятного "
                   "вывода: " + "; ".join(short_prob) +
                   " — рекомендуется НПВ (совокупность совпадений недостаточна).")
    return FORM_NPV, reasons, bd


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
