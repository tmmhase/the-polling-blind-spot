"""Unit tests for polling standardization and margins."""

import csv
import hashlib
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from polling_blind_spot.ingest.schemas import FTE_COLUMNS, WIKIPEDIA_COLUMNS
from polling_blind_spot.preprocess.errors import PreprocessError
from polling_blind_spot.preprocess.margins import build_questions
from polling_blind_spot.preprocess.pipeline import (
    clean_fte_responses,
    clean_wikipedia_responses,
    run_preprocessing,
)
from polling_blind_spot.preprocess.standardize import (
    classify_response_label,
    parse_field_dates,
    parse_fte_date,
    parse_published_margin,
    parse_wikipedia_sample,
    parse_wikipedia_share,
    pollster_is_implausible,
    standardize_pollster,
    standardize_state,
)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
FTE_PATH = RAW / "fivethirtyeight_senate_polls_historical.csv"
WIKI_PATH = RAW / "wikipedia_2026_us_senate_polls.csv"


def test_state_names_and_unknown_places():
    assert standardize_state("north carolina") == ("North Carolina", "NC")
    assert standardize_state("ME") == ("Maine", "ME")
    assert standardize_state("  Maine ") == ("Maine", "ME")
    assert standardize_state("Narnia") == ("Narnia", None)
    assert standardize_state("") == (None, None)


def test_fte_dates_use_the_2000s_and_keep_blanks_missing():
    assert parse_fte_date("11/5/24").isoformat() == "2024-11-05"
    assert parse_fte_date("1/5/21").isoformat() == "2021-01-05"
    assert parse_fte_date("11/6/18").isoformat() == "2018-11-06"
    assert parse_fte_date("") is None
    assert parse_fte_date("  ") is None


def test_wikipedia_dates_do_not_invent_days():
    ranged = parse_field_dates("May 5–8, 2025")
    assert (ranged.start.isoformat(), ranged.end.isoformat(), ranged.grain) == (
        "2025-05-05",
        "2025-05-08",
        "day",
    )
    cross_month = parse_field_dates("September 19 – October 1, 2025")
    assert (cross_month.start.isoformat(), cross_month.end.isoformat()) == (
        "2025-09-19",
        "2025-10-01",
    )
    unicode_minus = parse_field_dates("March 19−22, 2026")
    assert (unicode_minus.start.isoformat(), unicode_minus.end.isoformat()) == (
        "2026-03-19",
        "2026-03-22",
    )
    cross_year = parse_field_dates("December 18, 2024 – January 15, 2025")
    assert (cross_year.start.isoformat(), cross_year.end.isoformat(), cross_year.grain) == (
        "2024-12-18",
        "2025-01-15",
        "day",
    )
    month = parse_field_dates("August 2025")
    assert month.start is None and month.end is None and month.grain == "month"
    late = parse_field_dates("Late June 2025")
    mid = parse_field_dates("Mid–April 2025")
    assert late.grain == "approximate" and late.start is None and late.end is None
    assert mid.grain == "approximate" and mid.start is None
    as_of = parse_field_dates("through October 10, 2026")
    assert as_of.start is None and as_of.end.isoformat() == "2026-10-10" and as_of.grain == "as_of"
    shifted = parse_field_dates("46%")
    assert shifted.grain == "unparsed" and shifted.start is None and shifted.end is None
    assert parse_field_dates("").grain == "missing"


def test_sample_size_parser_preserves_missing_and_censored_values():
    assert parse_wikipedia_sample("1,200 (LV)") == (1200, "lv", "parsed")
    assert parse_wikipedia_sample("600") == (600, None, "parsed")
    missing = parse_wikipedia_sample("— (LV)")
    assert missing.sample_size is None and missing.population == "lv" and missing.status == "missing"
    assert parse_wikipedia_sample("– (V)").population == "v"
    tba = parse_wikipedia_sample("TBA (LV)")
    assert tba.sample_size is None and tba.population == "lv" and tba.status == "missing"
    censored = parse_wikipedia_sample(">1,000 (LV)")
    assert censored.sample_size is None and censored.population == "lv" and censored.status == "censored"
    unparsed = parse_wikipedia_sample("41%")
    assert unparsed.sample_size is None and unparsed.status == "unparsed"
    assert parse_wikipedia_sample("—") == (None, None, "missing")


