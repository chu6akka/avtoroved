"""
analyzer/cache_manager.py — Кэширование результатов NLP-анализа.

Использует diskcache для хранения результатов на диске между сессиями.
Fallback на in-memory dict если diskcache не установлен.
Ключ кэша = MD5 от текста (без учёта пробелов по краям).
TTL по умолчанию: 30 дней.
"""
from __future__ import annotations
import hashlib
import os
from typing import Any, Optional

_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache")
_TTL = 30 * 24 * 3600  # 30 дней в секундах

try:
    import diskcache
    _cache = diskcache.Cache(_CACHE_DIR, size_limit=500_000_000)  # 500 МБ
    _BACKEND = "diskcache"
except ImportError:
    _cache: dict = {}
    _BACKEND = "memory"


def _key(text: str) -> str:
    return hashlib.md5(text.strip().encode("utf-8")).hexdigest()


def get(text: str) -> Optional[Any]:
    """Вернуть закэшированный результат или None."""
    k = _key(text)
    if _BACKEND == "diskcache":
        return _cache.get(k)
    return _cache.get(k)


def set(text: str, data: Any) -> None:
    """Сохранить результат в кэш."""
    k = _key(text)
    try:
        if _BACKEND == "diskcache":
            _cache.set(k, data, expire=_TTL)
        else:
            _cache[k] = data
    except Exception:
        pass  # кэш не критичен


def invalidate(text: str) -> None:
    """Удалить конкретную запись из кэша."""
    k = _key(text)
    try:
        if _BACKEND == "diskcache":
            _cache.delete(k)
        else:
            _cache.pop(k, None)
    except Exception:
        pass


def clear() -> None:
    """Очистить весь кэш."""
    try:
        if _BACKEND == "diskcache":
            _cache.clear()
        else:
            _cache.clear()
    except Exception:
        pass


def stats() -> dict:
    """Статистика кэша для отображения в UI."""
    try:
        if _BACKEND == "diskcache":
            return {
                "backend": "diskcache (диск)",
                "entries": len(_cache),
                "size_mb": round(_cache.volume() / 1_048_576, 1),
                "path": _CACHE_DIR,
            }
        return {
            "backend": "memory (без diskcache)",
            "entries": len(_cache),
            "size_mb": 0,
            "path": "",
        }
    except Exception:
        return {"backend": _BACKEND, "entries": 0, "size_mb": 0, "path": ""}
