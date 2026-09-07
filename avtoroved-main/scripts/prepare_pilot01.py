"""CLI for the isolated first pass over IlyaGusev/pikabu."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pilot_corpus.scanner import DEFAULT_REVISION, ScanConfig, export_existing, scan


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "pilot01_corpus",
    )
    result.add_argument("--max-records", type=int, default=250_000)
    result.add_argument("--checkpoint-every", type=int, default=2_000)
    result.add_argument("--seed", type=int, default=20260907)
    result.add_argument("--revision", default=DEFAULT_REVISION)
    result.add_argument("--top-authors", type=int, default=30)
    result.add_argument("--max-posts-per-author", type=int, default=12)
    result.add_argument("--resume", action="store_true")
    result.add_argument(
        "--export-only",
        action="store_true",
        help="regenerate reports from the local checkpoint without network access",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    if args.max_records <= 0 or args.checkpoint_every <= 0:
        raise SystemExit("--max-records and --checkpoint-every must be positive")
    config = ScanConfig(
        output_dir=args.output.resolve(),
        max_records=args.max_records,
        checkpoint_every=args.checkpoint_every,
        seed=args.seed,
        revision=args.revision,
        top_authors=args.top_authors,
        max_posts_per_author=args.max_posts_per_author,
        resume=args.resume,
    )
    summary = export_existing(config) if args.export_only else scan(config)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
