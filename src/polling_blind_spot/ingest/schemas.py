"""Schema and data-quality checks for raw polling inputs.

These checks confirm that a download is the dataset it claims to be. They do
not impute values, score pollsters, or estimate uncertainty.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path

from polling_blind_spot.ingest.errors import DownloadError

MIN_CSV_BYTES = 1024

FTE_COLUMNS = [
    "poll_id",
    "pollster_id",
    "pollster",
    "sponsor_ids",
    "sponsors",
    "display_name",
    "pollster_rating_id",
    "pollster_rating_name",
    "numeric_grade",
    "pollscore",
    "methodology",
    "transparency_score",
    "state",
    "start_date",
    "end_date",
    "sponsor_candidate_id",
    "sponsor_candidate",
    "sponsor_candidate_party",
    "endorsed_candidate_id",
    "endorsed_candidate_name",
    "endorsed_candidate_party",
    "question_id",
    "sample_size",
    "population",
    "subpopulation",
    "population_full",
    "tracking",
    "created_at",
    "notes",
    "url",
    "url_article",
    "url_topline",
    "url_crosstab",
    "source",
    "internal",
    "partisan",
    "race_id",
    "cycle",
    "office_type",
    "seat_number",
    "seat_name",
    "election_date",
    "stage",
    "nationwide_batch",
    "ranked_choice_reallocated",
    "ranked_choice_round",
    "hypothetical",
    "party",
    "answer",
    "candidate_id",
    "candidate_name",
    "pct",
]

FTE_REQUIRED_NONEMPTY = (
    "poll_id",
    "pollster",
    "state",
    "start_date",
    "end_date",
    "question_id",
    "cycle",
    "office_type",
    "pct",
    "candidate_name",
    "answer",
)
FTE_CYCLES = {"2018", "2020", "2022", "2024"}
FTE_STAGES = {"general", "jungle primary", "runoff"}
FTE_DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2}$")
FTE_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")

MEDSL_COLUMNS = [
    "year",
    "state",
    "state_po",
    "state_fips",
    "state_cen",
    "state_ic",
    "office",
    "district",
    "stage",
    "special",
    "candidate",
    "party_detailed",
    "writein",
    "mode",
    "candidatevotes",
    "totalvotes",
    "unofficial",
    "version",
    "party_simplified",
]

WIKIPEDIA_COLUMNS = [
    "retrieved_at",
    "page_id",
    "page_title",
    "revision_id",
    "canonical_url",
    "state_name",
    "election_kind",
    "section_anchor",
    "section_path",
    "table_index",
    "table_kind",
    "table_group",
    "row_index",
    "metadata_inherited",
    "poll_source",
    "poll_source_url",
    "dates_administered",
    "dates_updated",
    "sample_size",
    "margin_of_error",
    "response_column_index",
    "response_label",
    "response_value",
]

# Floors, not expected totals. A parser failure should miss them; ordinary
# Wikipedia edits should not.
WIKIPEDIA_MIN_STATES_WITH_POLLS = 15
WIKIPEDIA_MIN_POLL_RESPONSES = 200

_PERCENT = re.compile(
    r"^[<>≈]?\s*\d{1,3}(?:\.\d+)?\s*%(?:\s*[A-Za-z]{1,4})?$"
)
# Dashes, Wikipedia's N/A template ("—N/a"), and a glued dash-plus-N/A.
_DASH = re.compile(
    r"^(?:[-–—−]+(?:\s*n/?a)?|n/?a|not available)$",
    re.IGNORECASE,
)
_MARGIN = re.compile(r"^.+\+\s*\d{1,3}(?:\.\d+)?\s*%$")
_TIE = re.compile(r"^(?:tie|tied|even)(?:\b.*)?$", re.IGNORECASE)
# Ranked-choice tables publish the round number, or "BA" before allocation.
_ROUND = re.compile(r"^\d{1,2}$|^[A-Z]{2,3}$")
_ISO_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def validate_csv_bytes(payload: bytes, source_name: str) -> dict:
    """Confirm payload is a delimited text table with a header and data rows."""
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


def validate_fte_historical(path: Path, *, min_rows: int = 8000) -> dict:
    """Validate the pinned FiveThirtyEight historical Senate poll schema."""
    rows = _read_csv(path, FTE_COLUMNS, "FiveThirtyEight historical Senate polls")
    errors: list[str] = []
    if len(rows) < min_rows:
        errors.append(f"expected at least {min_rows} rows, found {len(rows)}")

    cycles: set[str] = set()
    stages: set[str] = set()
    states: set[str] = set()
    for row in rows:
        for column in FTE_REQUIRED_NONEMPTY:
            if not row[column].strip():
                errors.append(f"blank {column}")
                break
        if row["office_type"] != "U.S. Senate":
            errors.append(f"unexpected office_type {row['office_type']!r}")
            break
        if row["pct"] and not FTE_NUMBER.match(row["pct"]):
            errors.append(f"non-numeric pct {row['pct']!r}")
            break
        if row["start_date"] and not FTE_DATE.match(row["start_date"]):
            errors.append(f"unexpected start_date {row['start_date']!r}")
            break
        if row["end_date"] and not FTE_DATE.match(row["end_date"]):
            errors.append(f"unexpected end_date {row['end_date']!r}")
            break
        cycles.add(row["cycle"])
        stages.add(row["stage"])
        states.add(row["state"])

    if cycles != FTE_CYCLES:
        errors.append(f"cycles were {sorted(cycles)}, expected {sorted(FTE_CYCLES)}")
    unknown_stages = stages - FTE_STAGES
    if unknown_stages:
        errors.append(f"unexpected stages {sorted(unknown_stages)}")
    if "general" not in stages:
        errors.append("no general-election rows")
    if len(states) < 45:
        errors.append(f"only {len(states)} states present")

    report = {
        "source": "fte-historical",
        "path": str(path),
        "n_rows": len(rows),
        "n_columns": len(FTE_COLUMNS),
        "cycles": sorted(cycles),
        "stages": sorted(stages),
        "n_states": len(states),
    }
    _raise_if(errors, "FiveThirtyEight historical Senate polls")
    return report


def validate_medsl_senate(path: Path, *, min_rows: int = 3000) -> dict:
    """Validate MIT Election Data + Science Lab statewide Senate returns."""
    rows = _read_csv(path, MEDSL_COLUMNS, "MEDSL Senate statewide returns")
    errors: list[str] = []
    if len(rows) < min_rows:
        errors.append(f"expected at least {min_rows} rows, found {len(rows)}")

    years: set[int] = set()
    states: set[str] = set()
    blank_named_candidates = 0
    unnamed_writeins = 0
    for row in rows:
        if row["office"] != "US SENATE":
            errors.append(f"unexpected office {row['office']!r}")
        elif not re.fullmatch(r"\d{4}", row["year"]):
            errors.append(f"unexpected year {row['year']!r}")
        else:
            years.add(int(row["year"]))
        if not re.fullmatch(r"[A-Z]{2}", row["state_po"]):
            errors.append(f"unexpected state_po {row['state_po']!r}")
        else:
            states.add(row["state_po"])
        if not row["candidate"].strip():
            if row["writein"] == "True":
                unnamed_writeins += 1
            else:
                blank_named_candidates += 1
        for column in ("candidatevotes", "totalvotes"):
            try:
                float(row[column])
            except ValueError:
                errors.append(f"non-numeric {column} {row[column]!r}")
        if row["special"] not in {"True", "False"}:
            errors.append(f"unexpected special flag {row['special']!r}")
    if blank_named_candidates:
        errors.append(f"{blank_named_candidates} rows have a blank candidate and are not write-ins")

    if years and (min(years) != 1976 or max(years) != 2024):
        errors.append(f"year coverage {min(years) if years else None}–{max(years) if years else None}")
    if 1976 not in years or 2024 not in years:
        errors.append("file does not include both 1976 and 2024")
    if len(states) != 50:
        errors.append(f"expected 50 state postal codes, found {len(states)}")

    report = {
        "source": "medsl-senate",
        "path": str(path),
        "n_rows": len(rows),
        "n_columns": len(MEDSL_COLUMNS),
        "year_min": min(years) if years else None,
        "year_max": max(years) if years else None,
        "n_states": len(states),
        "n_unnamed_writeins": unnamed_writeins,
    }
    _raise_if(errors, "MEDSL Senate statewide returns")
    return report


def validate_wikipedia_polls(
    path: Path,
    *,
    min_states: int = WIKIPEDIA_MIN_STATES_WITH_POLLS,
    min_poll_responses: int = WIKIPEDIA_MIN_POLL_RESPONSES,
) -> dict:
    """Validate the extracted 2026 Senate polling table."""
    rows = _read_csv(path, WIKIPEDIA_COLUMNS, "Wikipedia 2026 Senate polls")
    errors: list[str] = []
    keys: set[tuple[str, ...]] = set()
    states_with_polls: set[str] = set()
    poll_responses = 0
    aggregation_responses = 0
    empty_poll_source = 0
    implausible: list[str] = []
    plausible_poll_values = 0
    dated_poll_rows: set[tuple[str, ...]] = set()
    undated_poll_rows: set[tuple[str, ...]] = set()

    for row in rows:
        if not _ISO_TIMESTAMP.match(row["retrieved_at"]):
            errors.append(f"retrieved_at is not UTC ISO-8601: {row['retrieved_at']!r}")
            break
        if not row["page_id"].isdigit() or not row["revision_id"].isdigit():
            errors.append("page_id and revision_id must be integers")
            break
        if row["election_kind"] not in {"regular", "special"}:
            errors.append(f"unexpected election_kind {row['election_kind']!r}")
            break
        if row["table_kind"] not in {"poll", "aggregation"}:
            errors.append(f"unexpected table_kind {row['table_kind']!r}")
            break
        if row["metadata_inherited"] not in {"true", "false"}:
            errors.append("metadata_inherited must be true or false")
            break
        if not row["state_name"].strip() or not row["page_title"].strip():
            errors.append("blank state_name or page_title")
            break
        if "2026 United States Senate elections" == row["page_title"]:
            errors.append("national overview page was included")
            break
        key = (
            row["page_id"],
            row["revision_id"],
            row["section_anchor"],
            row["table_index"],
            row["row_index"],
            row["response_column_index"],
        )
        if key in keys:
            errors.append(f"duplicate response key {key}")
            break
        keys.add(key)
        if row["table_kind"] == "poll":
            poll_responses += 1
            states_with_polls.add(row["state_name"])
            if not row["poll_source"].strip():
                empty_poll_source += 1
            row_key = (row["page_id"], row["section_anchor"], row["table_index"], row["row_index"])
            if row["dates_administered"].strip():
                dated_poll_rows.add(row_key)
            else:
                undated_poll_rows.add(row_key)
            if _plausible_response(row["response_value"]):
                plausible_poll_values += 1
            elif len(implausible) < 8:
                implausible.append(row["response_value"])
        else:
            aggregation_responses += 1

    if poll_responses < min_poll_responses:
        errors.append(
            f"expected at least {min_poll_responses} individual-poll response cells, "
            f"found {poll_responses}"
        )
    if len(states_with_polls) < min_states:
        errors.append(
            f"expected polls in at least {min_states} states, found {len(states_with_polls)}"
        )
    if poll_responses and empty_poll_source / poll_responses > 0.15:
        errors.append(
            f"{empty_poll_source} of {poll_responses} poll cells have no poll source"
        )
    undated_only = undated_poll_rows - dated_poll_rows
    dated_or_not = dated_poll_rows | undated_poll_rows
    if dated_or_not and len(undated_only) / len(dated_or_not) > 0.2:
        errors.append("more than 20% of poll rows have no dates administered")
    if poll_responses and plausible_poll_values / poll_responses < 0.7:
        errors.append(
            "fewer than 70% of poll response values look like percentages, "
            f"dashes, ties, or margins; examples: {implausible}"
        )

    report = {
        "source": "wikipedia-2026",
        "path": str(path),
        "n_rows": len(rows),
        "n_columns": len(WIKIPEDIA_COLUMNS),
        "poll_response_rows": poll_responses,
        "aggregation_response_rows": aggregation_responses,
        "n_states_with_polls": len(states_with_polls),
        "states_with_polls": sorted(states_with_polls),
    }
    _raise_if(errors, "Wikipedia 2026 Senate polls")
    return report


def validate_wikipedia_bundle(csv_path: Path, manifest_path: Path, raw_dir: Path) -> dict:
    """Validate the extract, the revision manifest, and the saved HTML pages."""
    report = validate_wikipedia_polls(csv_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    pages = manifest.get("pages")
    if not isinstance(pages, list) or not pages:
        errors.append("manifest has no pages")
        pages = []
    if manifest.get("license") != "CC BY-SA 4.0":
        errors.append("manifest license is not CC BY-SA 4.0")
    if manifest.get("csv_sha256") != _sha256(csv_path):
        errors.append("manifest csv_sha256 does not match the extract")

    by_title = {}
    for page in pages:
        title = page.get("title")
        by_title[title] = page
        html_rel = page.get("html_path")
        if not html_rel:
            errors.append(f"{title} is missing html_path")
            continue
        html_path = raw_dir / html_rel
        if not html_path.is_file():
            errors.append(f"missing raw HTML for {title}")
            continue
        payload = html_path.read_bytes()
        if _sha256_bytes(payload) != page.get("html_sha256"):
            errors.append(f"HTML sha256 mismatch for {title}")
        if not payload.lstrip().lower().startswith((b"<!doctype html", b"<html")):
            errors.append(f"saved page for {title} is not HTML")
        revision = str(page.get("revision_id", ""))
        if not revision.isdigit():
            errors.append(f"missing revision_id for {title}")

    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            page = by_title.get(row["page_title"])
            if page is None:
                errors.append(f"CSV title {row['page_title']} is not in the manifest")
                break
            if str(page.get("revision_id")) != row["revision_id"]:
                errors.append(
                    f"revision mismatch for {row['page_title']}: "
                    f"csv {row['revision_id']} manifest {page.get('revision_id')}"
                )
                break

    _raise_if(errors, "Wikipedia 2026 Senate poll bundle")
    report["n_pages"] = len(pages)
    report["manifest"] = str(manifest_path)
    return report


def _plausible_response(value: str) -> bool:
    text = value.strip()
    return bool(
        _PERCENT.match(text)
        or _DASH.match(text)
        or _MARGIN.match(text)
        or _TIE.match(text)
        or _ROUND.match(text)
    )


def _read_csv(path: Path, expected: list[str], source_name: str) -> list[dict[str, str]]:
    if not path.is_file():
        raise DownloadError(f"{source_name} file does not exist: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise DownloadError(f"{source_name} has no header")
        fieldnames = [name.strip() for name in reader.fieldnames]
        if fieldnames != expected:
            raise DownloadError(
                f"{source_name} columns differ from the expected schema. "
                f"Missing {sorted(set(expected) - set(fieldnames))}; "
                f"unexpected {sorted(set(fieldnames) - set(expected))}"
            )
        rows = []
        for row in reader:
            rows.append({key: (row.get(key) or "") for key in expected})
    if not rows:
        raise DownloadError(f"{source_name} has a header but no data rows")
    return rows


def _raise_if(errors: list[str], source_name: str) -> None:
    if errors:
        preview = "; ".join(errors[:8])
        extra = f" (+{len(errors) - 8} more)" if len(errors) > 8 else ""
        raise DownloadError(f"{source_name} failed validation: {preview}{extra}")


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
