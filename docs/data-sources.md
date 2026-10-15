# Data sources

Raw files are written by `python3 scripts/download_data.py` to `data/raw/` and are gitignored. The script checks each file's schema before it treats the download as successful. Re-running it reuses files that still validate. `--force` downloads them again.

Retrieved for development on 2026-10-15. Wikipedia pages are living documents, so a later run stores newer revision IDs. The FiveThirtyEight file is pinned to one Internet Archive snapshot. The MIT file is whatever Harvard Dataverse marks as the latest released version at download time.

## FiveThirtyEight historical Senate polls

| | |
| --- | --- |
| File | `data/raw/fivethirtyeight_senate_polls_historical.csv` |
| Live URL | https://projects.fivethirtyeight.com/polls-page/data/senate_polls_historical.csv |
| Snapshot used | https://web.archive.org/web/20250306125405id_/https://projects.fivethirtyeight.com/polls-page/data/senate_polls_historical.csv |
| Snapshot time | 2025-03-06 12:54:05 UTC |
| Documentation | https://github.com/fivethirtyeight/data/blob/master/polls/README.md |

The live host now returns the ABC News politics HTML page, so the downloader falls back to the archive URL above. That snapshot is the file checked in development: 9,292 candidate-level rows, 52 columns, cycles 2018, 2020, 2022, and 2024.

FiveThirtyEight linked this CSV from the `fivethirtyeight/data` polls README. That repository says that, unless otherwise noted, its datasets are under the [Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/). The polls README does not state a different license. This CSV is not stored in the GitHub repository itself; it was the public poll-tracker export.

Coverage and limitations:

- One row per candidate (or response) within a poll question, not one row per poll.
- `office_type` is `U.S. Senate` on every row. Stages are `general`, `jungle primary`, and `runoff`.
- Dates are `M/D/YY` strings as published (`start_date`, `end_date`, `election_date`).
- The snapshot includes 49 states. Hawaii has no rows in this file.
- It stops at the 2024 cycle. It is not a source for 2026 polls. FiveThirtyEight stopped publishing after ABC shut the site down in 2025, and the live export URL no longer serves the CSV.
- Pollster grades, sample sizes, and population codes are FiveThirtyEight's coding of the original polls.

Expected columns: `poll_id`, `pollster_id`, `pollster`, `sponsor_ids`, `sponsors`, `display_name`, `pollster_rating_id`, `pollster_rating_name`, `numeric_grade`, `pollscore`, `methodology`, `transparency_score`, `state`, `start_date`, `end_date`, `sponsor_candidate_id`, `sponsor_candidate`, `sponsor_candidate_party`, `endorsed_candidate_id`, `endorsed_candidate_name`, `endorsed_candidate_party`, `question_id`, `sample_size`, `population`, `subpopulation`, `population_full`, `tracking`, `created_at`, `notes`, `url`, `url_article`, `url_topline`, `url_crosstab`, `source`, `internal`, `partisan`, `race_id`, `cycle`, `office_type`, `seat_number`, `seat_name`, `election_date`, `stage`, `nationwide_batch`, `ranked_choice_reallocated`, `ranked_choice_round`, `hypothetical`, `party`, `answer`, `candidate_id`, `candidate_name`, `pct`.

## MIT Election Data and Science Lab Senate returns

| | |
| --- | --- |
| File | `data/raw/medsl_us_senate_statewide_returns_1976_2024.csv` |
| Codebook | `data/raw/medsl_us_senate_returns_codebook.md` |
| Dataset | https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/PEJ5QU |
| API | https://dataverse.harvard.edu/api/datasets/:persistentId/?persistentId=doi:10.7910/DVN/PEJ5QU |
| DOI | [10.7910/DVN/PEJ5QU](https://doi.org/10.7910/DVN/PEJ5QU) |

The downloader asks the Dataverse API for the latest released version and downloads the file whose name contains `1976-2024-senate-state`, plus a codebook file when one is listed. On 2026-10-15 that was version 8.0, released 2026-05-11, data file id 13887039. The API reported the dataset license as **CC0 1.0** (`http://creativecommons.org/publicdomain/zero/1.0/`).

The checked file has 3,945 candidate-level rows, statewide U.S. Senate returns for all 50 states, from 1976 through 2024. `office` is `US SENATE` on every row.

Coverage and limitations:

- These are election results, not polls. They are the historical outcomes later milestones can join to polls. They do not contain 2026 results, because that election has not been held.
- The House Clerk's *Statistics of the Congressional Election* is the original source through the years covered by the MEDSL codebook. Later years also use state election sites. See the downloaded codebook.
- The codebook shipped with the dataset is still titled for 1976–2018 even though the data file runs through 2024. Prefer the data file's `year` values over the codebook title.
- `stage` and `mode` are not cased consistently (`gen` and `GEN`, `total` and `TOTAL`). `party_simplified` is blank on a handful of rows. The ingester does not rewrite those fields.
- Hundreds of rows are write-ins with an empty `candidate` string (`writein=True`, `party_simplified=OTHER`). Those vote totals are real. The ingester does not invent a candidate name for them.
- A candidate can have more than one party row when a state counts fusion or multiple lines separately. `special` is `True` or `False`.

Expected columns: `year`, `state`, `state_po`, `state_fips`, `state_cen`, `state_ic`, `office`, `district`, `stage`, `special`, `candidate`, `party_detailed`, `writein`, `mode`, `candidatevotes`, `totalvotes`, `unofficial`, `version`, `party_simplified`.

## 2026 U.S. Senate polls (English Wikipedia)

| | |
| --- | --- |
| Extract | `data/raw/wikipedia_2026_us_senate_polls.csv` |
| Revision manifest | `data/raw/wikipedia_2026_us_senate_manifest.json` |
| Saved HTML | `data/raw/wikipedia_2026_pages/{page_id}.html` |
| Page list | MediaWiki API `list=allpages` on https://en.wikipedia.org/w/api.php |
| Page HTML | `https://en.wikipedia.org/api/rest_v1/page/html/{Title}` |
| License | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) |
| Terms | https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use |

