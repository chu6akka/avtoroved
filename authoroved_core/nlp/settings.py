"""Настройки только локальных ресурсов. Никаких сетевых адресов.

Программа сама ищет уже установленные Java, LanguageTool и модели Stanza:
сначала в собственной папке .local, затем в стандартных местах установки,
переменных окружения, реестре Windows и неглубоко — в корнях всех дисков.
Ничего не скачивается; найденные пути можно исправить в «Локальных анализаторах».
"""
import json
import os
import shutil
import string
from dataclasses import asdict, dataclass
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = CORE_ROOT / ".local" / "settings.json"
LT_JAR = "languagetool-commandline.jar"
STANZA_MARKER = "resources.json"
# Глубина обхода от каждой базовой папки: достаточно для «Диск:\Программы\LanguageTool-6.6»,
# но без полного сканирования диска.
SEARCH_DEPTH = 3
SKIPPED_DIRS = {"windows", "$recycle.bin", "system volume information", "programdata",
                "node_modules", ".git", "site-packages", "__pycache__", "appdata", "winsxs"}


def _drives() -> list[Path]:
    if os.name != "nt":
        return [Path("/")]
    return [Path(f"{letter}:\\") for letter in string.ascii_uppercase if Path(f"{letter}:\\").exists()]


def _is_lt(directory: Path) -> bool:
    return (directory / LT_JAR).is_file()


def _is_stanza(directory: Path) -> bool:
    return (directory / STANZA_MARKER).is_file() and (directory / "ru").is_dir()


def _walk(base: Path, match, name_filter=None, depth: int = SEARCH_DEPTH):
    """Неглубокий обход папок; возвращает первые подходящие каталоги."""
    found = []
    level = [base]
    for _ in range(depth + 1):
        next_level = []
        for directory in level:
            try:
                if match(directory):
                    found.append(directory)
                    continue
                children = [child for child in directory.iterdir() if child.is_dir()]
            except OSError:
                continue
            for child in children:
                name = child.name.casefold()
                if name in SKIPPED_DIRS or name.startswith("."):
                    if name not in {".local", ".cache"}:
                        continue
                if name_filter is None or name_filter(name) or child.parent == base:
                    next_level.append(child)
        level = next_level
    return found


def _search_bases() -> list[Path]:
    home = Path.home()
    bases = [CORE_ROOT / ".local", CORE_ROOT.parent, home, home / "Downloads", home / "Desktop",
             home / "Documents", home / ".cache"]
    for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        if os.environ.get(variable):
            bases.append(Path(os.environ[variable]))
    bases.extend(_drives())
    unique, seen = [], set()
    for base in bases:
        key = str(base).casefold()
        if key not in seen and base.is_dir():
            seen.add(key)
            unique.append(base)
    return unique


def _newest(directories) -> str:
    """Из нескольких поставок выбирает более новую по имени (LanguageTool-6.6 > 6.5)."""
    candidates = sorted(set(directories), key=lambda path: path.name, reverse=True)
    return str(candidates[0]) if candidates else ""


def find_languagetool() -> str:
    explicit = [os.environ.get("LANGUAGETOOL_HOME", ""), os.environ.get("LTP_PATH", "")]
    for value in explicit:
        if value:
            path = Path(value)
            hits = [path] if _is_lt(path) else [item for item in path.glob("LanguageTool-*") if _is_lt(item)]
            if hits:
                return _newest(hits)
    looks_like_lt = lambda name: "languagetool" in name or name in {"programs", "program files", "tools",
                                                                      "soft", "apps", "language_tool_python",
                                                                      "проекты", "programs files", ".local", ".cache"}
    for base in _search_bases():
        hits = _walk(base, _is_lt, looks_like_lt)
        if hits:
            return _newest(hits)
    return ""


