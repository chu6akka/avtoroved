#!/usr/bin/env python3
"""
scripts/build_freq_dict.py
Загрузка и конвертация частотного словаря НКРЯ (Ляшевская О.Н., Шаров С.А., 2009)
в формат data/freq/freqrnc.json для freq_engine.py.

Источники (пробует по порядку):
  1. Локальный файл data/freq/freqrnc2011.csv  (положить вручную)
  2. https://ruscorpora.ru/downloads/freqrnc2011.zip
  3. https://raw.githubusercontent.com/akutuzov/universal-pos-tags/master/data/freqrnc2011.csv (mirror)

CSV-формат (tab-separated):
  Lemma  \t  PoS  \t  Freq(ipm)  \t  Rank  \t  Dispersion
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
import urllib.request
import zipfile

_ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUTDIR    = os.path.join(_ROOT, "data", "freq")
_OUTFILE   = os.path.join(_OUTDIR, "freqrnc.json")
_LOCAL_CSV = os.path.join(_OUTDIR, "freqrnc2011.csv")

# Известные источники (пробуем по порядку)
_SOURCES = [
    ("local",  _LOCAL_CSV),
    # Рабочий источник: Шаров С.А. (Ноябрьский 2011, ~32к лемм, ipm ≥ 1)
    # Формат: rank ipm word pos
    ("zip_sharov", "https://bokrcorpora.narod.ru/frqlist/lemma.num.zip"),
    # Резерв: старый URL НКРЯ (может быть недоступен)
    ("zip",    "https://ruscorpora.ru/downloads/freqrnc2011.zip"),
]

# Маппинг PoS из словаря → наш краткий ключ
_POS_MAP = {
    "s":   "noun", "a":   "adj",  "v":   "verb",  "adv": "adv",
    "spro": "pron", "apro": "pron", "advpro": "pron",
    "num": "num",   "anum": "num",
    "conj": "conj", "prep": "prep", "part": "part",
    "intj": "interj",
    "s.PROP": "noun",
}


def _pos_short(raw: str) -> str:
    raw = raw.strip().lower()
    for k, v in _POS_MAP.items():
        if raw.startswith(k.lower()):
            return v
    return raw[:4] if raw else ""


def _read_csv(text: str) -> list[dict]:
    """Разобрать CSV-содержимое, вернуть список записей."""
    reader = csv.reader(io.StringIO(text), delimiter="\t")
    records = []
    for i, row in enumerate(reader):
        if i == 0:
            # Пропустить заголовок
            if row and row[0].lower() in ("lemma", "word", "лемма", "#"):
                continue
        if len(row) < 4:
            continue
        lemma = row[0].strip().lower()
        pos   = _pos_short(row[1]) if len(row) > 1 else ""
        try:
            ipm  = float(row[2].replace(",", "."))
        except (ValueError, IndexError):
            ipm = 0.0
        try:
            rank = int(row[3])
        except (ValueError, IndexError):
            rank = 0
        if lemma and rank > 0:
            records.append({"lemma": lemma, "ipm": ipm, "rank": rank, "pos": pos})
    return records


def _try_local(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _try_zip(url: str) -> str | None:
    print(f"  Скачиваю ZIP: {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                if name.endswith(".csv") or name.endswith(".txt"):
                    return z.read(name).decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  Не удалось: {e}")
    return None


def _try_zip_raw(url: str) -> bytes | None:
    """Вернуть raw bytes первого файла в ZIP (без декодирования)."""
    print(f"  Скачиваю ZIP (raw): {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                return z.read(name)
    except Exception as e:
        print(f"  Не удалось: {e}")
    return None


def _try_csv(url: str) -> str | None:
    print(f"  Скачиваю CSV: {url}")
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  Не удалось: {e}")
    return None


def build() -> bool:
    os.makedirs(_OUTDIR, exist_ok=True)

    text = None
    for kind, src in _SOURCES:
        print(f"Пробую источник [{kind}]: {src}")
        if kind == "local":
            text = _try_local(src)
        elif kind in ("zip", "zip_sharov"):
            raw_zip = _try_zip_raw(src)
            if raw_zip:
                # Формат Шарова: "rank ipm word pos"
                lines = raw_zip.decode("cp1251", errors="replace").split("\n")
                rows = []
                for ln in lines:
                    parts = ln.strip().split()
                    if len(parts) >= 3:
                        try:
                            rows.append(f"{parts[2]}\t{parts[3] if len(parts)>3 else ''}\t{parts[1]}\t{parts[0]}")
                        except Exception:
                            pass
                text = "\n".join(rows)
        elif kind == "csv":
            text = _try_csv(src)
        if text:
            print(f"  Получено {len(text):,} символов")
            break

    if not text:
        print(
            "\nОшибка: не удалось загрузить словарь ни из одного источника.\n"
            "Вручную положите файл freqrnc2011.csv в папку data/freq/ и запустите скрипт снова.\n"
            "Формат файла: lemma<TAB>PoS<TAB>ipm<TAB>rank<TAB>dispersion\n"
            "Скачать: https://ruscorpora.ru/page/corpora-freq"
        )
        return False

    print("Разбираю записи...")
    records = _read_csv(text)
    if not records:
        print("Ошибка: файл получен но записей не нашлось. "
              "Проверьте формат CSV (разделитель TAB, колонки: lemma / PoS / ipm / rank).")
        return False

    # Построить словарь: lemma → [rank, ipm, pos]
    # При дублях (разные PoS) — брать с бо́льшим ipm
    data: dict[str, list] = {}
    for rec in records:
        lemma = rec["lemma"]
        if lemma not in data or rec["ipm"] > data[lemma][1]:
            data[lemma] = [rec["rank"], round(rec["ipm"], 3), rec["pos"]]

    print(f"Уникальных лемм: {len(data):,}")

    with open(_OUTFILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = os.path.getsize(_OUTFILE) // 1024
    print(f"\n✓ Сохранено: {_OUTFILE}  ({size_kb} KB)")
    print(f"  Записей: {len(data):,}")
    return True


if __name__ == "__main__":
    ok = build()
    sys.exit(0 if ok else 1)
