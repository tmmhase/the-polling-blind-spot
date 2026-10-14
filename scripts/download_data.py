#!/usr/bin/env python3
"""Download and validate raw datasets for The Polling Blind Spot.

This script uses only the Python standard library (plus the system `curl`
binary when Python cannot verify TLS certificates). Raw files are written
to data/raw/ and are never modified after download.

Usage:
    python3 scripts/download_data.py
    python3 scripts/download_data.py --source fte-historical --force
"""

from __future__ import annotations

import argparse
import csv
import io
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

USER_AGENT = (
    "ThePollingBlindSpot/0.1 (research portfolio; reproducible data download)"
)

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

MIN_CSV_BYTES = 1024


class DownloadError(RuntimeError):
    """Raised when a remote file cannot be fetched or validated."""


def download_bytes(url: str, timeout: int = 180) -> bytes:
    """Fetch URL contents, trying urllib then curl. Reject HTML error pages."""
    errors: list[str] = []

    try:
        return _download_with_urllib(url, timeout=timeout)
    except DownloadError as exc:
        errors.append(f"urllib: {exc}")

    curl_path = shutil.which("curl")
    if curl_path:
        try:
            return _download_with_curl(curl_path, url, timeout=timeout)
        except DownloadError as trans_exc:
            errors.append(f"curl: {trans_exc}")

    raise DownloadError(
        f"Failed to fetch {url}. " + " | ".join(errors)
    )


def _download_with_urllib(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/csv,application/json,*/*"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=timeout, context=ssl.create_default_context()
        ) as response:
            status = getattr(response, "status", None)
            if status is not None and status >= 400:
                raise DownloadError(f"HTTP {status}")
            content_type = response.headers.get("Content-Type", "")
            payload = response.read()
    except urllib.error.HTTPError as exc:
        raise DownloadError(f"HTTP {exc.code} {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise DownloadError(str(exc.reason)) from exc

    return _reject_html(payload, content_type, url)


def _download_with_curl(curl_path: str, url: str, timeout: int) -> bytes:
    completed = subprocess.run(
        [
            curl_path,
            "-sS",
            "-L",
            "--fail",
            "--max-time",
            str(timeout),
            "-A",
            USER_AGENT,
            "-H",
            "Accept: text/csv,application/json,*/*",
            url,
        ],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise DownloadError(stderr or f"curl exited {completed.returncode}")
    return _reject_html(completed.stdout, "", url)


def _reject_html(payload: bytes, content_type: str, url: str) -> bytes:
    if not payload:
        raise DownloadError(f"Empty response from {url}")
    if _looks_like_html(payload, content_type):
        raise DownloadError(
            f"Response from {url} looks like HTML, not a dataset "
            f"(Content-Type={content_type!r}, {len(payload)} bytes)"
        )
    return payload


def _looks_like_html(payload: bytes, content_type: str) -> bool:
    lowered_type = content_type.lower()
    if "text/html" in lowered_type:
        return True
    head = payload.lstrip()[:200].lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def validate_csv_bytes(payload: bytes, source_name: str) -> dict:
    """Confirm payload is a delimited text table with a header row."""
    if len(payload) < MIN_CSV_BYTES:
        raise DownloadError(
            f"{source_name} is too small to be a complete dataset "
            f"({len(payload)} bytes)"
        )

    text = payload.decode("utf-8-sig", errors="replace")
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error as exc:
        raise DownloadError(f"{source_name} is not recognizable as CSV: {exc}") from exc

    reader = csv.reader(io.StringIO(text), dialect)
    try:
        header = next(reader)
    except StopIteration as exc:
        raise DownloadError(f"{source_name} has no header row") from exc

    columns = [col.strip() for col in header if col.strip()]
    if len(columns) < 2:
        raise DownloadError(f"{source_name} header does not look tabular: {header!r}")

    row_count = sum(1 for _ in reader)
    if row_count < 1:
        raise DownloadError(f"{source_name} has a header but no data rows")

    return {
        "columns": columns,
        "n_columns": len(columns),
        "n_rows": row_count,
        "bytes": len(payload),
        "delimiter": dialect.delimiter,
    }


def write_raw_file(filename: str, payload: bytes) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = RAW_DIR / filename
    dest.write_bytes(payload)
    return dest


def download_fte_historical(*, force: bool = False) -> Path:
    """Download FiveThirtyEight historical U.S. Senate polls."""
    dest = RAW_DIR / FTE_HISTORICAL_FILENAME
    if dest.exists() and not force:
        payload = dest.read_bytes()
        stats = validate_csv_bytes(payload, dest.name)
        print(
            f"Using existing {dest} "
            f"({stats['n_rows']} rows, {stats['n_columns']} columns)"
        )
        return dest

    urls = [FTE_HISTORICAL_URL, FTE_HISTORICAL_WAYBACK_URL]
    last_error: DownloadError | None = None
    for url in urls:
        print(f"Downloading FiveThirtyEight historical Senate polls from {url}")
        try:
            payload = download_bytes(url)
            stats = validate_csv_bytes(payload, FTE_HISTORICAL_FILENAME)
        except DownloadError as exc:
            print(f"  skipped: {exc}")
            last_error = exc
            continue
        dest = write_raw_file(FTE_HISTORICAL_FILENAME, payload)
        print(
            f"Wrote {dest} ({stats['bytes']} bytes, {stats['n_rows']} rows, "
            f"{stats['n_columns']} columns)"
        )
        if url != FTE_HISTORICAL_URL:
            print(
                "Note: the live FiveThirtyEight URL did not return a CSV; "
                "used an Internet Archive snapshot of the same official file."
            )
        return dest

    raise last_error or DownloadError("No FiveThirtyEight historical poll URL succeeded")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        choices=["all", "fte-historical"],
        default="all",
        help="Which dataset to download (default: all implemented sources)",
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
    except DownloadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
