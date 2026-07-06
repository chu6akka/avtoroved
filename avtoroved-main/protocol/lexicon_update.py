"""
protocol/lexicon_update.py — обновление локальных словарных баз из интернета.

Принципы (важно для судебной воспроизводимости):
  • обновление происходит ТОЛЬКО по явной команде пользователя, никогда фоном;
  • перед заменой файл словаря бэкапится рядом (*.bak-ГГГГММДД-ЧЧММСС);
  • новая база валидируется (минимум записей) до записи;
  • метаданные обновления (источник, дата, sha256, число записей) пишутся в
    data/lexicons_meta.json и в audit_log — в каждом отчёте видно, на какой
    версии словаря шёл анализ.

Реестр источников расширяемый: сейчас RuSentiLex (тональный словарь,
labinform.ru). Новые источники добавляются записью в SOURCES + конвертером.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.request
from datetime import datetime
from typing import Callable, Optional

_META_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                          "data", "lexicons_meta.json")


# ── конвертеры «сырой текст → формат движка» ─────────────────────────────────
def parse_rusentilex(raw: str) -> dict:
    """
    RuSentiLex (labinform.ru, txt): строки «слово, POS, лемма, тональность,
    тип[, …]», комментарии начинаются с «!». Целевой формат senti_engine:
    {лемма: [тональность, тип, POS]}.
    """
    out: dict[str, list] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("!"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        _word, pos, lemma, sentiment, typ = parts[:5]
        if not lemma or not sentiment:
            continue
        out[lemma.lower()] = [sentiment, typ, pos]
    return out


# ── реестр источников ────────────────────────────────────────────────────────
def _senti_target() -> str:
    from analyzer import senti_engine
    return senti_engine._DICT_PATH


SOURCES: dict[str, dict] = {
    "rusentilex": {
        "name": "RuSentiLex — тональный словарь (labinform.ru)",
        "url": "https://www.labinform.ru/pub/rusentilex/rusentilex_2017.txt",
        "target": _senti_target,          # callable → путь целевого файла
        "converter": parse_rusentilex,
        "min_entries": 8000,              # защита от битой загрузки
        "encoding": "utf-8",
    },
}


# ── метаданные ───────────────────────────────────────────────────────────────
def read_meta() -> dict:
    try:
        with open(_META_PATH, encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return {}


def _write_meta(meta: dict) -> None:
    os.makedirs(os.path.dirname(_META_PATH), exist_ok=True)
    with open(_META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


# ── обновление ───────────────────────────────────────────────────────────────
def _default_fetcher(url: str, encoding: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Avtoroved/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode(encoding, errors="replace")


def update_source(
    key: str,
    status_cb: Optional[Callable[[str], None]] = None,
    fetcher: Optional[Callable[[str, str], str]] = None,
    log_to_db: bool = True,
) -> dict:
    """
    Обновить один словарь из реестра. Возвращает сводку
    {key, entries, sha256, target, backup}. Бросает исключение при любом сбое —
    целевой файл в этом случае не изменяется.
    """
    if key not in SOURCES:
        raise ValueError(f"Неизвестный источник словаря: {key}")
    src = SOURCES[key]
    target = src["target"]() if callable(src["target"]) else src["target"]

    def _status(msg: str):
        if status_cb:
            status_cb(msg)

    _status(f"Загрузка: {src['url']}")
    raw = (fetcher or _default_fetcher)(src["url"], src.get("encoding", "utf-8"))

    _status("Конвертация и валидация...")
    data = src["converter"](raw)
    if len(data) < src["min_entries"]:
        raise ValueError(
            f"Загруженный словарь подозрительно мал: {len(data)} записей "
            f"(ожидалось ≥{src['min_entries']}) — целевой файл не изменён.")

    # Бэкап прежней версии.
    backup = ""
    if os.path.exists(target):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = f"{target}.bak-{stamp}"
        shutil.copy2(target, backup)

    _status("Запись новой базы...")
    payload = json.dumps(data, ensure_ascii=False)
    with open(target, "w", encoding="utf-8") as f:
        f.write(payload)
    sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    meta = read_meta()
    meta[key] = {
        "name": src["name"], "url": src["url"],
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "entries": len(data), "sha256": sha, "backup": backup,
    }
    _write_meta(meta)

    if log_to_db:
        try:
            from protocol import db as protocol_db
            from protocol import PROGRAM_VERSION
            protocol_db.ProtocolDB().log_action(
                "обновлён словарь", project_id=None,
                details={"источник": key, "url": src["url"],
                         "записей": len(data), "sha256": sha,
                         "бэкап": backup or None},
                program_version=PROGRAM_VERSION)
        except Exception:
            pass

    _status("Готово.")
    return {"key": key, "entries": len(data), "sha256": sha,
            "target": target, "backup": backup}