There is no current FiveThirtyEight CSV for the 2026 cycle. English Wikipedia's state election articles are the public compilation used here. Each article is fetched as rendered HTML for one `content-revision-id`, saved unchanged, and then parsed. The manifest records the title, page id, revision id, REST URL, and SHA-256 of the HTML and of the extract. Reuse requires attribution and sharing alike.

Which pages are included:

- Canonical titles matching `2026 United States Senate election in {State}` and `2026 United States Senate special election in {State}`.
- Redirects are followed once. `2026 United States Senate elections in Alabama` is only a redirect to the Alabama article, so Alabama is included once. `2026 United States Senate election in Florida` and `... in Ohio` redirect to the special-election articles, so those races are stored under the special-election titles and are not duplicated.

Which page is excluded:

- `2026 United States Senate elections`, the national overview. It is race ratings and national summaries, not the state polling tables.

The extract is one row per response cell (a candidate, "Other", "Undecided", or an aggregation margin), not one row per poll. Individual polls and aggregator rows are both kept. `table_kind` is `poll` or `aggregation`. Later analysis should filter on `table_kind` before treating a row as a poll.

Parsing rules that affect interpretation:

- Only `wikitable` tables under a `Polling` heading are read. Results tables, infoboxes, and fundraising tables are ignored.
- `sup` footnotes are dropped, so pollster names do not include citation numbers. The reference URL itself is not followed; `poll_source_url` is the first non-footnote link in the pollster cell, which is often the pollster's Wikipedia article rather than the poll memo.
- A `—` (or similar dash) is Wikipedia's published "not available" mark. It is kept as text. Blank cells are left blank and are not imputed.
- `rowspan` copies the pollster, dates, sample size, and margin of error onto the following rows and sets `metadata_inherited=true`. Those continuation rows are a second line of the same poll table. Wikipedia often does not label whether that line is a different population or a with-leaners question.
- A `colspan` on a data cell, used by the Average row to cover the date columns, does not copy "Average" into the date fields. Those date fields stay empty.
- `table_group` stores a spanning label above a block of rows when the article provides one, including the title of a collapsed "Hypothetical polling" block.
- Response text is not converted to numbers in this step.

Expected columns: `retrieved_at`, `page_id`, `page_title`, `revision_id`, `canonical_url`, `state_name`, `election_kind`, `section_anchor`, `section_path`, `table_index`, `table_kind`, `table_group`, `row_index`, `metadata_inherited`, `poll_source`, `poll_source_url`, `dates_administered`, `dates_updated`, `sample_size`, `margin_of_error`, `response_column_index`, `response_label`, `response_value`.

Coverage and limitations:

- This is a secondary compilation by Wikipedia editors, not a pollster's microdata and not a complete census of every 2026 Senate poll.
- Tables differ by state. Some races have many matchups, including hypothetical candidates; the candidate names are whatever the article's column headers say.
- Aggregator rows (270toWin, RealClearPolitics, and similar averages printed in the articles) are not polls. They remain in the file so the download is complete, and they are labeled.
- Quality checks require a minimum number of states and individual-poll cells so a failed parse does not look like a successful download. Those floors are not the number of polls that exist.
- The national generic-ballot table on the overview page is not in this file.
- On the 2026-10-15 retrieval, 35 canonical articles were saved. Thirty of them contained individual poll cells (6,099 response cells) plus aggregator cells (the extract has 6,794 response cells in total). Delaware, New Jersey, Oregon, West Virginia, and Wyoming had no polling table in the saved revision. That is a gap in the articles, not a dropped file.
- Some published cells are not plain percentages. Ranked-choice tables include round numbers and `BA`. Alabama uses `—N/a` for a candidate who was not included. Alaska prints codes such as `5% U` and `4% NR`. Sample-size cells sometimes read `— (LV)`, which means the article gave a population but not a numeric sample size. Those strings are copied as published.

## What this step does not do

No polling margins are calculated here, missing sample sizes are not filled, and election results are not joined to polls. Those are later steps. The raw MIT file and the raw FiveThirtyEight file are stored separately from the Wikipedia extract.
