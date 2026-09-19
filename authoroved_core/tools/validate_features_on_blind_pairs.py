"""Проверка AUTO-признаков на слепых парах Pilot 01 с эталонным ключом.

Корпус собирался именно под эту проверку: пары составлены из текстов одного
автора и разных авторов, ответы лежат отдельно в `cases_gold_private.csv`,
авторы псевдонимизированы. Проверка до сих пор не проводилась:
`run_engineering_pilot` прогоняет те же пары, но ключ не открывает и
убеждается лишь в том, что разбор не падает и координаты сходятся.

**Что здесь измеряется и что нет.** Измеряется, несёт ли значение признака
сведения о тождестве автора: расходятся ли значения между текстами разных
авторов сильнее, чем между текстами одного. Это проверка пригодности
признака, а не вывод об авторстве. Порогов отсюда не выводится, и вывода о
тождестве инструмент не делает: он сравнивает два распределения расстояний.

Мера разделения — доля пар, в которых расстояние у разных авторов больше,
чем у одного, при случайном выборе по одной паре из каждой группы. Значение
0,5 означает, что признак сведений о тождестве не несёт; 1,0 — полное
разделение. Совпадения расстояний считаются за половину.

Расстояние по признаку — сумма модулей разностей по всем числовым
составляющим его нормализованного значения. Для признака-скаляра это модуль
разности, для признака-распределения — суммарное расхождение частот на 1000
слов по объединению словоформ.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from math import sqrt
from pathlib import Path
from statistics import median
from time import perf_counter

from authoroved_core.core.analysis import AnalysisService
from authoroved_core.core.document import load_document
from authoroved_core.core.feature_models import Applicability
from authoroved_core.nlp.settings import LocalSettings


DEFAULT_CORPUS = Path("avtoroved-main/artifacts/pilot01_corpus")
SAME, DIFFERENT = "SAME", "DIFFERENT"


def flatten_numeric(value, prefix: str = "") -> dict[str, float]:
    """Числовые составляющие нормализованного значения с их путями."""
    result: dict[str, float] = {}
    if isinstance(value, bool):
        return result
    if isinstance(value, (int, float)):
        return {prefix or "value": float(value)}
    if isinstance(value, dict):
        for key, item in value.items():
            result.update(flatten_numeric(item, f"{prefix}.{key}" if prefix else str(key)))
    return result


def feature_distance(first, second) -> float | None:
    """Сумма модулей разностей по объединению числовых составляющих."""
    if first is None or second is None:
        return None
    left, right = flatten_numeric(first), flatten_numeric(second)
    if not left and not right:
        return None
    keys = set(left) | set(right)
    return round(sum(abs(left.get(key, 0.0) - right.get(key, 0.0)) for key in keys), 6)


def separation(same: list[float], different: list[float]) -> float | None:
    """Доля пар, где расстояние у разных авторов больше, чем у одного.

    0,5 — признак сведений о тождестве не несёт. Совпадения считаются за
    половину, как принято для этой меры.
    """
    if not same or not different:
        return None
    wins = sum(1.0 if value > other else 0.5 if value == other else 0.0
               for value in different for other in same)
    return round(wins / (len(same) * len(different)), 4)


def significance_threshold(same_count: int, different_count: int) -> float | None:
    """Значение разделения, ниже которого случайный разброс не исключён.

    Стандартная ошибка меры при отсутствии разделения равна
    sqrt((n1 + n2 + 1) / (12 * n1 * n2)); порог — 0,5 плюс 1,96 такой ошибки,
    то есть двусторонний уровень 0,05. На десяти парах против десяти порог
    равен 0,76: там от случайности не отличается ничто. На восьмидесяти против
    восьмидесяти — 0,59.

    Считается по числу пар, но пары одного автора между собой независимы не
    вполне: одна пара на автора — это n авторов, несколько пар от одного автора
    порог занижают. Корпус собирается по одной паре на автора именно поэтому.
    """
    if not same_count or not different_count:
        return None
    error = sqrt((same_count + different_count + 1) / (12 * same_count * different_count))
    return round(0.5 + 1.96 * error, 4)


def _rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_cases(corpus: Path) -> list[dict]:
    """Слепые пары вместе с эталонным ответом.

    Пути к текстам лежат в `cases_public.csv`, а в `cases_gold_private.csv`
    в тех же столбцах стоят внутренние идентификаторы документов, а не пути:
    ключ описывает, что за документы сравниваются, но файлы называет только
    публичный список. Поэтому пути берутся из публичного списка, отношение —
    из ключа, связываются по `case_id`.

    Ключ служебный: эксперту в слепой работе он не передаётся. Здесь он
    используется разработчиком для проверки признаков, а не для разбора дела.
    """
    gold_path = corpus / "cases_gold_private.csv"
    public_path = corpus / "cases_public.csv"
    if not gold_path.is_file():
        raise FileNotFoundError(
            f"Не найден эталонный ключ {gold_path}. Без него проверка невозможна."
        )
    if not public_path.is_file():
        raise FileNotFoundError(
            f"Не найден список пар {public_path}: в нём лежат пути к текстам."
        )
    paths = {row["case_id"]: row for row in _rows(public_path)}
    cases = []
    for row in _rows(gold_path):
        case_id = row["case_id"]
        if case_id not in paths:
            raise ValueError(f"Пара {case_id} есть в ключе, но отсутствует в списке пар.")
        relation = row["expected_relation"].strip().upper()
        if relation not in {SAME, DIFFERENT}:
            raise ValueError(f"Неизвестное отношение {relation!r} в {case_id}.")
        cases.append({"case_id": case_id, "relation": relation,
                      "document_a": paths[case_id]["document_a"],
                      "document_b": paths[case_id]["document_b"]})
    return cases


def observations_by_feature(result) -> dict[str, object]:
    return {item.feature_id: item.normalized_value
            for item in result.feature_observations
            if item.applicability is Applicability.APPLICABLE}


def summarize(distances_by_case: list[dict]) -> dict:
    """Сводка по признакам: расстояния внутри автора и между авторами."""
    features = sorted({name for case in distances_by_case for name in case["distances"]})
    summary = {}
    for name in features:
        same, different = [], []
        for case in distances_by_case:
            value = case["distances"].get(name)
            if value is None:
                continue
            (same if case["relation"] == SAME else different).append(value)
        value = separation(same, different)
        threshold = significance_threshold(len(same), len(different))
        summary[name] = {
            "same_pairs": len(same), "different_pairs": len(different),
            "median_same": round(median(same), 6) if same else None,
            "median_different": round(median(different), 6) if different else None,
            "separation": value,
            "significance_threshold": threshold,
            "above_chance": None if value is None or threshold is None else value >= threshold,
        }
    ordered = sorted(summary.items(),
                     key=lambda item: (item[1]["separation"] is None,
                                       -(item[1]["separation"] or 0)))
    return dict(ordered)


def print_report(report: dict) -> None:
    print(f"\nпар: {report['cases']} "
          f"(один автор {report['same_pairs']}, разные {report['different_pairs']})")
    print("\nразделение: 0,50 — признак сведений о тождестве не несёт, 1,00 — полное")
    thresholds = {item["significance_threshold"] for item in report["by_feature"].values()
                  if item["significance_threshold"] is not None}
    if thresholds:
        print(f"порог случайного разброса при таком числе пар: "
              f"{', '.join(str(item) for item in sorted(thresholds))}")
    print()
    print(f"  {'признак':10} {'разделение':>11} {'медиана один':>14} {'медиана разные':>16}")
    for name, value in report["by_feature"].items():
        if value["separation"] is None:
            mark = ""
        elif value["separation"] < 0.5:
            mark = "   <-- ниже случайного"
        elif not value["above_chance"]:
            mark = "   <-- от случайности не отличается"
        else:
            mark = ""
        print(f"  {name:10} {str(value['separation'] or '—'):>11} "
              f"{str(value['median_same'] or '—'):>14} "
              f"{str(value['median_different'] or '—'):>16}{mark}")
    print("\nЭто проверка пригодности признаков, а не вывод об авторстве: "
          "порогов отсюда не выводится.")


def run(corpus: Path, service: AnalysisService, cases, progress=lambda message: None):
    started = perf_counter()
    per_case, failures = [], []
    for number, case in enumerate(cases, start=1):
        progress(f"[{number}/{len(cases)}] {case['case_id']}")
        try:
            first = service.analyze(load_document(corpus / case["document_a"]))
            second = service.analyze(load_document(corpus / case["document_b"]))
        except Exception as error:  # разбор пары не должен ронять проверку целиком
            failures.append({"case_id": case["case_id"], "error": f"{type(error).__name__}: {error}"})
            continue
        left, right = observations_by_feature(first), observations_by_feature(second)
        distances = {}
        for name in sorted(set(left) | set(right)):
            value = feature_distance(left.get(name), right.get(name))
            if value is not None:
                distances[name] = value
        per_case.append({"case_id": case["case_id"], "relation": case["relation"],
                         "distances": distances})
    return {
        "kind": "Проверка пригодности AUTO-признаков на слепых парах; не оценка авторства",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_seconds": round(perf_counter() - started, 3),
        "cases": len(per_case),
        "same_pairs": sum(item["relation"] == SAME for item in per_case),
        "different_pairs": sum(item["relation"] == DIFFERENT for item in per_case),
        "failures": failures,
        "by_feature": summarize(per_case),
        "per_case": per_case,
        "measure": ("Доля пар, в которых расстояние между разными авторами больше, "
                    "чем между текстами одного автора. 0,5 — признак сведений о "
                    "тождестве не несёт. Порогов отсюда не выводится."),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--limit", type=int, default=0, help="сколько пар взять; 0 — все")
    parser.add_argument("--output", type=Path,
                        default=Path("authoroved_core/artifacts/feature_validity.json"))
    args = parser.parse_args()

    cases = read_cases(args.corpus)
    if args.limit:
        cases = cases[:args.limit]
    report = run(args.corpus, AnalysisService(LocalSettings.load()), cases,
                 lambda message: print(" ", message, flush=True))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print_report(report)
    if report["failures"]:
        print(f"\nне разобрано пар: {len(report['failures'])}")
    print(f"\nотчёт: {args.output}")


if __name__ == "__main__":
    main()
