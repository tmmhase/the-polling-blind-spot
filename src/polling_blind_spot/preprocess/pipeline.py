"""Build cleaned Senate polling tables from the raw downloads.

The raw files are read and left unchanged. Cleaned tables are written to a
separate directory. Missing sample sizes, dates, and response shares stay
missing. Wikipedia rows whose poll-source cell is a number or a percentage
are written to a quarantine file instead of being realigned.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from polling_blind_spot.ingest.schemas import FTE_COLUMNS, WIKIPEDIA_COLUMNS
from polling_blind_spot.preprocess.errors import PreprocessError
from polling_blind_spot.preprocess.margins import QUESTION_COLUMNS, build_questions
from polling_blind_spot.preprocess.standardize import (
    classify_response_label,
    collapse,
    isoformat,
    parse_field_dates,
    parse_flag,
    parse_fte_date,
    parse_fte_pct,
    parse_margin_of_error,
    parse_numeric_sample,
    parse_population,
    parse_wikipedia_sample,
    parse_wikipedia_share,
    pollster_is_implausible,
    section_is_hypothetical,
    section_is_ranked_choice,
    stage_from_section,
    standardize_pollster,
    standardize_stage,
    standardize_state,
)

FTE_FILENAME = "fivethirtyeight_senate_polls_historical.csv"
WIKIPEDIA_FILENAME = "wikipedia_2026_us_senate_polls.csv"

RESPONSE_COLUMNS = [
    "source",
    "record_type",
    "question_id",
    "poll_id",
    "cycle",
    "state_name",
    "state_po",
    "election_kind",
    "seat_class",
    "seat_number",
    "stage",
    "hypothetical",
    "ranked_choice",
    "pollster",
    "pollster_raw",
    "pollster_display",
    "pollster_key",
    "pollster_affiliation",
    "pollster_id",
    "start_date",
    "end_date",
    "date_grain",
    "dates_raw",
    "election_date",
    "sample_size",
    "sample_size_raw",
    "sample_size_status",
    "population",
    "population_raw",
    "margin_of_error",
    "margin_of_error_raw",
    "margin_of_error_status",
    "methodology",
    "tracking",
    "internal",
    "partisan",
    "metadata_inherited",
    "table_group",
    "section_path",
    "revision_id",
    "page_id",
    "page_title",
    "candidate_name",
    "candidate_name_raw",
    "candidate_short",
    "party",
    "party_raw",
    "response_role",
    "pct",
    "pct_raw",
    "pct_status",
    "response_order",
    "poll_url",
    "notes",
]

FLAG_COLUMNS = {
    "hypothetical",
    "ranked_choice",
    "tracking",
    "internal",
    "metadata_inherited",
    "two_party_general",
    "top_two_tie",
    "published_margin_tie",
}
INTEGER_COLUMNS = {
    "cycle",
    "sample_size",
    "response_order",
    "n_response_rows",
    "n_candidates_with_pct",
}
_POPULATION_TOKEN = re.compile(r"\(([^)]*)\)\s*$")

OUTPUTS = {
    "fte_responses": "fte_senate_poll_responses.csv",
    "fte_questions": "fte_senate_poll_questions.csv",
    "wikipedia_responses": "wikipedia_2026_poll_responses.csv",
    "wikipedia_questions": "wikipedia_2026_poll_questions.csv",
    "wikipedia_quarantine": "wikipedia_2026_poll_quarantine.csv",
    "wikipedia_aggregations": "wikipedia_2026_aggregation_responses.csv",
    "report": "preprocess_report.json",
}

MARGIN_DEFINITION = (
    "margin_dem_minus_rep is the published Democratic percentage minus the "
    "published Republican percentage, in percentage points. It is calculated "
    "only when the question has exactly one Democratic-side candidate "
    "(DEM or DFL) and exactly one REP candidate with numeric shares. "
    "Shares are not rescaled to exclude undecided or other responses."
)


def run_preprocessing(raw_dir: Path, processed_dir: Path) -> dict[str, Any]:
    """Read raw polls and write cleaned response and question tables."""
    raw_dir = raw_dir.resolve()
    processed_dir = processed_dir.resolve()
    if raw_dir == processed_dir:
        raise PreprocessError("The processed directory must be separate from the raw directory.")

    fte_path = raw_dir / FTE_FILENAME
    wiki_path = raw_dir / WIKIPEDIA_FILENAME
    fte_raw = _read_raw(fte_path, FTE_COLUMNS)
    wiki_raw = _read_raw(wiki_path, WIKIPEDIA_COLUMNS)

    fte_responses = clean_fte_responses(fte_raw)
    wiki_polls, wiki_quarantine = clean_wikipedia_responses(wiki_raw, record_type="poll")
    wiki_aggregations, _ = clean_wikipedia_responses(wiki_raw, record_type="aggregation")
    fte_questions = build_questions(fte_responses)
    wiki_questions = build_questions(wiki_polls)

    processed_dir.mkdir(parents=True, exist_ok=True)
    _write_frame(fte_responses, processed_dir / OUTPUTS["fte_responses"])
    _write_frame(fte_questions, processed_dir / OUTPUTS["fte_questions"])
    _write_frame(wiki_polls, processed_dir / OUTPUTS["wikipedia_responses"])
    _write_frame(wiki_questions, processed_dir / OUTPUTS["wikipedia_questions"])
    _write_frame(wiki_quarantine, processed_dir / OUTPUTS["wikipedia_quarantine"])
    _write_frame(wiki_aggregations, processed_dir / OUTPUTS["wikipedia_aggregations"])

    report = {
        "margin_definition": MARGIN_DEFINITION,
        "inputs": {
            "fte_historical": {
                "path": str(fte_path),
                "sha256": _sha256(fte_path),
                "rows": int(len(fte_raw)),
            },
            "wikipedia_2026": {
                "path": str(wiki_path),
                "sha256": _sha256(wiki_path),
                "rows": int(len(wiki_raw)),
            },
        },
        "outputs": {
            "fte_responses": _response_summary(fte_responses),
            "fte_questions": _question_summary(fte_questions),
            "wikipedia_responses": _response_summary(wiki_polls),
            "wikipedia_questions": _question_summary(wiki_questions),
            "wikipedia_quarantine": _response_summary(wiki_quarantine),
            "wikipedia_aggregations": _response_summary(wiki_aggregations),
        },
    }
    (processed_dir / OUTPUTS["report"]).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def clean_fte_responses(raw: pd.DataFrame) -> pd.DataFrame:
    """Standardize FiveThirtyEight candidate rows. Every input row is kept."""
    _require_columns(raw, FTE_COLUMNS, "FiveThirtyEight historical Senate polls")
    rows: list[dict[str, Any]] = []
    order_within_question: dict[str, int] = {}
    for record in raw.to_dict(orient="records"):
        question_id = str(record["question_id"]).strip()
        order_within_question[question_id] = order_within_question.get(question_id, 0) + 1
        state_name, state_po = standardize_state(record["state"])
        pollster = standardize_pollster(record["pollster"])
        display = standardize_pollster(record["display_name"])
        sample_size, sample_status = parse_numeric_sample(record["sample_size"])
        share = parse_fte_pct(record["pct"])
        start = parse_fte_date(record["start_date"])
        end = parse_fte_date(record["end_date"])
        election = parse_fte_date(record["election_date"])
        if start and end:
            date_grain = "day"
        elif not str(record["start_date"]).strip() and not str(record["end_date"]).strip():
            date_grain = "missing"
        elif (str(record["start_date"]).strip() and start is None) or (
            str(record["end_date"]).strip() and end is None
        ):
            date_grain = "unparsed"
        else:
            date_grain = "partial"
        rows.append(
            {
                "source": "fte_historical",
                "record_type": "poll",
                "question_id": question_id,
                "poll_id": str(record["poll_id"]).strip() or None,
                "cycle": _int_or_none(record["cycle"]),
                "state_name": state_name,
                "state_po": state_po,
                "election_kind": None,
                "seat_class": _blank_none(record["seat_name"]),
                "seat_number": _blank_none(record["seat_number"]),
                "stage": standardize_stage(record["stage"]),
                "hypothetical": parse_flag(record["hypothetical"]),
                "ranked_choice": parse_flag(record["ranked_choice_reallocated"]),
                "pollster": pollster.name,
                "pollster_raw": _blank_none(record["pollster"]),
                "pollster_display": display.name,
                "pollster_key": pollster.key,
                "pollster_affiliation": pollster.affiliation,
                "pollster_id": _blank_none(record["pollster_id"]),
                "start_date": isoformat(start),
                "end_date": isoformat(end),
                "date_grain": date_grain,
                "dates_raw": _join_dates(record["start_date"], record["end_date"]),
                "election_date": isoformat(election),
                "sample_size": sample_size,
                "sample_size_raw": _blank_none(record["sample_size"]),
                "sample_size_status": sample_status,
                "population": parse_population(record["population"]),
                "population_raw": _blank_none(record["population"]),
                "margin_of_error": None,
                "margin_of_error_raw": None,
                "margin_of_error_status": None,
                "methodology": _blank_none(record["methodology"]),
                "tracking": parse_flag(record["tracking"]),
                "internal": parse_flag(record["internal"]),
                "partisan": _blank_none(record["partisan"]),
                "metadata_inherited": False,
                "table_group": None,
                "section_path": None,
                "revision_id": None,
                "page_id": None,
                "page_title": None,
                "candidate_name": _blank_none(collapse(record["candidate_name"])),
                "candidate_name_raw": _blank_none(record["candidate_name"]),
                "candidate_short": _blank_none(record["answer"]),
                "party": _blank_none(record["party"]),
                "party_raw": _blank_none(record["party"]),
                "response_role": "candidate",
                "pct": share.pct,
                "pct_raw": _blank_none(record["pct"]),
                "pct_status": share.status,
                "response_order": order_within_question[question_id],
                "poll_url": _blank_none(record["url"]),
                "notes": _blank_none(record["notes"]),
            }
        )
    return pd.DataFrame.from_records(rows, columns=RESPONSE_COLUMNS)


def clean_wikipedia_responses(
    raw: pd.DataFrame,
    *,
    record_type: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Standardize Wikipedia response cells of one ``table_kind``.

    Poll rows with an implausible poll source are returned in the quarantine
    frame. Aggregation rows are never quarantined by that rule; callers that
    ask for aggregations receive an empty quarantine frame.
    """
    if record_type not in {"poll", "aggregation"}:
        raise PreprocessError(f"Unsupported Wikipedia record type: {record_type}")
    _require_columns(raw, WIKIPEDIA_COLUMNS, "Wikipedia 2026 Senate polls")
    selected = raw.loc[raw["table_kind"] == record_type]
    parsed: list[dict[str, Any]] = []
    reasons: dict[str, str] = {}
    for record in selected.to_dict(orient="records"):
        question_id = _wikipedia_question_id(record)
        row = _wikipedia_row(record, question_id, record_type)
        parsed.append(row)
        if record_type == "poll" and pollster_is_implausible(record["poll_source"]):
            reasons[question_id] = "poll_source_is_not_a_pollster"

    kept = [row for row in parsed if row["question_id"] not in reasons]
    quarantined = []
    for row in parsed:
        reason = reasons.get(row["question_id"])
        if reason is None:
            continue
        quarantined.append({**row, "quarantine_reason": reason})
    kept_frame = pd.DataFrame.from_records(kept, columns=RESPONSE_COLUMNS)
    quarantine_columns = [*RESPONSE_COLUMNS, "quarantine_reason"]
    quarantine_frame = pd.DataFrame.from_records(quarantined, columns=quarantine_columns)
    return kept_frame, quarantine_frame


