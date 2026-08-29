from __future__ import annotations

from collections import defaultdict


def _div(a, b):
    return a / b if b else 0.0


def evaluate_multilabel(predictions: list[dict], gold_rows: list[dict], *,
                        label_kind: str) -> dict:
    """Метрики темы/стиля без преобразования их в вывод об авторстве."""
    key = lambda r: (r["document_id"], r.get("segment_id"))
    predictions_by_key = {key(r): list(r.get("labels", [])) for r in predictions}
    gold_by_key = {key(r): list(r.get("labels", [])) for r in gold_rows}
    labels = sorted({label for rows in (predictions, gold_rows)
                     for row in rows for label in row.get("labels", [])})
    per_label = {}
    total_tp = total_fp = total_fn = 0
    mixed_total = mixed_hit = 0
    top1_hits = 0
    abstentions = 0
    for item_key, expected in gold_by_key.items():
        actual = predictions_by_key.get(item_key, [])
        abstentions += not actual
        top1_hits += bool(actual and actual[0] in expected)
        if len(expected) > 1:
            mixed_total += 1
            mixed_hit += bool(set(actual) & set(expected))
    for label in labels:
        tp = sum(label in gold_by_key[k] and label in predictions_by_key.get(k, []) for k in gold_by_key)
        fp = sum(label not in gold_by_key.get(k, []) and label in values for k, values in predictions_by_key.items())
        fn = sum(label in values and label not in predictions_by_key.get(k, []) for k, values in gold_by_key.items())
        p, r = _div(tp, tp + fp), _div(tp, tp + fn)
        f1 = _div(2 * p * r, p + r)
        per_label[label] = {"precision": round(p, 6), "recall": round(r, 6),
                            "f1": round(f1, 6), "support": tp + fn}
        total_tp += tp; total_fp += fp; total_fn += fn
    micro_p, micro_r = _div(total_tp, total_tp + total_fp), _div(total_tp, total_tp + total_fn)
    result = {
        "label_kind": label_kind,
        "top1_accuracy": round(_div(top1_hits, len(gold_by_key)), 6),
        # В single-choice top-1 micro P/R/F1 совпадают с accuracy; поля
        # сохраняются явно, чтобы отчёт не смешивал top-1 и multi-label режимы.
        "top1_micro_precision": round(_div(top1_hits, len(gold_by_key)), 6),
        "top1_micro_recall": round(_div(top1_hits, len(gold_by_key)), 6),
        "top1_micro_f1": round(_div(top1_hits, len(gold_by_key)), 6),
        "micro_precision": round(micro_p, 6), "micro_recall": round(micro_r, 6),
        "micro_f1": round(_div(2 * micro_p * micro_r, micro_p + micro_r), 6),
        "macro_f1": round(_div(sum(v["f1"] for v in per_label.values()), len(per_label)), 6),
        "mixed_label_recall": round(_div(mixed_hit, mixed_total), 6),
        "mixed_label_support": mixed_total, "per_label": per_label,
    }
    if label_kind == "style":
        result["abstention_rate"] = round(_div(abstentions, len(gold_by_key)), 6)
        result["focus_styles"] = {name: per_label.get(name, {"status": "no_support"})
                                  for name in ("publicistic", "conversational")}
    segment_keys = [k for k in gold_by_key if k[1] is not None]
    if segment_keys:
        by_document = defaultdict(list)
        for doc, segment in segment_keys:
            by_document[doc].append(segment)
        transition_total = transition_hit = 0
        for doc, segments in by_document.items():
            ordered = sorted(segments)
            for left, right in zip(ordered, ordered[1:]):
                gold_transition = set(gold_by_key[(doc, left)]) != set(gold_by_key[(doc, right)])
                pred_transition = set(predictions_by_key.get((doc, left), [])) != set(predictions_by_key.get((doc, right), []))
                if gold_transition:
                    transition_total += 1
                    transition_hit += pred_transition
        result["segment_transition_recall"] = round(_div(transition_hit, transition_total), 6)
        result["segment_transition_support"] = transition_total
    return result
