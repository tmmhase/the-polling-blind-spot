"""Schema checks for the three raw inputs."""

import csv
from pathlib import Path

import pytest

from polling_blind_spot.ingest.errors import DownloadError
from polling_blind_spot.ingest.schemas import (
    FTE_COLUMNS,
    MEDSL_COLUMNS,
    WIKIPEDIA_COLUMNS,
    validate_csv_bytes,
    validate_fte_historical,
    validate_medsl_senate,
    validate_wikipedia_polls,
)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
FTE_PATH = RAW / "fivethirtyeight_senate_polls_historical.csv"
MEDSL_PATH = RAW / "medsl_us_senate_statewide_returns_1976_2024.csv"
WIKI_CSV = RAW / "wikipedia_2026_us_senate_polls.csv"
WIKI_MANIFEST = RAW / "wikipedia_2026_us_senate_manifest.json"


def test_csv_bytes_rejects_html_and_tiny_payloads():
    with pytest.raises(DownloadError):
        validate_csv_bytes(b"<html><body>nope</body></html>", "example")
    with pytest.raises(DownloadError):
        validate_csv_bytes(b"a,b\n1,2\n", "example")


def test_fte_schema_rejects_a_missing_column(tmp_path: Path):
    path = tmp_path / "fte.csv"
    columns = [column for column in FTE_COLUMNS if column != "pct"]
    _write(path, columns, [{column: "x" for column in columns}])
    with pytest.raises(DownloadError, match="pct"):
        validate_fte_historical(path, min_rows=1)


def test_medsl_schema_rejects_a_non_senate_office(tmp_path: Path):
    path = tmp_path / "medsl.csv"
    row = {column: "0" for column in MEDSL_COLUMNS}
    row.update(
        {
            "year": "2024",
            "state": "MAINE",
            "state_po": "ME",
            "office": "US HOUSE",
            "candidate": "SOMEONE",
            "candidatevotes": "10",
            "totalvotes": "20",
            "special": "False",
        }
    )
    _write(path, MEDSL_COLUMNS, [row])
    with pytest.raises(DownloadError, match="office"):
        validate_medsl_senate(path, min_rows=1)


def test_wikipedia_schema_accepts_published_ranked_choice_and_missing_codes(tmp_path: Path):
    path = tmp_path / "wiki.csv"
    published = ["48%", "—", "—N/a", "5% U", "El-Sayed +4.0%", "1", "BA", "Tie"]
    rows = []
    for index, value in enumerate(published):
        row = {column: "" for column in WIKIPEDIA_COLUMNS}
        row.update(
            {
                "retrieved_at": "2026-10-15T13:15:27Z",
                "page_id": "1",
                "page_title": "2026 United States Senate election in Alaska",
                "revision_id": "2",
                "canonical_url": "https://en.wikipedia.org/wiki/Example",
                "state_name": "Alaska",
                "election_kind": "regular",
                "section_anchor": "Polling",
                "section_path": "General election > Polling",
                "table_index": "0",
                "table_kind": "poll",
                "row_index": str(index),
                "metadata_inherited": "false",
                "poll_source": "Alaska Survey Research",
                "dates_administered": "October 1–3, 2026",
                "sample_size": "1,512 (LV)",
                "response_column_index": "4",
                "response_label": "RCV round" if value in {"1", "BA"} else "Candidate",
                "response_value": value,
            }
        )
        rows.append(row)
    _write(path, WIKIPEDIA_COLUMNS, rows)
    report = validate_wikipedia_polls(path, min_states=1, min_poll_responses=1)
    assert report["poll_response_rows"] == len(published)


def test_wikipedia_schema_rejects_the_national_overview(tmp_path: Path):
    path = tmp_path / "wiki.csv"
    row = {column: "" for column in WIKIPEDIA_COLUMNS}
    row.update(
        {
            "retrieved_at": "2026-10-15T13:00:00Z",
            "page_id": "1",
            "page_title": "2026 United States Senate elections",
            "revision_id": "2",
            "state_name": "United States",
            "election_kind": "regular",
            "table_index": "0",
            "table_kind": "poll",
            "row_index": "0",
            "metadata_inherited": "false",
            "poll_source": "Example",
            "dates_administered": "October 1, 2026",
            "response_column_index": "4",
            "response_label": "Candidate",
            "response_value": "48%",
        }
    )
    _write(path, WIKIPEDIA_COLUMNS, [row])
    with pytest.raises(DownloadError, match="overview"):
        validate_wikipedia_polls(path, min_states=1, min_poll_responses=1)


@pytest.mark.skipif(not FTE_PATH.is_file(), reason="FiveThirtyEight file has not been downloaded")
def test_downloaded_fte_historical_file_matches_the_pinned_snapshot():
    report = validate_fte_historical(FTE_PATH)
    assert report["n_rows"] == 9292
    assert report["n_columns"] == 52
    assert report["cycles"] == ["2018", "2020", "2022", "2024"]
    assert report["n_states"] == 49


@pytest.mark.skipif(not MEDSL_PATH.is_file(), reason="MEDSL file has not been downloaded")
def test_downloaded_medsl_file_covers_1976_through_2024():
    report = validate_medsl_senate(MEDSL_PATH)
    assert report["n_rows"] == 3945
    assert report["year_min"] == 1976
    assert report["year_max"] == 2024
    assert report["n_states"] == 50


@pytest.mark.skipif(
    not (WIKI_CSV.is_file() and WIKI_MANIFEST.is_file()),
    reason="Wikipedia extract has not been downloaded",
)
def test_downloaded_wikipedia_bundle():
    from polling_blind_spot.ingest.schemas import validate_wikipedia_bundle

    report = validate_wikipedia_bundle(WIKI_CSV, WIKI_MANIFEST, RAW)
    assert report["poll_response_rows"] >= 200
    assert report["n_states_with_polls"] >= 15
    assert "Alabama" in report["states_with_polls"]


def _write(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
