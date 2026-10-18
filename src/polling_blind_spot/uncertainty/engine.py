"""Fit the uncertainty model, simulate poll-average errors, and backtest coverage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from polling_blind_spot.uncertainty.backtest import run_backtests
from polling_blind_spot.uncertainty.errors import UncertaintyError
from polling_blind_spot.uncertainty.model import (
    ModelPriors,
    SamplerSettings,
    fit_error_model,
    posterior_summary,
)
from polling_blind_spot.uncertainty.plots import write_figures
from polling_blind_spot.uncertainty.predict import predictive_errors, stylized_late_rosters, variance_components
from polling_blind_spot.uncertainty.prepare import prepare_modeling_frame

_SUMMARY_QUANTILES = (0.025, 0.10, 0.25, 0.50, 0.75, 0.90, 0.975)


def run_uncertainty_engine(
    poll_errors_path: Path,
    output_dir: Path,
    priors: ModelPriors | None = None,
    settings: SamplerSettings | None = None,
) -> dict:
    """Read scored historical errors and write the uncertainty outputs.

    The poll-error file is not modified. Result votes are not an input.
    Intervals for a cycle are fit without that cycle's errors.
    """
    priors = priors or ModelPriors()
    settings = settings or SamplerSettings()
    path = Path(poll_errors_path)
    if not path.is_file():
        raise UncertaintyError(f"Poll-error file does not exist: {path}")
    polls = pd.read_csv(path)
    modeling, exclusions, preparation = prepare_modeling_frame(polls)
    posterior = fit_error_model(modeling, priors, settings)
    summary = posterior_summary(posterior)
    designs = stylized_late_rosters(preparation["median_sampling_variance"])
    component_frames = []
    simulation_frames = []
    quantile_rows = []
    rng = np.random.default_rng(settings.seed + 1)
    for name, roster in designs:
        components = variance_components(posterior.draws, roster)
        components.insert(0, "design", name)
        component_frames.append(components)
        draws = predictive_errors(posterior.draws, roster, rng)["unweighted"]
        simulation_frames.append(pd.DataFrame({"design": name, "error": draws}))
        quantile_rows.append(_simulation_row(name, draws, roster))
    components_out = pd.concat(component_frames, ignore_index=True)
    simulations = pd.concat(simulation_frames, ignore_index=True)
    sensitivity = _prior_sensitivity(modeling, settings)
    backtest = run_backtests(modeling, priors, settings)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    figure_names = write_figures(
        posterior.draws,
        components_out,
        simulations,
        backtest.races,
        backtest.coverage,
        output_dir / "figures",
    )
    report = _report(
        path=path,
        preparation=preparation,
        priors=priors,
        settings=settings,
        summary=summary,
        components=components_out,
        quantiles=pd.DataFrame(quantile_rows),
        sensitivity=sensitivity,
        coverage=backtest.coverage,
        figure_names=figure_names,
    )
    _write_tables(
        output_dir,
        modeling=modeling,
        exclusions=exclusions,
        summary=summary,
        draws=posterior.draws,
        components=components_out,
        simulations=simulations,
        quantiles=pd.DataFrame(quantile_rows),
        sensitivity=sensitivity,
        races=backtest.races,
        coverage=backtest.coverage,
        report=report,
    )
    return report


def _prior_sensitivity(modeling: pd.DataFrame, settings: SamplerSettings) -> pd.DataFrame:
    rows = []
    for scale in (2.5, 5.0, 10.0):
        priors = ModelPriors(half_cauchy_scale=scale)
        posterior = fit_error_model(modeling, priors, settings)
        summary = posterior_summary(posterior)
        for _, parameter in summary.iterrows():
            rows.append(
                {
                    "half_cauchy_scale": scale,
                    "parameter": parameter["parameter"],
                    "p50": parameter["p50"],
                    "p05": parameter["p05"],
                    "p95": parameter["p95"],
                    "ess": parameter["ess"],
                }
            )
    return pd.DataFrame(rows)


def _simulation_row(name: str, draws: np.ndarray, roster) -> dict:
    quantiles = np.quantile(draws, _SUMMARY_QUANTILES)
    return {
        "design": name,
        "n_polls": len(roster.bands),
        "n_pollsters": len(set(roster.pollster_ids)),
        "n_draws": int(len(draws)),
        "mean": float(np.mean(draws)),
        "sd": float(np.std(draws, ddof=1)),
        "p025": float(quantiles[0]),
        "p10": float(quantiles[1]),
        "p25": float(quantiles[2]),
        "p50": float(quantiles[3]),
        "p75": float(quantiles[4]),
        "p90": float(quantiles[5]),
        "p975": float(quantiles[6]),
    }


def _report(
    path: Path,
    preparation: dict,
    priors: ModelPriors,
    settings: SamplerSettings,
    summary: pd.DataFrame,
    components: pd.DataFrame,
    quantiles: pd.DataFrame,
    sensitivity: pd.DataFrame,
    coverage: pd.DataFrame,
    figure_names: list[str],
) -> dict:
    payload = path.read_bytes()
    return {
        "error_definition": (
            "Signed error is poll_margin_two_party minus result_margin_two_party, "
            "in percentage points. Positive means the poll average was more Democratic "
            "than the two-candidate result."
        ),
        "model": (
            "error = mu + beta_mid * mid + beta_early * early + cycle + race + "
            "pollster_within_race + sampling_noise. Late polls are the baseline. "
            "Sampling noise has variance phi times the simple-random-sample variance."
        ),
        "input": {
            "file": path.name,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
        },
        "preparation": preparation,
        "priors": {
            "mu": f"Normal(0, {priors.mean_sd}^2)",
            "beta_mid": f"Normal(0, {priors.timing_sd}^2)",
            "beta_early": f"Normal(0, {priors.timing_sd}^2)",
            "sd_race": f"Half-Cauchy(scale={priors.half_cauchy_scale})",
            "sd_house": f"Half-Cauchy(scale={priors.half_cauchy_scale})",
            "sd_cycle": f"Half-Cauchy(scale={priors.half_cauchy_scale})",
            "phi": f"InvGamma(shape={priors.phi_shape}, scale={priors.phi_scale}), prior mean 1",
        },
        "sampler": {
            "burn_in": settings.burn_in,
            "draws": settings.draws,
            "thin": settings.thin,
            "seed": settings.seed,
            "algorithm": "Gibbs, with a joint draw for the mean and cycle effects and a scale-mixture draw for half-Cauchy standard deviations",
        },
        "posterior": summary.to_dict(orient="records"),
        "stylized_sampling_variance": preparation["median_sampling_variance"],
        "variance_decomposition": components.to_dict(orient="records"),
        "simulation_quantiles": quantiles.to_dict(orient="records"),
        "prior_sensitivity": sensitivity.to_dict(orient="records"),
        "backtest_coverage": coverage.to_dict(orient="records"),
        "figures": figure_names,
        "leakage_controls": [
            "The likelihood uses signed errors only for contests in the training cycles.",
            "A leave-one-cycle-out fit drops every contest in the scored cycle.",
            "The forward chain uses only earlier cycles. 2018 has no earlier cycle in this file.",
            "Predictive draws are computed from timing bands, sampling variances, and pollster ids. The held-out signed error is attached afterward for scoring.",
            "Result vote totals are not read by this step.",
            "2026 results are not imputed.",
        ],
        "limitations": [
            "Four election cycles identify the cycle standard deviation weakly. That posterior is sensitive to the half-Cauchy scale.",
            "Pollster effects are redrawn for each race. A firm's historical bias does not shift the center of a new race's interval.",
            "The sampling variance is the simple-random-sample delta method. phi is one average inflation factor, not a design effect by mode.",
            "Random effects are normal. Heavier tails in the historical errors are not given a separate degrees-of-freedom parameter.",
            "Questions that share a poll id are collapsed to one observation. Their sampling variances are averaged, not divided by the question count.",
            "The primary estimand is the unweighted mean of those polls. A pollster-equal mean is reported beside it.",
            "Internal and partisan polls stay in the training set. FiveThirtyEight pollster grades are not used as weights.",
            "Leave-one-cycle-out for 2018 trains on later cycles, so it is not a real-time score. The forward chain is the real-time score.",
        ],
    }


def _write_tables(
    output_dir: Path,
    modeling: pd.DataFrame,
    exclusions: pd.DataFrame,
    summary: pd.DataFrame,
    draws: pd.DataFrame,
    components: pd.DataFrame,
    simulations: pd.DataFrame,
    quantiles: pd.DataFrame,
    sensitivity: pd.DataFrame,
    races: pd.DataFrame,
    coverage: pd.DataFrame,
    report: dict,
) -> None:
    _csv(modeling, output_dir / "modeling_frame.csv")
    _csv(exclusions, output_dir / "question_exclusions.csv")
    _csv(summary, output_dir / "posterior_summary.csv")
    _csv(draws, output_dir / "posterior_draws.csv", decimals=6)
    _csv(components, output_dir / "variance_decomposition.csv")
    _csv(simulations, output_dir / "simulation_draws.csv", decimals=6)
    _csv(quantiles, output_dir / "simulation_quantiles.csv")
    _csv(sensitivity, output_dir / "prior_sensitivity.csv")
    _csv(races, output_dir / "backtest_races.csv")
    _csv(coverage, output_dir / "backtest_coverage.csv")
    (output_dir / "model_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def _csv(frame: pd.DataFrame, path: Path, decimals: int = 4) -> None:
    formatted = frame.copy()
    for column in formatted.columns:
        if pd.api.types.is_float_dtype(formatted[column]):
            formatted[column] = formatted[column].map(lambda value, digits=decimals: round(float(value), digits))
    formatted.to_csv(path, index=False)
