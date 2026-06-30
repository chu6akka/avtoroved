"""
Простое хранение настроек приложения в JSON-файле рядом с программой.
"""
from __future__ import annotations
import json
import os

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
_cache: dict | None = None


def load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            _cache = json.load(f)
    except Exception:
        _cache = {}
    return _cache


def save(data: dict) -> None:
    global _cache
    current = load()
    current.update(data)
    _cache = current
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)


def get(key: str, default=None):
    return load().get(key, default)


def set(key: str, value) -> None:
    save({key: value})
