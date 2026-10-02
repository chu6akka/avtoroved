"""Разбор корпуса Stanza с кешем: один раз, затем повторные замеры читают JSON.

Кеш лежит в `authoroved_core/artifacts/corpus_tokens/<корпус>/<document_id>.json`
и хранит токены вместе с SHA-256 текста: изменённый текст будет разобран заново.
Разбор локальный, тот же, что в программе (`StanzaAdapter`).
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter

from authoroved_core.core.models import Span, Token
from authoroved_core.tools.measure_topic_overlap import parse_tags

DEFAULT_CORPUS = Path("avtoroved-main/artifacts/pilot02c_corpus")
CACHE_ROOT = Path("authoroved_core/artifacts/corpus_tokens")


def read_documents(corpus: Path) -> list[dict]:
    """Документы корпуса из манифеста: автор, метки, путь к тексту, резерв или основной."""
    manifest = corpus / "manifest.csv"
    if not manifest.is_file():
        raise FileNotFoundError(f"Не найден манифест {manifest}.")
    with manifest.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    documents = []
    for row in rows:
        path = corpus / row["analysis_path"]
        documents.append({
            "document_id": row["document_id"], "author": row["author_code"],
            "tags": parse_tags(row.get("tags", "")), "path": path,
            "reserve": row.get("is_reserve", "").strip().lower() == "true",
            "words": int(row["word_count"]) if row.get("word_count") else None,
        })
    return documents


def token_to_list(token: Token) -> list:
    span = token.span
    return [token.text, token.lemma, token.pos, token.feats, token.dependency, token.head,
            token.sentence, token.index, span.start if span else None, span.end if span else None]


def token_from_list(item: list) -> Token:
    text, lemma, pos, feats, dependency, head, sentence, index, start, end = item
    span = Span(start, end) if start is not None and end is not None else None
    return Token(text, lemma, pos, feats, dependency, head, sentence, index, span)


def cache_path(corpus: Path, document_id: str) -> Path:
    return CACHE_ROOT / corpus.name / f"{document_id}.json"


def load_tokens(corpus: Path, document: dict, adapter=None) -> list[Token]:
    """Токены документа из кеша; при отсутствии или смене текста — разбор и запись."""
    text = document["path"].read_text(encoding="utf-8")
    digest = sha256(text.encode("utf-8")).hexdigest()
    path = cache_path(corpus, document["document_id"])
    if path.is_file():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            cached = {}  # недописанный файл прерванного разбора — разбираем заново
        if cached.get("text_sha256") == digest:
            return [token_from_list(item) for item in cached["tokens"]]
    if adapter is None:
        raise RuntimeError(f"Нет кеша разбора для {document['document_id']}, а разборщик не передан.")
    tokens, _ = adapter.analyze(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"text_sha256": digest, "tokens": [token_to_list(t) for t in tokens]},
                                    ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return tokens


def main():
    parser = argparse.ArgumentParser(description="Разобрать корпус Stanza и сохранить кеш токенов.")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--shard", default="0/1",
                        help="часть корпуса «k/n» для параллельного разбора несколькими процессами")
    args = parser.parse_args()
    shard, shards = (int(part) for part in args.shard.split("/"))
    from authoroved_core.nlp.settings import LocalSettings
    from authoroved_core.nlp.stanza_adapter import StanzaAdapter

    adapter = StanzaAdapter(LocalSettings.load().stanza_dir)
    documents = read_documents(args.corpus)[shard::shards]
    started = perf_counter()
    for number, document in enumerate(documents, start=1):
        load_tokens(args.corpus, document, adapter)
        if number % 20 == 0 or number == len(documents):
            print(f"{number}/{len(documents)} · {perf_counter() - started:.0f} с", flush=True)


if __name__ == "__main__":
    main()
