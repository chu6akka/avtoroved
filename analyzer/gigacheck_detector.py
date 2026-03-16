"""
GigaCheck интеграция — определение ИИ-сгенерированных фрагментов текста.

Использует открытую модель iitolstykh/GigaCheck-Detector-Multi с HuggingFace.
Модель анализирует текст и возвращает интервалы с вероятностью ИИ-генерации.

Установка:
    pip install transformers torch
    pip install git+https://github.com/ai-forever/gigacheck
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Callable, Optional


MODEL_NAME = "iitolstykh/GigaCheck-Detector-Multi"


@dataclass
class GigaCheckResult:
    """Результат анализа ИИ-генерации."""
    overall_score: float                     # 0.0–1.0 (вероятность ИИ)
    ai_intervals: List[tuple] = field(default_factory=list)  # [(start, end, score), ...]
    text_length: int = 0
    model_name: str = MODEL_NAME
    error: Optional[str] = None


class GigaCheckDetector:
    """
    Обёртка над GigaCheck-Detector-Multi.
    Ленивая загрузка модели (~1–4 ГБ).
    """

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

    def load(self, status_callback: Optional[Callable[[str], None]] = None) -> bool:
        """
        Загрузить модель. Возвращает True при успехе.
        status_callback(msg) вызывается с текущим статусом.
        """
        if self._ready:
            return True

        if status_callback:
            status_callback(f"Загрузка модели {MODEL_NAME}...")
            status_callback("Первая загрузка может занять несколько минут (~1–4 ГБ).")

        try:
            from transformers import AutoModel
            import torch

            if status_callback:
                status_callback("Загрузка весов модели...")

            device = "cuda:0" if _cuda_available() else "cpu"
            self._model = AutoModel.from_pretrained(
                MODEL_NAME,
                trust_remote_code=True,
                device_map=device,
                torch_dtype=torch.float32,
            )
            self._ready = True
            self._load_error = None
            if status_callback:
                status_callback(f"GigaCheck готов (устройство: {device})")
            return True

        except ImportError as e:
            msg = (f"Не установлены зависимости: {e}\n"
                   "Установите: pip install transformers torch\n"
                   "и: pip install git+https://github.com/ai-forever/gigacheck")
            self._load_error = msg
            if status_callback:
                status_callback(f"Ошибка: {msg}")
            return False

        except Exception as e:
            msg = f"Ошибка загрузки модели: {e}"
            self._load_error = msg
            if status_callback:
                status_callback(msg)
            return False

    def detect(self, text: str,
               conf_threshold: float = 0.5) -> GigaCheckResult:
        """
        Определить ИИ-сгенерированные фрагменты в тексте.

        Args:
            text: Анализируемый текст.
            conf_threshold: Порог уверенности для интервалов (0.0–1.0).

        Returns:
            GigaCheckResult с интервалами и общим score.
        """
        if not self._ready or self._model is None:
            return GigaCheckResult(
                overall_score=0.0,
                error="Модель не загружена. Нажмите «Загрузить модель»."
            )

        if not text or not text.strip():
            return GigaCheckResult(overall_score=0.0, text_length=0)

        try:
            output = self._model([text], conf_interval_thresh=conf_threshold)

            ai_intervals = []
            if hasattr(output, 'ai_intervals') and output.ai_intervals:
                raw = output.ai_intervals[0] if isinstance(output.ai_intervals[0], list) else output.ai_intervals
                for item in raw:
                    if isinstance(item, (tuple, list)) and len(item) >= 3:
                        start, end, score = item[0], item[1], item[2]
                        ai_intervals.append((int(start), int(end), float(score)))

            overall_score = _compute_overall_score(ai_intervals, len(text))

            return GigaCheckResult(
                overall_score=overall_score,
                ai_intervals=ai_intervals,
                text_length=len(text),
            )

        except Exception as e:
            return GigaCheckResult(
                overall_score=0.0,
                error=f"Ошибка анализа: {e}"
            )

    def unload(self):
        """Выгрузить модель из памяти."""
        if self._model is not None:
            try:
                import torch
                del self._model
                torch.cuda.empty_cache()
            except Exception:
                pass
        self._model = None
        self._ready = False


def _cuda_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def _compute_overall_score(intervals: List[tuple], text_len: int) -> float:
    """Вычислить общий процент ИИ-контента по интервалам."""
    if not intervals or text_len == 0:
        return 0.0
    total_ai_chars = sum(max(0, end - start) for start, end, _ in intervals)
    return min(1.0, total_ai_chars / text_len)
