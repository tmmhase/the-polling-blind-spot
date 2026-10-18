"""Historical polling-error joins, leakage rules, and summaries."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from polling_blind_spot.analysis.errors import AnalysisError
from polling_blind_spot.analysis.names import names_match
from polling_blind_spot.analysis.plots import write_figures
from polling_blind_spot.analysis.polling_error import (
    race_poll_summaries,
    run_historical_polling_error,
    score_questions,
    summarize_by_cycle,
    variance_decomposition,
)
from polling_blind_spot.analysis.results import (
    all_ballot_margin,
    build_result_candidates,
    poll_two_party_margin,
    two_candidate_margin,
)
from polling_blind_spot.ingest.schemas import MEDSL_COLUMNS

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
FTE_PATH = RAW / "fivethirtyeight_senate_polls_historical.csv"
MEDSL_PATH = RAW / "medsl_us_senate_statewide_returns_1976_2024.csv"


def test_name_matching_accepts_published_variants_and_rejects_near_misses():
    assert names_match("Timothy Michael Kaine", "TIMOTHY M. KAINE")
    assert names_match("Catherine Cortez Masto", "CORTEZ MASTO, CATHERINE")
    assert names_match("Ron Wyden", "WYDEN RON")
    assert names_match("Jo Rae Perkins", "PERKINS JO RAE")
    assert names_match("Raul Garcia", "DR RAUL GARCIA")
    assert names_match("Susan M. Collins", "SUSAN MARGARET COLLINS")
    assert names_match("Mary Jennings Hegar", 'MARY "MJ" HEGAR')
    assert names_match("Ben Ray Luján", "BEN R. LUJAN")
    assert names_match("Doug Jones", "GORDON DOUGLAS JONES")
    assert names_match("Gordon Douglas Jones", "DOUG JONES")
    assert names_match("Thom Tillis", "THOMAS ROLAND TILLIS")
    assert names_match("Chele Farley", "CHELE CHIAVACCI FARLEY")
    assert not names_match("Kevin J. O'Connor", "KEVIN J. O'CONNER")
    assert not names_match("Bryant Messner", "CORKY MESSNER")
    assert not names_match("Jon Ossoff", "David Perdue")


def test_two_candidate_margins_use_the_same_denominator_rule():
    assert two_candidate_margin(120, 60) == pytest.approx(100 * 60 / 180)
    assert poll_two_party_margin(50, 40) == pytest.approx(100 * 10 / 90)
    assert all_ballot_margin(120, 60, 1000) == pytest.approx(6)
    assert all_ballot_margin(120, 60, 100) is None
    assert two_candidate_margin(0, 0) is None
    assert poll_two_party_margin(0, 0) is None


def test_democratic_detailed_label_is_used_when_simplified_party_is_other():
    frame = _returns(
        [
            _line("TAMMY DUCKWORTH", "OTHER", "200", party_detailed="DEMOCRATIC", state="ILLINOIS", state_po="IL"),
            _line("KATHY SALVI", "REPUBLICAN", "100", state="ILLINOIS", state_po="IL"),
            _line(
                "NICHOLAS N. GLENN",
                "OTHER",
                "5",
                party_detailed="INDEPENDENT REPUBLICAN PARTY",
                state="ARIZONA",
                state_po="AZ",
            ),
        ]
    )
    candidates = build_result_candidates(frame)
    duckworth = candidates.loc[candidates["candidate_name"] == "TAMMY DUCKWORTH"].iloc[0]
    glenn = candidates.loc[candidates["candidate_name"] == "NICHOLAS N. GLENN"].iloc[0]
    assert duckworth["party"] == "DEM"
    assert glenn["party"] == "OTHER"


def test_fusion_lines_are_summed_and_blank_write_ins_stay_unnamed():
    frame = _returns(
        [
            _line("KIRSTEN E. GILLIBRAND", "DEMOCRAT", "100", party_detailed="DEMOCRAT"),
            _line("KIRSTEN E. GILLIBRAND", "OTHER", "20", party_detailed="WORKING FAMILIES"),
            _line("CHELE CHIAVACCI FARLEY", "REPUBLICAN", "50", party_detailed="REPUBLICAN"),
            _line("CHELE CHIAVACCI FARLEY", "OTHER", "10", party_detailed="CONSERVATIVE"),
            _line("", "OTHER", "5", writein="True"),
            _line("UNDERVOTES", "OTHER", "15"),
        ]
    )
    candidates = build_result_candidates(frame)
    assert list(candidates["candidate_name"]) == ["CHELE CHIAVACCI FARLEY", "KIRSTEN E. GILLIBRAND"]
    gillibrand = candidates.loc[candidates["party"] == "DEM"].iloc[0]
    farley = candidates.loc[candidates["party"] == "REP"].iloc[0]
    assert int(gillibrand["votes"]) == 120
    assert int(farley["votes"]) == 60
    assert int(gillibrand["total_votes"]) == 1000
    assert int(farley["total_votes"]) == 1000


def test_scored_poll_uses_fusion_totals_and_keeps_the_sign_convention():
    questions = _questions(
        [
            _question(
                dem_candidate="Kirsten Gillibrand",
                rep_candidate="Chele Farley",
                dem_pct=50,
                rep_pct=40,
                margin_dem_minus_rep=10,
                state_po="NY",
                state_name="New York",
            )
        ]
    )
    scoring = score_questions(questions, _fusion_candidates())
    assert len(scoring.included) == 1
    row = scoring.included.iloc[0]
    assert int(row["result_dem_votes"]) == 120
    assert int(row["result_rep_votes"]) == 60
    assert row["poll_margin_two_party"] == pytest.approx(poll_two_party_margin(50, 40))
    assert row["result_margin_two_party"] == pytest.approx(two_candidate_margin(120, 60))
    assert row["error_two_party"] == pytest.approx(row["poll_margin_two_party"] - row["result_margin_two_party"])
    assert row["error_two_party"] < 0
    assert row["error_published_vs_all_votes"] == pytest.approx(10 - 6)


def test_post_election_polls_are_excluded_before_a_result_is_attached():
    questions = _questions(
        [
            _question(question_id="before", end_date="2020-11-03"),
            _question(question_id="after", end_date="2020-11-04"),
            _question(question_id="no-date", election_date=None),
        ]
    )
    scoring = score_questions(questions, _georgia_candidates())
    assert list(scoring.included["question_id"]) == ["before"]
    assert bool(scoring.included.iloc[0]["ends_on_election_day"]) is True
    assert int(scoring.included.iloc[0]["days_before_election"]) == 0
    reasons = dict(zip(scoring.exclusions["question_id"], scoring.exclusions["reason"], strict=True))
    assert reasons == {"after": "after_election", "no-date": "missing_election_date"}
    assert "result_dem_votes" not in scoring.exclusions.columns


def test_runoff_poll_does_not_use_the_general_election_totals():
    questions = _questions(
        [
            _question(question_id="general", stage="general", election_date="2020-11-03", end_date="2020-10-20"),
            _question(question_id="runoff", stage="runoff", election_date="2021-01-05", end_date="2020-12-20"),
        ]
    )
    scoring = score_questions(questions, _georgia_candidates())
    by_id = scoring.included.set_index("question_id")
    assert int(by_id.loc["general", "result_dem_votes"]) == 100
    assert int(by_id.loc["general", "election_year"]) == 2020
    assert int(by_id.loc["runoff", "result_dem_votes"]) == 60
    assert int(by_id.loc["runoff", "result_rep_votes"]) == 55
    assert int(by_id.loc["runoff", "election_year"]) == 2021
    assert int(by_id.loc["runoff", "cycle"]) == 2020


def test_same_day_duplicate_ballots_are_not_scored():
    candidates = pd.concat(
        [
            build_result_candidates(_returns([
                _line("JON OSSOFF", "DEMOCRAT", "100"),
                _line("DAVID A. PERDUE", "REPUBLICAN", "80"),
            ])),
            build_result_candidates(_returns([
                _line("JON OSSOFF", "DEMOCRAT", "70", special="True"),
                _line("DAVID A. PERDUE", "REPUBLICAN", "30", special="True"),
            ])),
        ],
        ignore_index=True,
    )
    scoring = score_questions(_questions([_question()]), candidates)
    assert scoring.included.empty
    assert list(scoring.exclusions["reason"]) == ["ambiguous_duplicate_ballot"]
    assert set(scoring.ambiguous["result_dem_votes"]) == {100, 70}
    assert scoring.ambiguous["poll_margin_two_party"].nunique() == 1


def test_identical_names_are_not_split_by_vote_total():
    candidates = build_result_candidates(
        _returns(
            [
                _line("JOHN A. SMITH", "DEMOCRAT", "10"),
                _line("JOHN B. SMITH", "DEMOCRAT", "900"),
                _line("JANE DOE", "REPUBLICAN", "400"),
            ]
        )
    )
    scoring = score_questions(
        _questions([_question(dem_candidate="John Smith", rep_candidate="Jane Doe")]),
        candidates,
    )
    assert scoring.included.empty
    assert list(scoring.exclusions["reason"]) == ["ambiguous_candidate"]


def test_a_party_disagreement_is_not_overridden():
    scoring = score_questions(
        _questions([_question(dem_candidate="David Perdue", rep_candidate="Jon Ossoff")]),
        _georgia_candidates(),
    )
    assert scoring.included.empty
    assert list(scoring.exclusions["reason"]) == ["party_mismatch"]


def test_jungle_primary_and_hypothetical_questions_stay_out():
    questions = _questions(
        [
            _question(question_id="jungle", stage="jungle_primary"),
            _question(question_id="hypo", hypothetical=True),
            _question(question_id="ranked", ranked_choice=True),
        ]
    )
    scoring = score_questions(questions, _georgia_candidates())
    assert scoring.included.empty
    assert set(scoring.exclusions["reason"]) == {"stage_not_comparable", "hypothetical", "ranked_choice"}


def test_pre_election_average_ignores_result_columns_and_missing_sample_sizes():
    base = pd.DataFrame(
        [
            _average_row(margin=10, sample=1000, result=50),
            _average_row(margin=0, sample=100, result=50),
            _average_row(margin=0, sample=None, result=50),
        ]
    )
    altered = base.copy()
    altered["result_margin_two_party"] = -100
    altered["error_two_party"] = 999
    original = race_poll_summaries(base).iloc[0]
    changed = race_poll_summaries(altered).iloc[0]
    assert original["poll_margin_two_party_mean"] == pytest.approx(10 / 3)
    assert changed["poll_margin_two_party_mean"] == pytest.approx(original["poll_margin_two_party_mean"])
    assert original["poll_margin_two_party_weighted"] == pytest.approx((10 * 1000) / 1100)
    assert int(original["n_polls_with_sample_size"]) == 2
    assert int(original["n_polls"]) == 3


def test_race_error_is_applied_after_the_average():
    questions = _questions(
        [
            _question(question_id="a", dem_pct=60, rep_pct=40, margin_dem_minus_rep=20, sample_size=100),
            _question(question_id="b", dem_pct=50, rep_pct=50, margin_dem_minus_rep=0, end_date="2020-11-10"),
        ]
    )
    scoring = score_questions(questions, _georgia_candidates())
    assert list(scoring.included["question_id"]) == ["a"]
    summaries = race_poll_summaries(scoring.included)
    assert "result_margin_two_party" not in summaries.columns
    from polling_blind_spot.analysis.polling_error import attach_race_results

    races = attach_race_results(summaries, scoring.included)
    row = races.iloc[0]
    assert row["error_of_unweighted_mean"] == pytest.approx(
        row["poll_margin_two_party_mean"] - row["result_margin_two_party"]
    )
    assert int(row["n_polls"]) == 1


def test_variance_decomposition_uses_races_as_the_grouping():
    questions = _questions(
        [
            _question(question_id="g1", dem_pct=60, rep_pct=40),
            _question(question_id="g2", dem_pct=40, rep_pct=60, end_date="2020-10-28"),
        ]
    )
    included = score_questions(questions, _georgia_candidates()).included
    parts = variance_decomposition(included)
    assert parts["n_polls"] == 2
    assert parts["n_races"] == 1
    assert parts["within_race_df"] == 1
    assert parts["within_race_variance"] is not None
    assert parts["between_race_variance"] is None


def test_cycle_summary_counts_match_the_scored_polls():
    scoring = score_questions(_questions([_question(), _question(question_id="q2", end_date="2020-10-01")]), _georgia_candidates())
    summary = summarize_by_cycle(scoring.included, race_poll_summaries(scoring.included))
    assert int(summary.loc[summary["cycle"] == "2020", "n_polls"].iloc[0]) == 2


def test_figures_are_written_for_a_scored_contest(tmp_path: Path):
    scoring = score_questions(_questions([_question()]), _georgia_candidates())
    from polling_blind_spot.analysis.polling_error import attach_race_results

    races = attach_race_results(race_poll_summaries(scoring.included), scoring.included)
    pollsters = pd.DataFrame(
        [
            {
                "pollster": "Example Poll",
                "pollster_key": "example poll",
                "n_polls": 25,
                "mean_signed_error": 1.5,
            }
        ]
    )
    written = write_figures(scoring.included, races, pollsters, tmp_path)
    assert "signed_error_distribution.png" in written
    assert "race_poll_average_vs_result.png" in written
    for name in written:
        assert (tmp_path / name).stat().st_size > 1000


def test_analysis_refuses_to_write_into_the_raw_directory(tmp_path: Path):
    with pytest.raises(AnalysisError):
        run_historical_polling_error(tmp_path, tmp_path)


def test_cli_reports_a_missing_raw_file(tmp_path: Path):
    import subprocess
    import sys

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "analyze_polling_error.py"),
            "--raw-dir",
            str(tmp_path / "raw"),
            "--output-dir",
            str(tmp_path / "out"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1
    assert "does not exist" in completed.stderr


@pytest.mark.skipif(
    not (FTE_PATH.is_file() and MEDSL_PATH.is_file()),
    reason="Historical poll and MEDSL files have not been downloaded",
)
def test_real_historical_files_score_without_leaking_later_results(tmp_path: Path):
    before = {path.name: _sha256(path) for path in (FTE_PATH, MEDSL_PATH)}
    report = run_historical_polling_error(RAW, tmp_path)
    after = {path.name: _sha256(path) for path in (FTE_PATH, MEDSL_PATH)}
    assert after == before
    assert report["n_included_polls"] + report["n_excluded_questions"] == report["n_questions"]
    assert report["n_included_polls"] > 2000
    assert report["n_races"] > 100

    included = pd.read_csv(tmp_path / "poll_errors.csv")
    exclusions = pd.read_csv(tmp_path / "exclusions.csv")
    assert (pd.to_datetime(included["end_date"]) <= pd.to_datetime(included["election_date"])).all()
    assert not (included["cycle"] == 2026).any()
    difference = included["poll_margin_two_party"] - included["result_margin_two_party"]
    assert (included["error_two_party"] - difference).abs().max() < 1e-3

    runoff = included[
        (included["state_po"] == "GA")
        & (included["stage"] == "runoff")
        & (included["election_year"] == 2021)
        & included["dem_candidate_poll"].str.contains("Ossoff", na=False)
    ]
    general = included[
        (included["state_po"] == "GA")
        & (included["stage"] == "general")
        & (included["election_year"] == 2020)
        & included["dem_candidate_poll"].str.contains("Ossoff", na=False)
    ]
    assert not runoff.empty and not general.empty
    assert int(runoff["result_dem_votes"].iloc[0]) != int(general["result_dem_votes"].iloc[0])
    candidates = build_result_candidates(pd.read_csv(MEDSL_PATH, dtype=str, keep_default_na=False, na_filter=False))
    official = candidates.loc[candidates["contest_id"] == "2021-GA-runoff-0"]
    ossoff = official.loc[official["candidate_name"].str.contains("OSSOFF")].iloc[0]
    assert int(runoff["result_dem_votes"].iloc[0]) == int(ossoff["votes"])

    ct = exclusions[(exclusions["state_po"] == "CT") & (exclusions["cycle"] == 2022)]
    assert not ct.empty
    assert set(ct["reason"]) <= {"no_result_contest", "not_two_party_margin", "hypothetical", "ranked_choice", "stage_not_comparable", "missing_election_date", "missing_end_date", "after_election"}
    assert "no_result_contest" in set(ct["reason"])
    assert included[(included["state_po"] == "CA") & (included["cycle"].isin([2022, 2024]))].empty
    special = included["special"].astype(str).str.lower()
    nebraska = included[(included["state_po"] == "NE") & (included["cycle"] == 2024) & special.isin(["true", "1"])]
    assert not nebraska.empty
    assert (tmp_path / "figures" / "signed_error_distribution.png").stat().st_size > 1000
    assert "error_two_party = poll_margin_two_party - result_margin_two_party" in report["error_definition"]


def _questions(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _question(**overrides) -> dict:
    row = {
        "question_id": "q1",
        "poll_id": "p1",
        "pollster": "Example Poll",
        "pollster_key": "example poll",
        "cycle": 2020,
        "state_name": "Georgia",
        "state_po": "GA",
        "stage": "general",
        "hypothetical": False,
        "ranked_choice": False,
        "margin_status": "two_party",
        "dem_candidate": "Jon Ossoff",
        "rep_candidate": "David Perdue",
        "dem_party": "DEM",
        "rep_party": "REP",
        "dem_pct": 48.0,
        "rep_pct": 46.0,
        "margin_dem_minus_rep": 2.0,
        "election_date": "2020-11-03",
        "start_date": "2020-10-20",
        "end_date": "2020-10-22",
        "sample_size": 800,
        "population": "lv",
        "methodology": "live phone",
        "internal": False,
        "partisan": None,
        "seat_class": "Class II",
    }
    row.update(overrides)
    return row


def _average_row(*, margin: float, sample: int | None, result: float) -> dict:
    return {
        "contest_id": "2020-GA-general-0",
        "cycle": 2020,
        "election_year": 2020,
        "state_name": "Georgia",
        "state_po": "GA",
        "stage": "general",
        "special": False,
        "poll_margin_two_party": margin,
        "sample_size": sample,
        "dem_candidate_result": "JON OSSOFF",
        "rep_candidate_result": "DAVID A. PERDUE",
        "result_margin_two_party": result,
        "error_two_party": margin - result,
    }


def _georgia_candidates() -> pd.DataFrame:
    return pd.concat(
        [
            build_result_candidates(
                _returns(
                    [
                        _line("JON OSSOFF", "DEMOCRAT", "100"),
                        _line("DAVID A. PERDUE", "REPUBLICAN", "80"),
                    ]
                )
            ),
            build_result_candidates(
                _returns(
                    [
                        _line("JON OSSOFF", "DEMOCRAT", "60", year="2021", stage="runoff"),
                        _line("DAVID A. PERDUE", "REPUBLICAN", "55", year="2021", stage="runoff"),
                    ]
                )
            ),
        ],
        ignore_index=True,
    )


def _fusion_candidates() -> pd.DataFrame:
    return build_result_candidates(
        _returns(
            [
                _line("KIRSTEN E. GILLIBRAND", "DEMOCRAT", "100", state="NEW YORK", state_po="NY"),
                _line(
                    "KIRSTEN E. GILLIBRAND",
                    "OTHER",
                    "20",
                    state="NEW YORK",
                    state_po="NY",
                    party_detailed="WORKING FAMILIES",
                ),
                _line("CHELE CHIAVACCI FARLEY", "REPUBLICAN", "50", state="NEW YORK", state_po="NY"),
                _line(
                    "CHELE CHIAVACCI FARLEY",
                    "OTHER",
                    "10",
                    state="NEW YORK",
                    state_po="NY",
                    party_detailed="CONSERVATIVE",
                ),
            ]
        )
    )


def _returns(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=MEDSL_COLUMNS)


def _line(
    candidate: str,
    party: str,
    votes: str,
    *,
    year: str = "2020",
    state: str = "GEORGIA",
    state_po: str = "GA",
    stage: str = "gen",
    special: str = "False",
    writein: str = "False",
    party_detailed: str | None = None,
) -> dict:
    row = {column: "" for column in MEDSL_COLUMNS}
    row.update(
        {
            "year": year,
            "state": state,
            "state_po": state_po,
            "office": "US SENATE",
            "district": "statewide",
            "stage": stage,
            "special": special,
            "candidate": candidate,
            "party_detailed": party if party_detailed is None else party_detailed,
            "writein": writein,
            "mode": "total",
            "candidatevotes": votes,
            "totalvotes": "1000",
            "unofficial": "False",
            "version": "test",
            "party_simplified": party,
        }
    )
    return row


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
