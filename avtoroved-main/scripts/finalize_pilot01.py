"""Finalize an explicitly approved Pilot 01 shortlist."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pilot_corpus.finalize import SEED, finalize_approved_corpus


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=ROOT / "artifacts" / "pilot01_corpus")
    parser.add_argument("--author-count", type=int, default=15)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument(
        "--approved",
        action="store_true",
        help="required acknowledgement that the shortlist was manually approved",
    )
    args = parser.parse_args()
    if not args.approved:
        parser.error("--approved is required; finalization cannot precede manual approval")
    result = finalize_approved_corpus(args.corpus.resolve(), args.author_count, args.seed)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
