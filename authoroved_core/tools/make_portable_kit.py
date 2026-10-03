"""Переносной комплект для установки на ноутбук без интернета.

Собирает папку (по умолчанию рядом с репозиторием, `Авторовед_комплект_<версия>`):
  app/       — код из метки Git (только Core и запуск), частотный словарь НКРЯ,
               модели Stanza, LanguageTool и Java (Temurin, лицензия GPLv2 + CE);
  wheels/    — пакеты Python для Windows x64, Python 3.12 и 3.13;
  Установить.cmd / install.ps1 — офлайн-установка окружения и самопроверка;
  ПРОЧТИ_МЕНЯ.txt — инструкция.
На ноутбуке нужен только установленный Python 3.12 или 3.13. Сборка требует сети
лишь для скачивания пакетов Python с PyPI; программа ей не пользуется.
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "authoroved_core"
FREQUENCY = Path("avtoroved-main/data/freq/freqrnc.json")
MARKER = "АВТОРОВЕД_КОМПЛЕКТ.txt"
CPU_INDEX = "https://download.pytorch.org/whl/cpu"

INSTALL_PS1 = r'''$ErrorActionPreference = 'Stop'
$kit = $PSScriptRoot
$core = Join-Path $kit 'app\authoroved_core'
Write-Host 'Авторовед Core — установка без интернета' -ForegroundColor Cyan

$exe = $null; $prefix = @()
foreach ($candidate in @(@('py', '-3.13'), @('py', '-3.12'), @('python'))) {
    $tryPrefix = @($candidate | Select-Object -Skip 1)
    try {
        $version = & $candidate[0] @tryPrefix -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($version -in @('3.12', '3.13')) { $exe = $candidate[0]; $prefix = $tryPrefix; break }
    } catch {}
}
if (-not $exe) {
    Write-Host 'Не найден Python 3.12 или 3.13. Установите его (python.org или Microsoft Store) и запустите установку снова.' -ForegroundColor Red
    exit 1
}
Write-Host "Python: $exe $($prefix -join ' ') ($version)"

$venv = Join-Path $core '.venv'
if (Test-Path $venv) { Remove-Item $venv -Recurse -Force }
& $exe @prefix -m venv $venv
$venvPython = Join-Path $venv 'Scripts\python.exe'
& $venvPython -m pip install --no-index --find-links (Join-Path $kit 'wheels') -r (Join-Path $core 'requirements.txt')
if ($LASTEXITCODE -ne 0) { Write-Host 'Не удалось установить пакеты.' -ForegroundColor Red; exit 1 }

Push-Location (Join-Path $kit 'app')
& $venvPython -X utf8 -m authoroved_core.tools.selfcheck
$status = $LASTEXITCODE
Pop-Location
if ($status -ne 0) { Write-Host 'Самопроверка не пройдена — см. сообщения выше.' -ForegroundColor Red; exit 1 }

$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Авторовед Core.lnk'))
$link.TargetPath = Join-Path $kit 'app\Запустить_Авторовед_Core.cmd'
$link.WorkingDirectory = Join-Path $kit 'app'
$link.IconLocation = (Join-Path $core 'ui\assets\avtoroved.ico') + ',0'
$link.WindowStyle = 7
$link.Save()
Write-Host 'Готово. Ярлык «Авторовед Core» создан на рабочем столе.' -ForegroundColor Green
'''

INSTALL_CMD = "@echo off\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File \"%~dp0install.ps1\"\r\npause\r\n"

README = """Авторовед Core {version} — переносной комплект для защиты

1. Скопируйте всю папку комплекта на ноутбук, например в C:\\Авторовед.
   Путь лучше без длинных вложенных папок.
2. Нужен Python 3.12 или 3.13 (python.org или Microsoft Store). Интернет не нужен.
3. Запустите «Установить.cmd». Он создаст окружение из папки wheels, проверит
   Stanza, LanguageTool и Java пробным анализом и положит ярлык на рабочий стол.
   Должна появиться строка «Готово к работе».
4. Запуск — ярлыком «Авторовед Core» или файлом app\\Запустить_Авторовед_Core.cmd.

Перед защитой: app\\authoroved_core\\.venv\\Scripts\\python.exe -m authoroved_core.tools.selfcheck
(из папки app) — за полминуты покажет, что всё на месте.

Состав: код из метки {ref}; модели Stanza; LanguageTool 6.6; Java Temurin
(GPLv2 + Classpath Exception); шрифты Golos Text и PT Serif (SIL OFL).
Материалы экспертиз и учебных работ в комплект не входят.
"""


def run(command: list[str], **kwargs):
    print("  $", " ".join(str(part) for part in command), flush=True)
    return subprocess.run(command, check=True, **kwargs)


def prepare_output(output: Path) -> None:
    """Перезаписывается только папка, созданная этим же сборщиком."""
    if output.exists():
        if not (output / MARKER).is_file():
            raise SystemExit(f"Папка {output} существует и не похожа на комплект — не трогаю.")
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / MARKER).write_text("Папка создана tools/make_portable_kit.py и может быть пересобрана.\n",
                                 encoding="utf-8")


def export_code(ref: str, app: Path) -> None:
    archive = subprocess.run(["git", "-C", str(REPO), "archive", "--format=zip", ref,
                              "authoroved_core", "Запустить_Авторовед_Core.cmd", "docs"],
                             check=True, capture_output=True).stdout
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        bundle.extractall(app)
    target = app / FREQUENCY
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO / FREQUENCY, target)


def copy_engines(app: Path) -> None:
    from authoroved_core.nlp.settings import LocalSettings
    settings = LocalSettings.load()
    local = app / "authoroved_core" / ".local"
    local.mkdir(parents=True, exist_ok=True)
    shutil.copytree(settings.stanza_dir, local / "stanza_resources")
    shutil.copytree(settings.languagetool_dir, local / "languagetool" / Path(settings.languagetool_dir).name)
    java_home = Path(settings.java_executable).resolve().parents[1]
    shutil.copytree(java_home, local / "java")


def download_wheels(wheels: Path) -> None:
    requirements = CORE / "requirements.txt"
    for version in ("3.12", "3.13"):
        run([sys.executable, "-m", "pip", "download", "--only-binary=:all:", "--platform", "win_amd64",
             "--python-version", version, "--implementation", "cp", "-r", str(requirements),
             "-d", str(wheels), "--extra-index-url", CPU_INDEX])


def main():
    from authoroved_core import __version__
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ref", default="diploma-mvp-1.0", help="метка или коммит Git, из которого берётся код")
    parser.add_argument("--output", type=Path, default=REPO.parent / f"Авторовед_комплект_{__version__}")
    args = parser.parse_args()
    output = args.output
    prepare_output(output)
    print("1/4 код из", args.ref, flush=True)
    export_code(args.ref, output / "app")
    print("2/4 Stanza, LanguageTool, Java", flush=True)
    copy_engines(output / "app")
    print("3/4 пакеты Python", flush=True)
    download_wheels(output / "wheels")
    print("4/4 установщик и инструкция", flush=True)
    (output / "install.ps1").write_text(INSTALL_PS1, encoding="utf-8-sig")
    (output / "Установить.cmd").write_bytes(INSTALL_CMD.encode("cp866"))
    (output / "ПРОЧТИ_МЕНЯ.txt").write_text(README.format(version=__version__, ref=args.ref), encoding="utf-8-sig")
    size = sum(path.stat().st_size for path in output.rglob("*") if path.is_file())
    print(f"Комплект: {output} · {size / 1024 ** 3:.2f} ГБ")


if __name__ == "__main__":
    main()
