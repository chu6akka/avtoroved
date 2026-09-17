"""Лист разметки нераспознанных словоформ для замера точности подсказки.

Точность режима подсказки не измерена: контрольного набора нет. Инструмент
собирает его из текстов корпуса Pilot 01 — LanguageTool находит
нераспознанные словоформы, Python считает по каждой детерминированную
справку, эксперт проставляет верную метку.

Лист рассчитан на чтение человеком, а не только на разбор программой:

* одинаковые словоформы сведены в одну строку с числом вхождений, иначе
  «пикабушник» занял бы десяток строк подряд;
* контекст укладывается в одну строку, сама словоформа выделена скобками;
* сначала идут случаи, где числа ничего не решили, — именно они и нужны для
  замера подсказки, остальные решены без модели;
* столбец `gold_label` пустой, допустимые значения перечислены в легенде
  рядом с листом.

Анализ запускается полный, со Stanza, а не только LanguageTool: справка в
программе берёт лемму из разметки Stanza, и без неё столбец `corpus_ipm`
заполнялся бы реже, чем в самой программе. Контрольный набор обязан
повторять поведение программы, иначе он измеряет не её.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
from pathlib import Path
import re

from authoroved_core.core.analysis import AnalysisService
from authoroved_core.core.document import Document
from authoroved_core.core.lt_grouping import (
    UNKNOWN_WORD_CLASSIFICATIONS, candidate_group_key,
)
from authoroved_core.core.word_evidence import FrequencyDictionary, collect
from authoroved_core.nlp.settings import LocalSettings
from authoroved_core.tools.evaluate_qwen_shadow_blind import iter_corpus_documents


DEFAULT_CORPUS = Path("avtoroved-main/artifacts/pilot01_corpus")
CONTEXT_MARGIN = 55
FIELDS = ["row_id", "word", "context", "occurrences", "documents", "corpus_ipm",
          "repeats_in_document", "nearest_correction", "edits", "flags",
          "deterministic", "deterministic_reason", "gold_label", "note"]


def one_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def context_line(text: str, start: int, end: int, margin: int = CONTEXT_MARGIN) -> str:
    left = one_line(text[max(0, start - margin):start])
    right = one_line(text[end:end + margin])
    return f"…{left} [{text[start:end]}] {right}…"


def build_rows(documents, service, dictionary, *, limit: int = 0):
    """Одна строка на словоформу, а не на каждое её вхождение."""
    seen: dict[str, dict] = {}
    for number, (document_id, text) in enumerate(documents, start=1):
        print(f"  [{number}/{len(documents)}] {document_id}", flush=True)
        payload = text.encode("utf-8")
        document = Document(
            id=document_id, name=document_id, text=text, original_bytes=payload,
            file_sha256=sha256(payload).hexdigest(),
            text_sha256=sha256(text.encode("utf-8")).hexdigest(),
            encoding="utf-8", import_note="Текст корпуса Pilot 01",
        )
        result = service.analyze(document)
        candidates, result_tokens = result.candidates, result.tokens
        for candidate in candidates:
            if candidate_group_key(candidate) != "unknown_words":
                continue
            key = candidate.fragment.casefold()
            if key in seen:
                seen[key]["occurrences"] += 1
                seen[key]["_documents"].add(document_id)
                continue
            evidence = collect(candidate, text, result_tokens, dictionary)
            flags = [name for name, active in (
                ("латиница", evidence.has_latin),
                ("тройная буква", evidence.has_tripled_letter),
                ("заглавная не в начале", evidence.capitalized_inside_sentence),
            ) if active]
            seen[key] = {
                "word": candidate.fragment,
                "context": context_line(text, candidate.span.start, candidate.span.end),
                "occurrences": 1,
                "_documents": {document_id},
                "corpus_ipm": "" if evidence.frequency_ipm is None else f"{evidence.frequency_ipm:.2f}",
                "repeats_in_document": evidence.repeats_in_text,
                "nearest_correction": evidence.nearest_replacement,
                "edits": "" if evidence.edit_distance is None else evidence.edit_distance,
                "flags": ", ".join(flags),
                "deterministic": evidence.verdict,
                "deterministic_reason": one_line(evidence.verdict_reason),
                "gold_label": "", "note": "",
            }
    rows = list(seen.values())
    for row in rows:
        row["documents"] = len(row.pop("_documents"))
    # Сначала нерешённое: именно на нём и меряется подсказка.
    rows.sort(key=lambda item: (bool(item["deterministic"]), item["word"].casefold()))
    if limit:
        rows = rows[:limit]
    for number, row in enumerate(rows, start=1):
        row["row_id"] = f"W{number:04d}"
    return rows


def write_sheet(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_legend(path: Path) -> None:
    lines = ["Допустимые значения столбца gold_label:", ""]
    lines += [f"  {key:16} {title}" for key, title in UNKNOWN_WORD_CLASSIFICATIONS]
    lines += [
        "",
        "Оставьте пустым, если не уверены, и напишите почему в столбце note.",
        "Столбец deterministic — метка, выведенная из чисел без модели.",
        "Строки с пустым deterministic идут первыми: на них и меряется подсказка.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--limit", type=int, default=150,
                        help="сколько словоформ включить; 0 — все")
    parser.add_argument("--output", type=Path,
                        default=Path("authoroved_core/artifacts/hint_labeling_sheet.csv"))
    args = parser.parse_args()

    documents = iter_corpus_documents(args.corpus)
    service = AnalysisService(LocalSettings.load())
    try:
        dictionary = FrequencyDictionary.load()
    except (OSError, ValueError):
        dictionary = FrequencyDictionary.empty()
        print("Снимок частотного словаря недоступен: столбец corpus_ipm останется пустым")

    rows = build_rows(documents, service, dictionary, limit=args.limit)
    write_sheet(args.output, rows)
    legend = args.output.with_name(args.output.stem + "_легенда.txt")
    write_legend(legend)

    undecided = sum(not row["deterministic"] for row in rows)
    print(f"текстов: {len(documents)}")
    print(f"различных словоформ в листе: {len(rows)}")
    print(f"из них числами не решено: {undecided} — это и есть работа для подсказки")
    print(f"лист: {args.output}")
    print(f"легенда: {legend}")


if __name__ == "__main__":
    main()
