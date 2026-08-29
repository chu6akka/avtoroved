from __future__ import annotations

from collections import defaultdict


def _safe_div(a: int, b: int) -> float:
    return round(a / b, 6) if b else 0.0


def _prf(tp: int, fp: int, fn: int) -> dict:
    precision, recall = _safe_div(tp, tp + fp), _safe_div(tp, tp + fn)
    f1 = round(2 * precision * recall / (precision + recall), 6) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision,
            "recall": recall, "f1": f1, "support": tp + fn}


def resolve_detection_gold(annotations: list[dict]) -> tuple[dict, list[dict]]:
    """Gold присутствия отдельно от решения accepted; raw не изменяется."""
    grouped = defaultdict(list)
    for row in annotations:
        grouped[(row["document_id"], row["method_feature_id"])].append(row)
    gold = {}
    conflicts = []
    for key, rows in grouped.items():
        adjudicated = [r for r in rows if "adjudicated_present" in r]
        if adjudicated:
            value = adjudicated[-1]["adjudicated_present"]
            source = "ADJUDICATED"
        else:
            certain = [r["present"] for r in rows if r["present"] != "uncertain"]
            if not certain:
                value, source = "uncertain", "SINGLE_EXPERT"
            elif all(v == certain[0] for v in certain):
                value = certain[0]
                source = "CONSENSUS" if len(certain) > 1 else "SINGLE_EXPERT"
            else:
                value, source = "uncertain", "CONSENSUS"
                conflicts.append({"document_id": key[0], "method_feature_id": key[1]})
        gold[key] = {"present": value, "gold_source": source,
                     "accepted_votes": sum(bool(r["accepted"]) for r in rows),
                     "annotation_count": len(rows)}
    return gold, conflicts


def evaluate_features(predictions: list[dict], annotations: list[dict],
                      registry: dict[str, dict], minimum_support: int = 3) -> dict:
    gold, conflicts = resolve_detection_gold(annotations)
    predicted = {(r["document_id"], r["method_feature_id"]): r for r in predictions}
    keys = set(gold) | set(predicted)
    counts = defaultdict(lambda: [0, 0, 0])
    errors = []
    feature_ids = set(registry) | {key[1] for key in keys}
    for key in keys:
        feature_id = key[1]
        spec = registry.get(feature_id, {})
        level = spec.get("automation_level", "CANDIDATE_ONLY")
        if level == "EXPERT_ONLY":
            continue
        truth = gold.get(key, {}).get("present", False)
        if truth == "uncertain":
            continue
        detected = key in predicted and bool(predicted[key].get("detected", True))
        if detected and truth is True:
            counts[feature_id][0] += 1
        elif detected and truth is False:
            counts[feature_id][1] += 1
            errors.append({"type": "FP", "document_id": key[0], "method_feature_id": feature_id})
        elif not detected and truth is True:
            counts[feature_id][2] += 1
            errors.append({"type": "FN", "document_id": key[0], "method_feature_id": feature_id})
    rows = []
    for feature_id in sorted(feature_ids):
        spec = registry.get(feature_id, {})
        level = spec.get("automation_level", "CANDIDATE_ONLY")
        if level == "EXPERT_ONLY":
            rows.append({"method_feature_id": feature_id,
                         "group": spec.get("group"),
                         "automation_level": level,
                         "status": "not_automated_by_design"})
            continue
        row = {"method_feature_id": feature_id, "group": spec.get("group"),
               "automation_level": level,
               "metric_scope": "candidate_detection" if level == "CANDIDATE_ONLY" else "detection",
               **_prf(*counts[feature_id])}
        row["status"] = "insufficient_support" if row["support"] < minimum_support else "ok"
        rows.append(row)
    group_counts = defaultdict(lambda: [0, 0, 0])
    for row in rows:
        if "tp" not in row or not row.get("group"):
            continue
        group_counts[row["group"]][0] += row["tp"]
        group_counts[row["group"]][1] += row["fp"]
        group_counts[row["group"]][2] += row["fn"]
    groups = [{"group": group, **_prf(*values)} for group, values in sorted(group_counts.items())]
    return {"features": rows, "groups": groups, "errors": errors,
            "gold_conflicts": conflicts,
            "accepted_workflow": {
                "accepted_votes": sum(bool(r["accepted"]) for r in annotations),
                "annotation_count": len(annotations),
                "note": "Экспертное принятие учтено отдельно от обнаружения.",
            }}
