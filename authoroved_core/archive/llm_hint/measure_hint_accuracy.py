"""Замер точности подсказки по эталонному набору словоформ.

Подсказка по кандидатам LanguageTool до сих пор не измерена: эталон
`tests/fixtures/unknown_word_gold.json` собран именно для этого. Инструмент
задаёт модели вопрос по каждой словоформе набора и сравнивает её метку с
экспертной.

Числа справки берутся из эталона, а не пересчитываются: там записано ровно
то, что программа показывала эксперту при разметке, и замер обязан повторять
её поведение.

Метка `unclear` — не ошибка, а воздержание. Поэтому точность считается по
тем случаям, где модель ответила, а доля воздержаний приводится отдельно:
это и есть размен полноты на точность.

Девять словоформ набора оставлены без экспертной метки (растяжения написания
и «зы»): восемь классификаций LanguageTool покрывают лексику и не покрывают
графику. Они в замер не входят и считаются отдельной строкой.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter

from authoroved_core.core.lt_grouping import UNKNOWN_WORD_CLASSIFICATION_LABELS
from authoroved_core.core.models import Candidate, Span
from authoroved_core.core.qwen_classification import QwenClassificationService
from authoroved_core.core.word_evidence import WordEvidence
from authoroved_core.nlp.qwen_local import LlamaCppLocalProvider, LocalQwenConfig
from authoroved_core.nlp.qwen_server import LocalQwenServer, QwenServerSettings, file_sha256


DEFAULT_GOLD = (Path(__file__).parents[1] / "tests" / "fixtures" / "unknown_word_gold.json")


def gold_items(path: Path = DEFAULT_GOLD) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["items"]


def text_and_span(item: dict) -> tuple[str, Span]:
    """Восстанавливает окрестность словоформы из записи эталона.

    В эталоне контекст хранится как «…слева [слово] справа…»: скобки
    показывают, какая именно форма разбиралась.
    """
    context = item["context"]
    left, rest = context.split("[", 1)
    word, right = rest.split("]", 1)
    left = left.lstrip("…")
    right = right.rstrip("…")
    text = f"{left}{word}{right}"
    return text, Span(len(left), len(left) + len(word))


def candidate_from_gold(item: dict, span: Span) -> Candidate:
    return Candidate(
        id=f"gold-{item['word']}", document_id="gold",
        name="Слово не распознано словарём", category="Слово не распознано словарём",
        explanation="Словарь LanguageTool не знает эту форму",
        fragment=item["word"], span=span, rule_id="MORFOLOGIK_RULE_RU_RU",
        replacements=(item["nearest_correction"],) if item["nearest_correction"] else (),
    )


def evidence_from_gold(item: dict) -> WordEvidence:
    """Справка берётся из эталона, а не считается заново."""
    return WordEvidence(
        form=item["word"], lemma=item["word"],
        frequency_ipm=item["corpus_ipm"], frequency_rank=None, word_class="",
        repeats_in_text=item["repeats_in_document"],
        nearest_replacement=item["nearest_correction"], edit_distance=item["edits"],
        lt_replacements=(item["nearest_correction"],) if item["nearest_correction"] else (),
        has_latin="латиница" in item["flags"],
        has_tripled_letter="тройная буква" in item["flags"],
        capitalized_inside_sentence="заглавная" in item["flags"],
    )


def measure(service: QwenClassificationService, items, progress=lambda message: None):
    started = perf_counter()
    rows, skipped = [], []
    for number, item in enumerate(items, start=1):
        if not item["gold_label"]:
            skipped.append(item["word"])
            continue
        progress(f"[{number}/{len(items)}] {item['word']}")
        text, span = text_and_span(item)
        hint = service.hint(candidate_from_gold(item, span), text, evidence_from_gold(item))
        rows.append({
            "word": item["word"], "gold": item["gold_label"],
            "status": hint.status.value, "answer": hint.classification,
            "reason": hint.reason, "correct": hint.classification == item["gold_label"],
            "rejection_reason": hint.rejection_reason,
        })
    answered = [row for row in rows if row["status"] == "VALIDATED_HINT"]
    correct = [row for row in answered if row["correct"]]
    unclear = [row for row in rows if row["status"] == "MODEL_UNCLEAR"]
    rejected = [row for row in rows if row["status"] == "SYSTEM_REJECTED"]
    confusion = Counter((row["gold"], row["answer"]) for row in answered if not row["correct"])
    by_label = {}
    for label in sorted({row["gold"] for row in rows}):
        same = [row for row in rows if row["gold"] == label]
        hit = [row for row in same if row["correct"]]
        by_label[label] = {"total": len(same), "correct": len(hit),
                           "unclear": sum(row["status"] == "MODEL_UNCLEAR" for row in same)}
    return {
        "kind": "Замер подсказки по эталону; не оценка авторства",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_seconds": round(perf_counter() - started, 3),
        "gold_items": len(items),
        "measured": len(rows),
        "skipped_without_label": skipped,
        "answered": len(answered),
        "correct": len(correct),
        "unclear": len(unclear),
        "system_rejected": len(rejected),
        "precision_when_answered": round(len(correct) / len(answered), 3) if answered else None,
        "share_of_all_items": round(len(correct) / len(rows), 3) if rows else None,
        "by_label": by_label,
        "confusions": [{"gold": gold, "answer": answer, "count": count}
                       for (gold, answer), count in confusion.most_common()],
        "rows": rows,
    }


def print_report(report: dict) -> None:
    print(f"\nсловоформ в эталоне: {report['gold_items']}; "
          f"замерено: {report['measured']}; "
          f"без экспертной метки пропущено: {len(report['skipped_without_label'])}")
    print(f"модель ответила: {report['answered']}, воздержалась: {report['unclear']}, "
          f"отклонено валидатором: {report['system_rejected']}")
    if report["precision_when_answered"] is not None:
        print(f"верных среди ответов: {report['correct']} из {report['answered']} "
              f"({report['precision_when_answered'] * 100:.1f} %)")
    print(f"верных от всего набора: {report['correct']} из {report['measured']} "
          f"({(report['share_of_all_items'] or 0) * 100:.1f} %)")
    print("\nпо меткам:")
    for label, value in report["by_label"].items():
        title = UNKNOWN_WORD_CLASSIFICATION_LABELS.get(label, label)
        print(f"  {title:42} верно {value['correct']:3} из {value['total']:3}"
              f"   воздержаний {value['unclear']}")
    if report["confusions"]:
        print("\nчто с чем путает:")
        for item in report["confusions"][:12]:
            print(f"  {item['gold']:16} -> {item['answer']:16} {item['count']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--output", type=Path,
                        default=Path("authoroved_core/artifacts/hint_accuracy.json"))
    parser.add_argument("--port", type=int, default=8089)
    args = parser.parse_args()

    items = gold_items(args.gold)
    settings = QwenServerSettings(args.runtime.resolve(), args.model.resolve(), port=args.port)
    server = LocalQwenServer(settings, Path("authoroved_core/.local/qwen/llama-server.log"))
    model_hash = file_sha256(settings.model)
    runtime_version = server.version()
    with server:
        provider = LlamaCppLocalProvider(LocalQwenConfig(
            endpoint=server.endpoint, model_name=settings.model.name,
            model_sha256=model_hash, runtime_version=runtime_version,
            api_key=server.api_key,
        ))
        report = measure(QwenClassificationService(provider), items,
                         lambda message: print(" ", message, flush=True))
    report["model_name"] = settings.model.name
    report["model_sha256"] = model_hash
    report["runtime_version"] = runtime_version
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print_report(report)
    print(f"\nотчёт: {args.output}")


if __name__ == "__main__":
    main()
