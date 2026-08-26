"""Стадия 4: нейтральный методический контроль и решение эксперта.

Модуль предъявляет наблюдаемые условия, но никогда не выбирает и не
рекомендует форму вывода об авторстве. Форму и обоснование определяет эксперт.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from protocol import comparison as cmp
from protocol import db as protocol_db

FORM_POS_CATEGORICAL = "категорический_положительный"
FORM_POS_PROBABLE = "вероятный_положительный"
FORM_NEG_CATEGORICAL = "категорический_отрицательный"
FORM_NEG_PROBABLE = "вероятный_отрицательный"
FORM_NPV = "НПВ"

FORMS = (FORM_POS_CATEGORICAL, FORM_POS_PROBABLE,
         FORM_NEG_CATEGORICAL, FORM_NEG_PROBABLE, FORM_NPV)

FORM_LABELS = {
    FORM_POS_CATEGORICAL: "Категорический положительный (тексты написаны одним лицом)",
    FORM_POS_PROBABLE: "Вероятный положительный (вероятно, одним лицом)",
    FORM_NEG_CATEGORICAL: "Категорический отрицательный (разными лицами)",
    FORM_NEG_PROBABLE: "Вероятный отрицательный (вероятно, разными лицами)",
    FORM_NPV: "Не представляется возможным (НПВ)",
}

_DIFF_TYPES = (cmp.MATCH_DIFFERENCE, cmp.MATCH_ONLY_A, cmp.MATCH_ONLY_B)
_ID_KEYS = ("низкая", "средняя", "высокая", "без оценки")


def _level_breakdown(pdb: "protocol_db.ProtocolDB", doc_a: int, doc_b: int) -> dict:
    coin = {level: 0 for level in cmp.LEVELS}
    diff = {level: 0 for level in cmp.LEVELS}
    coin_nolevel = 0
    diff_nolevel = 0
    total_confirmed = 0
    for row in pdb.fetch_comparisons(doc_a, doc_b):
        if row["match_type"] in cmp.GEN_TYPES or row["status"] != cmp.STATUS_CONFIRMED:
            continue
        if not cmp.position_is_countable(pdb, row):
            continue
        total_confirmed += 1
        level = row["level"] or ""
        target = coin if row["match_type"] == cmp.MATCH_COINCIDENCE else (
            diff if row["match_type"] in _DIFF_TYPES else None)
        if target is coin:
            if level in coin:
                coin[level] += 1
            else:
                coin_nolevel += 1
        elif target is diff:
            if level in diff:
                diff[level] += 1
            else:
                diff_nolevel += 1
    return {
        "coincidence": coin, "difference": diff,
        "total_confirmed": total_confirmed,
        "coincidence_nolevel": coin_nolevel,
        "difference_nolevel": diff_nolevel,
        "total_coincidence": sum(coin.values()) + coin_nolevel,
        "total_difference": sum(diff.values()) + diff_nolevel,
        "levels_with_coincidence": [lv for lv, count in coin.items() if count],
        "levels_with_difference": [lv for lv, count in diff.items() if count],
    }


def _significance_counts(rows: list, match_types: tuple[str, ...]) -> dict[str, int]:
    result = {key: 0 for key in _ID_KEYS}
    for row in rows:
        if row["status"] != cmp.STATUS_CONFIRMED or row["match_type"] not in match_types:
            continue
        result[row["identification_value"] or "без оценки"] += 1
    return result


def _load_json(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def methodological_checks(
    pdb: "protocol_db.ProtocolDB", project_id: int, doc_a: int, doc_b: int,
) -> dict[str, Any]:
    """Вернуть только наблюдения и формализованные проверки для эксперта."""
    all_rows = list(pdb.fetch_comparisons(doc_a, doc_b))
    rows = [row for row in all_rows
            if row["match_type"] in cmp.GEN_TYPES
            or cmp.position_is_countable(pdb, row)]
    rubtsova = _level_breakdown(pdb, doc_a, doc_b)

    skill_rows = [row for row in rows if row["match_type"] in cmp.GEN_TYPES]
    skills = {row["subgroup"] or row["label"]: {
        "condition": row["match_type"], "disputed": row["value_a"],
        "sample": row["value_b"],
    } for row in skill_rows}
    vula_hits = [row["subgroup"] for row in skill_rows
                 if row["match_type"] == cmp.GEN_HIGHER
                 and (row["subgroup"] or "") in cmp.VUL_DECISIVE_SKILLS]
    vula_note = (
        "Показано выполнение или невыполнение формализованного условия правила Вула. "
        "Экспертная оценка и вывод программой не формулируются."
    )

    by_category: dict[str, dict] = {}
    for key in cmp.CATEGORY_MIN_CATEGORICAL:
        cat_rows = [row for row in rows
                    if row["match_type"] not in cmp.GEN_TYPES
                    and cmp.category_key(row["group_name"], row["subgroup"]) == key]
        coincidence = _significance_counts(cat_rows, (cmp.MATCH_COINCIDENCE,))
        difference = _significance_counts(cat_rows, _DIFF_TYPES)
        by_category[key] = {
            "coincidence": sum(coincidence.values()),
            "difference": sum(difference.values()),
            "coincidence_by_identification_value": coincidence,
            "difference_by_identification_value": difference,
            "high_identification_value_coincidence": coincidence["высокая"],
        }

    categorical_met = [key for key, values in by_category.items()
                       if values["high_identification_value_coincidence"] >=
                       cmp.CATEGORY_MIN_CATEGORICAL[key]]
    probable_met = [key for key, values in by_category.items()
                    if values["high_identification_value_coincidence"] >=
                    cmp.CATEGORY_MIN_PROBABLE[key]]

    coincidences_by_category = {}
    differences_by_category = {}
    for key, values in by_category.items():
        high_coincidences = values["high_identification_value_coincidence"]
        total_differences = values["difference"]
        coincidences_by_category[key] = {
            "actual_count": values["coincidence"],
            "high_identification_value_count": high_coincidences,
            "categorical": {
                "reference_minimum": cmp.CATEGORY_MIN_CATEGORICAL[key],
                "condition_met": high_coincidences >= cmp.CATEGORY_MIN_CATEGORICAL[key],
            },
            "probable": {
                "reference_minimum": cmp.CATEGORY_MIN_PROBABLE[key],
                "condition_met": high_coincidences >= cmp.CATEGORY_MIN_PROBABLE[key],
            },
        }
        differences_by_category[key] = {
            "actual_count": total_differences,
            "probable_negative": {
                "reference_minimum": cmp.CATEGORY_MIN_PROBABLE_NEGATIVE[key],
                "condition_met": total_differences >= cmp.CATEGORY_MIN_PROBABLE_NEGATIVE[key],
            },
        }

    difference_counts_ru = _significance_counts(rows, _DIFF_TYPES)
    difference_significance_counts = {
        "low": difference_counts_ru["низкая"],
        "medium": difference_counts_ru["средняя"],
        "high": difference_counts_ru["высокая"],
        "unset": difference_counts_ru["без оценки"],
        "total": sum(difference_counts_ru.values()),
    }
    observed_conditions = {
        "no_differences": difference_significance_counts["total"] == 0,
        "low_differences_not_more_than_3": difference_significance_counts["low"] <= 3,
        "high_differences_at_least_5": difference_significance_counts["high"] >= 5,
    }

    suitability = {"warnings": [], "methodological": [], "instrumental": []}
    for row in pdb.fetch_suitability(project_id):
        pair_hit = row["pair_doc_a"] == doc_a and row["pair_doc_b"] == doc_b
        doc_hit = row["document_id"] in (doc_a, doc_b)
        if not (pair_hit or doc_hit):
            continue
        for flag in _load_json(row["flags"], []):
            message = flag.get("message", str(flag)) if isinstance(flag, dict) else str(flag)
            target = "instrumental" if isinstance(flag, dict) and flag.get("code") == "извлечение" \
                else "methodological"
            suitability[target].append(message)
        if row["verdict"] != "пригоден":
            suitability["warnings"].append(row["verdict"])
        if row["blocks_strong_conclusion"]:
            suitability["warnings"].append(
                "На стадии оценки пригодности зафиксированы ограничения материала; "
                "их влияние на исследование и форму вывода оценивает эксперт")

    result = {
        "rubtsova": rubtsova,
        "vula": {
            "skills": skills,
            "condition_higher_in_disputed": vula_hits,
            "condition_met": bool(vula_hits),
            "note": vula_note,
        },
        "moiseeva_ogorelkov": {
            "coincidences_by_category": coincidences_by_category,
            "differences_by_category": differences_by_category,
            "reference_coincidence_thresholds": {
                "categorical": dict(cmp.CATEGORY_MIN_CATEGORICAL),
                "probable": dict(cmp.CATEGORY_MIN_PROBABLE),
            },
            "reference_difference_thresholds": {
                "probable_negative": dict(cmp.CATEGORY_MIN_PROBABLE_NEGATIVE),
            },
            "difference_significance_counts": difference_significance_counts,
            "observed_conditions": observed_conditions,
            # Совместимые поля для ранее созданного UI/снимков.
            "by_category": by_category,
            "categorical_reference_thresholds": dict(cmp.CATEGORY_MIN_CATEGORICAL),
            "probable_reference_thresholds": dict(cmp.CATEGORY_MIN_PROBABLE),
            "categorical_thresholds_met": categorical_met,
            "categorical_thresholds_not_met": [k for k in by_category if k not in categorical_met],
            "probable_thresholds_met": probable_met,
            "probable_thresholds_not_met": [k for k in by_category if k not in probable_met],
        },
        "suitability": suitability,
    }
    assert "recommended_form" not in result
    return result


def decide(
    pdb: "protocol_db.ProtocolDB", project_id: int, doc_a: int, doc_b: int,
    form: str, justification: str = "", program_version: Optional[str] = None,
) -> dict:
    """Зафиксировать самостоятельное решение эксперта (append-only)."""
    if form not in FORMS:
        raise ValueError(f"Недопустимая форма вывода: {form}")
    snapshot = methodological_checks(pdb, project_id, doc_a, doc_b)
    pdb.record_conclusion(
        project_id, doc_a, doc_b, form, justification=justification,
        recommended_form=None, stats_snapshot=snapshot,
        program_version=program_version)
    pdb.log_action(
        "зафиксирован вывод по паре", project_id=project_id,
        details={"pair_doc_a": doc_a, "pair_doc_b": doc_b,
                 "выбранная_экспертом_форма": form,
                 "обоснование": justification,
                 "methodological_checks": snapshot,
                 "program_version": program_version},
        program_version=program_version)
    return {"form": form, "methodological_checks": snapshot}
