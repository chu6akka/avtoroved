from __future__ import annotations

import csv
from pathlib import Path


def _flatten(rows: list[dict]) -> list[dict]:
    flat = []
    for row in rows:
        flat.append({key: value for key, value in row.items()
                     if not isinstance(value, (dict, list, tuple))})
    return flat


def write_csv(path: Path, rows: list[dict]) -> None:
    rows = _flatten(rows)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def render_report(run_meta: dict, corpus_check: dict, metrics: dict) -> str:
    limitation = (
        "Этот прогон оценивает обнаружение кандидатов, воспроизводимость, "
        "вспомогательные тематические/стилевые слои и трудозатраты. Он не "
        "оценивает точность вывода об авторстве и не заменяет решение эксперта.")
    lines = [f"# Отчёт валидации {run_meta['run_id']}", "",
             "> **ПИЛОТНЫЙ/ВАЛИДАЦИОННЫЙ ТЕХНИЧЕСКИЙ ПРОГОН.** " + limitation, "",
             "## Паспорт прогона", "",
             f"- Режим: `{run_meta['mode']}`",
             f"- Дата UTC: `{run_meta['timestamp_utc']}`",
             f"- Git commit: `{run_meta['git_commit']}`",
             f"- Python: `{run_meta['python_version']}`", "",
             "## Состав корпуса и распределение меток", "",
             f"Документов: {corpus_check['document_count']}. Синтетическая демонстрация: {run_meta.get('synthetic_demo', False)}.", "",
             "Распределение gold-меток хранится в исходных аннотациях; detection gold и экспертное принятие рассчитываются раздельно.", "",
             "## Конфигурация", "",
             "Точный замороженный снимок ThemeEngineV2/StyleEngineV2 сохранён в `config_snapshot.json` и включён в контроль хэшей.", "",
             "## Контроль корпуса", "",
             f"Документов: {corpus_check['document_count']}; ошибок: {corpus_check['error_count']}; предупреждений: {corpus_check['warning_count']}.", "",
             "## Обнаружение методических признаков", ""]
    feature = metrics.get("features", {})
    for row in feature.get("groups", []):
        lines.append(f"- {row['group']}: P={row['precision']:.3f}, R={row['recall']:.3f}, F1={row['f1']:.3f}, support={row['support']}")
    lines += ["", "## Тематический слой", "", str(metrics.get("theme", "нет gold-данных")),
              "", "## Стилевой слой", "", str(metrics.get("style", "нет gold-данных")),
              "", "## Межэкспертное согласие", "", str(metrics.get("agreement", "нет данных")),
              "", "## Время", "", str(metrics.get("time", "нет парных данных")),
              "", "## Ошибки и ограничения", "",
              f"FP/FN случаев: {len(feature.get('errors', []))}. {limitation}", "",
              "Список отдельных FP/FN сохранён в `error_cases.csv`; случаи малой опоры имеют статус `insufficient_support`.", "",
              "## Воспроизводимость", "",
              "Хэши входов, аннотаций, конфигурации и сырых результатов сохранены в `hashes.json`; конфигурация движков — в `config_snapshot.json`.", ""]
    return "\n".join(lines)


def write_reports(run_dir: Path, run_meta: dict, corpus_check: dict,
                  metrics: dict) -> Path:
    report = run_dir / "report.md"
    report.write_text(render_report(run_meta, corpus_check, metrics), encoding="utf-8")
    feature = metrics.get("features", {})
    write_csv(run_dir / "feature_metrics.csv", feature.get("features", []))
    write_csv(run_dir / "error_cases.csv", feature.get("errors", []))
    write_csv(run_dir / "theme_metrics.csv", [metrics["theme"]] if metrics.get("theme") else [])
    write_csv(run_dir / "style_metrics.csv", [metrics["style"]] if metrics.get("style") else [])
    write_csv(run_dir / "time_metrics.csv", metrics.get("time", {}).get("paired", []))
    return report
