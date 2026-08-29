from __future__ import annotations

import argparse
import statistics
from collections import defaultdict

from .io import load_jsonl
from .schema import validate_time_record


def evaluate_time(records: list[dict]) -> dict:
    grouped = defaultdict(dict)
    for row in records:
        validate_time_record(row)
        key = (row["case_id"], row["expert_id_pseudonymous"], row["stage"])
        grouped[key][row["mode"]] = row
    paired, unmatched = [], []
    for key, modes in sorted(grouped.items()):
        if {"MANUAL", "ASSISTED"} <= modes.keys():
            manual = float(modes["MANUAL"]["duration_seconds"])
            assisted = float(modes["ASSISTED"]["duration_seconds"])
            paired.append({"case_id": key[0], "expert_id_pseudonymous": key[1],
                           "stage": key[2], "manual_seconds": manual,
                           "assisted_seconds": assisted,
                           "saved_seconds": manual - assisted,
                           "manual_session_order": modes["MANUAL"]["session_order"],
                           "assisted_session_order": modes["ASSISTED"]["session_order"]})
        else:
            unmatched.append({"case_id": key[0], "expert_id_pseudonymous": key[1],
                              "stage": key[2], "available_modes": sorted(modes)})
    savings = [row["saved_seconds"] for row in paired]
    aggregate = None if not savings else {
        "count": len(savings), "mean_saved_seconds": round(statistics.mean(savings), 3),
        "median_saved_seconds": round(statistics.median(savings), 3),
        "min_saved_seconds": min(savings), "max_saved_seconds": max(savings),
    }
    return {"paired": paired, "unmatched": unmatched, "aggregate": aggregate,
            "order_effect_note": "session_order обязателен; порядок MANUAL/ASSISTED должен быть контрбалансирован."}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("records")
    args = parser.parse_args(argv)
    print(evaluate_time(load_jsonl(args.records)))


if __name__ == "__main__":
    main()
