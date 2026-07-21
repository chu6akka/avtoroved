"""Тесты гарантированного поиска Java (analyzer/java_locator.py)."""
import os
import shutil
import sys

import pytest

from analyzer import java_locator as jl


def _make_fake_jdk(tmp_path):
    """Каталог, похожий на JDK: bin/java.exe существует."""
    home = tmp_path / "jdk"
    (home / "bin").mkdir(parents=True)
    exe = home / "bin" / ("java.exe" if os.name == "nt" else "java")
    exe.write_bytes(b"")
    return str(home), str(exe)


def test_java_exe_detects_layout(tmp_path):
    home, exe = _make_fake_jdk(tmp_path)
    assert jl._java_exe(home) == exe
    assert jl._java_exe(str(tmp_path / "нет")) is None


def test_from_env_java_home(tmp_path, monkeypatch):
    home, exe = _make_fake_jdk(tmp_path)
    monkeypatch.setenv("JAVA_HOME", home)
    assert jl._from_env() == exe
    monkeypatch.setenv("JAVA_HOME", str(tmp_path / "мимо"))
    assert jl._from_env() is None


def test_from_config(tmp_path, monkeypatch):
    home, exe = _make_fake_jdk(tmp_path)
    from analyzer import config as app_config
    monkeypatch.setattr(app_config, "get",
                        lambda key, default=None: home if key == "java_home" else default)
    assert jl._from_config() == exe


def test_ensure_java_prepends_path(tmp_path, monkeypatch):
    """Java вне PATH → локатор находит её и добавляет в PATH процесса."""
    home, exe = _make_fake_jdk(tmp_path)
    # Пустой PATH: which('java') ничего не находит.
    monkeypatch.setenv("PATH", str(tmp_path / "пусто"))
    monkeypatch.delenv("JAVA_HOME", raising=False)
    assert shutil.which("java") is None
    # Подсовываем источник «конфиг».
    from analyzer import config as app_config
    monkeypatch.setattr(app_config, "get",
                        lambda key, default=None: home if key == "java_home" else default)
    found = jl.ensure_java_in_path()
    assert found and os.path.normcase(found) == os.path.normcase(exe)
    # Каталог добавлен в PATH процесса — which теперь находит java.
    assert shutil.which("java") is not None


@pytest.mark.skipif(sys.platform != "win32", reason="реестр Windows")
def test_registry_source_on_this_machine():
    """
    Интеграционная проверка: если в реестре есть запись Adoptium (как на
    машине разработки), локатор обязан вернуть существующий java.exe.
    """
    try:
        import winreg
        winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                       r"SOFTWARE\Eclipse Adoptium\JDK").Close()
    except OSError:
        pytest.skip("Adoptium в реестре нет")
    exe = jl._from_registry()
    assert exe is not None and os.path.isfile(exe)
