"""Source cards for the dashboard.

The facts below are the public locations, licenses, and coverage limits
documented in ``docs/data-sources.md``. They are not performance statistics.
"""

from __future__ import annotations

SOURCES: list[dict[str, object]] = [
    {
        "id": "fivethirtyeight",
        "title": "FiveThirtyEight historical U.S. Senate polls",
        "role": "Polls scored against 2018–2024 results",
        "file": "data/raw/fivethirtyeight_senate_polls_historical.csv",
        "url": "https://projects.fivethirtyeight.com/polls-page/data/senate_polls_historical.csv",
        "snapshot_url": (
            "https://web.archive.org/web/20250306125405id_/"
            "https://projects.fivethirtyeight.com/polls-page/data/senate_polls_historical.csv"
        ),
        "documentation_url": "https://github.com/fivethirtyeight/data/blob/master/polls/README.md",
        "license": "Creative Commons Attribution 4.0 International",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "coverage": (
            "Internet Archive snapshot from 2025-03-06 of the Senate historical export: "
            "cycles 2018, 2020, 2022, and 2024. The development check found 9,292 "
            "candidate-level rows and no Hawaii rows."
        ),
        "limitations": [
            "The live export URL now returns an ABC News HTML page, so the pipeline uses the archive snapshot.",
            "The file ends with the 2024 cycle. It is not a 2026 polling source.",
            "Grades, sample sizes, methodology strings, and population codes are FiveThirtyEight's coding of the original polls.",
            "Rows are candidate responses within a question, not one row per poll.",
        ],
    },
    {
        "id": "medsl",
        "title": "MIT Election Data and Science Lab statewide Senate returns",
        "role": "Official results joined after poll margins are computed",
        "file": "data/raw/medsl_us_senate_statewide_returns_1976_2024.csv",
        "url": "https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/PEJ5QU",
        "snapshot_url": None,
        "documentation_url": "https://doi.org/10.7910/DVN/PEJ5QU",
        "license": "CC0 1.0",
        "license_url": "http://creativecommons.org/publicdomain/zero/1.0/",
        "coverage": (
            "Harvard Dataverse doi:10.7910/DVN/PEJ5QU. The 2026-10-15 download resolved "
            "version 8.0, file id 13887039: statewide U.S. Senate returns, 1976–2024, 3,945 candidate rows."
        ),
        "limitations": [
            "These are election results, not polls. The 2026 election has not been held, so the file has no 2026 result.",
            "The codebook title still says 1976–2018. The data file's year field runs through 2024.",
            "Unnamed write-in rows stay unnamed. Fusion lines with the same published name are summed in the error analysis.",
            "Some returns are flagged unofficial, including both Georgia runoffs.",
        ],
    },
    {
        "id": "wikipedia-2026",
        "title": "2026 U.S. Senate polling tables on English Wikipedia",
        "role": "Ingestion source for the unscored 2026 cycle",
        "file": "data/raw/wikipedia_2026_us_senate_polls.csv",
        "url": "https://en.wikipedia.org/w/api.php",
        "snapshot_url": None,
        "documentation_url": "https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use",
        "license": "Creative Commons Attribution-ShareAlike 4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "coverage": (
            "State and special-election articles titled '2026 United States Senate election in {State}'. "
            "The 2026-10-15 retrieval saved 35 pages. Thirty contained individual poll cells. "
            "Delaware, New Jersey, Oregon, West Virginia, and Wyoming had no polling table in that revision."
        ),
        "limitations": [
            "Wikipedia is a secondary compilation, not a pollster's microdata and not a complete census of 2026 polls.",
            "The national overview page is excluded. Aggregator rows are labeled and are not polls.",
            "Cleaned 2026 tables are gitignored and are not an input to this dashboard.",
            "No 2026 contest is given a result or a model score on this page.",
        ],
    },
]

POPULATION_LABELS = {
    "lv": "Likely voters",
    "rv": "Registered voters",
    "v": "Voters",
    "a": "Adults",
    "(missing)": "Missing",
}

EXCLUSION_LABELS = {
    "hypothetical": "Hypothetical matchup",
    "not_two_party_margin": "No comparable two-party margin",
    "ambiguous_duplicate_ballot": "Ambiguous duplicate ballot",
    "unmatched_candidate": "Candidate names did not match one official contest",
    "no_result_contest": "No official contest in the results file",
    "ranked_choice": "Ranked-choice reallocation",
    "stage_not_comparable": "Stage is not a general election or runoff",
    "missing_election_date": "Missing election date",
}

PARAMETER_LABELS = {
    "mu": "Late-poll mean",
    "beta_mid": "Mid-campaign shift",
    "beta_early": "Early-campaign shift",
    "sd_race": "Race standard deviation",
    "sd_house": "Pollster-within-race standard deviation",
    "sd_cycle": "Cycle standard deviation",
    "phi": "Sampling-variance inflation",
}

PARAMETER_UNITS = {
    "mu": "points",
    "beta_mid": "points",
    "beta_early": "points",
    "sd_race": "points",
    "sd_house": "points",
    "sd_cycle": "points",
    "phi": "multiplier",
}

DESIGN_LABELS = {
    "one_late_poll": "One late poll",
    "ten_late_polls_one_pollster": "Ten late polls, one pollster",
    "ten_late_polls_ten_pollsters": "Ten late polls, ten pollsters",
}

COMPONENT_LABELS = {
    "sampling": "Sampling",
    "house": "Pollster within race",
    "race": "Race",
    "cycle": "Cycle",
    "mean_parameter": "Uncertainty in the mean",
}

TIMING_ORDER = (
    "1-7 days",
    "8-30 days",
    "31-90 days",
    "91-180 days",
    "181 or more days",
)

SENATE_STATES = (
    ("AL", "Alabama"),
    ("AK", "Alaska"),
    ("AZ", "Arizona"),
    ("AR", "Arkansas"),
    ("CA", "California"),
    ("CO", "Colorado"),
    ("CT", "Connecticut"),
    ("DE", "Delaware"),
    ("FL", "Florida"),
    ("GA", "Georgia"),
    ("HI", "Hawaii"),
    ("ID", "Idaho"),
    ("IL", "Illinois"),
    ("IN", "Indiana"),
    ("IA", "Iowa"),
    ("KS", "Kansas"),
    ("KY", "Kentucky"),
    ("LA", "Louisiana"),
    ("ME", "Maine"),
    ("MD", "Maryland"),
    ("MA", "Massachusetts"),
    ("MI", "Michigan"),
    ("MN", "Minnesota"),
    ("MS", "Mississippi"),
    ("MO", "Missouri"),
    ("MT", "Montana"),
    ("NE", "Nebraska"),
    ("NV", "Nevada"),
    ("NH", "New Hampshire"),
    ("NJ", "New Jersey"),
    ("NM", "New Mexico"),
    ("NY", "New York"),
    ("NC", "North Carolina"),
    ("ND", "North Dakota"),
    ("OH", "Ohio"),
    ("OK", "Oklahoma"),
    ("OR", "Oregon"),
    ("PA", "Pennsylvania"),
    ("RI", "Rhode Island"),
    ("SC", "South Carolina"),
    ("SD", "South Dakota"),
    ("TN", "Tennessee"),
    ("TX", "Texas"),
    ("UT", "Utah"),
    ("VT", "Vermont"),
    ("VA", "Virginia"),
    ("WA", "Washington"),
    ("WV", "West Virginia"),
    ("WI", "Wisconsin"),
    ("WY", "Wyoming"),
)
