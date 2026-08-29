from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from .io import load_jsonl, sha256_file
from .schema import SchemaError, validate_corpus_item


def check_corpus(corpus_dir: str | Path, minimum_words: int = 20) -> dict:
    root = Path(corpus_dir)
    rows = load_jsonl(root / "manifest.jsonl")
    issues: list[dict] = []
    ids = Counter(row.get("document_id") for row in rows)
    hashes = defaultdict(list)
    author_subsets = defaultdict(set)
    text_subsets = defaultdict(set)
    for row in rows:
        doc_id = row.get("document_id", "<unknown>")
        try:
            validate_corpus_item(row)
        except (SchemaError, ValueError) as exc:
            issues.append({"severity": "error", "code": "metadata", "document_id": doc_id, "detail": str(exc)})
            continue
        path = root / row["text_path"]
        if not path.is_file():
            issues.append({"severity": "error", "code": "missing_text", "document_id": doc_id})
            continue
        text = path.read_text(encoding="utf-8")
        actual_hash = sha256_file(path)
        if actual_hash != row["input_sha256"]:
            issues.append({"severity": "error", "code": "hash_mismatch", "document_id": doc_id})
        if not text.strip():
            issues.append({"severity": "error", "code": "empty_text", "document_id": doc_id})
        if len(text.split()) < minimum_words:
            issues.append({"severity": "warning", "code": "too_short", "document_id": doc_id})
        if row["word_count"] != len(text.split()) or row["character_count"] != len(text):
            issues.append({"severity": "warning", "code": "count_mismatch", "document_id": doc_id})
        hashes[actual_hash].append(doc_id)
        author_subsets[row["author_id_pseudonymous"]].add(row["subset"])
        text_subsets[actual_hash].add(row["subset"])
    for doc_id, count in ids.items():
        if count > 1:
            issues.append({"severity": "error", "code": "duplicate_document_id", "document_id": doc_id})
    for digest, documents in hashes.items():
        if len(documents) > 1:
            issues.append({"severity": "error", "code": "duplicate_sha256", "documents": documents, "sha256": digest})
    for author, subsets in author_subsets.items():
        if "VALIDATION" in subsets and len(subsets) > 1:
            issues.append({"severity": "error", "code": "author_split_leakage", "author_id_pseudonymous": author, "subsets": sorted(subsets)})
    for digest, subsets in text_subsets.items():
        if len(subsets) > 1:
            issues.append({"severity": "error", "code": "exact_text_split_leakage", "sha256": digest, "subsets": sorted(subsets)})
    return {
        "document_count": len(rows), "issues": issues,
        "error_count": sum(i["severity"] == "error" for i in issues),
        "warning_count": sum(i["severity"] == "warning" for i in issues),
        "valid": not any(i["severity"] == "error" for i in issues),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus")
    args = parser.parse_args(argv)
    result = check_corpus(args.corpus)
    print(result)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
