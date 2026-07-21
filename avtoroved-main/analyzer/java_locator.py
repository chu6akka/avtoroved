"""
analyzer/java_locator.py — гарантированный поиск Java для локального LanguageTool.

Проблема: language_tool_python ищет `java` только в PATH процесса. PATH хрупок
(старый ярлык, другая машина, переустановка) — и при его потере LT молча
падал бы в публичный API, который протокол не использует. Этот модуль делает
запуск детерминированным: Java ищется по цепочке источников, найденная —
прописывается в PATH ТЕКУЩЕГО процесса.

Порядок поиска:
  1. PATH (уже настроен — ничего не делаем);
  2. ключ "java_home" в config.json программы (ручное закрепление);
  3. переменная окружения JAVA_HOME;
  4. реестр Windows: HKLM\\SOFTWARE\\Eclipse Adoptium\\JDK\\*\\hotspot\\MSI
     (стандартная запись MSI-установщика Temurin; на этой машине Path=F:\\);
  5. типовые каталоги установки (Program Files\\Eclipse Adoptium, …\\Java).

Вызывается из lt_checker.ensure_loaded() перед стартом локального сервера —
то есть срабатывает для GUI, скриптов и exe-сборки одинаково.
"""
from __future__ import annotations

import os
import shutil
import sys
from typing import Callable, Optional


def _java_exe(java_home: str) -> Optional[str]:
    """Путь к java.exe внутри каталога JDK/JRE, если он там есть."""
    cand = os.path.join(java_home, "bin", "java.exe" if os.name == "nt" else "java")
    return cand if os.path.isfile(cand) else None


def _from_config() -> Optional[str]:
    try:
        from analyzer import config as app_config
        home = app_config.get("java_home", "")
        return _java_exe(home) if home else None
    except Exception:
        return None


def _from_env() -> Optional[str]:
    home = os.environ.get("JAVA_HOME", "")
    return _java_exe(home) if home else None


def _from_registry() -> Optional[str]:
    """HKLM\\SOFTWARE\\Eclipse Adoptium\\JDK\\<версия>\\hotspot\\MSI → Path."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Eclipse Adoptium\JDK") as jdk:
            i = 0
            versions = []
            while True:
                try:
                    versions.append(winreg.EnumKey(jdk, i))
                    i += 1
                except OSError:
                    break
        for ver in sorted(versions, reverse=True):   # свежая версия первой
            try:
                with winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        rf"SOFTWARE\Eclipse Adoptium\JDK\{ver}\hotspot\MSI") as msi:
                    home, _t = winreg.QueryValueEx(msi, "Path")
                # ВАЖНО: не срезать хвостовой слэш — корень диска "F:\"
                # превратился бы в диск-относительный путь "F:".
                exe = _java_exe(home)
                if exe:
                    return exe
            except OSError:
                continue
    except Exception:
        pass
    return None


def _from_common_dirs() -> Optional[str]:
    roots = []
    for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if not base:
            continue
        roots += [os.path.join(base, "Eclipse Adoptium"),
                  os.path.join(base, "Java"),
                  os.path.join(base, "Programs", "Eclipse Adoptium")]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root), reverse=True):
            exe = _java_exe(os.path.join(root, name))
            if exe:
                return exe
    return None


def find_java() -> Optional[str]:
    """Найти java.exe по цепочке источников (без изменения окружения)."""
    return (shutil.which("java")
            or _from_config()
            or _from_env()
            or _from_registry()
            or _from_common_dirs())


def ensure_java_in_path(status_cb: Optional[Callable[[str], None]] = None) -> Optional[str]:
    """
    Гарантировать, что `java` доступна процессу: если её нет в PATH — найти
    по цепочке источников и добавить каталог в PATH текущего процесса.
    Возвращает путь к java или None (Java не установлена вовсе).
    """
    exe = shutil.which("java")
    if exe:
        return exe
    exe = find_java()
    if exe:
        os.environ["PATH"] = os.path.dirname(exe) + os.pathsep + os.environ.get("PATH", "")
        if status_cb:
            status_cb(f"Java найдена вне PATH и подключена: {exe}")
        return shutil.which("java") or exe
    if status_cb:
        status_cb("Java не найдена (PATH, config.json:java_home, JAVA_HOME, "
                  "реестр Adoptium, типовые каталоги) — установите с adoptium.net")
    return None
