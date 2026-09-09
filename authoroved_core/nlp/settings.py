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
        if SETTINGS_PATH.is_file():
            return cls(**json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
        lt_dir = ""
        try:
            cache = Path.home() / ".cache" / "language_tool_python"
            for directory in sorted(cache.glob("LanguageTool-*"), reverse=True):
                if (directory / "languagetool-commandline.jar").is_file():
                    lt_dir = str(directory)
                    break
        except OSError:
            pass
        bundled = SETTINGS_PATH.parent / "stanza_resources"
        stanza_dir = bundled if (bundled / "resources.json").is_file() else Path.home() / "stanza_resources"
        return cls(str(stanza_dir), lt_dir, find_java())

    def save(self):
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = SETTINGS_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(SETTINGS_PATH)
