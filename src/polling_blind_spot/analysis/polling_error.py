"""Score historical Senate polls against the election they were asking about.

A poll enters the error set only when its fieldwork ended on or before
election day and both named major-party candidates match one contest. The
pre-election average uses those poll margins alone. Result margins are
attached afterward and are not written back onto the cleaned poll file.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from polling_blind_spot.analysis.errors import AnalysisError
from polling_blind_spot.analysis.names import names_match
from polling_blind_spot.analysis.plots import write_figures
from polling_blind_spot.analysis.results import (
    all_ballot_margin,
    build_result_candidates,
    poll_two_party_margin,
    two_candidate_margin,
)
from polling_blind_spot.ingest.schemas import FTE_COLUMNS, MEDSL_COLUMNS
from polling_blind_spot.preprocess.margins import build_questions
from polling_blind_spot.preprocess.pipeline import FTE_FILENAME, clean_fte_responses

MEDSL_FILENAME = "medsl_us_senate_statewide_returns_1976_2024.csv"

ERROR_DEFINITION = (
    "error_two_party = poll_margin_two_party - result_margin_two_party, "
    "in percentage points. Positive means the poll's two-candidate margin "
    "was more Democratic than the official two-candidate margin."
)
MARGIN_DEFINITION = (
    "poll_margin_two_party and result_margin_two_party are both "
    "(Democratic share - Republican share) / (Democratic share + Republican share) "
    "* 100 for the same two candidates. Other candidates, undecided responses, "
    "and blank ballots are outside that denominator. "
    "margin_dem_minus_rep, the unrescaled published poll gap, is retained "
    "and is not the primary error."
)

POLL_ERROR_COLUMNS = [
    "question_id",
    "poll_id",
    "pollster",
    "pollster_key",
    "cycle",
    "election_year",
    "state_name",
    "state_po",
    "contest_id",
    "stage",
    "special",
    "seat_class",
    "election_date",
    "start_date",
    "end_date",
    "days_before_election",
    "ends_on_election_day",
    "sample_size",
    "population",
    "methodology",
    "internal",
    "partisan",
    "dem_candidate_poll",
    "rep_candidate_poll",
    "dem_candidate_result",
    "rep_candidate_result",
    "dem_party",
    "rep_party",
    "dem_pct",
    "rep_pct",
    "poll_margin_published",
    "poll_margin_two_party",
    "result_dem_votes",
    "result_rep_votes",
    "result_total_votes",
    "result_unofficial",
    "result_margin_two_party",
    "result_margin_all_votes",
    "error_two_party",
    "absolute_error_two_party",
    "error_published_vs_all_votes",
]

EXCLUSION_COLUMNS = [
    "question_id",
    "poll_id",
    "pollster",
    "pollster_key",
    "cycle",
    "state_name",
    "state_po",
    "stage",
    "election_date",
    "end_date",
    "dem_candidate",
    "rep_candidate",
    "margin_status",
    "reason",
]

AMBIGUOUS_COLUMNS = [
    "question_id",
    "poll_id",
    "cycle",
    "state_po",
    "election_year",
    "contest_id",
    "special",
    "dem_candidate_poll",
    "rep_candidate_poll",
    "dem_candidate_result",
    "rep_candidate_result",
    "poll_margin_two_party",
    "result_dem_votes",
    "result_rep_votes",
    "result_total_votes",
    "result_margin_two_party",
    "result_margin_all_votes",
]

RACE_COLUMNS = [
    "contest_id",
    "cycle",
    "election_year",
    "state_name",
    "state_po",
    "stage",
    "special",
    "dem_candidate_result",
    "rep_candidate_result",
    "n_polls",
    "n_polls_with_sample_size",
    "poll_margin_two_party_mean",
    "poll_margin_two_party_median",
    "poll_margin_two_party_weighted",
    "result_dem_votes",
    "result_rep_votes",
    "result_total_votes",
    "result_unofficial",
    "result_margin_two_party",
    "result_margin_all_votes",
    "error_of_unweighted_mean",
    "error_of_median",
    "error_of_weighted_mean",
]

_AVERAGE_COLUMNS = [
    "contest_id",
    "cycle",
    "election_year",
    "state_name",
    "state_po",
    "stage",
    "special",
    "poll_margin_two_party",
    "sample_size",
    "dem_candidate_result",
    "rep_candidate_result",
]

_TIMING_BINS = (
    "0 election day",
    "1-7 days",
    "8-30 days",
    "31-90 days",
    "91-180 days",
    "181 or more days",
)

_COMPARED_STAGES = {"general", "runoff"}


@dataclass
class ScoringResult:
    included: pd.DataFrame
    exclusions: pd.DataFrame
    ambiguous: pd.DataFrame


def run_historical_polling_error(raw_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Read raw historical polls and Senate returns, write error tables and figures."""
    raw_dir = raw_dir.resolve()
    output_dir = output_dir.resolve()
    if output_dir == raw_dir or _is_inside(output_dir, raw_dir):
        raise AnalysisError("The output directory must be separate from the raw directory.")

    fte_path = raw_dir / FTE_FILENAME
    medsl_path = raw_dir / MEDSL_FILENAME
    fte_raw = _read_table(fte_path, FTE_COLUMNS, "FiveThirtyEight historical Senate polls")
    medsl_raw = _read_table(medsl_path, MEDSL_COLUMNS, "MEDSL Senate returns")
    questions = build_questions(clean_fte_responses(fte_raw))
    candidates = build_result_candidates(medsl_raw)
    scoring = score_questions(questions, candidates)
    _assert_pre_election(scoring.included)
    races = attach_race_results(race_poll_summaries(scoring.included), scoring.included)
    report = _report(
        questions=questions,
        scoring=scoring,
        races=races,
        fte_path=fte_path,
        fte_rows=len(fte_raw),
        medsl_path=medsl_path,
        medsl_raw=medsl_raw,
    )
    _write_outputs(output_dir, scoring, races, report)
    write_figures(
        scoring.included,
        races,
        summarize_by_pollster(scoring.included),
        output_dir / "figures",
    )
    return report


