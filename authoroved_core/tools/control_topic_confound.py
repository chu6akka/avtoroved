"""Пригодность признаков на парах, где тема групп не различает.

Замер тематического смешения (`measure_topic_overlap`) на корпусе Pilot 02
дал 0,7797 при пороге 0,5897 — выше, чем разделение у любого признака.
Значит, объяснять разделение признаков темой есть чем, и таблицу
пригодности в исходном виде читать нельзя.

Здесь смешение устраняется отбором, а не поправкой. Берутся только те пары,
у которых общих меток нет вовсе, — в обеих группах. На такой подвыборке доля
общих меток одинакова (нулевая) и у пар одного автора, и у пар разных, то
есть тема группы не различает по построению. Разделение, которое на ней
остаётся, теме приписать уже нельзя.

Платой служит объём: пар становится меньше, порог случайного разброса растёт,
и часть признаков его не проходит. Это не ухудшение признаков, а снятие
завышения.

Новых разборов текста не требуется: берутся отчёт проверки признаков с
расстояниями по каждой паре и отчёт по меткам, связываются по `case_id`.

Выводов об авторстве отсюда не следует, и в дело результат не входит.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from authoroved_core.tools.validate_features_on_blind_pairs import (
    DIFFERENT, SAME, separation, significance_threshold, summarize,
)


def load_report(path: Path, what: str) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Не найден отчёт {what}: {path}.")
    report = json.loads(path.read_text(encoding="utf-8"))
    if "per_case" not in report:
        raise ValueError(
            f"В отчёте {path} нет разбора по парам (`per_case`): "
            "нужен полный отчёт прогона, а не сводка."
        )
    return report


def overlap_by_case(topics: dict) -> dict[str, float]:
    return {item["case_id"]: item["overlap"] for item in topics["per_case"]}


def select_topic_neutral(features: dict, overlaps: dict[str, float],
                         max_overlap: float = 0.0) -> tuple[list[dict], list[str]]:
    """Пары без общих меток; пары с неизвестными метками исключаются.

    Пара, для которой меток нет, не нейтральна по теме — про неё просто
    ничего не известно, поэтому она не годится ни туда, ни сюда.
    """
    kept, unknown = [], []
    for case in features["per_case"]:
        value = overlaps.get(case["case_id"])
        if value is None:
            unknown.append(case["case_id"])
            continue
        if value <= max_overlap:
            kept.append(case)
    return kept, unknown


def residual_topic_separation(kept: list[dict], overlaps: dict[str, float]) -> float | None:
    """Разделение по теме на отобранной подвыборке; должно быть ровно 0,5."""
    same = [overlaps[case["case_id"]] for case in kept if case["relation"] == SAME]
    different = [overlaps[case["case_id"]] for case in kept if case["relation"] == DIFFERENT]
    return separation(different, same)


def compare(before: dict, after: dict) -> dict:
    """Разделение до и после отбора по каждому признаку."""
    rows = {}
    for name in sorted(set(before) | set(after)):
        left, right = before.get(name, {}), after.get(name, {})
        rows[name] = {
            "separation_all_pairs": left.get("separation"),
            "above_chance_all_pairs": left.get("above_chance"),
            "separation_topic_neutral": right.get("separation"),
            "significance_threshold": right.get("significance_threshold"),
            "above_chance_topic_neutral": right.get("above_chance"),
            "same_pairs": right.get("same_pairs"),
            "different_pairs": right.get("different_pairs"),
        }
    return dict(sorted(rows.items(),
                       key=lambda item: (item[1]["separation_topic_neutral"] is None,
                                         -(item[1]["separation_topic_neutral"] or 0))))


def control(features: dict, topics: dict, max_overlap: float = 0.0) -> dict:
    overlaps = overlap_by_case(topics)
    kept, unknown = select_topic_neutral(features, overlaps, max_overlap)
    same = sum(case["relation"] == SAME for case in kept)
    different = sum(case["relation"] == DIFFERENT for case in kept)
    return {
        "kind": ("Пригодность признаков на парах без общих тематических меток; "
                 "не оценка авторства"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "max_overlap": max_overlap,
        "pairs_before": len(features["per_case"]),
        "pairs_kept": len(kept),
        "same_pairs": same,
        "different_pairs": different,
        "pairs_without_known_tags": len(unknown),
        "topic_separation_before": topics.get("topic_separation"),
        "topic_separation_after": residual_topic_separation(kept, overlaps),
        "significance_threshold": significance_threshold(same, different),
        "by_feature": compare(features.get("by_feature", {}), summarize(kept)),
        "measure": ("Та же мера, что и в проверке признаков, на подвыборке, где "
                    "тема групп не различает. Порогов отсюда не выводится."),
    }


def print_report(report: dict) -> None:
    print(f"\nпар было {report['pairs_before']}, осталось {report['pairs_kept']} "
          f"(один автор {report['same_pairs']}, разные {report['different_pairs']})")
    if report["pairs_without_known_tags"]:
        print(f"пар с неизвестными метками, исключено: {report['pairs_without_known_tags']}")
    print(f"тематическое разделение было {report['topic_separation_before']}, "
          f"стало {report['topic_separation_after']}")
    print(f"порог случайного разброса на этой подвыборке: {report['significance_threshold']}\n")
    print(f"  {'признак':10} {'все пары':>10} {'без общих тем':>15}")
    for name, row in report["by_feature"].items():
        after = row["separation_topic_neutral"]
        mark = "" if after is None else ("   +" if row["above_chance_topic_neutral"]
                                         else "   <-- порог не пройден")
        print(f"  {name:10} {str(row['separation_all_pairs'] or '—'):>10} "
              f"{str(after or '—'):>15}{mark}")
    print("\nЧто осталось выше порога, то теме приписать нельзя. "
          "Это проверка пригодности\nпризнаков, а не вывод об авторстве: "
          "порогов отсюда не выводится.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", type=Path,
                        default=Path("authoroved_core/artifacts/feature_validity.json"),
                        help="полный отчёт проверки признаков с разбором по парам")
    parser.add_argument("--topics", type=Path,
                        default=Path("authoroved_core/artifacts/topic_overlap.json"),
                        help="отчёт замера тематического смешения")
    parser.add_argument("--max-overlap", type=float, default=0.0,
                        help="наибольшая допустимая доля общих меток; 0 — общих меток нет")
    parser.add_argument("--output", type=Path,
                        default=Path("authoroved_core/artifacts/feature_validity_topic_neutral.json"))
    args = parser.parse_args()

    report = control(load_report(args.features, "проверки признаков"),
                     load_report(args.topics, "замера меток"),
                     args.max_overlap)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print_report(report)
    print(f"\nотчёт: {args.output}")


if __name__ == "__main__":
    main()