def test_share_parser_does_not_turn_codes_or_zero_into_other_numbers():
    assert parse_wikipedia_share("48.4%").pct == 48.4
    assert parse_wikipedia_share("0%").pct == 0
    assert parse_wikipedia_share("—").status == "missing"
    assert parse_wikipedia_share("—N/a").pct is None
    censored = parse_wikipedia_share("<1%")
    assert censored.pct is None and censored.status == "censored"
    qualified = parse_wikipedia_share("5% U")
    assert qualified.pct is None and qualified.status == "qualified"
    assert parse_wikipedia_share("4% NR").status == "qualified"
    assert parse_wikipedia_share("1").status == "not_a_share"
    assert parse_wikipedia_share("BA").status == "not_a_share"
    assert parse_wikipedia_share("TBA").status == "not_a_share"


def test_candidate_labels_keep_printed_parties_only():
    assert classify_response_label("Mike Rogers (R)") == ("candidate", "Mike Rogers", "REP")
    assert classify_response_label("Ben Ray Luján") == ("candidate", "Ben Ray Luján", None)
    assert classify_response_label("John Cornyn").party is None
    generic = classify_response_label("Generic Democrat")
    assert generic.role == "generic" and generic.party == "DEM" and generic.candidate_name == "Generic Democrat"
    assert classify_response_label("Undecided").role == "undecided"
    assert classify_response_label("Other / Undecided").role == "residual_undecided"
    assert classify_response_label("Someone Else").role == "residual"
    assert classify_response_label("Margin").role == "published_margin"
    dfl = classify_response_label("Tina Smith (DFL)")
    assert dfl.candidate_name == "Tina Smith" and dfl.party == "DFL"


def test_pollster_names_drop_party_tags_and_keep_real_slashes():
    ppp = standardize_pollster("Public Policy Polling (D)")
    assert ppp.name == "Public Policy Polling" and ppp.affiliation == "DEM"
    coefficient = standardize_pollster("co/efficient (R)")
    assert coefficient.name == "co/efficient" and coefficient.affiliation == "REP"
    joint = standardize_pollster("Beacon Research (D)/ Shaw & Co. Research (R)")
    assert joint.name == "Beacon Research/Shaw & Co. Research"
    assert joint.affiliation == "DEM+REP"
    ohio = standardize_pollster("Miami University (Ohio)")
    assert ohio.name == "Miami University (Ohio)" and ohio.affiliation is None
    assert pollster_is_implausible("2,070 (RV)")
    assert pollster_is_implausible("6%")
    assert pollster_is_implausible("")
    assert not pollster_is_implausible("Emerson College")


def test_published_margin_text_is_not_a_vote_share():
    parsed = parse_published_margin("El-Sayed +3.5%")
    assert parsed.leader == "El-Sayed" and parsed.points == 3.5 and parsed.tie is False
    tie = parse_published_margin("Tie")
    assert tie.tie is True and tie.points == 0


def test_two_party_margin_is_the_unscaled_democratic_minus_republican_share():
    frame = pd.DataFrame(
        [
            _option("q", "Jane Doe", "DEM", 48),
            _option("q", "John Roe", "REP", 44),
            _option("q", None, None, 5, role="residual"),
            _option("q", None, None, 3, role="undecided"),
        ]
    )
    question = build_questions(frame).iloc[0]
    assert question["margin_dem_minus_rep"] == 4
    assert question["margin_status"] == "two_party"
    assert question["other_pct"] == 5
    assert question["undecided_pct"] == 3
    assert question["pct_sum"] == 100
    assert question["two_party_general"] == True


