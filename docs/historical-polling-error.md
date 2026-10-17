# Historical Senate polling error

`python3 scripts/analyze_polling_error.py` compares FiveThirtyEight Senate polls from the 2018–2024 cycles with MIT Election Data and Science Lab statewide returns. It writes tables and figures to `outputs/historical_polling_error/`. Raw files and the cleaned poll tables are not modified.

2026 polls are not scored. That election has not been held, and a result margin is not filled in for it.

The run that produced the committed tables used the Internet Archive FiveThirtyEight snapshot and Harvard Dataverse file id 13887039 (MEDSL version values `20210114`, `20230920`, `20241212`, and `11/20/25` on the 2018–2024 rows). Re-running the script against those same files reproduces the tables.

## The margin being compared

Both sides are the two-candidate margin, in percentage points:

`(Democratic share − Republican share) / (Democratic share + Republican share) × 100`

For a poll, the shares are the published Democratic and Republican percentages. Undecided and other responses are left out of the denominator. This is not `margin_dem_minus_rep` from the cleaning step. That column is still stored. It is the unrescaled gap, so undecided respondents keep the two percentages from summing to 100.

For the result, the shares are the two matched candidates' vote totals. Other candidates and blank ballots are outside the denominator. Fusion and other ballot lines that use the identical published name are added together. `totalvotes` is the official contest total from the file. It is not rebuilt by summing lines. An all-ballot gap, `(Democratic votes − Republican votes) / totalvotes`, is stored as `result_margin_all_votes` and is not the primary error.

The signed error is:

`error_two_party = poll_margin_two_party − result_margin_two_party`

Positive means the poll's two-candidate margin was more Democratic than the official two-candidate margin. Absolute error is the absolute value of that difference.

A contest enters the race table only after its polls have been averaged. The unweighted mean, the median, and a sample-size-weighted mean use poll margins only. Polls with no numeric sample size are omitted from the weighted mean and are not given a filled-in size. The result margin is subtracted after those averages exist.

## Which polls are scored

A FiveThirtyEight question is scored only when all of the following hold:

- It has exactly one Democratic-side share (`DEM` or `DFL`) and one Republican share.
- It is not hypothetical and not a ranked-choice reallocation.
- The stage is `general` or `runoff`. Jungle primaries stay out. A runoff poll is joined to the runoff return, not to the November general.
- The state, the election date, and the fieldwork end date are present. A missing election date is not looked up.
- The end date is on or before the election date. In this file every scored poll ends at least one day before the election.
- If a start date is present, it is also on or before election day.
- The Democratic name matches one Democratic candidate and the Republican name matches one Republican candidate in exactly one contest for that state, stage, and election year.

Vote totals are not used to pick a candidate or a contest. If two official ballots on the same day carry the same two names, as in the California 2022 and 2024 special and full-term elections, the question is excluded and both result margins are written to `ambiguous_duplicate_ballots.csv`. If two candidates in one contest collapse to the same name, the question is excluded rather than awarded to the person with more votes.

`party_simplified` is the party used for that match. When it says `OTHER` and `party_detailed` is exactly `DEMOCRATIC` or `DEMOCRAT`, the detailed label is used. That is how the 2022 Illinois and Maryland Democratic nominees are coded in this MEDSL file. `INDEPENDENT REPUBLICAN PARTY` is not treated as the Republican nominee.

Names match after accents, initials, titles, suffixes, and double-quoted nicknames are removed. A comma puts the surname first. A surname-first string with no comma is also tried in given-name order, which is how Oregon prints `WYDEN RON`. Given names may differ by a middle name or by a standard nickname (`Thom` and `Thomas`, `Doug` and `Douglas`). Last names must match exactly. `O'CONNER` does not match `O'Connor`.

Internal and partisan polls stay in the primary set. Their flags are kept, and `summary_overall.csv` repeats the poll-level statistics without them.

## What this run found

These figures describe the scored polls only. They are not a 2026 forecast, and they do not give a poll equal to one independent election.