def score_questions(questions: pd.DataFrame, candidates: pd.DataFrame) -> ScoringResult:
    """Classify every poll question and score the comparable pre-election rows."""
    index = _candidate_index(candidates)
    included: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    for record in questions.to_dict(orient="records"):
        decision = _classify(record, index)
        if decision["status"] == "included":
            included.append(decision["row"])
        else:
            exclusions.append(decision["exclusion"])
            ambiguous.extend(decision["ambiguous"])
    return ScoringResult(
        included=_frame(included, POLL_ERROR_COLUMNS),
        exclusions=_frame(exclusions, EXCLUSION_COLUMNS),
        ambiguous=_frame(ambiguous, AMBIGUOUS_COLUMNS),
    )


def race_poll_summaries(included: pd.DataFrame) -> pd.DataFrame:
    """Unweighted, median, and sample-size-weighted poll margins by contest.

    Only poll columns are read. A result margin passed in on the frame cannot
    change these averages. Sample sizes that are missing are left out of the
    weighted mean and are not filled with zero.
    """
    if included.empty:
        return pd.DataFrame(columns=[*RACE_COLUMNS])
    missing = [column for column in _AVERAGE_COLUMNS if column not in included.columns]
    if missing:
        raise AnalysisError(f"Poll error rows are missing columns required to average them: {missing}")
    frame = included.loc[:, _AVERAGE_COLUMNS]
    rows: list[dict[str, Any]] = []
    for contest_id, group in frame.groupby("contest_id", sort=True):
        margins = [_number(value) for value in group["poll_margin_two_party"]]
        margins = [value for value in margins if value is not None]
        if not margins:
            continue
        weights = [
            (_number(margin), _positive_int(sample))
            for margin, sample in zip(group["poll_margin_two_party"], group["sample_size"], strict=True)
        ]
        weighted_pairs = [(margin, sample) for margin, sample in weights if margin is not None and sample is not None]
        cycles = sorted({int(value) for value in group["cycle"] if _number(value) is not None})
        first = group.iloc[0]
        rows.append(
            {
                "contest_id": contest_id,
                "cycle": cycles[0] if len(cycles) == 1 else None,
                "election_year": _int_or_none(first["election_year"]),
                "state_name": first["state_name"],
                "state_po": first["state_po"],
                "stage": first["stage"],
                "special": bool(first["special"]),
                "dem_candidate_result": first["dem_candidate_result"],
                "rep_candidate_result": first["rep_candidate_result"],
                "n_polls": int(len(group)),
                "n_polls_with_sample_size": len(weighted_pairs),
                "poll_margin_two_party_mean": sum(margins) / len(margins),
                "poll_margin_two_party_median": float(pd.Series(margins).median()),
                "poll_margin_two_party_weighted": _weighted_mean(weighted_pairs),
            }
        )
    return pd.DataFrame.from_records(rows)


