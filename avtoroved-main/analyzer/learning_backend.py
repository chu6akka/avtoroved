"""
analyzer/learning_backend.py — SBERT-эмбеддинги для сравнения текстов.

Модель: cointegrated/rubert-tiny2 (~120 MB, русский язык)
Загружается по запросу (кнопка в sidebar), кешируется HuggingFace локально.

Использование:
    lb = learning_backend.get()
    lb.load_sbert()
    sim = lb.vector_similarity(lemmas1, lemmas2)  # float 0..1
"""
from __future__ import annotations
import logging
from typing import List

_SBERT_MODEL_NAME = "cointegrated/rubert-tiny2"


class LearningBackend:
    """SBERT-бэкенд для семантического сходства текстов."""

    def __init__(self):
        self._sbert = None
        self._sbert_ready = False

    def load_sbert(self, model_name: str = _SBERT_MODEL_NAME, status_cb=None) -> bool:
        """Загрузить SBERT-модель (скачивается ~120 MB при первом запуске)."""
        try:
            if status_cb:
                status_cb(f"Загрузка SBERT ({model_name})…")
            from sentence_transformers import SentenceTransformer
            self._sbert = SentenceTransformer(model_name)
            self._sbert_ready = True
            if status_cb:
                status_cb("SBERT загружен — семантическое сходство активно")
            return True
        except ImportError:
            if status_cb:
                status_cb("sentence-transformers не установлен: pip install sentence-transformers")
            return False
        except Exception as e:
            if status_cb:
                status_cb(f"Ошибка загрузки SBERT: {e}")
            return False

    def vector_similarity(self, lemmas1: List[str], lemmas2: List[str]) -> float:
        """Косинусное сходство двух текстов через SBERT. Возвращает 0.0 если не загружен."""
        if not self._sbert_ready or self._sbert is None:
            return 0.0
        try:
            import numpy as np
            t1 = " ".join(lemmas1)
            t2 = " ".join(lemmas2)
            if not t1.strip() or not t2.strip():
                return 0.0
            embs = self._sbert.encode([t1, t2], convert_to_numpy=True, show_progress_bar=False)
            v1, v2 = embs[0], embs[1]
            cos = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9))
            return round(max(0.0, min(1.0, cos)), 3)
        except Exception:
            return 0.0

    @property
    def sbert_ready(self) -> bool:
        return self._sbert_ready


# Singleton
_instance = LearningBackend()


def get() -> LearningBackend:
    return _instance
