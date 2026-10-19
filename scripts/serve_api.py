#!/usr/bin/env python3
"""Serve the dashboard API.

The process reads committed files under ``outputs/`` and does not download data.

Usage:
    python3 scripts/serve_api.py
    python3 scripts/serve_api.py --port 8000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import uvicorn


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    uvicorn.run(
        "polling_blind_spot.api.app:app",
        host=args.host,
        port=args.port,
        factory=False,
    )


if __name__ == "__main__":
    main()
