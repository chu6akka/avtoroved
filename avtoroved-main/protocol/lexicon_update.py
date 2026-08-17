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


def parse_opensubtitles_freq(raw: str) -> dict:
    """
    Частотный список словоформ OpenSubtitles-2018 (проект hermitdave/
    FrequencyWords, строки «форма частота») → лемматизированный частотный
    словарь в формате freq_engine: {лемма: [ранг, ipm, часть речи]}.

    Формы сводятся к леммам через pymorphy3 (уже используется в проекте),
    частоты форм суммируются по лемме, затем считается ipm и ранг.
    Источник — субтитры: живая разговорная и сетевая речь, которой нет в
    словаре Ляшевской–Шарова 2009 г. Это ПАРАЛЛЕЛЬНАЯ норма, базовую
    (НКРЯ) она не заменяет.
    """
    import pymorphy3
    morph = pymorphy3.MorphAnalyzer()

    counts: dict[str, int] = {}
    pos_of: dict[str, str] = {}
    form_to_lemma: dict[str, str] = {}
    total = 0
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        form, num = parts[0].strip().lower(), parts[1]
        if not num.isdigit() or not form:
            continue
        # Только кириллические словоформы (латиница/цифры — шум списка).
        if not all("а" <= ch <= "я" or ch in "ё-" for ch in form):
            continue
        n = int(num)
        parse = morph.parse(form)
        if not parse:
            continue
        p = parse[0]
        pos = str(p.tag.POS or "")
        # У неизменяемых частей речи нормальная форма pymorphy3 уходит в
        # другую лексему («ладно» → «ладный»), а Stanza в тексте даёт саму
        # форму. Чтобы поиск по лемме совпадал, оставляем форму как есть.
        if pos in ("ADVB", "PRED", "INTJ", "PRCL", "CONJ", "PREP"):
            lemma = form
        else:
            lemma = (p.normal_form or form).lower()
        counts[lemma] = counts.get(lemma, 0) + n
        pos_of.setdefault(lemma, pos.lower())
        form_to_lemma.setdefault(form, lemma)
        total += n

    if not total:
        return {}
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    out = {
        lemma: [rank, round(n / total * 1_000_000, 2), pos_of.get(lemma, "")]
        for rank, (lemma, n) in enumerate(ranked, start=1)
    }
    # Дополнительные ключи по исходным формам: лемматизаторы расходятся
    # (pymorphy3 сводит «ладно» к «ладный», Stanza в тексте даёт «ладно»),
    # и без этого частые слова не находились бы. Значение то же, что у леммы:
    # таблица отвечает на вопрос «насколько употребительно это слово».
    for form, lemma in form_to_lemma.items():
        if form not in out and lemma in out:
            out[form] = out[lemma]
    return out


# ── реестр источников ────────────────────────────────────────────────────────
def _senti_target() -> str:
    from analyzer import senti_engine
    return senti_engine._DICT_PATH


def _freq_modern_target() -> str:
    from analyzer import freq_engine
    return freq_engine.MODERN_DICT_PATH


SOURCES: dict[str, dict] = {
    "rusentilex": {
        "name": "RuSentiLex — тональный словарь (labinform.ru)",
        "url": "https://www.labinform.ru/pub/rusentilex/rusentilex_2017.txt",
        "target": _senti_target,          # callable → путь целевого файла
        "converter": parse_rusentilex,
        "min_entries": 8000,              # защита от битой загрузки
        "encoding": "utf-8",
    },
    "freq_modern": {
        "name": "Современная частотная норма (OpenSubtitles-2018, разговорная "
                "и сетевая речь) — дополняет НКРЯ 2009, не заменяет",
        "url": "https://raw.githubusercontent.com/hermitdave/FrequencyWords/"
               "master/content/2018/ru/ru_50k.txt",
        "target": _freq_modern_target,
        "converter": parse_opensubtitles_freq,
        "min_entries": 10000,
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
