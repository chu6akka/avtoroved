from __future__ import annotations

from collections import defaultdict


def expert_agreement(annotations: list[dict]) -> dict:
    groups = defaultdict(dict)
    for row in annotations:
        if row["present"] != "uncertain":
            groups[(row["document_id"], row["method_feature_id"])][row["expert_id_pseudonymous"]] = bool(row["present"])
    comparable = [values for values in groups.values() if len(values) >= 2]
    if not comparable:
        return {"comparable_items": 0, "percent_agreement": None,
                "cohen_kappa": None, "status": "insufficient_support"}
    pairs = []
    for values in comparable:
        ordered = sorted(values.items())[:2]
        pairs.append((ordered[0][1], ordered[1][1]))
    observed = sum(a == b for a, b in pairs) / len(pairs)
    p1a = sum(a for a, _ in pairs) / len(pairs)
    p1b = sum(b for _, b in pairs) / len(pairs)
    expected = p1a * p1b + (1 - p1a) * (1 - p1b)
    kappa = (observed - expected) / (1 - expected) if expected < 1 else None
    return {"comparable_items": len(pairs),
            "percent_agreement": round(observed * 100, 2),
            "cohen_kappa": round(kappa, 6) if kappa is not None else None,
            "status": "ok" if len(pairs) >= 2 else "insufficient_support"}
