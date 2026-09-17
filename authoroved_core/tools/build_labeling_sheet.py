"""Готовит лист предложений корпуса Pilot 01 для ручной разметки эталона.

Замер 17 сентября показал, что fixtures из одиночных коротких предложений не
воспроизводят условия реальных документов, поэтому измерять признаки не на чем.
Эталон строится по текстам корпуса и в дальнейшем служит и для замера, и для
подбора примеров в промпт.

Выборка стратифицирована намеренно. Обогащённая страта отбирается по
детерминированным сигналам необычной орфографии и даёт достаточное число
положительных случаев. Случайная страта ничем не отбирается и нужна, чтобы
эталон не унаследовал слепые зоны отбора: пропуски видны только на ней.
Страта каждой строки записана, поэтому доли по стратам считаются раздельно и
смешивать их нельзя.

Лемматизация здесь не применяется: freqrnc.json построен по леммам, поэтому
проверка «слова нет в словаре» давала бы сигнал на каждой словоформе.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
import random
import re

from authoroved_core.tools.evaluate_qwen_shadow_blind import iter_corpus_documents


SHEET_SEED = 20260917
DEFAULT_RANDOM = 80
DEFAULT_ENRICHED = 40

# Границей считается знак конца предложения с последующим пробелом и заглавной
# буквой или кавычкой. Разбиение приблизительное и на модель не опирается.
SENTENCE_BOUNDARY = re.compile(r'(?<=[.!?…])\s+(?=[«"А-ЯЁ])')
TRIPLED_LETTER = re.compile(r"(\w)\1\1", re.UNICODE)
LATIN_TOKEN = re.compile(r"\b[A-Za-z]{3,}\b")
REPEATED_PUNCTUATION = re.compile(r"([!?])\1")

FIELDS = ["row_id", "stratum", "document_id", "sentence_index", "doc_start",
          "doc_end", "signals", "sentence", "gold_features", "note"]


def split_sentences(text: str) -> list[tuple[int, int, str]]:
    """Предложения с координатами в исходном тексте."""
    result, offset = [], 0
    normalized = text.replace("\r\n", "\n")
    for piece in SENTENCE_BOUNDARY.split(normalized):
        start = normalized.find(piece, offset)
        if start < 0:
            continue
        stripped = piece.strip()
        if stripped:
            lead = len(piece) - len(piece.lstrip())
            result.append((start + lead, start + lead + len(stripped), stripped))
        offset = start + len(piece)
    return result


def orthographic_signals(sentence: str) -> tuple[str, ...]:
    """Детерминированные признаки необычной орфографии — только для отбора."""
    found = []
    if TRIPLED_LETTER.search(sentence):
        found.append("тройная буква")
    if LATIN_TOKEN.search(sentence):
        found.append("латиница")
    if REPEATED_PUNCTUATION.search(sentence):
        found.append("повтор знака")
    return tuple(found)


def build_rows(documents, *, random_size=DEFAULT_RANDOM, enriched_size=DEFAULT_ENRICHED,
               seed=SHEET_SEED, min_words=4):
    pool = []
    for document_id, text in documents:
        for index, (start, end, sentence) in enumerate(split_sentences(text)):
            if len(sentence.split()) < min_words:
                continue
            pool.append({
                "document_id": document_id, "sentence_index": index,
                "doc_start": start, "doc_end": end, "sentence": sentence,
                "signals": "; ".join(orthographic_signals(sentence)),
            })
    if not pool:
        raise ValueError("В корпусе не нашлось предложений нужной длины.")

    generator = random.Random(seed)
    enriched_pool = [item for item in pool if item["signals"]]
    enriched = generator.sample(enriched_pool, min(enriched_size, len(enriched_pool)))
    taken = {(item["document_id"], item["sentence_index"]) for item in enriched}
    plain_pool = [item for item in pool
                  if (item["document_id"], item["sentence_index"]) not in taken]
    plain = generator.sample(plain_pool, min(random_size, len(plain_pool)))

    rows = []
    for stratum, items in (("random", plain), ("enriched", enriched)):
        for item in sorted(items, key=lambda value: (value["document_id"],
                                                     value["sentence_index"])):
            rows.append({**item, "stratum": stratum, "gold_features": "", "note": ""})
    for number, row in enumerate(rows, start=1):
        row["row_id"] = f"R{number:04d}"
    return rows, len(pool), len(enriched_pool)


def write_sheet(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in FIELDS})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path,
                        default=Path("avtoroved-main/artifacts/pilot01_corpus"))
    parser.add_argument("--random-size", type=int, default=DEFAULT_RANDOM)
    parser.add_argument("--enriched-size", type=int, default=DEFAULT_ENRICHED)
    parser.add_argument("--output", type=Path,
                        default=Path("authoroved_core/artifacts/labeling_sheet.csv"))
    args = parser.parse_args()

    documents = iter_corpus_documents(args.corpus)
    rows, total, enriched_total = build_rows(
        documents, random_size=args.random_size, enriched_size=args.enriched_size,
    )
    write_sheet(args.output, rows)
    print(f"документов: {len(documents)}; предложений в корпусе: {total}; "
          f"из них с сигналами: {enriched_total}")
    print(f"в листе строк: {len(rows)} "
          f"(случайных {sum(r['stratum'] == 'random' for r in rows)}, "
          f"обогащённых {sum(r['stratum'] == 'enriched' for r in rows)})")
    print(f"записано: {args.output}")


if __name__ == "__main__":
    main()