def test_zero_percent_is_kept_and_dashes_are_not_zeros():
    zero = build_questions(
        pd.DataFrame(
            [
                _option("q", "Jane Doe", "DEM", 0),
                _option("q", "John Roe", "REP", 40),
            ]
        )
    ).iloc[0]
    assert zero["dem_pct"] == 0
    assert zero["margin_dem_minus_rep"] == -40

    missing = build_questions(
        pd.DataFrame(
            [
                _option("q", "Jane Doe", "DEM", None),
                _option("q", "John Roe", "REP", 40),
            ]
        )
    ).iloc[0]
    assert missing["margin_dem_minus_rep"] is None
    assert missing["margin_status"] == "missing_democrat"


def test_multiple_democrats_and_unlabeled_candidates_do_not_receive_a_party_margin():
    multiple = build_questions(
        pd.DataFrame(
            [
                _option("q", "Andy Kim", "DEM", 39),
                _option("q", "Bob Menendez", "DEM", 3),
                _option("q", "Curtis Bashaw", "REP", 33),
            ]
        )
    ).iloc[0]
    assert multiple["margin_status"] == "multiple_major_party_candidates"
    assert multiple["margin_dem_minus_rep"] is None

    unlabeled = build_questions(
        pd.DataFrame(
            [
                _option("q", "John Cornyn", None, 32),
                _option("q", "Ken Paxton", None, 28),
            ]
        )
    ).iloc[0]
    assert unlabeled["margin_status"] == "no_major_party"
    assert unlabeled["margin_dem_minus_rep"] is None
    assert unlabeled["top_two_leader"] == "John Cornyn"
    assert unlabeled["top_two_margin"] == 4
    assert unlabeled["top_two_tie"] == False


def test_dfl_is_the_democratic_side_and_published_margins_stay_separate():
    frame = pd.DataFrame(
        [
            _option("q", "Tina Smith", "DFL", 46),
            _option("q", "Jason Lewis", "REP", 40),
            {
                **_option("q", None, None, None, role="published_margin"),
                "pct_raw": "Smith +9%",
            },
        ]
    )
    question = build_questions(frame).iloc[0]
    assert question["margin_dem_minus_rep"] == 6
    assert question["dem_party"] == "DFL"
    assert question["published_margin_points"] == 9
    assert question["published_margin_leader"] == "Smith"
    assert question["published_margin_points"] != question["margin_dem_minus_rep"]


def test_tied_top_two_is_zero_and_ordered_by_name():
    question = build_questions(
        pd.DataFrame(
            [
                _option("q", "Deb Fischer", "REP", 47),
                _option("q", "Dan Osborn", "IND", 47),
            ]
        )
    ).iloc[0]
    assert question["margin_status"] == "missing_democrat"
    assert question["top_two_tie"] == True
    assert question["top_two_margin"] == 0
    assert question["top_two_leader"] == "Dan Osborn"
    assert question["top_two_trailer"] == "Deb Fischer"


def test_hypothetical_and_ranked_choice_questions_are_not_flagged_comparable():
    hypothetical = build_questions(
        pd.DataFrame([_option("q", "Jane Doe", "DEM", 48), _option("q", "John Roe", "REP", 44)])
    ).iloc[0]
    hypothetical_frame = pd.DataFrame(
        [
            {**_option("q", "Jane Doe", "DEM", 48), "hypothetical": True},
            {**_option("q", "John Roe", "REP", 44), "hypothetical": True},
        ]
    )
    assert build_questions(hypothetical_frame).iloc[0]["two_party_general"] == False
    ranked = pd.DataFrame(
        [
            {**_option("q", "Jane Doe", "DEM", 48), "ranked_choice": True},
            {**_option("q", "John Roe", "REP", 44), "ranked_choice": True},
        ]
    )
    assert build_questions(ranked).iloc[0]["margin_dem_minus_rep"] == 4
    assert build_questions(ranked).iloc[0]["two_party_general"] == False
    assert hypothetical["two_party_general"] == True


