#!/usr/bin/env python3
"""
scripts/build_exe.py
Автоматическая сборка Автороведческого анализатора в EXE-дистрибутив.

Использование:
    python scripts/build_exe.py              # обычная сборка (папка dist/)
    python scripts/build_exe.py --onefile    # один EXE (долго, большой файл)
    python scripts/build_exe.py --installer  # попытаться создать NSIS-установщик

Требования:
    pip install pyinstaller
    (опционально) установить NSIS: https://nsis.sourceforge.io/
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist", "avtoroved")
SPEC = os.path.join(ROOT, "avtoroved.spec")


def check_pyinstaller():
    try:
        import PyInstaller
        print(f"PyInstaller {PyInstaller.__version__} — OK")
    except ImportError:
        print("PyInstaller не найден. Устанавливаю...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def run_pyinstaller(onefile: bool = False):
    cmd = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm"]
    if onefile:
        # Один файл — медленный старт из-за распаковки во временную папку
        cmd += ["--onefile", "--windowed"]
        cmd += ["main.py", "--name", "avtoroved"]
    else:
        cmd += [SPEC]

    print(f"\nЗапуск: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("\n❌ Сборка завершилась с ошибкой.")
        sys.exit(1)
    print("\n✅ Сборка завершена.")


def copy_extras():
    """Скопировать дополнительные файлы которые PyInstaller мог пропустить."""
    if not os.path.exists(DIST):
        return

    # data/ — словари НКРЯ, тематика, стратификация, сентимент
    src_data = os.path.join(ROOT, "data")
    dst_data = os.path.join(DIST, "data")
    if os.path.exists(src_data):
        shutil.copytree(src_data, dst_data, dirs_exist_ok=True)
        print(f"Скопировано: data/ → {dst_data}")

    # README или инструкция для пользователя
    inst_path = os.path.join(DIST, "КАК_ЗАПУСТИТЬ.txt")
    with open(inst_path, "w", encoding="utf-8") as f:
        f.write(
            "АВТОРОВЕДЧЕСКИЙ АНАЛИЗАТОР v5\n"
            "="*40 + "\n\n"
            "ПЕРВЫЙ ЗАПУСК:\n"
            "  При первом запуске программа автоматически скачает\n"
            "  языковую модель Stanza (~500 МБ). Нужно интернет-соединение.\n"
            "  Загрузка выполняется один раз.\n\n"
            "ЗАПУСК:\n"
            "  Запустите avtoroved.exe\n\n"
            "СИСТЕМНЫЕ ТРЕБОВАНИЯ:\n"
            "  Windows 10/11, 64-bit\n"
            "  RAM: минимум 4 ГБ (рекомендуется 8 ГБ)\n"
            "  Свободное место: ~3 ГБ (включая модели)\n\n"
            "ВКЛАДКИ:\n"
            "  Статистика      — лингвостатистические показатели\n"
            "  Морфемы/100 слов— распределение падежей, видов, времён\n"
            "  Ошибки          — орфография и пунктуация (LanguageTool)\n"
            "  Стратификация   — лексические пласты (жаргон, просторечие...)\n"
            "  Тематика        — тематическая атрибуция текста\n"
            "  НКРЯ: частоты   — частотный профиль по корпусу НКРЯ\n"
            "  Тональность     — позитивная/негативная лексика (RuSentiLex)\n"
        )
    print(f"Создана: {inst_path}")


def build_nsis_installer():
    """Создать NSIS-установщик если nsis.exe доступен."""
    nsis_paths = [
        r"C:\Program Files (x86)\NSIS\makensis.exe",
        r"C:\Program Files\NSIS\makensis.exe",
        "makensis",
    ]
    nsis_exe = None
    for p in nsis_paths:
        if shutil.which(p) or os.path.exists(p):
            nsis_exe = p
            break

    if not nsis_exe:
        print(
            "\nNSIS не найден. Установите NSIS для создания установщика:\n"
            "  https://nsis.sourceforge.io/Download\n"
            "Или распространяйте папку dist/avtoroved/ как есть (в ZIP-архиве)."
        )
        return

    # Генерировать .nsi скрипт
    nsi_content = f"""
!define APP_NAME "Автороведческий анализатор"
!define APP_VERSION "5.0"
!define APP_DIR "{DIST.replace(chr(92), chr(92)*2)}"
!define OUTPUT "dist\\\\AvtorAn_Setup_v5.exe"

Name "${{APP_NAME}} v${{APP_VERSION}}"
OutFile "${{OUTPUT}}"
InstallDir "$PROGRAMFILES64\\\\${{APP_NAME}}"
RequestExecutionLevel admin

Section "Программа"
  SetOutPath "$INSTDIR"
  File /r "${{APP_DIR}}\\\\*.*"
  CreateShortcut "$DESKTOP\\\\${{APP_NAME}}.lnk" "$INSTDIR\\\\avtoroved.exe"
  CreateShortcut "$SMPROGRAMS\\\\${{APP_NAME}}.lnk" "$INSTDIR\\\\avtoroved.exe"
SectionEnd

Section "Удаление"
  Delete "$INSTDIR\\\\*.*"
  RMDir /r "$INSTDIR"
  Delete "$DESKTOP\\\\${{APP_NAME}}.lnk"
SectionEnd
"""
    nsi_path = os.path.join(ROOT, "dist", "installer.nsi")
    with open(nsi_path, "w", encoding="utf-8") as f:
        f.write(nsi_content)

    result = subprocess.run([nsis_exe, nsi_path], cwd=ROOT)
    if result.returncode == 0:
        print(f"\n✅ Установщик создан: dist/AvtorAn_Setup_v5.exe")
    else:
        print("\n❌ Ошибка NSIS. Проверьте dist/installer.nsi")


def zip_dist():
    """Запаковать dist/avtoroved/ в ZIP для передачи студентам."""
    import zipfile, pathlib
    zip_path = os.path.join(ROOT, "dist", "AvtorAn_v5.zip")
    print(f"\nСоздание ZIP: {zip_path}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in pathlib.Path(DIST).rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(os.path.join(ROOT, "dist")))
    size_mb = os.path.getsize(zip_path) // (1024 * 1024)
    print(f"✅ ZIP создан: {zip_path} ({size_mb} МБ)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Сборка EXE-дистрибутива")
    parser.add_argument("--onefile",   action="store_true", help="Один .exe файл")
    parser.add_argument("--installer", action="store_true", help="Создать NSIS-установщик")
    parser.add_argument("--zip",       action="store_true", help="Создать ZIP-архив")
    args = parser.parse_args()

    os.chdir(ROOT)
    check_pyinstaller()
    run_pyinstaller(onefile=args.onefile)
    copy_extras()

    if args.installer:
        build_nsis_installer()
    if args.zip:
        zip_dist()

    print(f"\n📦 Дистрибутив готов: {DIST if not args.onefile else 'dist/avtoroved.exe'}")
    print("Для передачи студентам запакуйте папку dist/avtoroved/ в ZIP")
    print("или запустите: python scripts/build_exe.py --zip")
