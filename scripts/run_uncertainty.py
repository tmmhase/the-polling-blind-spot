#!/usr/bin/env python3
"""Fit the Senate polling-error model and write backtest diagnostics.

The input is the scored historical error table. Raw files and cleaned poll
tables are not modified, and a held-out cycle's results are not part of the
fit that scores that cycle.

Usage:
    python3 scripts/run_uncertainty.py
    python3 scripts/run_uncertainty.py --poll-errors outputs/historical_polling_error/poll_errors.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from polling_blind_spot.uncertainty.engine import run_uncertainty_engine
from polling_blind_spot.uncertainty.errors import UncertaintyError
from polling_blind_spot.uncertainty.model import SamplerSettings


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--poll-errors",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "historical_polling_error" / "poll_errors.csv",
        help="Scored historical poll errors (default: outputs/historical_polling_error/poll_errors.csv)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "uncertainty",
        help="Directory for posterior, simulation, and backtest tables (default: outputs/uncertainty)",
    )
    parser.add_argument("--seed", type=int, default=20261018)
    parser.add_argument("--burn-in", type=int, default=2000)
    parser.add_argument("--draws", type=int, default=2000)
    parser.add_argument("--thin", type=int, default=2)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = SamplerSettings(burn_in=args.burn_in, draws=args.draws, thin=args.thin, seed=args.seed)
    try:
        report = run_uncertainty_engine(args.poll_errors, args.output_dir, settings=settings)
    except UncertaintyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    posterior = {row["parameter"]: row for row in report["posterior"]}
    print(
        "Fitted hierarchical polling-error model on "
        f"{report['preparation']['n_polls']} polls in {report['preparation']['n_races']} contests"
    )
    print(
        "Late-poll mean error "
        f"{posterior['mu']['p50']:.2f} points "
        f"(5th–95th {posterior['mu']['p05']:.2f} to {posterior['mu']['p95']:.2f}); "
        f"race sd {posterior['sd_race']['p50']:.2f}, "
        f"pollster-within-race sd {posterior['sd_house']['p50']:.2f}, "
        f"cycle sd {posterior['sd_cycle']['p50']:.2f}, "
        f"sampling inflation {posterior['phi']['p50']:.2f}"
    )
    print(f"Output directory: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
