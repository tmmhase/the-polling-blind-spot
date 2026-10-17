#!/usr/bin/env python3
"""Score historical Senate polls against official two-candidate results.

Raw files are not modified, and result margins are not written back onto the
cleaned poll tables. Re-running this script overwrites the analysis outputs.

Usage:
    python3 scripts/analyze_polling_error.py
    python3 scripts/analyze_polling_error.py --raw-dir data/raw --output-dir outputs/historical_polling_error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from polling_blind_spot.analysis.errors import AnalysisError
from polling_blind_spot.analysis.polling_error import run_historical_polling_error


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "raw",
        help="Directory containing the raw downloads (default: data/raw)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "historical_polling_error",
        help="Directory for error tables and figures (default: outputs/historical_polling_error)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = run_historical_polling_error(args.raw_dir, args.output_dir)
    except AnalysisError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    poll = report["poll_level"]
    race = report["race_level_unweighted_mean"]
    print(
        "Scored historical Senate polls: "
        f"{report['n_included_polls']} polls in {report['n_races']} contests "
        f"({report['n_excluded_questions']} questions excluded)"
    )
    print(
        "Poll-level mean signed error "
        f"{poll['mean_signed_error']} points, MAE {poll['mae']} "
        "(positive means the poll was more Democratic than the two-candidate result)"
    )
    print(
        "Race-level mean error of the unweighted poll average "
        f"{race['mean_signed_error']} points, MAE {race['mae']}"
    )
    print(f"Output directory: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