def _wikipedia_row(record: dict[str, str], question_id: str, record_type: str) -> dict[str, Any]:
    state_name, state_po = standardize_state(record["state_name"])
    pollster = standardize_pollster(record["poll_source"])
    dates = parse_field_dates(record["dates_administered"])
    sample = parse_wikipedia_sample(record["sample_size"])
    share = parse_wikipedia_share(record["response_value"])
    moe, moe_status = parse_margin_of_error(record["margin_of_error"])
    label = classify_response_label(record["response_label"])
    if label.role == "published_margin":
        share_pct = None
        share_status = "not_a_share"
    else:
        share_pct = share.pct
        share_status = share.status
    return {
        "source": "wikipedia_2026",
        "record_type": record_type,
        "question_id": question_id,
        "poll_id": question_id,
        "cycle": 2026,
        "state_name": state_name,
        "state_po": state_po,
        "election_kind": _blank_none(record["election_kind"]),
        "seat_class": None,
        "seat_number": None,
        "stage": stage_from_section(record["section_path"]),
        "hypothetical": section_is_hypothetical(record["table_group"], record["section_path"]),
        "ranked_choice": section_is_ranked_choice(record["section_path"]),
        "pollster": pollster.name,
        "pollster_raw": _blank_none(record["poll_source"]),
        "pollster_display": pollster.name,
        "pollster_key": pollster.key,
        "pollster_affiliation": pollster.affiliation,
        "pollster_id": None,
        "start_date": isoformat(dates.start),
        "end_date": isoformat(dates.end),
        "date_grain": dates.grain,
        "dates_raw": _blank_none(record["dates_administered"]),
        "election_date": None,
        "sample_size": sample.sample_size,
        "sample_size_raw": _blank_none(record["sample_size"]),
        "sample_size_status": sample.status,
        "population": sample.population,
        "population_raw": _raw_population(record["sample_size"]),
        "margin_of_error": moe,
        "margin_of_error_raw": _blank_none(record["margin_of_error"]),
        "margin_of_error_status": moe_status,
        "methodology": None,
        "tracking": None,
        "internal": None,
        "partisan": None,
        "metadata_inherited": parse_flag(record["metadata_inherited"]),
        "table_group": _blank_none(record["table_group"]),
        "section_path": _blank_none(record["section_path"]),
        "revision_id": _blank_none(record["revision_id"]),
        "page_id": _blank_none(record["page_id"]),
        "page_title": _blank_none(record["page_title"]),
        "candidate_name": _blank_none(collapse(label.candidate_name)),
        "candidate_name_raw": _blank_none(record["response_label"]),
        "candidate_short": None,
        "party": label.party,
        "party_raw": label.party,
        "response_role": label.role,
        "pct": share_pct,
        "pct_raw": _blank_none(record["response_value"]),
        "pct_status": share_status,
        "response_order": _int_or_none(record["response_column_index"]),
        "poll_url": _blank_none(record["poll_source_url"]),
        "notes": None,
    }


