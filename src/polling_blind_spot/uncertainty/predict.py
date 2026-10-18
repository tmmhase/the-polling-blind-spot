"""Posterior predictive draws for the error of a poll average.

The roster supplies timing bands, sampling variances, and pollster ids.
It does not supply a result margin or a signed error. Random effects for a
new race are drawn from the prior given the posterior variance components, so
adding another poll from a pollster already in the roster shrinks sampling
noise and does not shrink that pollster's shared error.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from polling_blind_spot.uncertainty.errors import UncertaintyError

ESTIMANDS = ("unweighted", "pollster_equal")


@dataclass(frozen=True)
class Roster:
    """Pre-election description of the polls in one contest.

    `bands` are late, mid, or early. `sampling_variances` are in points
    squared. `pollster_ids` identify a firm inside this roster only.
    """

    bands: tuple[str, ...]
    sampling_variances: tuple[float, ...]
    pollster_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        n_polls = len(self.bands)
        if n_polls == 0 or len(self.sampling_variances) != n_polls or len(self.pollster_ids) != n_polls:
            raise UncertaintyError("A roster needs at least one poll and equal-length fields.")
        if any(band not in {"late", "mid", "early"} for band in self.bands):
            raise UncertaintyError("Roster timing bands must be late, mid, or early.")
        if any(not np.isfinite(variance) or variance <= 0 for variance in self.sampling_variances):
            raise UncertaintyError("Roster sampling variances must be finite and positive.")
        if any(str(pollster).strip() == "" for pollster in self.pollster_ids):
            raise UncertaintyError("Roster pollster ids must be non-blank.")


def roster_factors(roster: Roster) -> dict[str, dict[str, float]]:
    """Timing shares and variance multipliers for both poll averages.

    The house factor multiplies the pollster-within-race variance. The sampling
    factor multiplies φ. For the unweighted mean, a firm that fields most of
    the polls keeps most of its house variance. For the pollster-equal mean,
    each firm contributes one house effect.
    """
    bands = np.asarray(roster.bands)
    variances = np.asarray(roster.sampling_variances, dtype=float)
    pollsters = np.asarray(roster.pollster_ids)
    n_polls = len(bands)
    unique, inverse, counts = np.unique(pollsters, return_inverse=True, return_counts=True)
    n_pollsters = len(unique)
    unweighted = {
        "mid_share": float(np.mean(bands == "mid")),
        "early_share": float(np.mean(bands == "early")),
        "house_factor": float(np.sum((counts / n_polls) ** 2)),
        "sampling_factor": float(np.sum(variances) / n_polls**2),
        "n_polls": float(n_polls),
        "n_pollsters": float(n_pollsters),
    }
    sampling_variances = []
    mid_shares = []
    early_shares = []
    for index, count in enumerate(counts):
        mask = inverse == index
        sampling_variances.append(float(np.sum(variances[mask]) / count**2))
        mid_shares.append(float(np.mean(bands[mask] == "mid")))
        early_shares.append(float(np.mean(bands[mask] == "early")))
    pollster_equal = {
        "mid_share": float(np.mean(mid_shares)),
        "early_share": float(np.mean(early_shares)),
        "house_factor": 1.0 / n_pollsters,
        "sampling_factor": float(np.sum(sampling_variances) / n_pollsters**2),
        "n_polls": float(n_polls),
        "n_pollsters": float(n_pollsters),
    }
    return {"unweighted": unweighted, "pollster_equal": pollster_equal}


def roster_from_polls(polls: pd.DataFrame) -> Roster:
    """Build a roster from modeling-frame rows. Signed errors are not copied."""
    required = {"band", "sampling_variance", "pollster_key"}
    missing = required.difference(polls.columns)
    if missing:
        raise UncertaintyError(f"Cannot build a roster without {', '.join(sorted(missing))}.")
    ordered = polls.sort_values("poll_id") if "poll_id" in polls.columns else polls
    return Roster(
        bands=tuple(ordered["band"].astype(str)),
        sampling_variances=tuple(float(value) for value in ordered["sampling_variance"]),
        pollster_ids=tuple(str(value) for value in ordered["pollster_key"]),
    )


def predictive_errors(
    draws: pd.DataFrame,
    roster: Roster,
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """One predictive draw of each average's signed error per posterior row.

    A positive draw means the poll average is more Democratic than the
    two-candidate result. The draws are not a result margin.
    """
    _require_draws(draws)
    factors = roster_factors(roster)
    return {estimand: _draw_estimand(draws, factors[estimand], rng) for estimand in ESTIMANDS}


def variance_components(draws: pd.DataFrame, roster: Roster) -> pd.DataFrame:
    """Law-of-total-variance split of the predictive error, in points squared.

    Cycle, race, house, and sampling pieces are the posterior means of the
    conditional variances. Mean-parameter uncertainty is the variance of the
    predictive mean across posterior draws. Shares use that sum as the
    denominator.
    """
    _require_draws(draws)
    rows = []
    for estimand, factors in roster_factors(roster).items():
        location = (
            draws["mu"].to_numpy()
            + draws["beta_mid"].to_numpy() * factors["mid_share"]
            + draws["beta_early"].to_numpy() * factors["early_share"]
        )
        components = {
            "cycle": float(np.mean(draws["sd_cycle"].to_numpy() ** 2)),
            "race": float(np.mean(draws["sd_race"].to_numpy() ** 2)),
            "house": float(np.mean(draws["sd_house"].to_numpy() ** 2) * factors["house_factor"]),
            "sampling": float(np.mean(draws["phi"].to_numpy()) * factors["sampling_factor"]),
            "mean_parameter": float(np.var(location, ddof=1)),
        }
        total = float(sum(components.values()))
        for name, variance in components.items():
            rows.append(
                {
                    "estimand": estimand,
                    "component": name,
                    "variance": variance,
                    "share": variance / total if total > 0 else np.nan,
                    "sd_if_only_this_component": float(np.sqrt(variance)),
                    "predictive_sd": float(np.sqrt(total)),
                    "n_polls": int(factors["n_polls"]),
                    "n_pollsters": int(factors["n_pollsters"]),
                }
            )
    return pd.DataFrame(rows)


def stylized_late_rosters(sampling_variance: float) -> list[tuple[str, Roster]]:
    """Three late-poll rosters that isolate sample size from pollster diversity.

    Every poll uses the same sampling variance, taken from the historical
    modeling frame rather than from a hypothetical sample size.
    """
    if not np.isfinite(sampling_variance) or sampling_variance <= 0:
        raise UncertaintyError("Stylized rosters need a positive sampling variance.")
    one = Roster(bands=("late",), sampling_variances=(sampling_variance,), pollster_ids=("pollster-1",))
    repeated = Roster(
        bands=tuple("late" for _ in range(10)),
        sampling_variances=tuple(sampling_variance for _ in range(10)),
        pollster_ids=tuple("pollster-1" for _ in range(10)),
    )
    diverse = Roster(
        bands=tuple("late" for _ in range(10)),
        sampling_variances=tuple(sampling_variance for _ in range(10)),
        pollster_ids=tuple(f"pollster-{index}" for index in range(1, 11)),
    )
    return [
        ("one_late_poll", one),
        ("ten_late_polls_one_pollster", repeated),
        ("ten_late_polls_ten_pollsters", diverse),
    ]


def _draw_estimand(draws: pd.DataFrame, factors: dict[str, float], rng: np.random.Generator) -> np.ndarray:
    n_draws = len(draws)
    location = (
        draws["mu"].to_numpy()
        + draws["beta_mid"].to_numpy() * factors["mid_share"]
        + draws["beta_early"].to_numpy() * factors["early_share"]
    )
    cycle = rng.normal(size=n_draws) * draws["sd_cycle"].to_numpy()
    race = rng.normal(size=n_draws) * draws["sd_race"].to_numpy()
    house = rng.normal(size=n_draws) * draws["sd_house"].to_numpy() * np.sqrt(factors["house_factor"])
    sampling = rng.normal(size=n_draws) * np.sqrt(draws["phi"].to_numpy() * factors["sampling_factor"])
    return location + cycle + race + house + sampling


def _require_draws(draws: pd.DataFrame) -> None:
    required = {"mu", "beta_mid", "beta_early", "sd_race", "sd_house", "sd_cycle", "phi"}
    missing = required.difference(draws.columns)
    if missing:
        raise UncertaintyError(f"Posterior draws are missing {', '.join(sorted(missing))}.")
    if draws.empty:
        raise UncertaintyError("Posterior draws are empty.")
    if not np.isfinite(draws.loc[:, list(required)].to_numpy(dtype=float)).all():
        raise UncertaintyError("Posterior draws contain a non-finite value.")
