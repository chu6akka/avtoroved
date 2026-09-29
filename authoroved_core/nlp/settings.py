"""Настройки только локальных ресурсов. Никаких сетевых адресов."""
import json
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

SETTINGS_PATH = Path(__file__).resolve().parents[1] / ".local" / "settings.json"


def find_java() -> str:
    found = shutil.which("java")
    if found:
        return found
    java_home = os.environ.get("JAVA_HOME")
    if java_home and (Path(java_home) / "bin" / "java.exe").is_file():
        return str(Path(java_home) / "bin" / "java.exe")
    if os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Eclipse Adoptium\JDK") as root:
                for index in range(winreg.QueryInfoKey(root)[0]):
                    version = winreg.EnumKey(root, index)
                    try:
                        with winreg.OpenKey(root, version + r"\hotspot\MSI") as entry:
                            candidate = Path(winreg.QueryValueEx(entry, "Path")[0]) / "bin" / "java.exe"
                            if candidate.is_file():
                                return str(candidate)
                    except OSError:
                        continue
        except OSError:
            pass
    return ""


@dataclass
class LocalSettings:
    stanza_dir: str = ""
    languagetool_dir: str = ""
    java_executable: str = ""

    @classmethod
    def load(cls):
        detected = cls.detect()
        if not SETTINGS_PATH.is_file():
            return detected
        saved = cls(**json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
        # Сохранённый путь мог устареть (например, после переноса папки на другой диск).
        if not (Path(saved.stanza_dir) / "resources.json").is_file():
            saved.stanza_dir = detected.stanza_dir
        if not (Path(saved.languagetool_dir) / "languagetool-commandline.jar").is_file():
            saved.languagetool_dir = detected.languagetool_dir
        if not Path(saved.java_executable).is_file():
            saved.java_executable = detected.java_executable
        return saved

    @classmethod
    def detect(cls):
        lt_dir = ""
        for root in (SETTINGS_PATH.parent / "languagetool", Path.home() / ".cache" / "language_tool_python"):
            try:
                for directory in sorted(root.glob("LanguageTool-*"), reverse=True):
                    if (directory / "languagetool-commandline.jar").is_file():
                        lt_dir = str(directory)
                        break
            except OSError:
                continue
            if lt_dir:
                break
        bundled = SETTINGS_PATH.parent / "stanza_resources"
        stanza_dir = bundled if (bundled / "resources.json").is_file() else Path.home() / "stanza_resources"
        return cls(str(stanza_dir), lt_dir, find_java())

    def save(self):
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = SETTINGS_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(SETTINGS_PATH)