def test_fte_cleaner_keeps_blank_sample_size_and_blank_election_date():
    rows = [
        _fte_row(
            question_id="10",
            candidate_id="1",
            party="DEM",
            candidate_name="Jon Tester",
            answer="Tester",
            pct="49",
            sample_size="",
            population="lv",
            election_date="",
            internal="",
            tracking="",
        ),
        _fte_row(
            question_id="10",
            candidate_id="2",
            party="REP",
            candidate_name="Tim Sheehy",
            answer="Sheehy",
            pct="45",
            sample_size="",
            population="lv",
            election_date="",
            internal="",
        ),
    ]
    cleaned = clean_fte_responses(pd.DataFrame(rows, columns=FTE_COLUMNS))
    assert len(cleaned) == 2
    assert cleaned["sample_size"].isna().all()
    assert cleaned.loc[0, "sample_size_status"] == "missing"
    assert cleaned.loc[0, "population"] == "lv"
    assert cleaned["election_date"].isna().all()
    assert cleaned["internal"].isna().all()
    assert cleaned.loc[0, "tracking"] is None or pd.isna(cleaned.loc[0, "tracking"])
    questions = build_questions(cleaned)
    assert questions.loc[0, "margin_dem_minus_rep"] == 4
    assert questions.loc[0, "state_po"] == "ME"
    assert questions.loc[0, "start_date"] == "2024-10-01"
    assert questions.loc[0, "stage"] == "general"


def test_wikipedia_cleaner_quarantines_shifted_rows_and_parses_a_real_poll():
    good = _wiki_row(
        row_index="0",
        poll_source="Quantus Insights (R)",
        dates_administered="October 5–6, 2026",
        sample_size="762 (LV)",
        margin_of_error="± 4.0%",
        response_label="Abdul El-Sayed (D)",
        response_value="48%",
        response_column_index="4",
        table_group="Hypothetical polling",
    )
    partner = _wiki_row(
        row_index="0",
        poll_source="Quantus Insights (R)",
        dates_administered="October 5–6, 2026",
        sample_size="762 (LV)",
        margin_of_error="± 4.0%",
        response_label="Mike Rogers (R)",
        response_value="47%",
        response_column_index="5",
        table_group="Hypothetical polling",
    )
    shifted = _wiki_row(
        row_index="1",
        poll_source="2,070 (RV)",
        dates_administered="46%",
        sample_size="41%",
        margin_of_error="3%",
        response_label="Ashley Moody (R)",
        response_value="10%",
        response_column_index="4",
    )
    aggregation = _wiki_row(
        row_index="2",
        table_kind="aggregation",
        poll_source="Average",
        dates_administered="",
        response_label="Margin",
        response_value="El-Sayed +3.5%",
        response_column_index="8",
    )
    raw = pd.DataFrame([good, partner, shifted, aggregation], columns=WIKIPEDIA_COLUMNS)
    polls, quarantine = clean_wikipedia_responses(raw, record_type="poll")
    aggregations, _ = clean_wikipedia_responses(raw, record_type="aggregation")
    assert list(polls["pollster"]) == ["Quantus Insights", "Quantus Insights"]
    assert list(polls["pollster_affiliation"]) == ["REP", "REP"]
    assert list(polls["candidate_name"]) == ["Abdul El-Sayed", "Mike Rogers"]
    assert list(polls["party"]) == ["DEM", "REP"]
    assert polls.loc[0, "sample_size"] == 762
    assert polls.loc[0, "population"] == "lv"
    assert polls.loc[0, "population_raw"] == "LV"
    assert polls.loc[0, "start_date"] == "2026-10-05"
    assert polls.loc[0, "end_date"] == "2026-10-06"
    assert polls.loc[0, "margin_of_error"] == 4.0
    assert bool(polls.loc[0, "hypothetical"]) is True
    assert polls.loc[0, "cycle"] == 2026
    assert polls["election_date"].isna().all()
    assert list(quarantine["pollster_raw"]) == ["2,070 (RV)"]
    assert quarantine.loc[0, "quarantine_reason"] == "poll_source_is_not_a_pollster"
    assert list(aggregations["record_type"]) == ["aggregation"]
    question = build_questions(polls).iloc[0]
    assert question["margin_dem_minus_rep"] == 1
    assert question["two_party_general"] == False


