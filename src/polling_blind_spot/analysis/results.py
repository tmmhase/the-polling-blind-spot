"""Two-candidate Senate margins from MIT Election Lab statewide returns.

Fusion and multi-party ballot lines for the same published name are added
together. ``totalvotes`` is the contest total printed on those rows. It is
not recomputed by summing candidate lines, and blank write-ins are not given
a name.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from polling_blind_spot.analysis.errors import AnalysisError
from polling_blind_spot.analysis.names import is_non_candidate
from polling_blind_spot.ingest.schemas import MEDSL_COLUMNS
from polling_blind_spot.preprocess.standardize import standardize_state

CANDIDATE_COLUMNS = [
    "contest_id",
    "election_year",
    "state_name",
    "state_po",
    "stage",
    "special",
    "candidate_name",
    "party",
    "votes",
    "total_votes",
    "unofficial",
]

RESULT_STAGE_GENERAL = "general"
RESULT_STAGE_RUNOFF = "runoff"


def build_result_candidates(returns: pd.DataFrame) -> pd.DataFrame:
    """Collapse statewide Senate returns to one row per candidate in a contest."""
    _require_medsl(returns)
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for record in returns.to_dict(orient="records"):
        parsed = _candidate_line(record)
        if parsed is None:
            continue
        key = (
            parsed["contest_id"],
            parsed["candidate_name"].upper(),
        )
        grouped.setdefault(key, []).append(parsed)

    rows: list[dict[str, Any]] = []
    for lines in grouped.values():
        combined = _combine_lines(lines)
        if combined is not None:
            rows.append(combined)
    if not rows:
        return pd.DataFrame(columns=CANDIDATE_COLUMNS)
    frame = pd.DataFrame.from_records(rows, columns=CANDIDATE_COLUMNS)
    return frame.sort_values(
        ["election_year", "state_po", "stage", "special", "candidate_name"],
        kind="mergesort",
    ).reset_index(drop=True)


def two_candidate_margin(dem_votes: int | None, rep_votes: int | None) -> float | None:
    """Democratic share minus Republican share among those two candidates' votes.

    The unit is percentage points. Other candidates and blank ballots are
    outside this denominator, matching a poll margin that has been limited to
    the same two people.
    """
    if dem_votes is None or rep_votes is None:
        return None
    if dem_votes < 0 or rep_votes < 0:
        return None
    denominator = dem_votes + rep_votes
    if denominator <= 0:
        return None
    return (dem_votes - rep_votes) / denominator * 100


def all_ballot_margin(
    dem_votes: int | None,
    rep_votes: int | None,
    total_votes: int | None,
) -> float | None:
    """Democratic votes minus Republican votes, divided by the official total.

    This is not the primary comparison. The published poll margin and this
    all-ballot gap treat other responses differently. When the official total
    is missing, or smaller than the two candidates' combined votes, the margin
    stays missing rather than being repaired.
    """
    if dem_votes is None or rep_votes is None or total_votes is None:
        return None
    if total_votes <= 0 or dem_votes + rep_votes > total_votes:
        return None
    return (dem_votes - rep_votes) / total_votes * 100


def poll_two_party_margin(dem_pct: float | None, rep_pct: float | None) -> float | None:
    """Rescale one Democratic and one Republican poll share to those two shares.

    ``(dem - rep) / (dem + rep) * 100``. Undecided and other responses leave
    the denominator. A zero pair stays missing.
    """
    if dem_pct is None or rep_pct is None:
        return None
    if dem_pct < 0 or rep_pct < 0:
        return None
    denominator = dem_pct + rep_pct
    if denominator <= 0:
        return None
    return (dem_pct - rep_pct) / denominator * 100


def _candidate_line(record: dict[str, Any]) -> dict[str, Any] | None:
    office = str(record.get("office", "")).strip().upper()
    if office != "US SENATE":
        return None
    if str(record.get("district", "")).strip().casefold() != "statewide":
        return None
    mode = str(record.get("mode", "")).strip().casefold()
    if mode != "total":
        return None
    stage = _stage(record.get("stage"))
    if stage is None:
        return None
    name = record.get("candidate")
    if is_non_candidate(None if _missing(name) else str(name)):
        return None
    year = _int_value(record.get("year"))
    special = _bool_value(record.get("special"))
    votes = _int_value(record.get("candidatevotes"))
    total = _int_value(record.get("totalvotes"))
    if year is None or special is None or votes is None or total is None:
        return None
    state_name, state_po = standardize_state(None if _missing(record.get("state")) else str(record.get("state")))
    if state_po is None:
        state_name, state_po = standardize_state(
            None if _missing(record.get("state_po")) else str(record.get("state_po"))
        )
    if state_po is None:
        return None
    contest_id = f"{year}-{state_po}-{stage}-{int(special)}"
    return {
        "contest_id": contest_id,
        "election_year": year,
        "state_name": state_name,
        "state_po": state_po,
        "stage": stage,
        "special": special,
        "candidate_name": str(name).strip(),
        "party_label": _party_label(record.get("party_simplified"), record.get("party_detailed")),
        "votes": votes,
        "total_votes": total,
        "unofficial": _bool_value(record.get("unofficial")) is True,
    }


def _combine_lines(lines: list[dict[str, Any]]) -> dict[str, Any] | None:
    parties = {line["party_label"] for line in lines}
    if "DEM" in parties and "REP" in parties:
        party = "AMBIGUOUS"
    elif "DEM" in parties:
        party = "DEM"
    elif "REP" in parties:
        party = "REP"
    else:
        party = "OTHER"
    totals = {line["total_votes"] for line in lines}
    display = next(
        (line["candidate_name"] for line in lines if line["party_label"] == party),
        lines[0]["candidate_name"],
    )
    first = lines[0]
    return {
        "contest_id": first["contest_id"],
        "election_year": first["election_year"],
        "state_name": first["state_name"],
        "state_po": first["state_po"],
        "stage": first["stage"],
        "special": first["special"],
        "candidate_name": display,
        "party": party,
        "votes": sum(line["votes"] for line in lines),
        "total_votes": next(iter(totals)) if len(totals) == 1 else None,
        "unofficial": any(line["unofficial"] for line in lines),
    }


def _stage(value: Any) -> str | None:
    text = "" if _missing(value) else str(value).strip().casefold()
    if "runoff" in text:
        return RESULT_STAGE_RUNOFF
    if text in {"gen", "general"}:
        return RESULT_STAGE_GENERAL
    return None


_DETAILED_DEMOCRATIC = {
    "DEMOCRAT",
    "DEMOCRATIC",
    "DEMOCRATIC-FARMER-LABOR",
    "DEMOCRATIC-NPL",
    "DFL",
}


def _party_label(simplified: Any, detailed: Any) -> str:
    """Use the simplified party, then an explicit major-party detailed label.

    A few 2022 rows say ``DEMOCRATIC`` in ``party_detailed`` and ``OTHER`` in
    ``party_simplified``. That detailed value is the published party. A label
    that only contains the word Republican, such as ``INDEPENDENT REPUBLICAN
    PARTY``, is not treated as the Republican nominee.
    """
    simple = "" if _missing(simplified) else str(simplified).strip().upper()
    if simple == "DEMOCRAT":
        return "DEM"
    if simple == "REPUBLICAN":
        return "REP"
    detail = "" if _missing(detailed) else str(detailed).strip().upper()
    if detail in _DETAILED_DEMOCRATIC:
        return "DEM"
    if detail == "REPUBLICAN":
        return "REP"
    return "OTHER"


def _require_medsl(frame: pd.DataFrame) -> None:
    columns = list(frame.columns)
    if columns != MEDSL_COLUMNS:
        missing = [column for column in MEDSL_COLUMNS if column not in columns]
        unexpected = [column for column in columns if column not in MEDSL_COLUMNS]
        raise AnalysisError(
            "MEDSL Senate returns columns differ from the raw schema. "
            f"Missing {missing}; unexpected {unexpected}"
        )


def _int_value(value: Any) -> int | None:
    if _missing(value):
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not number.is_integer() or number < 0:
        return None
    return int(number)


def _bool_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if _missing(value):
        return None
    text = str(value).strip().casefold()
    if text in {"true", "t", "1", "yes"}:
        return True
    if text in {"false", "f", "0", "no"}:
        return False
    return None


def _missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except TypeError:
        return False
