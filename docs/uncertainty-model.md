# Polling uncertainty model

`python3 scripts/run_uncertainty.py` fits a hierarchical model to the signed two-candidate errors from `outputs/historical_polling_error/poll_errors.csv` and writes `outputs/uncertainty/`. It does not modify the raw downloads, the cleaned poll tables, or the historical error tables.

2026 polls are not given a result. This step estimates how wrong a Senate poll average has been, and how that error is shared. It does not impute a 2026 vote margin.

The run documented here used seed `20261018`, 2,000 burn-in iterations, 2,000 retained draws, and a thin of 2. Re-running the script on the same scored file reproduces the tables.

## What is being predicted

The signed error is the Day 3 quantity, in percentage points:

`error_two_party = poll_margin_two_party − result_margin_two_party`

Positive means the poll was more Democratic than the official two-candidate margin. Both margins are `(Democratic share − Republican share) / (Democratic share + Republican share) × 100`.

The predictive draws are draws of that error for a new contest. They are not simulated election results and not new poll observations. A roster used for prediction contains only timing bands, simple-random-sample variances, and pollster ids.

Two averages are scored:

- **Unweighted.** Each modeled poll counts once. This is the primary estimand.
- **Pollster-equal.** Each pollster's polls are averaged first, then those firm-level means are averaged. A firm that fields most of the wave no longer dominates the average.

## Sampling error and historical error

The sampling variance is not estimated from the election result. For a poll with published Democratic percentage `d`, Republican percentage `r`, and sample size `n`, it is the multinomial delta-method variance of the two-party margin under simple random sampling. Undecided and other responses stay in the complement. They are not allocated to a candidate. A missing sample size, a non-positive sample size, or shares that sum to more than 100 returns no variance. Those questions are dropped and listed in `question_exclusions.csv`. Nothing is filled in.

On this file that drops 11 of 3,212 scored questions: 10 with no sample size, and one 2018 Arizona question whose published Democratic and Republican percentages sum to 101. The questions that remain have a median sample size of 788 and, after polls are collapsed, a median sampling variance of 14.46 points squared. That is a simple-random-sample standard error of about 3.8 points for a single poll.

Questions that share a `poll_id` and a contest are one sample. Their errors are averaged, and their sampling variances are averaged. The variance is not divided by the number of questions. This run collapses 301 polls that had more than one scored question, leaving 2,794 polls in 119 contests.

An inflation factor `φ` multiplies every sampling variance. The posterior median is 1.12 (5th–95th percentile 1.05 to 1.19). Repeated polls from the same firm in the same race disagree by about the simple-random-sample amount, plus a small margin. `φ` is one average factor. It is not a design effect for live-phone versus online samples, and it is not a substitute for a missing sample size.

## Shared error

The mean structure, with late polls as the baseline, is:

`error = μ + β_mid × mid + β_early × early + cycle effect + race effect + pollster-within-race effect + sampling noise`

- The **race effect** is shared by every poll in a contest. More polls do not shrink it. The posterior median of its standard deviation is 4.48 points (3.90 to 5.14).
- The **pollster-within-race effect** is shared by polls from the same firm in that contest. Another wave from that firm shrinks sampling noise and leaves this term in place. A different firm draws a new copy. The posterior median standard deviation is 3.91 points (3.68 to 4.13). There are 1,444 such groups.
- The **cycle effect** is shared by every contest in an election year. Four cycles identify it weakly. The posterior median standard deviation is 2.09 points, with a 5th–95th interval of 0.89 to 5.60.

`μ` is the expected error of a late poll, after the random effects' mean of zero. Its posterior median is +2.39 points (0.21 to 4.82). The interval is wide because a permanent bias and a cycle shock are only partly separated when there are four cycles.

Mid-campaign polls, those ending 31 to 180 days before the election, are an additional +1.76 points more Democratic than late polls (1.45 to 2.10). Polls ending more than 180 days out have a shift of about zero (−0.49 to +0.48). The bands are fixed from the within-race timing pattern in the scored file. They are not a smooth of days before the election.

Effective sample sizes for the retained draws are about 1,200 for `μ`, 620 for the race standard deviation, 510 for the pollster standard deviation, 300 for the cycle standard deviation, and 860 for `φ`.

## Priors and computation

| Parameter | Prior |
| --- | --- |
| `μ` | Normal(0, 20²) |
| `β_mid`, `β_early` | Normal(0, 5²), independent |
| Race, pollster-within-race, and cycle standard deviations | Independent half-Cauchy with scale 5 |
| `φ` | Inverse-gamma, shape 2, scale 1, prior mean 1 |

The half-Cauchy scale of 5 points is a weakly informative scale for a polling miss, not a fitted variance. The sampler is Gibbs. The mean and the cycle effects are drawn together. Each half-Cauchy standard deviation uses the inverse-gamma scale mixture `τ² | ρ ~ InvGamma(1/2, 1/ρ)` and `ρ | τ² ~ InvGamma(1, 1/τ² + 1/scale²)`. Random effects are normal.

Race and pollster standard deviations barely move when the half-Cauchy scale is changed from 2.5 to 10. The cycle standard deviation does move. Its posterior median is 1.79, 2.09, and 2.33 at scales 2.5, 5, and 10, and its 95th percentile runs from 4.51 to 6.96. `φ` stays at 1.12. The sensitivity table is `prior_sensitivity.csv`.

