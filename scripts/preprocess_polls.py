#!/usr/bin/env python3
"""Clean historical and 2026 Senate polls into data/processed.

Raw files are not modified. Re-running this script overwrites the cleaned
tables in the processed directory.

Usage:
    python3 scripts/preprocess_polls.py
    python3 scripts/preprocess_polls.py --raw-dir data/raw --processed-dir data/processed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from polling_blind_spot.preprocess.errors import PreprocessError
from polling_blind_spot.preprocess.pipeline import run_preprocessing


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "raw",
        help="Directory containing the raw downloads (default: data/raw)",
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed",
        help="Directory for cleaned tables (default: data/processed)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = run_preprocessing(args.raw_dir, args.processed_dir)
    except PreprocessError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    fte = report["outputs"]["fte_questions"]
    wiki = report["outputs"]["wikipedia_questions"]
    quarantine = report["outputs"]["wikipedia_quarantine"]
    print(
        "Wrote cleaned FiveThirtyEight tables: "
        f"{fte['rows']} questions, {fte['two_party_general']} general-election "
        "two-party margins"
    )
    print(
        "Wrote cleaned 2026 Wikipedia poll tables: "
        f"{wiki['rows']} questions, {wiki['two_party_general']} general-election "
        "two-party margins"
    )
    print(
        "Quarantined 2026 poll rows whose poll source was not a pollster: "
        f"{quarantine['rows']}"
    )
    print(f"Processed directory: {args.processed_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
