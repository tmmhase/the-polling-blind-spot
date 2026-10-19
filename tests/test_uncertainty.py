"""Sampling variance, hierarchical updates, leakage rules, and predictive factors."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from polling_blind_spot.uncertainty.backtest import forward_chain_folds, leave_one_cycle_folds
from polling_blind_spot.uncertainty.errors import UncertaintyError
from polling_blind_spot.uncertainty.model import (
    ModelPriors,
    SamplerSettings,
    draw_invgamma,
    fit_error_model,
    normal_normal_posterior,
    sample_half_cauchy_prior,
)
from polling_blind_spot.uncertainty.predict import Roster, predictive_errors, roster_factors, variance_components
from polling_blind_spot.uncertainty.prepare import prepare_modeling_frame, timing_band
from polling_blind_spot.uncertainty.sampling import two_party_sampling_variance

ROOT = Path(__file__).resolve().parents[1]
POLL_ERRORS = ROOT / "outputs" / "historical_polling_error" / "poll_errors.csv"


def test_sampling_variance_matches_the_two_candidate_delta_method():
    # 50/50 with no undecided: SE of the margin is 200 * sqrt(0.25 / n).
    variance = two_party_sampling_variance(50, 50, 400)
    assert variance == pytest.approx(25.0)
    # Undecided respondents shrink the decided sample. 40/40 of n=100 is an
    # 80-person decided sample at a tied two-party margin.
    undecided = two_party_sampling_variance(40, 40, 100)
    assert undecided == pytest.approx(10000 * 0.25 / 80 * 4)
    # An uneven margin is not the tied-share formula.
    uneven = two_party_sampling_variance(60, 30, 500)
    assert uneven is not None
    assert uneven != pytest.approx(two_party_sampling_variance(45, 45, 500))


def test_sampling_variance_does_not_replace_a_missing_or_impossible_sample():
    assert two_party_sampling_variance(50, 40, None) is None
    assert two_party_sampling_variance(50, 40, float("nan")) is None
    assert two_party_sampling_variance(50, 40, 0) is None
    assert two_party_sampling_variance(50, 40, -10) is None
    assert two_party_sampling_variance(70, 40, 800) is None
    assert two_party_sampling_variance(0, 0, 800) is None
    assert two_party_sampling_variance(-1, 40, 800) is None


def test_timing_bands_follow_the_pre_election_cutpoints():
    assert timing_band(1) == "late"
    assert timing_band(30) == "late"
    assert timing_band(31) == "mid"
    assert timing_band(180) == "mid"
    assert timing_band(181) == "early"
    assert timing_band(0) is None
    assert timing_band(float("nan")) is None


def test_prepare_drops_unpublished_sample_sizes_and_collapses_one_poll():
    polls = pd.DataFrame(
        [
            _question(1, error=4, sample_size=400, dem=50, rep=40),
            _question(2, error=8, sample_size=400, dem=50, rep=40),
            _question(3, error=1, sample_size=None, dem=50, rep=40),
            _question(4, error=1, sample_size=500, dem=60, rep=50),
        ]
    )
    polls.loc[1, "poll_id"] = polls.loc[0, "poll_id"]
    modeling, exclusions, summary = prepare_modeling_frame(polls)
    assert set(exclusions["reason"]) == {"missing_sample_size", "shares_exceed_100"}
    assert summary["n_questions_excluded"] == 2
    assert len(modeling) == 1
    assert modeling.iloc[0]["n_questions"] == 2
    assert modeling.iloc[0]["error_two_party"] == pytest.approx(6)
    assert "sample_size" not in modeling.columns
    collapsed_variance = two_party_sampling_variance(50, 40, 400)
    assert modeling.iloc[0]["sampling_variance"] == pytest.approx(collapsed_variance)


def test_real_poll_errors_keep_a_positive_sampling_variance():
    modeling, exclusions, summary = prepare_modeling_frame(pd.read_csv(POLL_ERRORS))
    assert summary["n_questions"] == 3212
    assert summary["exclusions_by_reason"]["missing_sample_size"] == 10
    assert summary["exclusions_by_reason"]["shares_exceed_100"] == 1
    assert summary["n_polls"] < summary["n_questions_kept"]
    assert modeling["sampling_variance"].gt(0).all()
    assert modeling["error_two_party"].notna().all()
    assert set(modeling["band"]) <= {"late", "mid", "early"}
    assert exclusions["question_id"].is_unique


def test_normal_normal_update_matches_a_hand_calculation():
    # One observation y=10 with variance 4, prior N(0, 16).
    mean, variance = normal_normal_posterior(data_precision=0.25, weighted_sum=2.5, prior_variance=16)
    assert mean == pytest.approx(8.0)
    assert variance == pytest.approx(3.2)


def test_inverse_gamma_mean_and_half_cauchy_prior_median():
    rng = np.random.default_rng(11)
    draws = draw_invgamma(2.0, 20.0, rng, size=40000)
    assert draws.mean() == pytest.approx(20.0, rel=0.03)
    scale = sample_half_cauchy_prior(scale=5.0, n_draws=6000, seed=11, burn_in=2000)
    assert np.median(scale) == pytest.approx(5.0, rel=0.15)


def test_sampler_recovers_a_normal_hierarchy_and_is_reproducible():
    frame = _simulated_hierarchy(seed=21)
    settings = SamplerSettings(burn_in=400, draws=600, thin=2, seed=21)
    first = fit_error_model(frame, ModelPriors(), settings)
    second = fit_error_model(frame, ModelPriors(), settings)
    pd.testing.assert_frame_equal(first.draws, second.draws)
    median = first.draws.median()
    # Repeated polls identify the house effect and the sampling inflation.
    # The mean matches the realized sample, which is not the simulation's mu
    # once a handful of cycle effects have been drawn.
    assert median["mu"] == pytest.approx(float(frame["error_two_party"].mean()), abs=0.6)
    assert median["sd_house"] == pytest.approx(3.0, abs=1.0)
    assert median["phi"] == pytest.approx(1.0, abs=0.35)
    assert 1.0 < median["sd_race"] < 6.5
    assert first.ess["phi"] > 30


def test_roster_factors_distinguish_repeated_polls_from_new_pollsters():
    repeated = Roster(
        bands=tuple("late" for _ in range(10)),
        sampling_variances=tuple(16.0 for _ in range(10)),
        pollster_ids=tuple("one-firm" for _ in range(10)),
    )
    diverse = Roster(
        bands=tuple("late" for _ in range(10)),
        sampling_variances=tuple(16.0 for _ in range(10)),
        pollster_ids=tuple(f"firm-{index}" for index in range(10)),
    )
    repeated_factors = roster_factors(repeated)["unweighted"]
    diverse_factors = roster_factors(diverse)["unweighted"]
    assert repeated_factors["house_factor"] == pytest.approx(1.0)
    assert diverse_factors["house_factor"] == pytest.approx(0.1)
    assert repeated_factors["sampling_factor"] == pytest.approx(1.6)
    assert diverse_factors["sampling_factor"] == pytest.approx(1.6)
    single = Roster(bands=("late",), sampling_variances=(16.0,), pollster_ids=("one-firm",))
    single_factors = roster_factors(single)
    assert single_factors["unweighted"]["sampling_factor"] == pytest.approx(single_factors["pollster_equal"]["sampling_factor"])
    assert single_factors["unweighted"]["house_factor"] == pytest.approx(single_factors["pollster_equal"]["house_factor"])


def test_predictive_draws_do_not_need_a_result_and_keep_shared_error():
    draws = pd.DataFrame(
        {
            "mu": np.full(2000, 2.0),
            "beta_mid": np.full(2000, 1.0),
            "beta_early": np.zeros(2000),
            "sd_race": np.full(2000, 4.0),
            "sd_house": np.full(2000, 3.0),
            "sd_cycle": np.full(2000, 1.0),
            "phi": np.ones(2000),
        }
    )
    one_firm = Roster(
        bands=tuple("late" for _ in range(20)),
        sampling_variances=tuple(16.0 for _ in range(20)),
        pollster_ids=tuple("one-firm" for _ in range(20)),
    )
    many_firms = Roster(
        bands=tuple("late" for _ in range(20)),
        sampling_variances=tuple(16.0 for _ in range(20)),
        pollster_ids=tuple(f"firm-{index}" for index in range(20)),
    )
    rng = np.random.default_rng(5)
    narrow = predictive_errors(draws, many_firms, rng)["unweighted"]
    wide = predictive_errors(draws, one_firm, np.random.default_rng(5))["unweighted"]
    # Twenty polls from one firm keep that firm's shared error. The analytic
    # standard deviations are sqrt(1 + 16 + 9 + 16/20) and sqrt(1 + 16 + 9/20 + 16/20).
    assert np.std(wide, ddof=1) == pytest.approx(np.sqrt(26.8), abs=0.25)
    assert np.std(narrow, ddof=1) == pytest.approx(np.sqrt(1 + 16 + 9 / 20 + 16 / 20), abs=0.25)
    assert np.std(wide, ddof=1) > np.std(narrow, ddof=1)
    components = variance_components(draws, one_firm)
    house = components.loc[
        (components["estimand"] == "unweighted") & (components["component"] == "house"),
        "variance",
    ].iloc[0]
    race = components.loc[
        (components["estimand"] == "unweighted") & (components["component"] == "race"),
        "variance",
    ].iloc[0]
    assert house == pytest.approx(9.0)
    assert race == pytest.approx(16.0)
    mid = Roster(bands=("mid",), sampling_variances=(16.0,), pollster_ids=("one-firm",))
    mid_draws = predictive_errors(draws, mid, np.random.default_rng(6))["unweighted"]
    assert mid_draws.mean() == pytest.approx(3.0, abs=0.4)


def test_backtest_folds_keep_the_scored_cycle_out_of_training():
    modeling, _, _ = prepare_modeling_frame(pd.read_csv(POLL_ERRORS))
    loco = leave_one_cycle_folds(modeling)
    assert [cycle for cycle, _, _ in loco] == [2018, 2020, 2022, 2024]
    for cycle, train, test in loco:
        assert cycle not in set(train["cycle"])
        assert set(test["cycle"]) == {cycle}
        assert set(train["contest_id"]).isdisjoint(set(test["contest_id"]))
    forward = forward_chain_folds(modeling)
    assert [cycle for cycle, _, _ in forward] == [2020, 2022, 2024]
    for cycle, train, test in forward:
        assert int(train["cycle"].max()) < cycle
        assert set(train["contest_id"]).isdisjoint(set(test["contest_id"]))


def test_short_real_data_fit_separates_sampling_inflation_from_shared_error():
    modeling, _, summary = prepare_modeling_frame(pd.read_csv(POLL_ERRORS))
    posterior = fit_error_model(
        modeling,
        ModelPriors(),
        SamplerSettings(burn_in=200, draws=300, thin=2, seed=20261018),
    )
    median = posterior.draws.median()
    assert 0.0 < median["mu"] < 6.0
    assert median["sd_race"] > 2.0
    assert median["sd_house"] > 2.0
    assert 0.7 < median["phi"] < 1.6
    assert summary["median_sampling_variance"] == pytest.approx(float(modeling["sampling_variance"].median()))


def test_roster_rejects_a_result_shaped_shortcut_and_bad_variance():
    with pytest.raises(UncertaintyError):
        Roster(bands=(), sampling_variances=(), pollster_ids=())
    with pytest.raises(UncertaintyError):
        Roster(bands=("late",), sampling_variances=(0.0,), pollster_ids=("a",))
    with pytest.raises(UncertaintyError):
        predictive_errors(pd.DataFrame({"mu": [1.0]}), Roster(("late",), (4.0,), ("a",)), np.random.default_rng(0))


def _question(question_id: int, error: float, sample_size: float | None, dem: float, rep: float) -> dict:
    return {
        "question_id": question_id,
        "poll_id": 1000 + question_id,
        "contest_id": "2018-AZ-general-0",
        "cycle": 2018,
        "pollster_key": "example",
        "days_before_election": 10,
        "sample_size": sample_size,
        "dem_pct": dem,
        "rep_pct": rep,
        "error_two_party": error,
    }


def _simulated_hierarchy(seed: int) -> pd.DataFrame:
    """Normal draws from the model's own distribution, for a sampler check.

    Each pollster contributes four repeated rows so the house effect is not
    the same number as the sampling residual. These rows are not polls and
    are not written to the research outputs.
    """
    rng = np.random.default_rng(seed)
    rows = []
    mu = 2.0
    for cycle in range(4):
        cycle_effect = rng.normal(0, 1.5)
        for race_index in range(6):
            race_effect = rng.normal(0, 4.0)
            contest_id = f"{2000 + cycle}-ST-{race_index}"
            for pollster_index in range(3):
                house = rng.normal(0, 3.0)
                for _repeat in range(4):
                    variance = 16.0
                    error = mu + cycle_effect + race_effect + house + rng.normal(0, np.sqrt(variance))
                    rows.append(
                        {
                            "error_two_party": error,
                            "sampling_variance": variance,
                            "contest_id": contest_id,
                            "cycle": 2000 + cycle,
                            "pollster_key": f"firm-{pollster_index}",
                            "band": "late",
                        }
                    )
    return pd.DataFrame(rows)