## Monte Carlo distributions

The stylized rosters below are not polls. Every poll in them is late, and every poll uses the historical median sampling variance of 14.46. The draws come from the posterior predictive distribution of the unweighted average's signed error.

| Roster | Predictive SD | 2.5th percentile | Median | 97.5th percentile |
| --- | ---: | ---: | ---: | ---: |
| One late poll | 8.19 | −13.1 | +2.4 | +18.7 |
| Ten late polls, one pollster | 7.30 | −11.9 | +2.2 | +15.3 |
| Ten late polls, ten pollsters | 5.77 | −8.8 | +2.7 | +14.3 |

For one late poll, the predictive variance splits about 32% race, 25% sampling, 24% pollster-within-race, 15% cycle, and 4% uncertainty in the mean. Ten polls from one firm cut the sampling share to about 3% and leave the pollster share near 31%. The standard deviation only falls from 8.2 to 7.3. Ten polls from ten firms cut the pollster share to about 4%. The race term is then 57% of the variance, and the standard deviation is still 5.8 points. The 95% interval for that diverse late average runs from about −9 to +14.

That floor is the historical finding this model is built to carry: averaging more Senate polls removes sampling noise, and it does not remove the miss that the whole contest shares.

## Backtest

Two protocols refit the model. Neither one puts the scored contest's error in the likelihood.

- **Leave-one-cycle-out.** The fit that scores 2020 uses 2018, 2022, and 2024 only, and likewise for the other cycles. The 2018 score trains on later cycles, so it is not a real-time test.
- **Forward chain.** The fit uses only earlier cycles in this file. There is no score for 2018. The 2020 score trains on 2018 alone.

The roster for a held-out contest is built from that contest's timing, sampling variances, and pollster ids. The signed error is attached only after the predictive draws exist. Result vote totals are not read.

Coverage is the share of contests whose actual average error falls in the central predictive interval. The probability integral transform (PIT) is the share of predictive draws below the actual error. A calibrated location sits near one half.

Leave-one-cycle-out, unweighted mean, 119 contests:

| Held-out cycle | Contests | 50% coverage | 80% coverage | 95% coverage | Mean 95% width | Mean actual error | Mean predicted median | Mean PIT |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All | 119 | 0.58 | 0.85 | 0.97 | 27.1 | +3.65 | +3.21 | 0.52 |
| 2018 | 31 | 0.52 | 0.94 | 0.97 | 27.0 | +1.86 | +3.79 | 0.41 |
| 2020 | 30 | 0.43 | 0.73 | 0.97 | 24.4 | +6.43 | +2.20 | 0.70 |
| 2022 | 28 | 0.57 | 0.75 | 0.96 | 27.5 | +2.72 | +3.51 | 0.46 |
| 2024 | 30 | 0.80 | 0.97 | 1.00 | 29.7 | +3.59 | +3.34 | 0.52 |

Across all four cycles, the 95% intervals cover 97% of contests and the average PIT is 0.52. The 80% intervals are a little conservative in total (85%) and too narrow for 2020 (73%). The model trained without 2020 puts the center at +2.2; the 2020 contests actually averaged +6.4. The wide interval still covers most of them. Holding out 2024 does the opposite: 2020 remains in the training sample, the cycle scale stays large, and the 50% interval covers 80% of 2024 contests.

The forward chain makes the same point with a real-time constraint. Trained only on 2018, the 2020 intervals have a mean 95% width of 59 points and a predicted median of +1.3 against an actual mean of +6.4. Coverage of the 95% interval is 100% because the interval is huge, not because the location traveled. By 2024, with 2018–2022 in the training sample, the predicted median is +3.5 and the actual mean is +3.6. The mean 95% width is still 31 points.

Pollster-equal averages give nearly the same coverage. In this file the two averages are close because most contests already have several firms. A roster dominated by one firm would separate them: the pollster-equal interval divides the firm effect by the number of firms, and the unweighted interval does not.

## What this model does not say

The normal random effects do not reproduce the heavier tails of the poll-level errors. There is no Student-t degrees of freedom. The backtest is the check on the intervals, and 2020 shows that a new national miss can sit in the far tail of a model trained on the other cycles.

Pollster effects are redrawn for every race. A firm that ran several points Republican in past races does not pull the center of a new race's interval. That persistent piece is smaller than the race-specific disagreement, and it is left inside the width rather than used as a house-effect adjustment. FiveThirtyEight grades are not weights. Internal and partisan polls stay in the training sample.

The sampling formula ignores clustering and weighting inside the poll. `φ` absorbs the average gap. It does not say that a particular methodology has a larger design effect.

The unweighted mean counts a collapsed poll once. It is not the question-level mean in the Day 3 race table when a poll has several questions, and it is not a precision-weighted average. Weighting by the inverse of the sampling variance would favor a large-sample tracking poll and understate the firm effect this model is measuring.

Leave-one-cycle-out for an earlier cycle uses later results. Only the forward chain is a real-time score, and it cannot score 2018 from this file. The full-sample posterior is the distribution available for a later cycle such as 2026. It is not itself a backtest. No 2026 roster was attached in this run. The predictive function will score one from timing, sample size, and pollster id without a result; this repository's cleaned 2026 tables are gitignored and were not an input.

The Gibbs quantiles are Monte Carlo estimates. The effective sample sizes above are the ones to use when reading a percentile as exact.
