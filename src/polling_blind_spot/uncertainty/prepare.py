"""Turn scored poll questions into one modeling row per poll and contest.

Questions that share a poll_id and a contest are one sample, not independent
polls. Their signed errors are averaged. Their sampling variances are averaged
and are not divided by the number of questions. A missing sample size drops
that question. It is not filled in.
"""

from __future__ import annotations

import pandas as pd

from polling_blind_spot.uncertainty.errors import UncertaintyError
from polling_blind_spot.uncertainty.sampling import two_party_sampling_variance

LATE_MAX_DAYS = 30
MID_MAX_DAYS = 180

_REQUIRED = (
    "question_id",
    "poll_id",
    "contest_id",
    "cycle",
    "pollster_key",
    "days_before_election",
    "sample_size",
    "dem_pct",
    "rep_pct",
    "error_two_party",
)


def timing_band(days_before_election: float) -> str | None:
    """Map days before the election to late, mid, or early.

    Late is day 1 through 30, mid is day 31 through 180, and early is day 181
    or later. Day 0 and negative values are election day or later and return
    None.
    """
    if pd.isna(days_before_election):
        return None
    days = float(days_before_election)
    if days < 1:
        return None
    if days <= LATE_MAX_DAYS:
        return "late"
    if days <= MID_MAX_DAYS:
        return "mid"
    return "early"


def prepare_modeling_frame(polls: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Return the modeling frame, question-level exclusions, and a count summary.

    The modeling frame has one row per poll_id and contest_id. `error_two_party`
    is the unweighted mean of the questions that remain in that poll. The result
    margin is not a column and is not recomputed here.
    """
    missing = [column for column in _REQUIRED if column not in polls.columns]
    if missing:
        raise UncertaintyError(f"Poll-error table is missing columns: {', '.join(missing)}")
    frame = polls.loc[:, list(_REQUIRED)].copy()
    reasons = _exclusion_reasons(frame)
    excluded = frame.loc[reasons.notna(), ["question_id", "poll_id", "contest_id"]].copy()
    excluded["reason"] = reasons.loc[reasons.notna()].to_numpy()
    kept = frame.loc[reasons.isna()].copy()
    kept["sampling_variance"] = [
        two_party_sampling_variance(dem, rep, size)
        for dem, rep, size in zip(kept["dem_pct"], kept["rep_pct"], kept["sample_size"], strict=True)
    ]
    variance_ok = kept["sampling_variance"].map(lambda value: value is not None and value > 0)
    if not variance_ok.all():
        failed = kept.loc[~variance_ok, ["question_id", "poll_id", "contest_id"]].copy()
        failed["reason"] = "undefined_sampling_variance"
        excluded = pd.concat([excluded, failed], ignore_index=True)
        kept = kept.loc[variance_ok].copy()
    if kept.empty:
        raise UncertaintyError("No polls have a usable sample size and two-party margin.")
    kept["sampling_variance"] = kept["sampling_variance"].astype(float)
    kept["band"] = kept["days_before_election"].map(timing_band)
    if kept["band"].isna().any():
        raise UncertaintyError("A question with a usable sample size has no pre-election timing band.")
    grouped = (
        kept.groupby(["poll_id", "contest_id"], as_index=False)
        .agg(
            cycle=("cycle", "first"),
            pollster_key=("pollster_key", "first"),
            days_before_election=("days_before_election", "min"),
            error_two_party=("error_two_party", "mean"),
            sampling_variance=("sampling_variance", "mean"),
            n_questions=("question_id", "size"),
        )
        .sort_values(["cycle", "contest_id", "poll_id"])
        .reset_index(drop=True)
    )
    inconsistent = kept.groupby(["poll_id", "contest_id"]).agg(
        pollsters=("pollster_key", "nunique"),
        cycles=("cycle", "nunique"),
        days=("days_before_election", "nunique"),
    )
    if (inconsistent[["pollsters", "cycles", "days"]] > 1).any().any():
        raise UncertaintyError("Questions that share a poll_id and contest disagree on pollster, cycle, or end date.")
    grouped["band"] = grouped["days_before_election"].map(timing_band)
    summary = {
        "n_questions": int(len(frame)),
        "n_questions_kept": int(len(kept)),
        "n_questions_excluded": int(len(excluded)),
        "exclusions_by_reason": {
            str(reason): int(count)
            for reason, count in excluded["reason"].value_counts().sort_index().items()
        },
        "n_polls": int(len(grouped)),
        "n_polls_with_multiple_questions": int((grouped["n_questions"] > 1).sum()),
        "n_races": int(grouped["contest_id"].nunique()),
        "n_pollster_race_groups": int(grouped.groupby(["contest_id", "pollster_key"]).ngroups),
        "n_cycles": int(grouped["cycle"].nunique()),
        "cycles": [int(cycle) for cycle in sorted(grouped["cycle"].unique())],
        "median_sample_size": float(kept["sample_size"].median()),
        "median_sampling_variance": float(grouped["sampling_variance"].median()),
    }
    return grouped, excluded.sort_values(["reason", "question_id"]).reset_index(drop=True), summary


def _exclusion_reasons(frame: pd.DataFrame) -> pd.Series:
    """One reason per dropped question, in the order the checks are applied."""
    reason = pd.Series(pd.NA, index=frame.index, dtype="object")

    def assign(mask: pd.Series, label: str) -> None:
        reason.loc[reason.isna() & mask] = label

    assign(frame["error_two_party"].isna(), "missing_error")
    assign(frame["poll_id"].isna() | frame["contest_id"].isna() | frame["cycle"].isna(), "missing_identifier")
    assign(frame["pollster_key"].isna() | (frame["pollster_key"].astype(str).str.strip() == ""), "missing_pollster")
    days = pd.to_numeric(frame["days_before_election"], errors="coerce")
    assign(days.isna(), "missing_days_before_election")
    assign(days < 1, "not_pre_election")
    size = pd.to_numeric(frame["sample_size"], errors="coerce")
    assign(size.isna(), "missing_sample_size")
    assign(size <= 0, "nonpositive_sample_size")
    dem = pd.to_numeric(frame["dem_pct"], errors="coerce")
    rep = pd.to_numeric(frame["rep_pct"], errors="coerce")
    assign(dem.isna() | rep.isna(), "missing_percentage")
    assign((dem < 0) | (rep < 0) | (dem > 100) | (rep > 100), "percentage_out_of_range")
    assign(dem + rep <= 0, "no_two_party_share")
    assign(dem + rep > 100, "shares_exceed_100")
    return reason
