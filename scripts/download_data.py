#!/usr/bin/env python3
"""Download and validate raw datasets for The Polling Blind Spot.

Raw files are written to data/raw/ and are not modified after download.
FiveThirtyEight and MIT returns are saved as published. The 2026 Senate
file is a long extract of English Wikipedia polling tables, with the
revision-pinned HTML kept beside it.

Usage:
    python3 scripts/download_data.py
    python3 scripts/download_data.py --source fte-historical --force
    python3 scripts/download_data.py --source medsl-senate --force
    python3 scripts/download_data.py --source wikipedia-2026 --force
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from polling_blind_spot.ingest.errors import DownloadError
from polling_blind_spot.ingest.http import download_bytes
from polling_blind_spot.ingest.schemas import (
    validate_csv_bytes,
    validate_fte_historical,
    validate_medsl_senate,
)
from polling_blind_spot.ingest.wikipedia_2026 import download_wikipedia_2026

RAW_DIR = PROJECT_ROOT / "data" / "raw"

# Official ABC News / FiveThirtyEight poll-tracker export. As of 2026-10 this
# host redirects to an HTML politics page, so the script falls back to a
# Wayback Machine snapshot of the same CSV.
FTE_HISTORICAL_URL = (
    "https://projects.fivethirtyeight.com/polls-page/data/senate_polls_historical.csv"
)
FTE_HISTORICAL_WAYBACK_URL = (
    "https://web.archive.org/web/20250306125405id_/"
    "https://projects.fivethirtyeight.com/polls-page/data/senate_polls_historical.csv"
)
FTE_HISTORICAL_FILENAME = "fivethirtyeight_senate_polls_historical.csv"

MEDSL_DATASET_DOI = "doi:10.7910/DVN/PEJ5QU"
MEDSL_DATASET_API_URL = (
    "https://dataverse.harvard.edu/api/datasets/:persistentId/"
    f"?persistentId={MEDSL_DATASET_DOI}"
)
MEDSL_FILE_API = "https://dataverse.harvard.edu/api/access/datafile/{file_id}"
MEDSL_SENATE_FILENAME = "medsl_us_senate_statewide_returns_1976_2024.csv"
MEDSL_CODEBOOK_FILENAME = "medsl_us_senate_returns_codebook.md"


def write_raw_file(filename: str, payload: bytes) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = RAW_DIR / filename
    dest.write_bytes(payload)
    return dest


def download_fte_historical(*, force: bool = False) -> Path:
    """Download FiveThirtyEight historical U.S. Senate polls."""
    dest = RAW_DIR / FTE_HISTORICAL_FILENAME
    if dest.exists() and not force:
        report = validate_fte_historical(dest)
        print(
            f"Using existing {dest} "
            f"({report['n_rows']} rows, {report['n_columns']} columns, "
            f"{report['n_states']} states)"
        )
        return dest

    urls = [FTE_HISTORICAL_URL, FTE_HISTORICAL_WAYBACK_URL]
    last_error: DownloadError | None = None
    for url in urls:
        print(f"Downloading FiveThirtyEight historical Senate polls from {url}")
        try:
            payload = download_bytes(url)
            validate_csv_bytes(payload, FTE_HISTORICAL_FILENAME)
        except DownloadError as exc:
            print(f"  skipped: {exc}")
            last_error = exc
            continue
        dest = write_raw_file(FTE_HISTORICAL_FILENAME, payload)
        report = validate_fte_historical(dest)
        print(
            f"Wrote {dest} ({report['n_rows']} rows, {report['n_columns']} columns, "
            f"cycles {', '.join(report['cycles'])})"
        )
        if url != FTE_HISTORICAL_URL:
            print(
                "Note: the live FiveThirtyEight URL did not return a CSV; "
                "used an Internet Archive snapshot of the same official file."
            )
        return dest

    raise last_error or DownloadError("No FiveThirtyEight historical poll URL succeeded")


def _dataverse_latest_files() -> list[dict]:
    """Return file records from the latest released MEDSL Senate dataset version."""
    payload = download_bytes(MEDSL_DATASET_API_URL)
    try:
        body = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise DownloadError("Harvard Dataverse metadata was not valid JSON") from exc
    version = body.get("data", {}).get("latestVersion", {})
    files = version.get("files", [])
    if not files:
        raise DownloadError("Harvard Dataverse metadata listed no files")
    license_info = version.get("license") or {}
    if license_info:
        print(
            "MEDSL license: "
            f"{license_info.get('name', 'unknown')} "
            f"({license_info.get('rightsIdentifier', 'no SPDX id')})"
        )
    return files


def _dataverse_file_id(files: list[dict], *, name_contains: str) -> int:
    needle = name_contains.lower()
    for record in files:
        data_file = record.get("dataFile") or {}
        names = [
            record.get("label") or "",
            data_file.get("filename") or "",
            data_file.get("originalFileName") or "",
        ]
        if any(needle in name.lower() for name in names):
            file_id = data_file.get("id")
            if file_id is None:
                raise DownloadError(f"Dataverse file matching {name_contains!r} has no id")
            return int(file_id)
    raise DownloadError(f"No Dataverse file matching {name_contains!r}")


def download_medsl_senate(*, force: bool = False) -> Path:
    """Download MIT Election Data + Science Lab U.S. Senate statewide returns."""
    dest = RAW_DIR / MEDSL_SENATE_FILENAME
    if dest.exists() and not force:
        report = validate_medsl_senate(dest)
        print(
            f"Using existing {dest} "
            f"({report['n_rows']} rows, {report['n_columns']} columns, "
            f"{report['year_min']}–{report['year_max']})"
        )
        return dest

    print(f"Resolving MEDSL Senate files from {MEDSL_DATASET_API_URL}")
    files = _dataverse_latest_files()
    file_id = _dataverse_file_id(files, name_contains="1976-2024-senate-state")
    url = f"{MEDSL_FILE_API.format(file_id=file_id)}?format=original"
    print(f"Downloading MEDSL Senate statewide returns from {url}")
    payload = download_bytes(url)
    validate_csv_bytes(payload, MEDSL_SENATE_FILENAME)
    dest = write_raw_file(MEDSL_SENATE_FILENAME, payload)
    report = validate_medsl_senate(dest)
    print(
        f"Wrote {dest} ({report['n_rows']} rows, {report['n_columns']} columns, "
        f"{report['year_min']}–{report['year_max']}, {report['n_states']} states)"
    )

    try:
        codebook_id = _dataverse_file_id(files, name_contains="codebook")
        codebook_url = MEDSL_FILE_API.format(file_id=codebook_id)
        codebook = download_bytes(codebook_url)
        if b"senate" not in codebook.lower():
            raise DownloadError("MEDSL codebook download did not mention the Senate")
        codebook_path = write_raw_file(MEDSL_CODEBOOK_FILENAME, codebook)
        print(f"Wrote {codebook_path} ({len(codebook)} bytes)")
    except DownloadError as exc:
        print(f"Codebook skipped: {exc}")

    return dest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        choices=["all", "fte-historical", "medsl-senate", "wikipedia-2026"],
        default="all",
        help="Which dataset to download (default: all)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if the raw file already exists",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.source in {"all", "fte-historical"}:
            download_fte_historical(force=args.force)
        if args.source in {"all", "medsl-senate"}:
            download_medsl_senate(force=args.force)
        if args.source in {"all", "wikipedia-2026"}:
            download_wikipedia_2026(RAW_DIR, force=args.force)
    except DownloadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
