"""
GigaCheck интеграция — определение ИИ-сгенерированных фрагментов текста.

Использует открытую модель iitolstykh/GigaCheck-Detector-Multi с HuggingFace.
Требуется пакет gigacheck:
    pip install git+https://github.com/ai-forever/gigacheck
    pip install transformers torch
"""
from __future__ import annotations
import subprocess
import sys
from dataclasses import dataclass, field
from typing import List, Callable, Optional


MODEL_NAME = "iitolstykh/GigaCheck-Detector-Multi"

_INSTALL_CMD = [
    sys.executable, "-m", "pip", "install", "--quiet",
    "git+https://github.com/ai-forever/gigacheck"
]


@dataclass
class GigaCheckResult:
    """Результат анализа ИИ-генерации."""
    overall_score: float
    ai_intervals: List[tuple] = field(default_factory=list)   # [(start, end, score)]
    text_length: int = 0
    model_name: str = MODEL_NAME
    error: Optional[str] = None


class GigaCheckDetector:
    """Обёртка над GigaCheck-Detector-Multi. Ленивая загрузка."""

    def __init__(self):
        self._model = None
        self._ready = False
        self._load_error: Optional[str] = None

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    # ─── Загрузка ──────────────────────────────────────────────────────────────
    def load(self, status_callback: Optional[Callable[[str], None]] = None) -> bool:
        if self._ready:
            return True

        cb = status_callback or (lambda _: None)

        # 1. Проверить наличие gigacheck (опционально — не блокирует загрузку)
        cb("Проверка зависимостей...")
        if not _gigacheck_installed():
            cb("Пакет gigacheck не найден — попытка установки из GitHub...")
            _install_gigacheck(cb)   # не прерываемся при ошибке

        # 2. Загрузить модель
        cb(f"Загрузка модели {MODEL_NAME}...")
        cb("Первый запуск: скачивание весов (~1–4 ГБ) — это займёт несколько минут.")
        try:
            from transformers import AutoModel
            import torch

            device = "cuda:0" if _cuda_available() else "cpu"
            cb(f"Устройство: {device}. Загрузка весов...")

            self._model = AutoModel.from_pretrained(
                MODEL_NAME,
                trust_remote_code=True,
                device_map=device,
                torch_dtype=torch.float32,
            )
            self._ready = True
            self._load_error = None
            cb(f"✓ GigaCheck готов (устройство: {device})")
            return True

        except Exception as e:
            self._load_error = f"Ошибка загрузки модели:\n{e}"
            cb(self._load_error)
            return False

    # ─── Анализ ────────────────────────────────────────────────────────────────
    def detect(self, text: str, conf_threshold: float = 0.5) -> GigaCheckResult:
        if not self._ready or self._model is None:
            return GigaCheckResult(
                overall_score=0.0,
                error="Модель не загружена. Нажмите «Загрузить модель».")

        if not text or not text.strip():
            return GigaCheckResult(overall_score=0.0, text_length=0)

        try:
            output = self._model([text], conf_interval_thresh=conf_threshold)

            ai_intervals = []
            # Парсим вывод — формат может варьироваться по версиям модели
            raw_intervals = None
            if hasattr(output, 'ai_intervals'):
                raw_intervals = output.ai_intervals
            elif isinstance(output, (list, tuple)) and len(output) > 0:
                raw_intervals = output[0] if isinstance(output[0], list) else output

            if raw_intervals:
                # Обработка списка списков
                items = raw_intervals[0] if (
                    isinstance(raw_intervals, list)
                    and raw_intervals
                    and isinstance(raw_intervals[0], list)
                ) else raw_intervals
                for item in items:
                    if isinstance(item, (tuple, list)) and len(item) >= 3:
                        ai_intervals.append(
                            (int(item[0]), int(item[1]), float(item[2])))
                    elif isinstance(item, dict):
                        s = item.get("start", item.get("begin", 0))
                        e = item.get("end", 0)
                        sc = item.get("score", item.get("prob", 0.5))
                        ai_intervals.append((int(s), int(e), float(sc)))

            overall = _compute_overall_score(ai_intervals, len(text))
            return GigaCheckResult(
                overall_score=overall,
                ai_intervals=ai_intervals,
                text_length=len(text))

        except Exception as e:
            return GigaCheckResult(overall_score=0.0, error=f"Ошибка анализа: {e}")

    def unload(self):
        if self._model is not None:
            try:
                import torch
                del self._model
                torch.cuda.empty_cache()
            except Exception:
                pass
        self._model = None
        self._ready = False


# ─── Утилиты ───────────────────────────────────────────────────────────────────

def _gigacheck_installed() -> bool:
    try:
        import gigacheck  # noqa: F401
        return True
    except ImportError:
        return False


def _install_gigacheck(cb: Callable[[str], None]) -> bool:
    """Автоустановка gigacheck из GitHub."""
    try:
        proc = subprocess.run(
            _INSTALL_CMD,
            capture_output=True, text=True, timeout=300)
        if proc.returncode == 0:
            cb("✓ gigacheck установлен")
            return True
        else:
            cb(f"pip вернул код {proc.returncode}: {proc.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        cb("Превышено время ожидания установки (5 мин).")
        return False
    except Exception as e:
        cb(f"Ошибка установки: {e}")
        return False


def _cuda_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def _compute_overall_score(intervals: List[tuple], text_len: int) -> float:
    if not intervals or text_len == 0:
        return 0.0
    total = sum(max(0, end - start) for start, end, _ in intervals)
    return min(1.0, total / text_len)
