"""Question-level polling margins.

The primary margin is the published Democratic percentage minus the published
Republican percentage, in percentage points. Positive means the Democrat is
ahead. Undecided and other shares are not dropped, and the two percentages
are not rescaled to sum to 100. A question with more than one candidate on
either major-party side does not receive this margin, because choosing or
summing those candidates would create a figure the poll did not publish.

DFL is the Democratic side. That is the party label Minnesota publishes, not
a guess about a candidate whose party was left blank.

A top-two gap is stored separately for questions that do not have one labeled
Democrat and one labeled Republican. It is the difference between the two
highest published candidate percentages and is always non-negative.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from polling_blind_spot.preprocess.standardize import (
    DEMOCRATIC_PARTIES,
    REPUBLICAN_PARTIES,
    parse_published_margin,
)

QUESTION_LEVEL_FIELDS = [
    "source",
    "record_type",
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
    "poll_url",
    "notes",
]

QUESTION_COLUMNS = [
    "question_id",
    *QUESTION_LEVEL_FIELDS,
    "n_response_rows",
    "n_candidates_with_pct",
    "dem_candidate",
    "dem_party",
    "dem_pct",
    "rep_candidate",
    "rep_party",
    "rep_pct",
    "margin_dem_minus_rep",
    "margin_status",
    "undecided_pct",
    "other_pct",
    "pct_sum",
    "top_two_leader",
    "top_two_leader_party",
    "top_two_leader_pct",
    "top_two_trailer",
    "top_two_trailer_party",
    "top_two_trailer_pct",
    "top_two_margin",
    "top_two_tie",
    "published_margin_text",
    "published_margin_leader",
    "published_margin_points",
    "published_margin_tie",
    "two_party_general",
]

_CANDIDATE_ROLES = {"candidate", "generic"}
_SHARE_ROLES = {"candidate", "generic", "residual", "undecided", "residual_undecided"}


def build_questions(responses: pd.DataFrame) -> pd.DataFrame:
    """Collapse candidate-level rows into one margin record per question."""
    if responses.empty:
        return pd.DataFrame(columns=QUESTION_COLUMNS)
    records = [
        _question_record(str(question_id), group)
        for question_id, group in responses.groupby("question_id", sort=False)
    ]
    return pd.DataFrame.from_records(records, columns=QUESTION_COLUMNS)


def _question_record(question_id: str, group: pd.DataFrame) -> dict[str, Any]:
    first = group.iloc[0]
    record: dict[str, Any] = {"question_id": question_id}
    for field in QUESTION_LEVEL_FIELDS:
        record[field] = _clean(first[field]) if field in group.columns else None
    record["n_response_rows"] = int(len(group))

    options = []
    shares: list[float] = []
    undecided: list[float] = []
    other: list[float] = []
    published_text: list[str] = []
    for row in group.to_dict(orient="records"):
        role = _text(row.get("response_role"))
        pct = _number(row.get("pct"))
        if role in _SHARE_ROLES and pct is not None:
            shares.append(pct)
        if role == "undecided" and pct is not None:
            undecided.append(pct)
        if role == "residual" and pct is not None:
            other.append(pct)
        if role == "published_margin":
            text = _text(row.get("pct_raw"))
            if text:
                published_text.append(text)
        if role in _CANDIDATE_ROLES and pct is not None and _text(row.get("candidate_name")):
            options.append(
                {
                    "name": _text(row.get("candidate_name")),
                    "party": _text(row.get("party")),
                    "pct": pct,
                }
            )

    record["n_candidates_with_pct"] = len(options)
    record["pct_sum"] = round(sum(shares), 4) if shares else None
    record["undecided_pct"] = undecided[0] if len(undecided) == 1 else None
    record["other_pct"] = other[0] if len(other) == 1 else None
    _fill_party_margin(record, options)
    _fill_top_two(record, options)
    _fill_published_margin(record, published_text)
    record["two_party_general"] = _two_party_general(record)
    return record


def _fill_party_margin(record: dict[str, Any], options: list[dict[str, Any]]) -> None:
    democrats = [row for row in options if row["party"] in DEMOCRATIC_PARTIES]
    republicans = [row for row in options if row["party"] in REPUBLICAN_PARTIES]
    record["dem_candidate"] = None
    record["dem_party"] = None
    record["dem_pct"] = None
    record["rep_candidate"] = None
    record["rep_party"] = None
    record["rep_pct"] = None
    record["margin_dem_minus_rep"] = None

    if len(democrats) == 1 and len(republicans) == 1:
        democrat = democrats[0]
        republican = republicans[0]
        record["dem_candidate"] = democrat["name"]
        record["dem_party"] = democrat["party"]
        record["dem_pct"] = democrat["pct"]
        record["rep_candidate"] = republican["name"]
        record["rep_party"] = republican["party"]
        record["rep_pct"] = republican["pct"]
        record["margin_dem_minus_rep"] = round(democrat["pct"] - republican["pct"], 4)
        record["margin_status"] = "two_party"
        return
    if len(democrats) == 0 and len(republicans) == 0:
        record["margin_status"] = "no_major_party"
    elif len(democrats) == 0:
        record["margin_status"] = "missing_democrat"
    elif len(republicans) == 0:
        record["margin_status"] = "missing_republican"
    else:
        record["margin_status"] = "multiple_major_party_candidates"


def _fill_top_two(record: dict[str, Any], options: list[dict[str, Any]]) -> None:
    record["top_two_leader"] = None
    record["top_two_leader_party"] = None
    record["top_two_leader_pct"] = None
    record["top_two_trailer"] = None
    record["top_two_trailer_party"] = None
    record["top_two_trailer_pct"] = None
    record["top_two_margin"] = None
    record["top_two_tie"] = None
    if len(options) < 2:
        return
    ordered = sorted(options, key=lambda row: (-row["pct"], row["name"].casefold()))
    leader, trailer = ordered[0], ordered[1]
    record["top_two_leader"] = leader["name"]
    record["top_two_leader_party"] = leader["party"]
    record["top_two_leader_pct"] = leader["pct"]
    record["top_two_trailer"] = trailer["name"]
    record["top_two_trailer_party"] = trailer["party"]
    record["top_two_trailer_pct"] = trailer["pct"]
    record["top_two_margin"] = round(leader["pct"] - trailer["pct"], 4)
    record["top_two_tie"] = leader["pct"] == trailer["pct"]


def _fill_published_margin(record: dict[str, Any], texts: list[str]) -> None:
    record["published_margin_text"] = None
    record["published_margin_leader"] = None
    record["published_margin_points"] = None
    record["published_margin_tie"] = None
    if len(texts) != 1:
        return
    parsed = parse_published_margin(texts[0])
    record["published_margin_text"] = texts[0]
    record["published_margin_leader"] = parsed.leader
    record["published_margin_points"] = parsed.points
    record["published_margin_tie"] = parsed.tie


def _two_party_general(record: dict[str, Any]) -> bool:
    return bool(
        record.get("stage") == "general"
        and _is_false(record.get("hypothetical"))
        and _is_false(record.get("ranked_choice"))
        and record.get("margin_status") == "two_party"
    )


def _is_false(value: Any) -> bool:
    """True only for an explicit false flag, including a numpy False."""
    if _missing(value):
        return False
    if isinstance(value, str):
        return value.strip().casefold() == "false"
    return bool(value) is False


def _clean(value: Any) -> Any:
    if _missing(value):
        return None
    return value


def _text(value: Any) -> str | None:
    if _missing(value):
        return None
    text = str(value).strip()
    return text or None


def _number(value: Any) -> float | None:
    if _missing(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except TypeError:
        return False
    return False
