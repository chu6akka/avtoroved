"""Демонстрация полного цикла идентификации на корпусе текстов по авторам.

Сценарий 1: спорный текст и образцы — одного автора (ожидаем сближение).
Сценарий 2: спорный текст и образцы — разных авторов (ожидаем различие).

Запуск:  python tools/demo_identify.py
"""
from __future__ import annotations

import pathlib

from aved.core.models import ObjectText, Role
from aved.core.pipeline import identify
from aved.core.registry import Registry

CORPUS = pathlib.Path(r"F:\програмка v3\avtoroved_git\avtoroved-main\data\corpus_auth")


def load_author(name: str) -> list[pathlib.Path]:
    return sorted((CORPUS / name).glob("*.txt"))


def run(label: str, disputed_file: pathlib.Path, sample_files: list[pathlib.Path], reg: Registry):
    objects = [ObjectText(id="Q", role=Role.DISPUTED, title=disputed_file.name,
                          text=disputed_file.read_text(encoding="utf-8", errors="ignore"))]
    for i, f in enumerate(sample_files):
        objects.append(ObjectText(id=f"S{i}", role=Role.SAMPLE, title=f.name,
                                  text=f.read_text(encoding="utf-8", errors="ignore")))
    res = identify(objects, reg)
    print(f"\n===== {label} =====")
    r = res.suitability
    print(f"спорный слов: {r.disputed_words}; образцов слов: {r.sample_words}; "
          f"соотношение ×{r.volume_ratio}; можно продолжать: {r.can_proceed}")
    if res.comparison:
        for lv, lc in res.comparison.levels.items():
            print(f"  {lv.value}: совпадений {len(lc.matching)}, различий {len(lc.differing)} "
                  f"(высокоинф. совп. {lc.matching_high})")
        print(f"  конфликт норм НН: {res.comparison.nn_norm_conflict} {res.comparison.nn_conflict_reason}")
    if res.verdict:
        print(f"  ВЫВОД: {res.verdict.type.value}")
        for line in res.verdict.rationale:
            print(f"    — {line}")


def main() -> None:
    reg = Registry.load()
    a = load_author("AnnieBronson")
    b = load_author("SLY_G")
    if len(a) >= 2 and len(b) >= 1:
        run("Сценарий 1: один автор (AnnieBronson)", a[0], a[1:], reg)
        run("Сценарий 2: разные авторы (спорный AnnieBronson, образцы SLY_G)", a[0], b, reg)


if __name__ == "__main__":
    main()
