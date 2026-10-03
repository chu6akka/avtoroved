"""Самопроверка перед работой: найдены ли движки и выполняется ли анализ.

Запуск: python -m authoroved_core.tools.selfcheck
Проверяет Stanza, LanguageTool и Java, затем анализирует короткий пробный текст
с заведомыми ошибками. Код выхода 0 — всё готово, 1 — что-то не так (причина
напечатана). Сеть не используется.
"""
from __future__ import annotations

import sys
from pathlib import Path
from time import perf_counter

SAMPLE = "Я пошол домой, потомушто очень устал. Мы долго гуляли по старому парку."


def main() -> int:
    from authoroved_core import __version__
    import tempfile
    from authoroved_core.core.analysis import AnalysisService
    from authoroved_core.core.document import load_document
    from authoroved_core.nlp.settings import LocalSettings

    print(f"Авторовед Core {__version__} · самопроверка")
    settings = LocalSettings.load()
    problems = []
    checks = (
        ("Модели Stanza", Path(settings.stanza_dir) / "resources.json", settings.stanza_dir),
        ("LanguageTool", Path(settings.languagetool_dir) / "languagetool-commandline.jar", settings.languagetool_dir),
        ("Java", Path(settings.java_executable), settings.java_executable),
    )
    for title, marker, location in checks:
        found = bool(location) and marker.is_file()
        print(f"  {'✓' if found else '✗'} {title}: {location or 'не найдено'}")
        if not found:
            problems.append(f"{title} не найдено")
    if problems:
        print("Не готово: " + "; ".join(problems) + ".")
        return 1

    started = perf_counter()
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "самопроверка.txt"
        path.write_text(SAMPLE, encoding="utf-8")
        document = load_document(path)
    result = AnalysisService(settings).analyze(document)
    seconds = perf_counter() - started
    words = next((m.value for m in result.metrics if m.name == "Слова"), "0")
    fragments = sorted({candidate.fragment for candidate in result.candidates})
    print(f"  ✓ Анализ выполнен за {seconds:.1f} с: слов {words}, кандидатов {len(result.candidates)} "
          f"({', '.join(fragments[:4])})")
    if result.errors:
        print("Не готово: " + " ".join(result.errors))
        return 1
    if not result.tokens or not result.candidates:
        print("Не готово: разбор или проверка не дали результата.")
        return 1
    print("Готово к работе.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
