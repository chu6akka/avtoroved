"""
analyzer/yandex_speller.py — Орфографическая проверка через Яндекс.Спеллер.

API: https://speller.yandex.net/services/spellservice.json/checkText
Бесплатный, без ключа. Работает офлайн-недружественно (нужен интернет).

Коды ошибок:
  1 — орфографическая ошибка
  2 — повторяющееся слово
  3 — неправильный регистр
"""
from __future__ import annotations
import json, time, urllib.parse, urllib.request
from typing import List, Optional, Callable
from analyzer.errors import TextError

_API_URL = "https://speller.yandex.net/services/spellservice.json/checkText"
_CHUNK   = 10_000
_DELAY   = 0.25
_OPTIONS = 4 | 8          # 4=игнорировать цифры, 8=игнорировать URL

_CODE_LABEL = {1: "Орфографическая ошибка", 2: "Повторяющееся слово", 3: "Ошибка регистра"}


class YandexSpeller:
    def __init__(self):
        self._ready       = False
        self._unavailable = False

    def ensure_loaded(self, status_cb: Optional[Callable] = None) -> bool:
        if self._ready:       return True
        if self._unavailable: return False
        if status_cb: status_cb("Яндекс.Спеллер: проверка соединения...")
        try:
            self._request("проверка")
            self._ready = True
            if status_cb: status_cb("Яндекс.Спеллер ✓")
            return True
        except Exception as e:
            self._unavailable = True
            if status_cb: status_cb(f"Яндекс.Спеллер ✗ ({e})")
            return False

    @property
    def is_ready(self) -> bool:
        return self._ready

    def check(self, text: str) -> List[TextError]:
        if not self._ready:
            return []
        chunks = _split(text, _CHUNK)
        errors, offset = [], 0
        for i, chunk in enumerate(chunks):
            if i: time.sleep(_DELAY)
            try:
                matches = self._request(chunk)
                errors.extend(self._to_errors(text, chunk, matches, offset))
            except Exception:
                pass
            offset += len(chunk)
        return errors

    def _request(self, text: str) -> list:
        payload = urllib.parse.urlencode({
            "text": text, "lang": "ru,en",
            "options": _OPTIONS, "format": "plain",
        }).encode("utf-8")
        req = urllib.request.Request(
            _API_URL, data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))

    @staticmethod
    def _to_errors(full: str, chunk: str, matches: list, offset: int) -> List[TextError]:
        out = []
        for m in matches:
            code  = m.get("code", 1)
            pos   = m.get("pos", 0)
            ln    = m.get("len", 0)
            word  = m.get("word", "")
            s     = m.get("s", [])
            a, b  = offset + pos, offset + pos + ln
            cs    = max(0, a - 40); ce = min(len(full), b + 40)
            ctx   = ("…" if cs else "") + full[cs:ce].replace("\n", " ") + ("…" if ce < len(full) else "")
            sugg  = (f"→ {s[0]}" + (f" (или: {', '.join(s[1:3])})" if len(s) > 1 else "")) if s else "Проверьте написание"
            label = _CODE_LABEL.get(code, "Орфографическая ошибка")
            out.append(TextError(
                error_type="Орфографическая",
                subtype=label,
                fragment=word,
                description=f"{label}: «{word}»",
                suggestion=sugg,
                position=(a, b),
                source="YASPELL",
                context=ctx,
            ))
        return out


def _split(text: str, size: int) -> List[str]:
    if len(text) <= size:
        return [text]
    out = []
    while text:
        if len(text) <= size:
            out.append(text); break
        cut = size
        for sep in ("\n", ". ", "! ", "? "):
            p = text.rfind(sep, 0, size)
            if p > size // 2:
                cut = p + len(sep); break
        out.append(text[:cut])
        text = text[cut:]
    return out


_instance = YandexSpeller()
def get() -> YandexSpeller: return _instance
