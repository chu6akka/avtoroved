"""Стадия S4 — оценка совокупности признаков и формулирование вывода (с. 85–86).

Правило методики:
  • различие на уровне НН (разные наборы норм) → категорический отрицательный;
  • совпадения высокоинформативных признаков на всех трёх уровнях, ≥20 таких
    признаков и отсутствие значимых различий → категорический положительный;
  • различия и на НСВ, и на НС → вероятный отрицательный;
  • совпадения на НН и НС, но НСВ почти не проявляется → вероятный положительный
    («нельзя исключить»);
  • иначе — решить не представляется возможным.
"""
from __future__ import annotations

from aved.core.models import Comparison, Level, Verdict, VerdictType


def decide(comparison: Comparison, min_high: int = 20) -> Verdict:
    nn = comparison.levels[Level.NN]
    ns = comparison.levels[Level.NS]
    nsv = comparison.levels[Level.NSV]

    matching_high = comparison.total_matching_high()
    differing_high = comparison.total_differing_high()
    lv_match = comparison.levels_with_matches()
    lv_diff = comparison.levels_with_differences()

    rationale: list[str] = []

    def make(vt: VerdictType) -> Verdict:
        return Verdict(
            type=vt,
            rationale=rationale,
            matching_high_count=matching_high,
            differing_high_count=differing_high,
            levels_with_matches=lv_match,
            levels_with_differences=lv_diff,
        )

    # 1. Различие на уровне НН → категорический отрицательный.
    if comparison.nn_norm_conflict:
        rationale.append(
            "Различие на уровне НН (наборов норм): " + comparison.nn_conflict_reason
            + ". По методике этого достаточно для категорического отрицательного вывода."
        )
        return make(VerdictType.CATEGORICAL_NEGATIVE)

    all_levels_match = nn.has_matches and ns.has_matches and nsv.has_matches

    # 2. Категорический положительный.
    if all_levels_match and matching_high >= min_high and differing_high == 0:
        rationale.append(
            f"Последовательные совпадения на всех трёх уровнях (НН, НС, НСВ); "
            f"высокоинформативных совпадений: {matching_high} (≥{min_high}); "
            f"значимых различий нет."
        )
        return make(VerdictType.CATEGORICAL_POSITIVE)

    # 3. Различия и на НСВ, и на НС → вероятный отрицательный.
    if nsv.has_differences and ns.has_differences:
        rationale.append(
            f"Различия наблюдаются и на уровне НСВ ({len(nsv.differing)}), "
            f"и на уровне НС ({len(ns.differing)}). Это основание для отрицательного "
            "вывода в вероятной форме."
        )
        return make(VerdictType.PROBABLE_NEGATIVE)

    # 4. Совпадения на НН и НС, НСВ слабо → вероятный положительный / «не исключается».
    if nn.has_matches and ns.has_matches:
        reason = "НСВ почти не проявляется" if not nsv.has_matches else (
            f"высокоинформативных совпадений {matching_high} (меньше порога {min_high})"
        )
        rationale.append(
            f"Совпадения на уровнях НН и НС; {reason}. Вывод — вероятный положительный "
            "(«нельзя исключить из круга возможных авторов»)."
        )
        return make(VerdictType.PROBABLE_POSITIVE)

    # 5. Иначе — решить не представляется возможным.
    rationale.append(
        "Совокупность признаков недостаточна для категорического или вероятного вывода."
    )
    return make(VerdictType.INCONCLUSIVE)
