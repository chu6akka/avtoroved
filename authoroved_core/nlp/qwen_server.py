"""Управляемый локальный llama-server для теневой проверки Qwen."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
from secrets import token_urlsafe
import subprocess
from time import monotonic, sleep
from urllib.request import urlopen


def file_sha256(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class QwenServerSettings:
    executable: Path
    model: Path
    port: int = 8089
    context_size: int = 16384
    gpu_layers: int = 99
    threads: int = 8
    startup_timeout_seconds: int = 180

    def validate(self):
        if not self.executable.is_file():
            raise FileNotFoundError(f"Не найден llama-server: {self.executable}")
        if not self.model.is_file():
            raise FileNotFoundError(f"Не найдена модель Qwen: {self.model}")
        if not 1024 <= self.port <= 65535:
            raise ValueError("Некорректный локальный порт Qwen.")


class LocalQwenServer:
    def __init__(self, settings: QwenServerSettings, log_path: str | Path):
        settings.validate()
        self.settings = settings
        self.log_path = Path(log_path)
        self.process = None
        self._log = None
        self.api_key = token_urlsafe(32)

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.settings.port}"

    def version(self) -> str:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        completed = subprocess.run(
            [str(self.settings.executable), "--version"], capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=30,
            creationflags=flags,
        )
        return (completed.stdout or completed.stderr).strip()

    def __enter__(self):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = self.log_path.open("w", encoding="utf-8")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        command = [
            str(self.settings.executable),
            "--model", str(self.settings.model),
            "--host", "127.0.0.1",
            "--port", str(self.settings.port),
            "--ctx-size", str(self.settings.context_size),
            "--parallel", "1",
            "--threads", str(self.settings.threads),
            "--n-gpu-layers", str(self.settings.gpu_layers),
            "--jinja",
            "--no-webui",
            "--api-key", self.api_key,
        ]
        self.process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=self._log,
            stderr=subprocess.STDOUT, creationflags=flags,
        )
        deadline = monotonic() + self.settings.startup_timeout_seconds
        while monotonic() < deadline:
            if self.process.poll() is not None:
                self._stop()
                raise RuntimeError(f"llama-server завершился при запуске. См. {self.log_path}")
            try:
                with urlopen(self.endpoint + "/health", timeout=2) as response:
                    if response.status == 200:
                        return self
            except OSError:
                sleep(0.5)
        self._stop()
        raise TimeoutError(f"llama-server не запустился за отведённое время. См. {self.log_path}")

    def __exit__(self, exc_type, exc, traceback):
        self._stop()

    def _stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self._log is not None:
            self._log.close()
            self._log = None
