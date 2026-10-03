"""Выгрузка профиля пригодности показателей для программы из отчёта проверки.

Программа корпус не читает и расчёт не повторяет: она получает небольшой
версионированный файл `methodology/coefficient_validity_profile.json` с итогом
проверки по каждому показателю (оценка, AUC, минимальный объём). Файл
пересоздаётся этой командой после нового прогона `coefficient_validity`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# В исследовании показатели длины предложений названы описательно; в программе — короче.
ALIASES = {
    "Средняя длина предложения (слов)": "Средняя длина предложения",
    "Доля предложений до 5 слов": "Предложения до 5 слов",
    "Доля предложений от 20 слов": "Предложения от 20 слов",
}
STATUS = {
    "различает авторов": "stable",
    "слабо различает": "weak",
    "различает, но не без общих тем": "topic",
    "не отличается от случайного": "uninformative",
}

DEFAULT_INPUT = Path("authoroved_core/artifacts/coefficient_validity.json")
DEFAULT_OUTPUT = Path("authoroved_core/methodology/coefficient_validity_profile.json")


def build_profile(report: dict) -> dict:
    discrimination = report["discrimination"]
    length = report["length"]["by_metric"]
    metrics = {}
    for name, item in discrimination["by_metric"].items():
        if item["verdict"] not in STATUS:
            continue
        stability = length.get(name, {})
        metrics[ALIASES.get(name, name)] = {
            "status": STATUS[item["verdict"]],
            "auc": item["auc"],
            "auc_topic_neutral": item["auc_topic_neutral"],
            "min_words_20": stability.get("min_words_20"),
            "min_words_10": stability.get("min_words_10"),
        }
    return {
        "profile": "coefficient_validity",
        "version": report["generated_at"][:10],
        "source": (f"Проверка пригодности на корпусе Pilot 02c: {discrimination['authors']} авторов, "
                   f"{discrimination['texts']} основных текстов Pikabu; seed {report['seed']}"),
        "max_tested_words": max(report["length"]["lengths"]),
        "notice": ("Оценки описывают пригодность признаков на текстах интернет-публикаций и не являются "
                   "нормативами или порогами вывода об авторстве."),
        "metrics": dict(sorted(metrics.items())),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    profile = build_profile(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(profile, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"профиль: {args.output} · показателей: {len(profile['metrics'])}")


if __name__ == "__main__":
    main()
