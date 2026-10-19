# the-polling-blind-spot

A data science platform analyzing historical polling errors and uncertainty in the 2026 U.S. Senate elections.

## Raw data

`scripts/download_data.py` downloads three public inputs into `data/raw/` (gitignored) and checks their schemas:

- FiveThirtyEight historical U.S. Senate polls, from the Internet Archive snapshot of the official CSV after the live host stopped serving it.
- MIT Election Data and Science Lab statewide Senate returns, 1976–2024, from Harvard Dataverse `doi:10.7910/DVN/PEJ5QU`.
- 2026 U.S. Senate polling tables from English Wikipedia state and special-election articles, saved as revision-pinned HTML plus a long CSV extract.

```bash
python3 scripts/download_data.py
python3 scripts/download_data.py --source wikipedia-2026 --force
python3 scripts/preprocess_polls.py
python3 -m pytest
```

Source URLs, licenses, coverage, and limitations are in [docs/data-sources.md](docs/data-sources.md).

## Cleaned polling tables

`scripts/preprocess_polls.py` standardizes state names, dates, pollsters, candidate names, and sample sizes, and writes question-level margins to `data/processed/`. Raw files are left unchanged. Missing percentages and sample sizes stay missing. The margin definition and the rows that are quarantined or held out are in [docs/preprocessing.md](docs/preprocessing.md).

## Historical polling error

`scripts/analyze_polling_error.py` joins the cleaned FiveThirtyEight questions to MIT Senate returns for 2018–2024. It scores only polls whose fieldwork ended on or before election day, and it keeps result margins out of the pre-election averages. Definitions, inclusion rules, and the limits of the name match are in [docs/historical-polling-error.md](docs/historical-polling-error.md). Tables and figures are written to `outputs/historical_polling_error/`.

```bash
python3 scripts/analyze_polling_error.py
```

## Polling uncertainty

`scripts/run_uncertainty.py` fits a hierarchical model to those signed errors. Sampling variance comes from the published sample size. Separate random effects capture the part a race shares, the part a pollster repeats inside that race, and a cycle-level shift. Monte Carlo draws show how little the interval shrinks when more polls come from the same firm. Leave-one-cycle-out and forward-chain backtests score each cycle without that cycle's results. Assumptions, coverage, and limitations are in [docs/uncertainty-model.md](docs/uncertainty-model.md). Tables and figures are written to `outputs/uncertainty/`.

```bash
python3 scripts/run_uncertainty.py
```

## Dashboard

The Day 5 dashboard is a Next.js app in `frontend/` backed by a read-only FastAPI service. The API serves the committed tables in `outputs/historical_polling_error/` and `outputs/uncertainty/`. It does not download polls, and it does not score a 2026 contest.

```bash
python3 scripts/serve_api.py
cd frontend && npm install && npm run dev
```

Open http://localhost:3000. The Next.js server proxies `/api/*` to FastAPI on `127.0.0.1:8000`. `API_PROXY_TARGET` overrides that address.
