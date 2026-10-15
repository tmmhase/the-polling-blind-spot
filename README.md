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
python3 -m pytest
```

Source URLs, licenses, coverage, and limitations are in [docs/data-sources.md](docs/data-sources.md).
