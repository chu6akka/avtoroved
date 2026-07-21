# -*- coding: utf-8 -*-
"""
scripts/check_lt.py — самопроверка локального LanguageTool.

Проверяет цепочку целиком: Java → пакет language_tool_python → запуск
ЛОКАЛЬНОГО сервера LT → реальная проверка эталонной фразы с ошибками →
режим, который увидит протокол (lt_checker.mode == 'local').

Запуск:  python scripts/check_lt.py
Код выхода 0 = локальный LT полностью работоспособен.
"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OK, FAIL = "[OK]  ", "[СБОЙ]"


def main() -> int:
    failed = False

    # 1) Java: гарантированный поиск (PATH → config → JAVA_HOME → реестр →
    # типовые каталоги) — тот же локатор, что использует сама программа.
    from analyzer.java_locator import ensure_java_in_path
    in_path_before = bool(shutil.which("java"))
    java = ensure_java_in_path(status_cb=lambda m: print(f"      {m}"))
    if java:
        try:
            out = subprocess.run(["java", "-version"], capture_output=True,
                                 text=True, timeout=30)
            ver = (out.stderr or out.stdout).splitlines()[0].strip()
            src = "PATH" if in_path_before else "локатор (вне PATH)"
            print(f"{OK}Java найдена через {src}: {java}")
            print(f"      {ver}")
        except Exception as e:
            print(f"{FAIL}java найдена, но не запускается: {e}")
            failed = True
    else:
        print(f"{FAIL}Java не найдена ни одним из способов.")
        print("      Установите Temurin JDK: https://adoptium.net")
        print("      (или пропишите путь в config.json: \"java_home\": \"...\")")
        return 1

    # 2) Пакет language_tool_python
    try:
        from importlib.metadata import version
        print(f"{OK}Пакет language_tool_python {version('language-tool-python')}")
    except Exception:
        print(f"{FAIL}Пакет language_tool_python не установлен: "
              "pip install language-tool-python")
        return 1

    # 3) Локальный сервер через штатную обёртку программы
    print("      Запуск локального сервера LT (первый раз может занять ~минуту;")
    print("      при первом использовании качается дистрибутив LT ~250 МБ)...")
    from analyzer import lt_checker
    lt = lt_checker.get()
    lt.ensure_loaded(status_callback=lambda m: print(f"      {m}"))

    if lt.mode != "local":
        print(f"{FAIL}LT поднялся в режиме «{lt.mode or 'нет'}», а не local —")
        print("      протокол такой режим НЕ использует (конфиденциальность).")
        return 1
    print(f"{OK}Режим: local — именно его использует протокол")

    # 4) Реальная проверка: фраза с орфографической и пунктуационной ошибками
    sample = "Однако он пришол домой , и сел на стул который стоял у окна"
    errors = lt.check(sample)
    print(f"{OK}Проверка эталонной фразы: найдено срабатываний: {len(errors)}")
    for e in errors[:5]:
        print(f"      - {e.rule_ref:28} | {e.fragment!r:20} | {e.description[:50]}")
    if not errors:
        print(f"{FAIL}0 срабатываний на заведомо ошибочной фразе — что-то не так.")
        failed = True

    lt.close()
    if not failed:
        print("\nИТОГ: локальный LanguageTool полностью работоспособен.")
        print("В программе это видно так: в сайдбаре «⚙ LT: локальный», а в")
        print("журнале проекта после построения профиля — запись")
        print('«languagetool»: {«режим»: «local», «версия»: …}.')
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