def attach_race_results(summaries: pd.DataFrame, included: pd.DataFrame) -> pd.DataFrame:
    """Subtract the contest result from averages that were already computed."""
    if summaries.empty:
        return _frame([], RACE_COLUMNS)
    result_fields = (
        "result_dem_votes",
        "result_rep_votes",
        "result_total_votes",
        "result_unofficial",
        "result_margin_two_party",
        "result_margin_all_votes",
    )
    lookup: dict[Any, dict[str, Any]] = {}
    for record in included.to_dict(orient="records"):
        current = lookup.setdefault(record["contest_id"], {field: record[field] for field in result_fields})
        for field in result_fields:
            if current[field] != record[field]:
                raise AnalysisError(f"Contest {record['contest_id']} has inconsistent result fields.")
    rows: list[dict[str, Any]] = []
    for record in summaries.to_dict(orient="records"):
        result = lookup[record["contest_id"]]
        result_margin = _number(result["result_margin_two_party"])
        combined = {**record, **result}
        combined["error_of_unweighted_mean"] = _subtract(record["poll_margin_two_party_mean"], result_margin)
        combined["error_of_median"] = _subtract(record["poll_margin_two_party_median"], result_margin)
        combined["error_of_weighted_mean"] = _subtract(record["poll_margin_two_party_weighted"], result_margin)
        rows.append(combined)
    return _frame(rows, RACE_COLUMNS)


def describe_errors(errors: pd.Series) -> dict[str, Any]:
    """Mean, spread, and absolute error of a signed-error series."""
    values = [float(value) for value in errors if _number(value) is not None]
    if not values:
        return {
            "n": 0,
            "mean_signed_error": None,
            "median_signed_error": None,
            "std_signed_error": None,
            "mae": None,
            "rmse": None,
            "p10": None,
            "p25": None,
            "p75": None,
            "p90": None,
        }
    series = pd.Series(values, dtype="float64")
    squared = sum(value * value for value in values) / len(values)
    return {
        "n": len(values),
        "mean_signed_error": float(series.mean()),
        "median_signed_error": float(series.median()),
        "std_signed_error": float(series.std(ddof=1)) if len(values) >= 2 else None,
        "mae": float(series.abs().mean()),
        "rmse": math.sqrt(squared),
        "p10": float(series.quantile(0.10)),
        "p25": float(series.quantile(0.25)),
        "p75": float(series.quantile(0.75)),
        "p90": float(series.quantile(0.90)),
    }


def summarize_by_cycle(included: pd.DataFrame, races: pd.DataFrame) -> pd.DataFrame:
    return _grouped_error_summary(included, races, "cycle", "cycle")


def summarize_by_state(included: pd.DataFrame, races: pd.DataFrame) -> pd.DataFrame:
    return _grouped_error_summary(included, races, "state_po", "state_po")


def summarize_by_pollster(included: pd.DataFrame) -> pd.DataFrame:
    if included.empty:
        return pd.DataFrame(columns=["pollster_key", "pollster", "n_polls", "n_races", "n_cycles"])
    rows = []
    for key, group in included.groupby(included["pollster_key"].map(_group_key), sort=True):
        stats = describe_errors(group["error_two_party"])
        rows.append(
            {
                "pollster_key": None if key == "(missing)" else key,
                "pollster": _common_label(group["pollster"]),
                "n_polls": stats["n"],
                "n_races": int(group["contest_id"].nunique()),
                "n_cycles": int(group["cycle"].nunique()),
                **{name: stats[name] for name in stats if name != "n"},
            }
        )
    frame = pd.DataFrame(rows)
    return frame.sort_values(["n_polls", "pollster_key"], ascending=[False, True], kind="mergesort").reset_index(drop=True)


