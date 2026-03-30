"""
scripts/download_freq_dict.py — Загрузка частотного словаря НКРЯ.

Словарь: Ляшевская О.Н., Шаров С.А. «Частотный словарь современного
русского языка (на материалах НКРЯ)». М.: Азбуковник, 2009.

Запуск: python scripts/download_freq_dict.py
"""
from __future__ import annotations
import csv
import io
import json
import os
import sys
import urllib.request
import zipfile

# Путь сохранения
_OUT = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                    "data", "freq", "freqrnc.json")

# Известные URL для скачивания (пробуем по очереди)
_URLS = [
    "http://www.ruscorpora.ru/new/res/freqrnc2011.csv",
    "http://dict.ruslang.ru/freq_list_lemm.txt",
    "https://raw.githubusercontent.com/akost/frequency-lists/master/ru/freqrnc2011.tsv",
]

# Если ни один URL не сработал — выводим инструкцию для ручной загрузки
_MANUAL_INSTRUCTION = """
Автоматическая загрузка не удалась.
Скачайте файл вручную:

  1. Перейдите на сайт: http://www.ruscorpora.ru/new/freq-dict.html
  2. Скачайте файл «freqrnc2011.csv» (~ 2 МБ)
  3. Поместите файл сюда: data/freq/freqrnc2011.csv
  4. Запустите скрипт повторно: python scripts/download_freq_dict.py --file data/freq/freqrnc2011.csv

Или укажите локальный файл при запуске:
  python scripts/download_freq_dict.py --file /путь/к/freqrnc2011.csv
"""


def _parse_lines(lines: list[str]) -> list[dict]:
    """Парсить строки CSV/TSV в список записей."""
    entries = []

    # Определить разделитель по первой строке
    header = lines[0] if lines else ""
    sep = "\t" if "\t" in header else ","

    reader = csv.DictReader(lines, delimiter=sep)

    # Возможные имена колонок в разных версиях файла
    _rank_keys = ["№", "N", "Rank", "rank", "#", "no", "No"]
    _lemma_keys = ["Лемма", "lemma", "Lemma", "word", "Word"]
    _pos_keys = ["Часть речи", "PoS", "pos", "POS", "tag", "Tag"]
    _ipm_keys = ["ipm", "Ipm", "IPM", "Freq", "freq", "frequency",
                 "Частота на миллион", "freq_ipm"]
    _doc_keys = ["r", "R", "doc_freq", "DocFreq", "d", "Частота в документах"]

    def _get(row: dict, keys: list[str], default=""):
        for k in keys:
            if k in row:
                return row[k]
        return default

    for row in reader:
        lemma = _get(row, _lemma_keys).strip()
        if not lemma or lemma.startswith("#"):
            continue
        try:
            rank = int(_get(row, _rank_keys, "0").strip() or "0")
            ipm  = float(_get(row, _ipm_keys, "0").strip().replace(",", ".") or "0")
            pos  = _get(row, _pos_keys, "").strip()
        except (ValueError, TypeError):
            continue
        if rank == 0 and ipm == 0:
            continue
        entries.append({"lemma": lemma, "rank": rank, "ipm": ipm, "pos": pos})

    return entries


def _download_and_parse(url: str) -> list[dict] | None:
    print(f"  Попытка: {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()

        # Обнаружить кодировку
        for enc in ("utf-8-sig", "utf-8", "cp1251", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            return None

        lines = text.splitlines()
        if len(lines) < 10:
            return None
        entries = _parse_lines(lines)
        print(f"  OK Загружено строк: {len(entries)}")
        return entries if entries else None
    except Exception as e:
        print(f"  FAIL {type(e).__name__}: {str(e)[:80]}")
        return None


def _parse_local_file(path: str) -> list[dict] | None:
    print(f"Читаю файл: {path}")
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            with open(path, encoding=enc) as f:
                lines = f.read().splitlines()
            break
        except UnicodeDecodeError:
            continue
    else:
        print("Ошибка: не удалось определить кодировку файла")
        return None

    entries = _parse_lines(lines)
    print(f"Прочитано строк: {len(entries)}")
    return entries if entries else None


def _build_json(entries: list[dict]) -> dict:
    """
    Строим словарь: lemma -> [rank, ipm, pos].
    Если одна лемма встречается несколько раз (разные PoS),
    берём запись с наибольшим ipm.
    """
    out: dict[str, list] = {}
    for e in entries:
        lemma = e["lemma"].lower()
        existing = out.get(lemma)
        if existing is None or e["ipm"] > existing[1]:
            out[lemma] = [e["rank"], round(e["ipm"], 3), e["pos"]]
    return out


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Загрузить частотный словарь НКРЯ")
    parser.add_argument("--file", help="Путь к локальному файлу (csv/tsv)")
    parser.add_argument("--out", default=_OUT, help=f"Путь сохранения JSON (по умолч. {_OUT})")
    args = parser.parse_args()

    entries = None

    if args.file:
        entries = _parse_local_file(args.file)
    else:
        print("Загрузка частотного словаря НКРЯ (Ляшевская, Шаров 2009)...")
        for url in _URLS:
            entries = _download_and_parse(url)
            if entries:
                break

    if not entries:
        print(_MANUAL_INSTRUCTION)
        sys.exit(1)

    data = _build_json(entries)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = os.path.getsize(args.out) // 1024
    print(f"\nОК Сохранено: {args.out}")
    print(f"  Лемм: {len(data)}, размер файла: {size_kb} КБ")


if __name__ == "__main__":
    main()
