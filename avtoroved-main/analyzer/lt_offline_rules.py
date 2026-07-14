"""
analyzer/lt_offline_rules.py — офлайн-исполнитель импортированных правил LT.

База: data/lt_rules_ru.json — простые правила grammar.xml (чистый текст/regex,
без теггера) и пары замен replace.txt из открытого репозитория LanguageTool
(LGPL-2.1-or-later, атрибуция в meta файла). Импорт/обновление —
tools/import_lt_rules.py. Исполнение не требует ни Java, ни интернета.

Используется профилем протокола ТОЛЬКО когда локальный LT-сервер недоступен:
при живом LT те же правила (те же id) сработали бы дважды.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import List, Optional

from analyzer.errors import TextError

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                         "data", "lt_rules_ru.json")

_loaded = False
_compiled_rules: list = []      # (regex, anchors|None, id, name, error_type, message)
_replace_rx: Optional[re.Pattern] = None   # одна альтернация всех замен
_replace_map: dict = {}         # нормализованная фраза → (correct, note)
_meta: dict = {}
_data_hash = ""

# Чисто литеральная альтернация (слова через |) — можно взять как якоря.
_PLAIN_ALT_RE = re.compile(r"^[а-яёА-ЯЁa-zA-Z0-9|]+$")


def _anchors_for(tokens: list[dict]) -> Optional[list]:
    """
    Литеральные якоря правила: правило запускается, только если хотя бы один
    якорь есть в тексте (быстрый substring-префильтр). None — якорей нет,
    правило гоняется всегда.
    """
    best: Optional[list] = None
    for tok in tokens:
        text = tok["text"].lower()
        if not tok.get("regexp"):
            if len(text) >= 3:
                # Один литеральный токен — лучший якорь, берём самый длинный.
                if best is None or (len(best) > 1) or len(best[0]) < len(text):
                    best = [text]
        elif best is None and _PLAIN_ALT_RE.match(text):
            alts = [a for a in text.split("|") if len(a) >= 3]
            if alts and len(alts) == len(text.split("|")):
                best = alts
    return best


def _boundary(pattern: str, first_ch: str, last_ch: str) -> str:
    if first_ch.isalnum() or first_ch == "_":
        pattern = r"\b" + pattern
    if last_ch.isalnum() or last_ch == "_":
        pattern = pattern + r"\b"
    return pattern


def _compile_tokens(tokens: list[dict]) -> Optional[re.Pattern]:
    parts: list[str] = []
    for i, tok in enumerate(tokens):
        text = tok["text"]
        piece = f"(?:{text})" if tok.get("regexp") else re.escape(text)
        if i:
            # Пунктуационный токен может прилегать без пробела.
            prev_last = tokens[i - 1]["text"][-1:]
            cur_first = text[:1]
            sep = r"\s*" if (not cur_first.isalnum()
                             or not prev_last.isalnum()) else r"\s+"
            parts.append(sep)
        parts.append(piece)
    body = "".join(parts)
    first = tokens[0]["text"][:1] or "x"
    last = tokens[-1]["text"][-1:] or "x"
    try:
        return re.compile(_boundary(body, first, last))
    except re.error:
        return None


def _load() -> None:
    global _loaded, _meta, _data_hash, _replace_rx
    if _loaded:
        return
    _loaded = True
    try:
        raw = open(DATA_PATH, "rb").read()
    except OSError:
        return
    _data_hash = hashlib.sha256(raw).hexdigest()[:12]
    data = json.loads(raw.decode("utf-8"))
    _meta.update(data.get("meta", {}))
    for r in data.get("rules", []):
        flags = 0 if r.get("case_sensitive") else re.IGNORECASE
        rx = _compile_tokens(r["tokens"])
        if rx is None:
            continue
        try:
            rx = re.compile(rx.pattern, flags)
        except re.error:
            continue
        _compiled_rules.append(
            (rx, _anchors_for(r["tokens"]), r["id"], r.get("name", ""),
             r.get("error_type", "Лексическая"), r.get("message", "")))
    # Все замены — одна альтернация (длинные фразы раньше коротких).
    alts = []
    for rep in sorted(data.get("replacements", []),
                      key=lambda x: -len(x["wrong"])):
        norm = re.sub(r"\s+", " ", rep["wrong"].lower())
        _replace_map[norm] = (rep["correct"], rep.get("note", ""))
        alts.append(re.escape(rep["wrong"]).replace(r"\ ", r"\s+"))
    if alts:
        try:
            _replace_rx = re.compile(
                r"\b(?:" + "|".join(alts) + r")\b", re.IGNORECASE)
        except re.error:
            _replace_rx = None


def data_version() -> str:
    """Версия базы для audit_log: хэш файла + дата импорта."""
    _load()
    return (f"{_data_hash} ({_meta.get('imported_at', '?')})"
            if _data_hash else "нет базы")


def rules_count() -> tuple[int, int]:
    _load()
    return len(_compiled_rules), len(_replace_map)


def _ctx(text: str, start: int, end: int, window: int = 45) -> str:
    cs, ce = max(0, start - window), min(len(text), end + window)
    return (("…" if cs > 0 else "") + text[cs:ce].replace("\n", " ")
            + ("…" if ce < len(text) else ""))


def check(text: str) -> List[TextError]:
    """Прогнать текст по импортированным правилам и заменам."""
    _load()
    if not text:
        return []
    out: List[TextError] = []
    text_low = text.lower()
    for rx, anchors, rid, name, etype, message in _compiled_rules:
        # Быстрый префильтр: без якоря в тексте правило не запускается.
        if anchors is not None and not any(a in text_low for a in anchors):
            continue
        for m in rx.finditer(text):
            out.append(TextError(
                error_type=etype,
                subtype=(name or rid)[:80],
                fragment=m.group(0)[:80],
                description=message or name or rid,
                suggestion="См. описание правила",
                position=(m.start(), m.end()),
                rule_ref=f"LTX:{rid}",
                source="LTX",
                context=_ctx(text, m.start(), m.end()),
                significance="средняя",
            ))
    if _replace_rx is not None:
        for m in _replace_rx.finditer(text):
            norm = re.sub(r"\s+", " ", m.group(0).lower())
            correct, note = _replace_map.get(norm, ("", ""))
            if not correct:
                continue
            out.append(TextError(
                error_type="Орфографическая",
                subtype=note or "Замена по словарю LT",
                fragment=m.group(0),
                description=f"«{m.group(0)}» → «{correct}»",
                suggestion=f"→ {correct}",
                position=(m.start(), m.end()),
                rule_ref="LTX:REPLACE",
                source="LTX",
                context=_ctx(text, m.start(), m.end()),
                significance="средняя",
            ))
    return out