def summarize_slices(included: pd.DataFrame, races: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, group in _poll_slices(included):
        stats = describe_errors(group["error_two_party"] if not group.empty else pd.Series(dtype="float64"))
        rows.append({"slice": name, "unit": "poll", **stats})
    race_stats = describe_errors(
        races["error_of_unweighted_mean"] if not races.empty else pd.Series(dtype="float64")
    )
    rows.append({"slice": "all_matched_races", "unit": "race", **race_stats})
    return pd.DataFrame(rows)


def summarize_by_population(included: pd.DataFrame) -> pd.DataFrame:
    if included.empty:
        return pd.DataFrame(columns=["population", "n"])
    rows = []
    labels = included["population"].map(lambda value: value if _text(value) else "(missing)")
    for label, group in included.groupby(labels, sort=True):
        rows.append({"population": label, **describe_errors(group["error_two_party"])})
    return pd.DataFrame(rows)


def summarize_by_timing(included: pd.DataFrame) -> pd.DataFrame:
    if included.empty:
        return pd.DataFrame(columns=["timing", "n"])
    labels = included["days_before_election"].map(_timing_bin)
    order = {label: index for index, label in enumerate(_TIMING_BINS)}
    rows = []
    for label, group in included.groupby(labels, sort=False):
        if label is None:
            continue
        rows.append({"timing": label, **describe_errors(group["error_two_party"])})
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["_order"] = frame["timing"].map(order)
    return frame.sort_values("_order", kind="mergesort").drop(columns="_order").reset_index(drop=True)


def variance_decomposition(included: pd.DataFrame) -> dict[str, Any]:
    """Separate within-race poll scatter from between-race mean error.

    This is a description of the included polls, not a hierarchical model.
    Races with a single poll do not enter the within-race variance.
    """
    if included.empty:
        return {
            "n_polls": 0,
            "n_races": 0,
            "n_races_with_two_polls": 0,
            "within_race_variance": None,
            "within_race_df": 0,
            "between_race_variance": None,
        }
    square_sum = 0.0
    degrees = 0
    race_means: list[float] = []
    multi = 0
    for _, group in included.groupby("contest_id", sort=True):
        errors = [float(value) for value in group["error_two_party"]]
        mean = sum(errors) / len(errors)
        race_means.append(mean)
        if len(errors) >= 2:
            multi += 1
            square_sum += sum((value - mean) ** 2 for value in errors)
            degrees += len(errors) - 1
    between = None
    if len(race_means) >= 2:
        center = sum(race_means) / len(race_means)
        between = sum((value - center) ** 2 for value in race_means) / (len(race_means) - 1)
    return {
        "n_polls": int(len(included)),
        "n_races": len(race_means),
        "n_races_with_two_polls": multi,
        "within_race_variance": None if degrees == 0 else square_sum / degrees,
        "within_race_df": degrees,
        "between_race_variance": between,
    }


def _classify(record: dict[str, Any], index: dict[tuple[Any, ...], list[dict[str, Any]]]) -> dict[str, Any]:
    reason = _screen(record)
    ambiguous: list[dict[str, Any]] = []
    row = None
    if reason is None:
        reason, row, ambiguous = _match_record(record, index)
    if row is not None:
        return {"status": "included", "row": row, "exclusion": None, "ambiguous": []}
    return {
        "status": "excluded",
        "row": None,
        "exclusion": _exclusion(record, reason or "unmatched_candidate"),
        "ambiguous": ambiguous,
    }


def _screen(record: dict[str, Any]) -> str | None:
    if _text(record.get("margin_status")) != "two_party":
        return "not_two_party_margin"
    if not _is_false(record.get("hypothetical")):
        return "hypothetical" if _is_true(record.get("hypothetical")) else "hypothetical_unknown"
    if not _is_false(record.get("ranked_choice")):
        return "ranked_choice" if _is_true(record.get("ranked_choice")) else "ranked_choice_unknown"
    if _text(record.get("stage")) not in _COMPARED_STAGES:
        return "stage_not_comparable"
    if not _text(record.get("state_po")):
        return "missing_state"
    election = _as_date(record.get("election_date"))
    end = _as_date(record.get("end_date"))
    start = _as_date(record.get("start_date"))
    if election is None:
        return "missing_election_date"
    if end is None:
        return "missing_end_date"
    if end > election:
        return "after_election"
    if start is not None and start > election:
        return "starts_after_election"
    if poll_two_party_margin(_number(record.get("dem_pct")), _number(record.get("rep_pct"))) is None:
        return "margin_not_computable"
    return None


def _match_record(
    record: dict[str, Any],
    index: dict[tuple[Any, ...], list[dict[str, Any]]],
) -> tuple[str | None, dict[str, Any] | None, list[dict[str, Any]]]:
    election = _as_date(record.get("election_date"))
    assert election is not None
    key = (record.get("state_po"), election.year, record.get("stage"))
    contests = _contests(index.get(key, []))
    if not contests:
        return "no_result_contest", None, []
    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    failures: list[str] = []
    for rows in contests.values():
        dem = _match_side(rows, record.get("dem_candidate"), "DEM")
        rep = _match_side(rows, record.get("rep_candidate"), "REP")
        if dem["status"] == "unique" and rep["status"] == "unique":
            matches.append((dem["candidate"], rep["candidate"]))
        else:
            failures.append(_pair_failure(dem["status"], rep["status"]))
    if len(matches) > 1:
        return "ambiguous_duplicate_ballot", None, _ambiguous_rows(record, matches)
    if len(matches) == 1:
        dem, rep = matches[0]
        if two_candidate_margin(dem["votes"], rep["votes"]) is None:
            return "non_positive_votes", None, []
        return None, _included_row(record, dem, rep), []
    return _failure_reason(failures), None, []


def _match_side(rows: list[dict[str, Any]], poll_name: Any, party: str) -> dict[str, Any]:
    hits = [row for row in rows if names_match(None if _missing(poll_name) else str(poll_name), row["candidate_name"])]
    right = [row for row in hits if row["party"] == party]
    if len(right) == 1:
        return {"status": "unique", "candidate": right[0]}
    if len(right) > 1:
        return {"status": "ambiguous", "candidate": None}
    if any(row["party"] in {"DEM", "REP"} for row in hits):
        return {"status": "party_mismatch", "candidate": None}
    return {"status": "unmatched", "candidate": None}


def _included_row(record: dict[str, Any], dem: dict[str, Any], rep: dict[str, Any]) -> dict[str, Any]:
    election = _as_date(record.get("election_date"))
    end = _as_date(record.get("end_date"))
    assert election is not None and end is not None
    dem_pct = _number(record.get("dem_pct"))
    rep_pct = _number(record.get("rep_pct"))
    published = _number(record.get("margin_dem_minus_rep"))
    poll_margin = poll_two_party_margin(dem_pct, rep_pct)
    result_margin = two_candidate_margin(dem["votes"], rep["votes"])
    total_votes = dem["total_votes"] if dem["total_votes"] == rep["total_votes"] else None
    all_ballot = all_ballot_margin(dem["votes"], rep["votes"], total_votes)
    assert poll_margin is not None and result_margin is not None
    error = poll_margin - result_margin
    published_error = None if published is None or all_ballot is None else published - all_ballot
    return {
        "question_id": record.get("question_id"),
        "poll_id": record.get("poll_id"),
        "pollster": record.get("pollster"),
        "pollster_key": record.get("pollster_key"),
        "cycle": _int_or_none(record.get("cycle")),
        "election_year": election.year,
        "state_name": record.get("state_name"),
        "state_po": record.get("state_po"),
        "contest_id": dem["contest_id"],
        "stage": record.get("stage"),
        "special": bool(dem["special"]),
        "seat_class": record.get("seat_class"),
        "election_date": election.isoformat(),
        "start_date": None if _as_date(record.get("start_date")) is None else _as_date(record.get("start_date")).isoformat(),
        "end_date": end.isoformat(),
        "days_before_election": (election - end).days,
        "ends_on_election_day": end == election,
        "sample_size": _positive_int(record.get("sample_size")),
        "population": _text(record.get("population")),
        "methodology": _text(record.get("methodology")),
        "internal": None if _missing(record.get("internal")) else _is_true(record.get("internal")),
        "partisan": _text(record.get("partisan")),
        "dem_candidate_poll": record.get("dem_candidate"),
        "rep_candidate_poll": record.get("rep_candidate"),
        "dem_candidate_result": dem["candidate_name"],
        "rep_candidate_result": rep["candidate_name"],
        "dem_party": record.get("dem_party"),
        "rep_party": record.get("rep_party"),
        "dem_pct": dem_pct,
        "rep_pct": rep_pct,
        "poll_margin_published": published,
        "poll_margin_two_party": poll_margin,
        "result_dem_votes": dem["votes"],
        "result_rep_votes": rep["votes"],
        "result_total_votes": total_votes,
        "result_unofficial": bool(dem["unofficial"] or rep["unofficial"]),
        "result_margin_two_party": result_margin,
        "result_margin_all_votes": all_ballot,
        "error_two_party": error,
        "absolute_error_two_party": abs(error),
        "error_published_vs_all_votes": published_error,
    }


def _ambiguous_rows(
    record: dict[str, Any],
    matches: list[tuple[dict[str, Any], dict[str, Any]]],
) -> list[dict[str, Any]]:
    poll_margin = poll_two_party_margin(_number(record.get("dem_pct")), _number(record.get("rep_pct")))
    rows = []
    for dem, rep in matches:
        total_votes = dem["total_votes"] if dem["total_votes"] == rep["total_votes"] else None
        rows.append(
            {
                "question_id": record.get("question_id"),
                "poll_id": record.get("poll_id"),
                "cycle": _int_or_none(record.get("cycle")),
                "state_po": record.get("state_po"),
                "election_year": _as_date(record.get("election_date")).year,
                "contest_id": dem["contest_id"],
                "special": bool(dem["special"]),
                "dem_candidate_poll": record.get("dem_candidate"),
                "rep_candidate_poll": record.get("rep_candidate"),
                "dem_candidate_result": dem["candidate_name"],
                "rep_candidate_result": rep["candidate_name"],
                "poll_margin_two_party": poll_margin,
                "result_dem_votes": dem["votes"],
                "result_rep_votes": rep["votes"],
                "result_total_votes": total_votes,
                "result_margin_two_party": two_candidate_margin(dem["votes"], rep["votes"]),
                "result_margin_all_votes": all_ballot_margin(dem["votes"], rep["votes"], total_votes),
            }
        )
    return rows


def _exclusion(record: dict[str, Any], reason: str) -> dict[str, Any]:
    election = _as_date(record.get("election_date"))
    end = _as_date(record.get("end_date"))
    return {
        "question_id": record.get("question_id"),
        "poll_id": record.get("poll_id"),
        "pollster": record.get("pollster"),
        "pollster_key": record.get("pollster_key"),
        "cycle": _int_or_none(record.get("cycle")),
        "state_name": record.get("state_name"),
        "state_po": record.get("state_po"),
        "stage": record.get("stage"),
        "election_date": None if election is None else election.isoformat(),
        "end_date": None if end is None else end.isoformat(),
        "dem_candidate": record.get("dem_candidate"),
        "rep_candidate": record.get("rep_candidate"),
        "margin_status": record.get("margin_status"),
        "reason": reason,
    }


def _assert_pre_election(included: pd.DataFrame) -> None:
    for record in included.to_dict(orient="records"):
        end = _as_date(record["end_date"])
        election = _as_date(record["election_date"])
        if end is None or election is None or end > election:
            raise AnalysisError("A scored poll ends after its election date.")
        expected = _number(record["poll_margin_two_party"]) - _number(record["result_margin_two_party"])
        if abs(expected - _number(record["error_two_party"])) > 1e-9:
            raise AnalysisError("Signed error does not equal poll margin minus result margin.")


def _report(
    *,
    questions: pd.DataFrame,
    scoring: ScoringResult,
    races: pd.DataFrame,
    fte_path: Path,
    fte_rows: int,
    medsl_path: Path,
    medsl_raw: pd.DataFrame,
) -> dict[str, Any]:
    reasons: dict[str, int] = {}
    if not scoring.exclusions.empty:
        for reason, count in scoring.exclusions["reason"].value_counts().items():
            reasons[str(reason)] = int(count)
    versions: dict[str, list[str]] = {}
    if not medsl_raw.empty:
        recent = medsl_raw[medsl_raw["year"].isin(["2018", "2020", "2021", "2022", "2024"])]
        for year, group in recent.groupby("year"):
            versions[str(year)] = sorted({str(value) for value in group["version"]})
    poll_slice = describe_errors(
        scoring.included["error_two_party"] if not scoring.included.empty else pd.Series(dtype="float64")
    )
    race_slice = describe_errors(
        races["error_of_unweighted_mean"] if not races.empty else pd.Series(dtype="float64")
    )
    return {
        "error_definition": ERROR_DEFINITION,
        "margin_definition": MARGIN_DEFINITION,
        "inclusion_rules": [
            "FiveThirtyEight historical Senate questions only. 2026 polls have no result and are not scored.",
            "Exactly one Democratic-side share (DEM or DFL) and one Republican share.",
            "Not hypothetical, not a ranked-choice reallocation, and a general or runoff stage.",
            "Fieldwork end date on or before the poll's election date. A missing election date is not filled in.",
            "Both candidate names match one official contest of the same state, stage, and election year.",
            "Two official contests with the same names, such as a same-day special and full-term ballot, are excluded.",
        ],
        "leakage_controls": [
            "Result votes are not used to choose which candidate or which contest a poll matches.",
            "Polls that ended after election day are excluded before a result margin is attached.",
            "Race averages are computed from poll margins and sample sizes only, then the result is subtracted.",
            "Result fields are written only to the analysis outputs, not back onto the cleaned poll tables.",
        ],
        "inputs": {
            "fte_file": fte_path.name,
            "fte_sha256": _sha256(fte_path),
            "fte_rows": int(fte_rows),
            "medsl_file": medsl_path.name,
            "medsl_sha256": _sha256(medsl_path),
            "medsl_rows": int(len(medsl_raw)),
            "medsl_version_by_year": versions,
        },
        "n_questions": int(len(questions)),
        "n_included_polls": int(len(scoring.included)),
        "n_excluded_questions": int(len(scoring.exclusions)),
        "n_races": int(len(races)),
        "exclusions_by_reason": reasons,
        "poll_level": _rounded_mapping(poll_slice),
        "race_level_unweighted_mean": _rounded_mapping(race_slice),
        "variance_decomposition": _rounded_mapping(variance_decomposition(scoring.included)),
        "slices": _records(summarize_slices(scoring.included, races)),
    }


def _write_outputs(output_dir: Path, scoring: ScoringResult, races: pd.DataFrame, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_frame(_sort_polls(scoring.included), output_dir / "poll_errors.csv")
    _write_frame(_sort_exclusions(scoring.exclusions), output_dir / "exclusions.csv")
    _write_frame(scoring.ambiguous, output_dir / "ambiguous_duplicate_ballots.csv")
    _write_frame(races, output_dir / "race_errors.csv")
    _write_frame(summarize_by_cycle(scoring.included, races), output_dir / "summary_by_cycle.csv")
    _write_frame(summarize_by_state(scoring.included, races), output_dir / "summary_by_state.csv")
    _write_frame(summarize_by_pollster(scoring.included), output_dir / "summary_by_pollster.csv")
    _write_frame(summarize_by_population(scoring.included), output_dir / "summary_by_population.csv")
    _write_frame(summarize_by_timing(scoring.included), output_dir / "summary_by_timing.csv")
    _write_frame(summarize_slices(scoring.included, races), output_dir / "summary_overall.csv")
    (output_dir / "analysis_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def _grouped_error_summary(
    included: pd.DataFrame,
    races: pd.DataFrame,
    poll_column: str,
    race_column: str,
) -> pd.DataFrame:
    if included.empty:
        return pd.DataFrame(columns=[poll_column, "n_polls", "n_races"])
    race_counts = (
        races.groupby(race_column).size().to_dict() if not races.empty and race_column in races.columns else {}
    )
    rows = []
    for key, group in included.groupby(included[poll_column].map(_group_key), sort=True):
        stats = describe_errors(group["error_two_party"])
        state_name = _common_label(group["state_name"]) if poll_column == "state_po" else None
        row = {
            poll_column: None if key == "(missing)" else key,
            "n_polls": stats["n"],
            "n_races": int(race_counts.get(key, group["contest_id"].nunique())),
            **{name: stats[name] for name in stats if name != "n"},
        }
        if state_name is not None:
            row = {poll_column: row[poll_column], "state_name": state_name, **{k: v for k, v in row.items() if k != poll_column}}
        rows.append(row)
    return pd.DataFrame(rows)


def _poll_slices(included: pd.DataFrame):
    yield "all_included_polls", included
    if included.empty:
        yield "excluding_flagged_internal", included
        yield "excluding_internal_and_partisan", included
        return
    not_internal = included.loc[~included["internal"].map(_is_true)].copy()
    yield "excluding_flagged_internal", not_internal
    partisan_blank = included["partisan"].map(lambda value: not _text(value))
    yield "excluding_internal_and_partisan", included.loc[~included["internal"].map(_is_true) & partisan_blank].copy()


def _candidate_index(candidates: pd.DataFrame) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    index: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    if candidates.empty:
        return index
    for record in candidates.to_dict(orient="records"):
        key = (record["state_po"], int(record["election_year"]), record["stage"])
        index.setdefault(key, []).append(record)
    return index


def _contests(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["contest_id"], []).append(row)
    return grouped


def _pair_failure(dem_status: str, rep_status: str) -> str:
    if "ambiguous" in {dem_status, rep_status}:
        return "ambiguous_candidate"
    if "party_mismatch" in {dem_status, rep_status}:
        return "party_mismatch"
    return "unmatched_candidate"


def _failure_reason(failures: list[str]) -> str:
    for reason in ("ambiguous_candidate", "party_mismatch", "unmatched_candidate"):
        if reason in failures:
            return reason
    return "unmatched_candidate"


def _timing_bin(value: Any) -> str | None:
    days = _int_or_none(value)
    if days is None:
        return None
    if days <= 0:
        return _TIMING_BINS[0]
    if days <= 7:
        return _TIMING_BINS[1]
    if days <= 30:
        return _TIMING_BINS[2]
    if days <= 90:
        return _TIMING_BINS[3]
    if days <= 180:
        return _TIMING_BINS[4]
    return _TIMING_BINS[5]


def _weighted_mean(pairs: list[tuple[float, int]]) -> float | None:
    if not pairs:
        return None
    weight = sum(sample for _, sample in pairs)
    if weight <= 0:
        return None
    return sum(margin * sample for margin, sample in pairs) / weight


def _subtract(left: Any, right: Any) -> float | None:
    left_number = _number(left)
    right_number = _number(right)
    if left_number is None or right_number is None:
        return None
    return left_number - right_number


def _frame(rows: list[dict[str, Any]], columns: list[str]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame.from_records(rows, columns=columns)


def _sort_polls(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame.sort_values(
        ["cycle", "state_po", "election_date", "end_date", "question_id"],
        kind="mergesort",
    ).reset_index(drop=True)


def _sort_exclusions(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame.sort_values(["reason", "cycle", "state_po", "question_id"], kind="mergesort").reset_index(drop=True)


def _write_frame(frame: pd.DataFrame, path: Path) -> None:
    output = frame.copy()
    for column in output.columns:
        if pd.api.types.is_bool_dtype(output[column]):
            output[column] = output[column].map(lambda value: "" if _missing(value) else ("true" if bool(value) else "false"))
        elif pd.api.types.is_float_dtype(output[column]):
            output[column] = output[column].map(lambda value: "" if _number(value) is None else f"{float(value):.4f}")
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(path, index=False)


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records = frame.to_dict(orient="records")
    return [_rounded_mapping(record) for record in records]


def _rounded_mapping(record: dict[str, Any]) -> dict[str, Any]:
    rounded = {}
    for key, value in record.items():
        number = _number(value)
        if number is None and not isinstance(value, (int, float)):
            rounded[key] = value
        elif isinstance(value, bool) or number is None:
            rounded[key] = value
        elif isinstance(value, int) and not isinstance(value, bool):
            rounded[key] = value
        else:
            rounded[key] = round(float(number), 4)
    return rounded


def _common_label(values: pd.Series) -> str | None:
    labels = [text for text in (_text(value) for value in values) if text]
    if not labels:
        return None
    counts = pd.Series(labels).value_counts()
    top = counts.max()
    return sorted(counts[counts == top].index)[0]


def _group_key(value: Any) -> str:
    text = _text(value)
    return text if text else "(missing)"


def _read_table(path: Path, expected: list[str], label: str) -> pd.DataFrame:
    if not path.is_file():
        raise AnalysisError(f"{label} file does not exist: {path}")
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)
    if list(frame.columns) != expected:
        missing = [column for column in expected if column not in frame.columns]
        unexpected = [column for column in frame.columns if column not in expected]
        raise AnalysisError(f"{label} columns differ from the raw schema. Missing {missing}; unexpected {unexpected}")
    return frame


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    text = _text(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _positive_int(value: Any) -> int | None:
    number = _number(value)
    if number is None or number <= 0 or not float(number).is_integer():
        return None
    return int(number)


def _int_or_none(value: Any) -> int | None:
    number = _number(value)
    if number is None or not float(number).is_integer():
        return None
    return int(number)


def _number(value: Any) -> float | None:
    if _missing(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _text(value: Any) -> str | None:
    if _missing(value):
        return None
    text = str(value).strip()
    return text or None


def _is_true(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() == "true"
    if _missing(value):
        return False
    return bool(value) is True


def _is_false(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() == "false"
    if _missing(value):
        return False
    return bool(value) is False


def _missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except TypeError:
        return False