def test_pipeline_writes_processed_files_and_leaves_raw_bytes_unchanged(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    raw_dir.mkdir()
    fte_rows = [
        _fte_row(question_id="10", candidate_id="1", party="DEM", candidate_name="Jane Doe", pct="51"),
        _fte_row(question_id="10", candidate_id="2", party="REP", candidate_name="John Roe", pct="44"),
    ]
    wiki_rows = [
        _wiki_row(
            response_label="Jane Doe (D)",
            response_value="40%",
            response_column_index="4",
        ),
        _wiki_row(
            response_label="John Roe (R)",
            response_value="39%",
            response_column_index="5",
        ),
    ]
    _write_csv(raw_dir / "fivethirtyeight_senate_polls_historical.csv", FTE_COLUMNS, fte_rows)
    _write_csv(raw_dir / "wikipedia_2026_us_senate_polls.csv", WIKIPEDIA_COLUMNS, wiki_rows)
    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in raw_dir.iterdir()
    }
    report = run_preprocessing(raw_dir, processed_dir)
    after = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in raw_dir.iterdir()
    }
    assert before == after
    assert (processed_dir / "fte_senate_poll_questions.csv").is_file()
    assert (processed_dir / "wikipedia_2026_poll_questions.csv").is_file()
    assert (processed_dir / "preprocess_report.json").is_file()
    questions = pd.read_csv(processed_dir / "fte_senate_poll_questions.csv")
    assert questions.loc[0, "margin_dem_minus_rep"] == 7
    assert report["outputs"]["fte_questions"]["two_party_general"] == 1
    with pytest.raises(PreprocessError):
        run_preprocessing(raw_dir, raw_dir)


@pytest.mark.skipif(
    not (FTE_PATH.is_file() and WIKI_PATH.is_file()),
    reason="Raw polling files have not been downloaded",
)
def test_downloaded_polls_keep_the_margin_identity_and_do_not_impute(tmp_path: Path):
    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (FTE_PATH, WIKI_PATH)
    }
    report = run_preprocessing(RAW, tmp_path)
    after = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (FTE_PATH, WIKI_PATH)
    }
    assert before == after

    fte_responses = pd.read_csv(tmp_path / "fte_senate_poll_responses.csv")
    fte_questions = pd.read_csv(tmp_path / "fte_senate_poll_questions.csv")
    wiki_responses = pd.read_csv(tmp_path / "wikipedia_2026_poll_responses.csv")
    wiki_questions = pd.read_csv(tmp_path / "wikipedia_2026_poll_questions.csv")
    quarantine = pd.read_csv(tmp_path / "wikipedia_2026_poll_quarantine.csv")
    aggregations = pd.read_csv(tmp_path / "wikipedia_2026_aggregation_responses.csv")

    raw_fte = pd.read_csv(FTE_PATH, dtype=str, keep_default_na=False)
    raw_wiki = pd.read_csv(WIKI_PATH, dtype=str, keep_default_na=False)
    assert len(fte_responses) == len(raw_fte)
    assert set(wiki_responses["record_type"]) == {"poll"}
    assert set(aggregations["record_type"]) == {"aggregation"}
    assert "Hawaii" not in set(fte_responses["state_name"])
    assert fte_responses.loc[fte_responses["election_date"].isna(), "dates_raw"].str.len().ge(0).all()

    _assert_margin_identity(fte_questions)
    _assert_margin_identity(wiki_questions)
    _assert_missing_shares_stay_missing(wiki_responses)
    _assert_censored_samples_stay_missing(wiki_responses)

    month = wiki_responses.loc[wiki_responses["dates_raw"] == "August 2025"]
    if not month.empty:
        assert month["start_date"].isna().all()
        assert month["end_date"].isna().all()
        assert set(month["date_grain"]) == {"month"}

    raw_polls = raw_wiki.loc[raw_wiki["table_kind"] == "poll", "poll_source"]
    for bad_source in ("6%", "2,070 (RV)"):
        if bad_source in set(raw_polls):
            assert bad_source in set(quarantine["pollster_raw"].astype(str))
            assert bad_source not in set(wiki_responses["pollster_raw"].astype(str))

    assert report["outputs"]["fte_questions"]["rows"] == len(fte_questions)
    assert report["inputs"]["fte_historical"]["sha256"] == before[FTE_PATH.name]
    fte_flags = fte_questions["two_party_general"].astype(str).str.lower()
    assert (fte_flags == "true").sum() > 1000
    raw_blank_election = raw_fte["election_date"].str.strip().eq("")
    assert fte_responses.loc[raw_blank_election.to_numpy(), "election_date"].isna().all()