| Set | N | Mean signed error | Median | SD | MAE | RMSE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Polls | 3,212 | +3.65 | +3.64 | 6.73 | 5.97 | 7.66 |
| Races, error of the unweighted mean | 119 | +3.74 | +3.95 | 5.58 | 5.30 | 6.70 |

Across 2018–2024, the comparable polls were on average a bit under 4 points more Democratic than the two-candidate result. The race-level mean is similar, so the poll-level mean is not just an artifact of a few heavily polled contests.

By election cycle, the poll-level means are +2.26 in 2018 (789 polls, 31 races), +5.32 in 2020 (846 polls, 30 races), +2.10 in 2022 (662 polls, 28 races), and +4.42 in 2024 (915 polls, 30 races). January 2021 Georgia runoffs stay in the 2020 cycle because that is the cycle on the poll. They are joined to the 2021 runoff totals, not the November 2020 totals.

Polls ending 1–7 days before the election (525 polls) have a mean signed error of +2.04 and an MAE of 4.59. Polls ending 31–90 days out (961) and 91–180 days out (550) have means of +4.74 and +4.88. Dropping flagged internal polls, or internal and partisan polls, leaves the mean at +3.67 (3,052 polls) and +3.77 (2,560 polls).

The within-race variance of poll errors is 31.2 (3,093 degrees of freedom, 104 races with at least two polls). The variance of the 119 race-mean errors is 31.2. Polls of the same contest disagree with each other about as much as the contest averages disagree with the results. That split is descriptive. It is not a fitted hierarchical model.

State means are poll-level and uneven. Vermont's mean is −16.1 points from 3 polls; South Dakota's is +13.8 from 5. Those are not precise state effects. Forty-seven states have at least one scored poll. The state figure prints the poll count on each row.

Among pollsters with at least 25 scored polls, Center Street PAC's mean is +10.9 (43 polls) and Trafalgar Group's is −2.1 (89 polls). The full pollster table is not limited to that display threshold.

## Rows left out of the 3,926 historical questions

| Reason | Questions |
| --- | ---: |
| Hypothetical | 452 |
| No two-candidate Democratic–Republican margin | 187 |
| Same two names on two ballots (California 2022 and 2024) | 27 |
| Candidate names or parties did not match one contest | 20 |
| No official contest on that state, stage, and election date | 18 |
| Ranked-choice reallocation | 7 |
| Stage is not general or runoff | 2 |
| Election date missing | 1 |

The 18 missing contests are the Mississippi 2018 runoff (8 questions; MEDSL has the November special but not the November 27 runoff) and Connecticut 2022 (10 questions; that state is absent from the 2022 returns). Louisiana's jungle-primary questions are the two stage exclusions.

The 20 unmatched questions are three contests:

- Massachusetts 2020. MEDSL prints the Republican as `KEVIN J. O'CONNER`. FiveThirtyEight prints Kevin J. O'Connor.
- New Hampshire 2020. The poll says Bryant Messner. The return says `CORKY MESSNER`.
- Wyoming 2020. Both candidates have `party_simplified=OTHER` and a blank `party_detailed`, so the file does not identify a Democratic and a Republican nominee.

Eight contests, covering 239 scored polls, have `unofficial=True` on a matched candidate row. The Georgia runoffs are in that set. The votes are still the published totals, and `result_unofficial` marks them.

## What the error is not

The result is not an input to which polls are averaged, and it is not written back onto the cleaned poll file. Post-election fieldwork is dropped before a result margin is attached. Nothing here imputes a 2026 result or borrows a future election's error.

The two-candidate rescaling does not say how undecided respondents or third-party voters eventually voted. That difference is part of the error. Ranked-choice reallocations are not compared with first-round totals. California's simultaneous ballots are not averaged into one synthetic result. Polls are not weighted by FiveThirtyEight's pollster grade. A simple mean treats every poll as one observation even when one firm fields many waves, which is why the race table exists beside the poll table.