def find_stanza() -> str:
    candidates = [CORE_ROOT / ".local" / "stanza_resources"]
    if os.environ.get("STANZA_RESOURCES_DIR"):
        candidates.append(Path(os.environ["STANZA_RESOURCES_DIR"]))
    candidates.append(Path.home() / "stanza_resources")
    for candidate in candidates:
        if _is_stanza(candidate):
            return str(candidate)
    looks_like_stanza = lambda name: "stanza" in name or name in {".local", "проекты", "models", "data"}
    for base in _search_bases():
        hits = _walk(base, _is_stanza, looks_like_stanza)
        if hits:
            return str(hits[0])
    return str(candidates[-1])


def _java_version_key(path: Path) -> tuple:
    digits = "".join(char if char.isdigit() else " " for char in str(path.parent.parent.name)).split()
    return tuple(int(item) for item in digits[:3]) or (0,)


def find_java() -> str:
    java_name = "java.exe" if os.name == "nt" else "java"
    for variable in ("JAVA_HOME", "JRE_HOME", "JDK_HOME"):
        home = os.environ.get(variable)
        if home and (Path(home) / "bin" / java_name).is_file():
            return str(Path(home) / "bin" / java_name)
    found = shutil.which("java")
    # Заглушка javapath от Oracle работает, но системный java из PATH тоже подходит.
    if found:
        return found
    if os.name == "nt":
        import winreg
        keys = (r"SOFTWARE\Eclipse Adoptium\JDK", r"SOFTWARE\Eclipse Adoptium\JRE",
                r"SOFTWARE\JavaSoft\JDK", r"SOFTWARE\JavaSoft\Java Runtime Environment",
                r"SOFTWARE\Microsoft\JDK", r"SOFTWARE\Azul Systems\Zulu")
        for key in keys:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as root:
                    for index in range(winreg.QueryInfoKey(root)[0]):
                        version = winreg.EnumKey(root, index)
                        for sub, value in ((r"\hotspot\MSI", "Path"), ("", "JavaHome"), ("", "InstallationPath")):
                            try:
                                with winreg.OpenKey(root, version + sub) as entry:
                                    candidate = Path(winreg.QueryValueEx(entry, value)[0]) / "bin" / java_name
                                    if candidate.is_file():
                                        return str(candidate)
                            except OSError:
                                continue
            except OSError:
                continue
    vendors = ("Java", "Eclipse Adoptium", "Eclipse Foundation", "Microsoft", "Zulu", "Amazon Corretto",
               "BellSoft", "OpenJDK", "AdoptOpenJDK", "Semeru")
    candidates = []
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        root = Path(os.environ.get(variable, ""))
        for vendor in vendors:
            candidates.extend((root / vendor).glob(f"*/bin/{java_name}"))
    candidates.extend((Path.home() / ".jdks").glob(f"*/bin/{java_name}"))
    if candidates:
        return str(max(candidates, key=_java_version_key))
    return ""


@dataclass
class LocalSettings:
    stanza_dir: str = ""
    languagetool_dir: str = ""
    java_executable: str = ""

    @classmethod
    def load(cls):
        saved = cls()
        if SETTINGS_PATH.is_file():
            try:
                saved = cls(**json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError):
                saved = cls()
        # Сохранённый путь мог устареть (например, после переноса папки на другой диск):
        # тогда программа ищет ресурс заново и запоминает найденное.
        changed = False
        if not _is_stanza(Path(saved.stanza_dir)):
            saved.stanza_dir, changed = find_stanza(), True
        if not _is_lt(Path(saved.languagetool_dir)):
            found = find_languagetool()
            changed = changed or found != saved.languagetool_dir
            saved.languagetool_dir = found
        if not Path(saved.java_executable).is_file():
            found = find_java()
            changed = changed or found != saved.java_executable
            saved.java_executable = found
        if changed and saved.languagetool_dir and saved.java_executable and _is_stanza(Path(saved.stanza_dir)):
            try:
                saved.save()
            except OSError:
                pass
        return saved

    @classmethod
    def detect(cls):
        return cls(find_stanza(), find_languagetool(), find_java())

    def save(self):
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = SETTINGS_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(SETTINGS_PATH)
