"""
analyzer/lt_checker.py — Проверка текста через LanguageTool.

Стратегия подключения:
  1. Локальный сервер LanguageTool (требует Java 8+).
  2. Прямые HTTP-запросы к публичному API languagetool.org
     (не требует Java, только интернет-соединение).
  3. Если ничего не доступно — check() возвращает [] без исключения.

Singleton: один экземпляр на весь процесс (lazy init через ensure_loaded).
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import List, Callable, Optional

from analyzer.errors import TextError

# Маппинг категорий LT → типы ошибок проекта
_CATEGORY_MAP = {
    "TYPOS":            "Орфографическая",
    "SPELLING":         "Орфографическая",
    "GRAMMAR":          "Грамматическая",
    "PUNCTUATION":      "Пунктуационная",
    "STYLE":            "Стилистическая",
    "TYPOGRAPHY":       "Пунктуационная",
    "REDUNDANCY":       "Лексическая",
    "SEMANTICS":        "Лексическая",
    "CASING":           "Орфографическая",
    "COLLOQUIALISMS":   "Лексическая",
    "CONFUSED_WORDS":   "Лексическая",
}

_SKIP_RULES = {
    "WHITESPACE_RULE",
    "COMMA_PARENTHESIS_WHITESPACE",
    "DOUBLE_PUNCTUATION",
}

# Публичный API — разбиваем текст на куски до этого размера
_CHUNK_SIZE = 2000
# Задержка между запросами (публичный API ограничивает частоту)
_REQUEST_DELAY = 0.5


class LTChecker:
    """Обёртка над LanguageTool для русского языка."""

    def __init__(self):
        self._tool = None          # language_tool_python.LanguageTool (local)
        self._ready = False
        self._unavailable = False
        self._mode = ""            # "local" / "http" / ""
        self._error_msg = ""

    # ── Инициализация ────────────────────────────────────────────────────────

    def ensure_loaded(self, status_callback: Optional[Callable] = None) -> bool:
        """Инициализировать LanguageTool (lazy). Возвращает True если готов."""
        if self._ready:
            return True
        if self._unavailable:
            return False

        # ── 1) Локальный сервер (требует Java) ──────────────────────────────
        if status_callback:
            status_callback("LanguageTool: попытка запустить локальный сервер...")
        try:
            import language_tool_python
            self._tool = language_tool_python.LanguageTool('ru-RU')
            self._ready = True
            self._mode = "local"
            if status_callback:
                status_callback("LanguageTool ✓ (локальный сервер)")
            return True
        except Exception as e_local:
            local_err = str(e_local)[:120]

        # ── 2) Прямые HTTP-запросы к api.languagetool.org ───────────────────
        if status_callback:
            status_callback("LanguageTool: Java недоступна, проверяю публичный API...")
        try:
            self._http_check("проверка связи с сервером")
            self._ready = True
            self._mode = "http"
            if status_callback:
                status_callback("LanguageTool ✓ (публичный API, HTTP)")
            return True
        except Exception as e_http:
            self._unavailable = True
            self._error_msg = (
                f"Локальный: {local_err}; "
                f"HTTP API: {str(e_http)[:80]}"
            )
            if status_callback:
                status_callback(
                    "LanguageTool ✗ — нет Java и нет доступа к сети. "
                    "Установите Java: https://adoptium.net"
                )
            return False

    def _http_check(self, text: str) -> List[dict]:
        """Отправить текст к публичному API и вернуть список matches."""
        url = "https://api.languagetool.org/v2/check"
        payload = urllib.parse.urlencode({
            "language": "ru-RU",
            "text": text,
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("matches", [])

    # ── Служебные ────────────────────────────────────────────────────────────

    def reset(self):
        """Сбросить состояние — позволяет повторную попытку подключения."""
        if self._tool is not None:
            try:
                self._tool.close()
            except Exception:
                pass
            self._tool = None
        self._ready = False
        self._unavailable = False
        self._mode = ""
        self._error_msg = ""

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def status_text(self) -> str:
        if self._ready:
            icon = "🌐" if self._mode == "http" else "⚙"
            label = "публичный API" if self._mode == "http" else "локальный"
            return f"{icon} LT: {label}"
        if self._unavailable:
            return "✗ LT: нет Java/сети"
        return "⏳ LT: инициализация..."

    # ── Проверка текста ───────────────────────────────────────────────────────

    def check(self, text: str) -> List[TextError]:
        """Проверить текст. Возвращает [] если LT недоступен."""
        if not self._ready:
            return []

        if self._mode == "local":
            return self._check_local(text)
        else:
            return self._check_http(text)

    def _check_local(self, text: str) -> List[TextError]:
        """Проверка через language_tool_python (локальный сервер)."""
        try:
            matches = self._tool.check(text)
        except Exception:
            return []
        return self._matches_to_errors(text, matches, use_lt_object=True)

    def _check_http(self, text: str) -> List[TextError]:
        """Проверка через прямые HTTP-запросы к api.languagetool.org.

        Длинные тексты разбиваются на куски с учётом границ предложений.
        """
        all_errors: List[TextError] = []

        # Разбить на куски по _CHUNK_SIZE символов (по границам предложений)
        chunks = self._split_text(text, _CHUNK_SIZE)
        offset = 0

        for i, chunk in enumerate(chunks):
            if i > 0:
                time.sleep(_REQUEST_DELAY)
            try:
                matches = self._http_check(chunk)
            except Exception:
                continue
            errors = self._matches_to_errors(chunk, matches,
                                             use_lt_object=False,
                                             global_offset=offset)
            all_errors.extend(errors)
            offset += len(chunk)

        return all_errors

    @staticmethod
    def _split_text(text: str, chunk_size: int) -> List[str]:
        """Разбить текст на куски не длиннее chunk_size по границам предложений."""
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        while text:
            if len(text) <= chunk_size:
                chunks.append(text)
                break
            # Найти ближайшую границу предложения не позже chunk_size
            cut = chunk_size
            for sep in ('.', '!', '?', '\n'):
                pos = text.rfind(sep, 0, chunk_size)
                if pos > chunk_size // 2:
                    cut = pos + 1
                    break
            chunks.append(text[:cut])
            text = text[cut:]
        return chunks

    def _matches_to_errors(self, text: str, matches,
                            use_lt_object: bool,
                            global_offset: int = 0) -> List[TextError]:
        """Конвертировать matches (LT-объекты или dicts) в List[TextError]."""
        errors: List[TextError] = []

        for m in matches:
            # Унифицированный доступ к полям (объект или dict)
            if use_lt_object:
                rule_id  = getattr(m, 'ruleId', '') or ''
                category = getattr(m, 'category', '') or ''
                message  = getattr(m, 'message', '') or ''
                offset   = m.offset
                length   = m.errorLength
                replacements = [r for r in (m.replacements or [])]
            else:
                rule_id  = m.get('rule', {}).get('id', '')
                category = m.get('rule', {}).get('category', {}).get('id', '')
                message  = m.get('message', '')
                offset   = m.get('offset', 0)
                length   = m.get('length', 0)
                replacements = [r['value'] for r in m.get('replacements', [])
                                if isinstance(r, dict) and 'value' in r]

            if rule_id in _SKIP_RULES:
                continue

            error_type = _CATEGORY_MAP.get(category.upper(), "LanguageTool")

            start = offset
            end   = offset + length
            fragment = text[start:end] if end <= len(text) else text[start:]

            # Контекст ±45 символов
            cs = max(0, start - 45)
            ce = min(len(text), end + 45)
            ctx = (
                ("…" if cs > 0 else "")
                + text[cs:ce].replace('\n', ' ')
                + ("…" if ce < len(text) else "")
            )

            # Рекомендация
            if replacements:
                suggestion = f"→ {replacements[0]}"
                if len(replacements) > 1:
                    suggestion += f" (или: {', '.join(replacements[1:3])})"
            else:
                suggestion = "Исправьте вручную"

            errors.append(TextError(
                error_type=error_type,
                subtype=message[:80] if message else rule_id,
                fragment=fragment,
                description=message or rule_id,
                suggestion=suggestion,
                position=(global_offset + start, global_offset + end),
                rule_ref=f"LT:{rule_id}",
                source="LT",
                context=ctx,
            ))

        return errors

    def close(self) -> None:
        """Освободить ресурсы локального сервера."""
        if self._tool is not None:
            try:
                self._tool.close()
            except Exception:
                pass


# Singleton
_instance = LTChecker()


def get() -> LTChecker:
    return _instance