def _wikipedia_question_id(record: dict[str, str]) -> str:
    parts = [
        record["page_id"].strip(),
        record["revision_id"].strip(),
        record["section_anchor"].strip(),
        record["table_index"].strip(),
        record["row_index"].strip(),
    ]
    return "wiki-" + "-".join(parts)


def _read_raw(path: Path, expected: list[str]) -> pd.DataFrame:
    if not path.is_file():
        raise PreprocessError(f"Raw file does not exist: {path}")
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)
    _require_columns(frame, expected, path.name)
    return frame


def _require_columns(frame: pd.DataFrame, expected: list[str], source_name: str) -> None:
    columns = list(frame.columns)
    if columns != expected:
        missing = [column for column in expected if column not in columns]
        unexpected = [column for column in columns if column not in expected]
        raise PreprocessError(
            f"{source_name} columns differ from the raw schema. "
            f"Missing {missing}; unexpected {unexpected}"
        )


def _write_frame(frame: pd.DataFrame, path: Path) -> None:
    output = frame.copy()
    for column in FLAG_COLUMNS:
        if column in output.columns:
            output[column] = output[column].map(_format_flag)
    for column in INTEGER_COLUMNS:
        if column in output.columns:
            output[column] = pd.to_numeric(output[column], errors="coerce").astype("Int64")
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(path, index=False, na_rep="")


