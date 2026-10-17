# Polling preprocessing

`python3 scripts/preprocess_polls.py` reads the raw FiveThirtyEight and Wikipedia polling files and writes cleaned tables to `data/processed/`. It does not edit `data/raw/`. The MIT election returns are not part of this step; joining them to polls is a later analysis.

Processed files are gitignored, same as the raw downloads. The command is deterministic given those inputs.

| Output | Contents |
| --- | --- |
| `fte_senate_poll_responses.csv` | One row per historical candidate share |
| `fte_senate_poll_questions.csv` | One row per historical poll question, with margins |
| `wikipedia_2026_poll_responses.csv` | One row per 2026 individual-poll response cell |
| `wikipedia_2026_poll_questions.csv` | One row per 2026 poll question, with margins |
| `wikipedia_2026_poll_quarantine.csv` | Poll rows whose source cell is not a pollster |
| `wikipedia_2026_aggregation_responses.csv` | Average and tracker rows, kept out of the poll tables |
| `preprocess_report.json` | Row counts, missingness, and input file hashes |

## What is standardized

State names become the Census-style name (`North Carolina`) plus the postal abbreviation. An unrecognized place keeps its published text and has no postal code.

FiveThirtyEight dates are `M/D/YY`. Two-digit years `00`–`49` map to 2000–2049. A blank election date stays blank.

Wikipedia fieldwork strings such as `May 5–8, 2025`, `September 19 – October 1, 2025`, and `December 18, 2024 – January 15, 2025` become ISO start and end dates. `August 2025` is stored as month precision with both endpoints empty. `Mid–April 2025` and `Late June 2025` are approximate, also with empty endpoints. Aggregator rows sometimes say `through October 10, 2026`; that cutoff is stored as the end date only. A day is never filled in from a month or a phrase.

Pollster strings lose extra whitespace. A trailing parenthetical party code is moved to `pollster_affiliation` (`Public Policy Polling (D)` → name `Public Policy Polling`, affiliation `DEM`). `co/efficient` keeps the slash that belongs to the name. `(Ohio)` is not a party code and stays in the name. Names are not fuzzy-matched across firms.

Candidate headers such as `Mike Rogers (R)` become the name `Mike Rogers` and party `REP`. A header with no party code does not get one. `Generic Democrat` and `Generic Republican` keep those names and the party the words state. `Undecided`, `Other`, `Someone Else`, and `Other / Undecided` are not candidates.

Sample sizes: `1,200 (LV)` is 1200 likely voters. `— (LV)` and `TBA (LV)` have a population and no sample size. `>1,000 (LV)` is censored, so the size stays empty rather than becoming 1000. A bare percentage in the sample-size column is left unparsed.

Population codes are `lv`, `rv`, `v`, and `a`.

## Missing values

Empty cells stay empty. Nothing is mean-filled, forward-filled, or replaced with zero. A published zero percent remains zero. A dash, `—N/a`, `<1%`, `5% U`, `5% NR`, `BA`, or a ranked-choice round number does not become a vote share. Margin of error is parsed only when the cell contains `±`.

Wikipedia rowspan copies were already flagged `metadata_inherited` during ingestion. This step keeps those copied dates and sample sizes and keeps the flag. It does not copy values across rows itself.

The 2026 `cycle` value is 2026 because that is the election cycle of the source pages. Fieldwork dates still carry the year the poll was in the field, including 2024 and 2025. No election date is filled in for 2026, and FiveThirtyEight's blank election dates are not looked up.

## Margins

`margin_dem_minus_rep` = Democratic percentage − Republican percentage, in percentage points. Positive means the Democrat is ahead.

It is calculated only when the question has exactly one Democratic-side share and exactly one Republican share. Democratic-side parties are `DEM` and `DFL`. The DFL label is the Minnesota Democratic-Farmer-Labor label already on the row, not a party assigned to an unlabeled candidate.

The subtraction uses the published percentages. Undecided and other shares are not removed, and the two party shares are not rescaled to 100. A question with two Democrats, two Republicans, or a missing major-party share has an empty margin and a `margin_status` that says why.

`top_two_margin` is separate. It is the gap between the two highest candidate or generic-ballot percentages, and it is never negative. When those percentages tie, `top_two_tie` is true and the names are ordered alphabetically only so the row is stable. This gap covers races without party labels, including independent-versus-Republican contests. It is not copied into `margin_dem_minus_rep`.

A prose margin such as `El-Sayed +3.5%` is stored as `published_margin_points`. It is not used as the calculated margin.

`two_party_general` is true only when the question is a non-hypothetical general-election question, is not a ranked-choice table, and has a two-party margin. Internal and partisan polls remain in that set; `internal`, `partisan`, and `pollster_affiliation` are available for a later filter. Jungle primaries, runoffs, primaries, and hypothetical matchups stay in the files and are not marked `two_party_general`.

## Rows that are kept apart

Aggregator rows (`Average`, 270toWin, RealClearPolitics, and the other tracker rows) are written only to the aggregation file.

A poll row is quarantined when its poll-source cell has no pollster name, for example `2,070 (RV)` or `6%`. The whole question is quarantined. The pipeline does not shift the columns back into place, because that would invent a pollster and a date. On the 2026-10-16 download those shifted cells were a Florida hypothetical row and a South Carolina primary row.

## What this step does not do

It does not join election results, estimate polling error, score pollsters, or impute 2026 outcomes. The historical join is a separate command, documented in [historical-polling-error.md](historical-polling-error.md). FiveThirtyEight's pollster grades stay in the raw file. Party labels that Wikipedia omitted stay missing even when the candidate's party is widely known. Louisiana's `Primary election` heading stays `primary`; it is not relabeled as a jungle primary. Senate class and `seat_number` are copied as published and are not treated as a special-election flag.
