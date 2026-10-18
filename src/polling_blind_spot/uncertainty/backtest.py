"""Historical backtests that do not train on the election being scored.

Leave-one-cycle-out refits the model without every race in the held-out
cycle, then builds that cycle's predictive intervals from poll timing,
sample sizes, and pollster ids only. The forward chain is stricter: the fit
for a cycle uses only earlier cycles in this file. The 2018 cycle has no
earlier cycle here, so the forward chain starts with 2020.

Coverage compares those intervals with the signed error of the poll average.
That comparison happens after the predictive draws exist.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from polling_blind_spot.uncertainty.errors import UncertaintyError
from polling_blind_spot.uncertainty.model import ModelPriors, Posterior, SamplerSettings, fit_error_model
from polling_blind_spot.uncertainty.predict import ESTIMANDS, predictive_errors, roster_from_polls

QUANTILES = (0.025, 0.10, 0.25, 0.50, 0.75, 0.90, 0.975)


@dataclass(frozen=True)
class BacktestResult:
    races: pd.DataFrame
    coverage: pd.DataFrame


def leave_one_cycle_folds(polls: pd.DataFrame) -> list[tuple[int, pd.DataFrame, pd.DataFrame]]:
    """Training rows exclude the scored cycle, and the two sets share no contest."""
    folds = []
    for cycle in _cycles(polls):
        train = polls.loc[polls["cycle"] != cycle].copy()
        test = polls.loc[polls["cycle"] == cycle].copy()
        _check_fold(cycle, train, test, allow_later=True)
        folds.append((cycle, train, test))
    return folds


def forward_chain_folds(polls: pd.DataFrame) -> list[tuple[int, pd.DataFrame, pd.DataFrame]]:
    """Training rows are limited to cycles earlier than the scored cycle."""
    cycles = _cycles(polls)
    folds = []
    for cycle in cycles[1:]:
        train = polls.loc[polls["cycle"] < cycle].copy()
        test = polls.loc[polls["cycle"] == cycle].copy()
        _check_fold(cycle, train, test, allow_later=False)
        folds.append((cycle, train, test))
    return folds


def run_backtests(
    polls: pd.DataFrame,
    priors: ModelPriors | None = None,
    settings: SamplerSettings | None = None,
) -> BacktestResult:
    """Fit each leakage-safe fold and score both poll-average estimands."""
    priors = priors or ModelPriors()
    settings = settings or SamplerSettings()
    race_rows: list[dict] = []
    protocols = (
        ("leave_one_cycle_out", leave_one_cycle_folds(polls)),
        ("forward_chain", forward_chain_folds(polls)),
    )
    for protocol, folds in protocols:
        for cycle, train, test in folds:
            fold_settings = SamplerSettings(
                burn_in=settings.burn_in,
                draws=settings.draws,
                thin=settings.thin,
                seed=settings.seed + int(cycle) + (0 if protocol == "leave_one_cycle_out" else 10_000),
            )
            posterior = fit_error_model(train, priors, fold_settings)
            race_rows.extend(_score_cycle(protocol, cycle, test, posterior, fold_settings.seed))
    races = pd.DataFrame(race_rows)
    if races.empty:
        raise UncertaintyError("The backtest produced no races.")
    return BacktestResult(races=races, coverage=coverage_table(races))


def coverage_table(races: pd.DataFrame) -> pd.DataFrame:
    """Coverage and interval width by protocol, estimand, and cycle, plus an all-cycles row."""
    rows: list[dict] = []
    group_columns = ["protocol", "estimand"]
    for keys, subset in races.groupby(group_columns, sort=True):
        rows.append(_coverage_row(subset, cycle="all"))
        for cycle, cycle_subset in subset.groupby("cycle", sort=True):
            row = _coverage_row(cycle_subset, cycle=int(cycle))
            rows.append(row)
    table = pd.DataFrame(rows)
    table["cycle"] = table["cycle"].astype(str)
    table["_cycle_order"] = table["cycle"].map(lambda value: -1 if value == "all" else int(value))
    table = table.sort_values(["protocol", "estimand", "_cycle_order"]).drop(columns="_cycle_order")
    return table.reset_index(drop=True)


def _score_cycle(
    protocol: str,
    cycle: int,
    test: pd.DataFrame,
    posterior: Posterior,
    seed: int,
) -> list[dict]:
    rng = np.random.default_rng(seed)
    rows = []
    for contest_id, race in test.groupby("contest_id", sort=True):
        roster = roster_from_polls(race)
        actual = {
            "unweighted": float(race["error_two_party"].mean()),
            "pollster_equal": float(race.groupby("pollster_key")["error_two_party"].mean().mean()),
        }
        predicted = predictive_errors(posterior.draws, roster, rng)
        n_pollsters = int(race["pollster_key"].nunique())
        for estimand in ESTIMANDS:
            draws = predicted[estimand]
            quantiles = np.quantile(draws, QUANTILES)
            pit = float(np.mean(draws < actual[estimand]) + 0.5 * np.mean(draws == actual[estimand]))
            rows.append(
                {
                    "protocol": protocol,
                    "estimand": estimand,
                    "cycle": int(cycle),
                    "contest_id": contest_id,
                    "state_po": _state_po(contest_id),
                    "n_polls": int(len(race)),
                    "n_pollsters": n_pollsters,
                    "actual_error": actual[estimand],
                    "pred_p025": float(quantiles[0]),
                    "pred_p10": float(quantiles[1]),
                    "pred_p25": float(quantiles[2]),
                    "pred_p50": float(quantiles[3]),
                    "pred_p75": float(quantiles[4]),
                    "pred_p90": float(quantiles[5]),
                    "pred_p975": float(quantiles[6]),
                    "covered_50": bool(quantiles[2] <= actual[estimand] <= quantiles[4]),
                    "covered_80": bool(quantiles[1] <= actual[estimand] <= quantiles[5]),
                    "covered_95": bool(quantiles[0] <= actual[estimand] <= quantiles[6]),
                    "width_95": float(quantiles[6] - quantiles[0]),
                    "pit": pit,
                }
            )
    return rows


def _coverage_row(subset: pd.DataFrame, cycle: int | str) -> dict:
    return {
        "protocol": subset["protocol"].iloc[0],
        "estimand": subset["estimand"].iloc[0],
        "cycle": cycle,
        "n_races": int(len(subset)),
        "coverage_50": float(subset["covered_50"].mean()),
        "coverage_80": float(subset["covered_80"].mean()),
        "coverage_95": float(subset["covered_95"].mean()),
        "mean_width_95": float(subset["width_95"].mean()),
        "median_width_95": float(subset["width_95"].median()),
        "mean_pit": float(subset["pit"].mean()),
        "mean_actual_error": float(subset["actual_error"].mean()),
        "mean_predicted_median": float(subset["pred_p50"].mean()),
    }


def _cycles(polls: pd.DataFrame) -> list[int]:
    if "cycle" not in polls.columns or polls.empty:
        raise UncertaintyError("Backtest polls need a cycle column and at least one row.")
    return [int(cycle) for cycle in sorted(polls["cycle"].unique())]


def _check_fold(cycle: int, train: pd.DataFrame, test: pd.DataFrame, allow_later: bool) -> None:
    if test.empty or train.empty:
        raise UncertaintyError(f"Cycle {cycle} does not have both training and test polls.")
    if int(cycle) in set(int(value) for value in train["cycle"]):
        raise UncertaintyError(f"Training data for cycle {cycle} still contains that cycle.")
    if set(train["contest_id"]).intersection(test["contest_id"]):
        raise UncertaintyError(f"A contest from cycle {cycle} is in the training data.")
    if not allow_later and int(train["cycle"].max()) >= int(cycle):
        raise UncertaintyError(f"Forward-chain training for {cycle} uses a later cycle.")


def _state_po(contest_id: object) -> str:
    parts = str(contest_id).split("-")
    return parts[1] if len(parts) >= 2 else ""
