"""Gibbs sampler for the hierarchical Senate polling-error model.

For poll i in race r, cycle k, and pollster-within-race group p:

    error_i = μ + β_mid * mid_i + β_early * early_i + c_k + b_r + h_p + ε_i
    ε_i ~ Normal(0, φ * v_i)

v_i is the simple-random-sample variance of that poll's two-party margin.
φ is a single inflation factor. c_k, b_r, and h_p are cycle, race, and
pollster-within-race random effects. Late polls (1–30 days out) are the
baseline, so μ is the mean error of a late poll.

The standard deviations of c, b, and h have independent half-Cauchy priors,
sampled with their inverse-gamma scale mixture. φ has an inverse-gamma prior
centered at 1. The sampler does not see a held-out race's result except
through the error column of the rows it is given.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from polling_blind_spot.uncertainty.errors import UncertaintyError

POSTERIOR_COLUMNS = (
    "mu",
    "beta_mid",
    "beta_early",
    "sd_race",
    "sd_house",
    "sd_cycle",
    "phi",
)


@dataclass(frozen=True)
class ModelPriors:
    """Priors on the percentage-point error scale."""

    mean_sd: float = 20.0
    timing_sd: float = 5.0
    half_cauchy_scale: float = 5.0
    phi_shape: float = 2.0
    phi_scale: float = 1.0

    def __post_init__(self) -> None:
        if self.mean_sd <= 0 or self.timing_sd <= 0 or self.half_cauchy_scale <= 0:
            raise UncertaintyError("Prior scales must be positive.")
        if self.phi_shape <= 0 or self.phi_scale <= 0:
            raise UncertaintyError("The prior on the sampling inflation must be positive.")


@dataclass(frozen=True)
class SamplerSettings:
    burn_in: int = 2000
    draws: int = 2000
    thin: int = 2
    seed: int = 20261018

    def __post_init__(self) -> None:
        if self.burn_in < 0 or self.draws < 1 or self.thin < 1:
            raise UncertaintyError("Sampler settings need a non-negative burn-in, at least one draw, and thin >= 1.")


@dataclass(frozen=True)
class Posterior:
    draws: pd.DataFrame
    priors: ModelPriors
    settings: SamplerSettings
    n_polls: int
    n_races: int
    n_houses: int
    n_cycles: int
    cycles: tuple[int, ...]
    ess: dict[str, float]


def draw_invgamma(shape: float, scale: float, rng: np.random.Generator, size: int | None = None) -> np.ndarray:
    """Draw from an inverse-gamma with mean scale / (shape - 1) when shape > 1.

    NumPy's gamma uses the scale parameterization. The inverse-gamma draw is
    scale / Gamma(shape, scale=1).
    """
    if shape <= 0 or scale <= 0:
        raise UncertaintyError("Inverse-gamma shape and scale must be positive.")
    gamma = rng.gamma(shape, scale=1.0, size=size)
    return scale / gamma


def sample_half_cauchy_prior(scale: float, n_draws: int, seed: int, burn_in: int = 2000) -> np.ndarray:
    """Draw standard deviations from the half-Cauchy prior, with no observations.

    This is the scale mixture used inside the Gibbs sampler:
    tau^2 | rho ~ InvGamma(1/2, 1/rho) and rho | tau^2 ~ InvGamma(1, 1/tau^2 + 1/scale^2).
    """
    if scale <= 0 or n_draws < 1 or burn_in < 0:
        raise UncertaintyError("Half-Cauchy prior sampling needs a positive scale and a valid length.")
    rng = np.random.default_rng(seed)
    rho = 1.0 / scale**2
    kept = np.empty(n_draws)
    tau2 = scale**2
    for draw in range(burn_in + n_draws):
        tau2 = float(draw_invgamma(0.5, 1.0 / rho, rng))
        rho = float(draw_invgamma(1.0, 1.0 / tau2 + 1.0 / scale**2, rng))
        if draw >= burn_in:
            kept[draw - burn_in] = np.sqrt(tau2)
    return kept


def normal_normal_posterior(data_precision: float, weighted_sum: float, prior_variance: float) -> tuple[float, float]:
    """Posterior mean and variance for a N(0, prior_variance) location given Gaussian data.

    `data_precision` is the sum of observation weights. `weighted_sum` is the
    sum of weight times residual. The prior mean is zero.
    """
    if prior_variance <= 0 or data_precision < 0:
        raise UncertaintyError("Normal-normal update needs a positive prior variance and a non-negative precision.")
    post_precision = 1.0 / prior_variance + data_precision
    post_variance = 1.0 / post_precision
    post_mean = weighted_sum * post_variance
    return post_mean, post_variance


def effective_sample_size(draws: np.ndarray) -> float:
    """Initial monotone positive-sequence estimate of the effective sample size."""
    values = np.asarray(draws, dtype=float)
    if values.ndim != 1 or len(values) < 2:
        return float(len(values))
    centered = values - values.mean()
    n = len(centered)
    variance = float(np.dot(centered, centered) / n)
    if variance <= 1e-18:
        return float(n)
    nfft = 1 << (2 * n - 1).bit_length()
    autocorr = np.fft.irfft(np.abs(np.fft.rfft(centered, n=nfft)) ** 2)[:n]
    autocorr /= autocorr[0]
    total = 0.0
    lag = 1
    while lag + 1 < n:
        pair = float(autocorr[lag] + autocorr[lag + 1])
        if pair < 0:
            break
        total += pair
        lag += 2
    return float(n / (1.0 + 2.0 * total))


def fit_error_model(
    polls: pd.DataFrame,
    priors: ModelPriors | None = None,
    settings: SamplerSettings | None = None,
) -> Posterior:
    """Fit the hierarchical model to a modeling frame of pre-election poll errors."""
    priors = priors or ModelPriors()
    settings = settings or SamplerSettings()
    arrays = _model_arrays(polls)
    draws = _gibbs(arrays, priors, settings)
    ess = {column: effective_sample_size(draws[column].to_numpy()) for column in POSTERIOR_COLUMNS}
    return Posterior(
        draws=draws,
        priors=priors,
        settings=settings,
        n_polls=int(arrays["n_polls"]),
        n_races=int(arrays["n_races"]),
        n_houses=int(arrays["n_houses"]),
        n_cycles=int(arrays["n_cycles"]),
        cycles=tuple(int(cycle) for cycle in arrays["cycles"]),
        ess=ess,
    )


def posterior_summary(posterior: Posterior) -> pd.DataFrame:
    """Mean, quantiles, and effective sample size for each saved parameter."""
    rows = []
    for column in POSTERIOR_COLUMNS:
        values = posterior.draws[column].to_numpy()
        rows.append(
            {
                "parameter": column,
                "mean": float(np.mean(values)),
                "p05": float(np.quantile(values, 0.05)),
                "p50": float(np.quantile(values, 0.50)),
                "p95": float(np.quantile(values, 0.95)),
                "ess": float(posterior.ess[column]),
            }
        )
    return pd.DataFrame(rows)


def _model_arrays(polls: pd.DataFrame) -> dict:
    required = {"error_two_party", "sampling_variance", "contest_id", "cycle", "pollster_key", "band"}
    missing = required.difference(polls.columns)
    if missing:
        raise UncertaintyError(f"Modeling frame is missing columns: {', '.join(sorted(missing))}")
    if polls.empty:
        raise UncertaintyError("The modeling frame is empty.")
    frame = polls.reset_index(drop=True)
    if frame["band"].isin(["late", "mid", "early"]).sum() != len(frame):
        raise UncertaintyError("Every modeled poll needs a late, mid, or early timing band.")
    variance = pd.to_numeric(frame["sampling_variance"], errors="coerce")
    error = pd.to_numeric(frame["error_two_party"], errors="coerce")
    if variance.isna().any() or (variance <= 0).any() or error.isna().any():
        raise UncertaintyError("Modeled polls need a finite error and a positive sampling variance.")
    race_codes, races = pd.factorize(frame["contest_id"], sort=True)
    cycle_codes, cycles = pd.factorize(frame["cycle"], sort=True)
    house_key = frame["contest_id"].astype(str) + "||" + frame["pollster_key"].astype(str)
    house_codes, houses = pd.factorize(house_key, sort=True)
    return {
        "y": error.to_numpy(dtype=float),
        "v": variance.to_numpy(dtype=float),
        "race": race_codes.astype(int),
        "cycle": cycle_codes.astype(int),
        "house": house_codes.astype(int),
        "mid": (frame["band"] == "mid").to_numpy(dtype=float),
        "early": (frame["band"] == "early").to_numpy(dtype=float),
        "n_polls": len(frame),
        "n_races": len(races),
        "n_houses": len(houses),
        "n_cycles": len(cycles),
        "cycles": cycles,
    }


def _gibbs(arrays: dict, priors: ModelPriors, settings: SamplerSettings) -> pd.DataFrame:
    y = arrays["y"]
    v = arrays["v"]
    race = arrays["race"]
    cycle = arrays["cycle"]
    house = arrays["house"]
    mid = arrays["mid"]
    early = arrays["early"]
    n_polls = arrays["n_polls"]
    n_races = arrays["n_races"]
    n_houses = arrays["n_houses"]
    n_cycles = arrays["n_cycles"]
    rng = np.random.default_rng(settings.seed)
    mu = float(np.mean(y))
    beta_mid = 0.0
    beta_early = 0.0
    phi = 1.0
    race_effect = np.zeros(n_races)
    house_effect = np.zeros(n_houses)
    cycle_effect = np.zeros(n_cycles)
    tau2_race = priors.half_cauchy_scale**2
    tau2_house = priors.half_cauchy_scale**2
    tau2_cycle = priors.half_cauchy_scale**2
    rho_race = 1.0 / priors.half_cauchy_scale**2
    rho_house = 1.0 / priors.half_cauchy_scale**2
    rho_cycle = 1.0 / priors.half_cauchy_scale**2
    mean_precision = 1.0 / priors.mean_sd**2
    timing_precision = 1.0 / priors.timing_sd**2
    cauchy_scale_sq = priors.half_cauchy_scale**2
    kept = np.empty((settings.draws, len(POSTERIOR_COLUMNS)))
    stored = 0
    total = settings.burn_in + settings.draws * settings.thin
    for iteration in range(total):
        mu, cycle_effect = _draw_mean_and_cycles(
            y, v, phi, mid, early, beta_mid, beta_early, race, house, cycle,
            race_effect, house_effect, tau2_cycle, mean_precision, n_cycles, rng,
        )
        beta_mid, beta_early = _draw_timing(
            y, v, phi, mid, early, mu, cycle_effect, race, house, cycle,
            race_effect, house_effect, timing_precision, rng,
        )
        base = mu + beta_mid * mid + beta_early * early
        weights = 1.0 / (phi * v)
        house_effect = _draw_groups(
            y - base - cycle_effect[cycle] - race_effect[race],
            weights, house, n_houses, tau2_house, rng,
        )
        race_effect = _draw_groups(
            y - base - cycle_effect[cycle] - house_effect[house],
            weights, race, n_races, tau2_race, rng,
        )
        tau2_race, rho_race = _draw_scale_variance(race_effect, rho_race, cauchy_scale_sq, rng)
        tau2_house, rho_house = _draw_scale_variance(house_effect, rho_house, cauchy_scale_sq, rng)
        tau2_cycle, rho_cycle = _draw_scale_variance(cycle_effect, rho_cycle, cauchy_scale_sq, rng)
        residual = y - base - cycle_effect[cycle] - race_effect[race] - house_effect[house]
        phi = float(
            draw_invgamma(
                priors.phi_shape + n_polls / 2.0,
                priors.phi_scale + 0.5 * float(np.sum(residual**2 / v)),
                rng,
            )
        )
        _require_finite(mu, beta_mid, beta_early, phi, tau2_race, tau2_house, tau2_cycle)
        if iteration >= settings.burn_in and (iteration - settings.burn_in) % settings.thin == 0:
            kept[stored, :] = (
                mu,
                beta_mid,
                beta_early,
                np.sqrt(tau2_race),
                np.sqrt(tau2_house),
                np.sqrt(tau2_cycle),
                phi,
            )
            stored += 1
    if stored != settings.draws:
        raise UncertaintyError("The sampler did not store the requested number of draws.")
    return pd.DataFrame(kept, columns=POSTERIOR_COLUMNS)


def _draw_mean_and_cycles(
    y, v, phi, mid, early, beta_mid, beta_early, race, house, cycle,
    race_effect, house_effect, tau2_cycle, mean_precision, n_cycles, rng,
) -> tuple[float, np.ndarray]:
    offset = y - beta_mid * mid - beta_early * early - race_effect[race] - house_effect[house]
    weights = 1.0 / (phi * v)
    sum_w = float(weights.sum())
    sum_w_cycle = np.bincount(cycle, weights=weights, minlength=n_cycles)
    sum_wy = float(np.dot(weights, offset))
    sum_wy_cycle = np.bincount(cycle, weights=weights * offset, minlength=n_cycles)
    dim = 1 + n_cycles
    precision = np.zeros((dim, dim))
    precision[0, 0] = mean_precision + sum_w
    precision[0, 1:] = sum_w_cycle
    precision[1:, 0] = sum_w_cycle
    diagonal = np.arange(1, dim)
    precision[diagonal, diagonal] = 1.0 / tau2_cycle + sum_w_cycle
    precision = 0.5 * (precision + precision.T)
    precision[np.diag_indices(dim)] += 1e-12
    covariance = np.linalg.inv(precision)
    covariance = 0.5 * (covariance + covariance.T)
    rhs = np.concatenate(([sum_wy], sum_wy_cycle))
    draw = rng.multivariate_normal(covariance @ rhs, covariance)
    return float(draw[0]), draw[1:]


def _draw_timing(
    y, v, phi, mid, early, mu, cycle_effect, race, house, cycle,
    race_effect, house_effect, timing_precision, rng,
) -> tuple[float, float]:
    residual = y - mu - cycle_effect[cycle] - race_effect[race] - house_effect[house]
    weights = 1.0 / (phi * v)
    beta_mid = _draw_slope(weights * mid, residual, timing_precision, rng)
    beta_early = _draw_slope(weights * early, residual, timing_precision, rng)
    return beta_mid, beta_early


def _draw_slope(weights: np.ndarray, residual: np.ndarray, prior_precision: float, rng: np.random.Generator) -> float:
    data_precision = float(weights.sum())
    weighted_sum = float(np.dot(weights, residual))
    post_precision = prior_precision + data_precision
    mean = weighted_sum / post_precision
    return float(mean + rng.normal() / np.sqrt(post_precision))


def _draw_groups(
    residual: np.ndarray,
    weights: np.ndarray,
    index: np.ndarray,
    n_groups: int,
    prior_variance: float,
    rng: np.random.Generator,
) -> np.ndarray:
    sum_w = np.bincount(index, weights=weights, minlength=n_groups)
    sum_wy = np.bincount(index, weights=weights * residual, minlength=n_groups)
    post_precision = 1.0 / prior_variance + sum_w
    post_mean = sum_wy / post_precision
    return post_mean + rng.normal(size=n_groups) / np.sqrt(post_precision)


def _draw_scale_variance(effects: np.ndarray, rho: float, cauchy_scale_sq: float, rng: np.random.Generator) -> tuple[float, float]:
    n_groups = len(effects)
    tau2 = float(draw_invgamma(0.5 + n_groups / 2.0, 1.0 / rho + 0.5 * float(np.dot(effects, effects)), rng))
    rho_draw = float(draw_invgamma(1.0, 1.0 / tau2 + 1.0 / cauchy_scale_sq, rng))
    return tau2, rho_draw


def _require_finite(*values: float) -> None:
    if not np.isfinite(values).all():
        raise UncertaintyError("The Gibbs sampler produced a non-finite parameter.")