def _format_flag(value: Any) -> str:
    if _is_missing(value):
        return ""
    return "true" if bool(value) else "false"


def _is_true(value: Any) -> bool:
    if _is_missing(value):
        return False
    if isinstance(value, str):
        return value.strip().casefold() == "true"
    return bool(value)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        missing = pd.isna(value)
    except TypeError:
        return False
    return bool(missing)


def _response_summary(frame: pd.DataFrame) -> dict[str, Any]:
    summary: dict[str, Any] = {"rows": int(len(frame))}
    if frame.empty:
        return summary
    if "question_id" in frame.columns:
        summary["questions"] = int(frame["question_id"].nunique())
    if "sample_size_status" in frame.columns:
        summary["sample_size_status"] = _counts(frame["sample_size_status"])
    if "date_grain" in frame.columns:
        summary["date_grain"] = _counts(frame["date_grain"])
    if "pct_status" in frame.columns:
        summary["pct_status"] = _counts(frame["pct_status"])
    return summary


def _question_summary(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"rows": 0}
    comparable_count = int(frame["two_party_general"].map(_is_true).sum())
    return {
        "rows": int(len(frame)),
        "margin_status": _counts(frame["margin_status"]),
        "two_party_general": comparable_count,
        "missing_sample_size": int(frame["sample_size"].map(_is_missing).sum()),
    }


def _counts(series: pd.Series) -> dict[str, int]:
    filled = series.fillna("(missing)").astype(str).replace({"": "(missing)"})
    return {str(key): int(value) for key, value in filled.value_counts().sort_index().items()}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _blank_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    text = _blank_none(value)
    if text is None or not text.isdigit():
        return None
    return int(text)


def _raw_population(value: Any) -> str | None:
    text = _blank_none(value)
    if text is None:
        return None
    match = _POPULATION_TOKEN.search(text)
    if match is None:
        return None
    return _blank_none(match.group(1))


def _join_dates(start: Any, end: Any) -> str | None:
    start_text = _blank_none(start)
    end_text = _blank_none(end)
    if start_text and end_text:
        return f"{start_text} – {end_text}"
    return start_text or end_text


# Re-exported for callers that want the question schema next to the writer.
__all__ = [
    "FTE_FILENAME",
    "OUTPUTS",
    "QUESTION_COLUMNS",
    "RESPONSE_COLUMNS",
    "WIKIPEDIA_FILENAME",
    "clean_fte_responses",
    "clean_wikipedia_responses",
    "run_preprocessing",
]
