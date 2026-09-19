"""Замер тематического смешения в слепых парах.

Проверка пригодности признаков (`validate_features_on_blind_pairs`) показала,
что расстояния между текстами разных авторов больше, чем между текстами
одного. Само по себе это ещё не говорит, что различает признак: тексты одного
автора на пользовательской площадке чаще посвящены одной теме, тексты разных
авторов — разным. Часть измеренного разделения может относиться к предмету
речи.

Здесь измеряется размер самой этой угрозы. Тема берётся не из текста, а из
меток, которые автор поставил публикации сам: они сохранены в `manifest.csv`
при сборке корпуса. Для каждой пары считается доля общих меток (пересечение,
делённое на объединение), затем сравниваются две группы пар — «один автор» и
«разные авторы».

Мера та же, что и в проверке признаков, и читается так же: доля случаев,
в которых у пары одного автора меток общего больше, чем у пары разных.
0,50 означает, что по тематике группы не различаются и объяснять разделение
признаков темой нечем. Значение заметно выше 0,50 означает, что тексты одного
автора в этом корпусе действительно ближе по теме, и тогда полученные ранее
значения признаков — верхняя оценка их пригодности, а не сама пригодность.

Выводов об авторстве отсюда не следует, и в дело результат не входит.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import median

from authoroved_core.tools.validate_features_on_blind_pairs import (
    DIFFERENT, SAME, separation, significance_threshold,
)


DEFAULT_CORPUS = Path("avtoroved-main/artifacts/pilot02c_corpus")


def parse_tags(raw: str) -> frozenset[str]:
    """Метки публикации из ячейки манифеста.

    В манифест они попадают как JSON-список, но корпус мог собираться и
    раньше, когда метки писались через запятую, поэтому разбор терпимый.
    Регистр и краевые пробелы не различаются: «Моё» и «моё» — одна метка.
    """
    text = (raw or "").strip()
    if not text:
        return frozenset()
    values: list[str]
    try:
        parsed = json.loads(text)
        values = [str(item) for item in parsed] if isinstance(parsed, list) else [str(parsed)]
    except (ValueError, TypeError):
        values = text.replace(";", ",").split(",")
    return frozenset(item.strip().lower() for item in values if item.strip())


def overlap(first: frozenset[str], second: frozenset[str]) -> float | None:
    """Доля общих меток. Пара без меток хотя бы с одной стороны не считается."""
    if not first or not second:
        return None
    return round(len(first & second) / len(first | second), 6)


def read_tags(corpus: Path) -> dict[str, frozenset[str]]:
    manifest = corpus / "manifest.csv"
    if not manifest.is_file():
        raise FileNotFoundError(
            f"Не найден манифест {manifest}: метки публикаций лежат в нём."
        )
    with manifest.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if rows and "tags" not in rows[0]:
        raise ValueError(f"В манифесте {manifest} нет столбца меток `tags`.")
    return {row["document_id"]: parse_tags(row.get("tags", "")) for row in rows}


def read_pairs(corpus: Path) -> list[dict]:
    """Пары с эталонным ответом; в ключе стоят идентификаторы документов.

    Здесь нужны именно они, а не пути: метки ищутся по `document_id`.
    """
    gold = corpus / "cases_gold_private.csv"
    if not gold.is_file():
        raise FileNotFoundError(
            f"Не найден эталонный ключ {gold}. Без него замер невозможен."
        )
    with gold.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    pairs = []
    for row in rows:
        relation = row["expected_relation"].strip().upper()
        if relation not in {SAME, DIFFERENT}:
            raise ValueError(f"Неизвестное отношение {relation!r} в {row['case_id']}.")
        pairs.append({"case_id": row["case_id"], "relation": relation,
                      "document_a": row["document_a"], "document_b": row["document_b"]})
    return pairs


def measure(pairs, tags_by_document) -> dict:
    per_case, missing = [], []
    for pair in pairs:
        first = tags_by_document.get(pair["document_a"])
        second = tags_by_document.get(pair["document_b"])
        if first is None or second is None:
            missing.append(pair["case_id"])
            continue
        value = overlap(first, second)
        if value is None:
            missing.append(pair["case_id"])
            continue
        per_case.append({"case_id": pair["case_id"], "relation": pair["relation"],
                         "shared_tags": sorted(first & second), "overlap": value})
    same = [item["overlap"] for item in per_case if item["relation"] == SAME]
    different = [item["overlap"] for item in per_case if item["relation"] == DIFFERENT]
    # Направление обратное проверке признаков: тематическое смешение — это когда
    # у пары одного автора меток общего БОЛЬШЕ, поэтому группы меняются местами.
    value = separation(different, same)
    threshold = significance_threshold(len(same), len(different))
    return {
        "kind": ("Замер тематического смешения в слепых парах; "
                 "не оценка авторства и не проверка признаков"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pairs": len(per_case),
        "same_pairs": len(same),
        "different_pairs": len(different),
        "pairs_without_tags": missing,
        "median_overlap_same": round(median(same), 6) if same else None,
        "median_overlap_different": round(median(different), 6) if different else None,
        "topic_separation": value,
        "significance_threshold": threshold,
        "above_chance": None if value is None or threshold is None else value >= threshold,
        "per_case": per_case,
        "measure": ("Доля пар, в которых доля общих меток у текстов одного автора "
                    "больше, чем у текстов разных. 0,5 — по тематике группы не "
                    "различаются. Выводов об авторстве отсюда не следует."),
    }


def print_report(report: dict) -> None:
    print(f"\nпар с метками: {report['pairs']} "
          f"(один автор {report['same_pairs']}, разные {report['different_pairs']})")
    if report["pairs_without_tags"]:
        print(f"пар без меток хотя бы с одной стороны: {len(report['pairs_without_tags'])}")
    print(f"\nмедиана доли общих меток: один автор "
          f"{report['median_overlap_same']}, разные {report['median_overlap_different']}")
    print(f"тематическое разделение: {report['topic_separation']} "
          f"(порог случайного разброса {report['significance_threshold']})")
    if report["above_chance"] is None:
        print("\nДанных для суждения не хватает.")
    elif report["above_chance"]:
        print("\nТексты одного автора в этом корпусе ближе по теме, чем тексты разных.\n"
              "Значит, значения признаков — верхняя оценка их пригодности:\n"
              "часть измеренного разделения может относиться к предмету речи.")
    else:
        print("\nПо тематике группы пар не различаются: объяснять разделение\n"
              "признаков темой на этом корпусе нечем.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path,
                        default=Path("authoroved_core/artifacts/topic_overlap.json"))
    args = parser.parse_args()

    report = measure(read_pairs(args.corpus), read_tags(args.corpus))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print_report(report)
    print(f"\nотчёт: {args.output}")


if __name__ == "__main__":
    main()