def test_preprocess_help_lists_the_output_directories():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "preprocess_polls.py"), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert "--raw-dir" in completed.stdout
    assert "--processed-dir" in completed.stdout


def _assert_margin_identity(questions: pd.DataFrame) -> None:
    two_party = questions.loc[questions["margin_status"] == "two_party"]
    assert not two_party.empty
    difference = two_party["dem_pct"] - two_party["rep_pct"]
    assert (two_party["margin_dem_minus_rep"] - difference).abs().max() < 1e-6


def _assert_missing_shares_stay_missing(responses: pd.DataFrame) -> None:
    raw_values = responses["pct_raw"].astype(str)
    missing = responses.loc[raw_values.isin(["—", "–", "-", "—N/a", "nan"])]
    assert missing["pct"].isna().all()
    qualified = responses.loc[raw_values.str.contains(r"% (?:U|NR)$", na=False)]
    if not qualified.empty:
        assert qualified["pct"].isna().all()


def _assert_censored_samples_stay_missing(responses: pd.DataFrame) -> None:
    censored = responses.loc[responses["sample_size_status"] == "censored"]
    if not censored.empty:
        assert censored["sample_size"].isna().all()
        assert censored["sample_size_raw"].astype(str).str.startswith(">").all()


def _option(question_id, name, party, pct, role="candidate"):
    return {
        "question_id": question_id,
        "response_role": role,
        "candidate_name": name,
        "party": party,
        "pct": pct,
        "pct_raw": None if pct is None else str(pct),
        "stage": "general",
        "hypothetical": False,
        "ranked_choice": False,
    }


def _fte_row(**overrides) -> dict[str, str]:
    row = {column: "" for column in FTE_COLUMNS}
    row.update(
        {
            "poll_id": "1",
            "pollster_id": "9",
            "pollster": "Example Polling",
            "display_name": "Example Polling",
            "question_id": "10",
            "state": "Maine",
            "start_date": "10/1/24",
            "end_date": "10/2/24",
            "sample_size": "500",
            "population": "lv",
            "population_full": "lv",
            "cycle": "2024",
            "office_type": "U.S. Senate",
            "seat_number": "0",
            "seat_name": "Class I",
            "election_date": "11/5/24",
            "stage": "general",
            "hypothetical": "false",
            "ranked_choice_reallocated": "false",
            "party": "DEM",
            "answer": "Doe",
            "candidate_id": "1",
            "candidate_name": "Jane Doe",
            "pct": "48",
        }
    )
    row.update(overrides)
    return row


def _wiki_row(**overrides) -> dict[str, str]:
    row = {column: "" for column in WIKIPEDIA_COLUMNS}
    row.update(
        {
            "retrieved_at": "2026-10-16T13:00:00Z",
            "page_id": "10",
            "page_title": "2026 United States Senate election in Michigan",
            "revision_id": "20",
            "canonical_url": "https://en.wikipedia.org/wiki/Example",
            "state_name": "Michigan",
            "election_kind": "regular",
            "section_anchor": "Polling",
            "section_path": "General election > Polling",
            "table_index": "0",
            "table_kind": "poll",
            "row_index": "0",
            "metadata_inherited": "false",
            "poll_source": "Example Polling",
            "dates_administered": "October 1–2, 2026",
            "sample_size": "500 (LV)",
            "margin_of_error": "± 4.4%",
            "response_column_index": "4",
            "response_label": "Jane Doe (D)",
            "response_value": "48%",
        }
    )
    row.update(overrides)
    return row


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
