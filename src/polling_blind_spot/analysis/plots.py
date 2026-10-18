"""Figures for the historical Senate polling-error tables.

Positive values mean the poll's two-candidate margin was more Democratic than
the official two-candidate margin. These charts describe completed elections.
They are not 2026 forecasts.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

DISPLAY_MIN_POLLS = 25
_TOO_DEMOCRATIC = "#2c7fb8"
_TOO_REPUBLICAN = "#d95f0e"
_SLATE = "#334155"
_GRID = "#e2e8f0"


def write_figures(
    included: pd.DataFrame,
    races: pd.DataFrame,
    pollsters: pd.DataFrame,
    figure_dir: Path,
) -> list[str]:
    """Write the summary figures. Returns the file names that were created."""
    figure_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    if not included.empty:
        _distribution(included, races, figure_dir / "signed_error_distribution.png")
        _by_cycle(included, figure_dir / "signed_error_by_cycle.png")
        _by_state(included, figure_dir / "signed_error_by_state.png")
        _by_timing(included, figure_dir / "signed_error_by_timing.png")
        written.extend(
            [
                "signed_error_distribution.png",
                "signed_error_by_cycle.png",
                "signed_error_by_state.png",
                "signed_error_by_timing.png",
            ]
        )
    if not pollsters.empty and (pollsters["n_polls"] >= DISPLAY_MIN_POLLS).any():
        _by_pollster(pollsters, figure_dir / "signed_error_by_pollster.png")
        written.append("signed_error_by_pollster.png")
    if not races.empty:
        _calibration(races, figure_dir / "race_poll_average_vs_result.png")
        written.append("race_poll_average_vs_result.png")
    return written


def _distribution(included: pd.DataFrame, races: pd.DataFrame, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.6))
    _histogram(
        axes[0],
        included["error_two_party"],
        "Poll-level signed error",
        "Each comparable pre-election poll",
    )
    _histogram(
        axes[1],
        races["error_of_unweighted_mean"],
        "Race-level error of the poll average",
        "Unweighted mean within each contest",
    )
    fig.suptitle("Historical Senate polling error, two-candidate margin", fontsize=14)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _histogram(ax: plt.Axes, values: pd.Series, title: str, subtitle: str) -> None:
    series = pd.to_numeric(values, errors="coerce").dropna()
    ax.hist(series, bins=40, color=_SLATE, edgecolor="white", linewidth=0.4)
    mean = float(series.mean())
    ax.axvline(0, color="#64748b", linewidth=1)
    ax.axvline(mean, color="#b45309", linewidth=1.4, label=f"Mean {mean:.1f}")
    ax.set_title(title)
    ax.set_xlabel("Poll minus result, percentage points\nPositive: poll more Democratic than the result")
    ax.set_ylabel("Count")
    ax.legend(frameon=False)
    ax.text(0.0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color="#475569")
    ax.grid(axis="y", color=_GRID)
    ax.set_axisbelow(True)


def _by_cycle(included: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    cycles = sorted(included["cycle"].dropna().unique())
    groups = [included.loc[included["cycle"] == cycle, "error_two_party"].astype(float) for cycle in cycles]
    counts = [int((included["cycle"] == cycle).sum()) for cycle in cycles]
    labels = [f"{int(cycle)}\n(n={count})" for cycle, count in zip(cycles, counts, strict=True)]
    drawn = ax.boxplot(
        groups,
        tick_labels=labels,
        patch_artist=True,
        flierprops={"marker": "o", "markersize": 3, "alpha": 0.45},
    )
    for patch in drawn["boxes"]:
        patch.set_facecolor("#dbeafe")
        patch.set_edgecolor(_SLATE)
    ax.axhline(0, color="#64748b", linewidth=1)
    ax.set_title("Signed polling error by election cycle")
    ax.set_ylabel("Poll minus result (percentage points)")
    ax.set_xlabel("Election cycle")
    ax.grid(axis="y", color=_GRID)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _by_state(included: pd.DataFrame, path: Path) -> None:
    grouped = (
        included.groupby(["state_po", "state_name"], dropna=False)["error_two_party"]
        .agg(["mean", "count"])
        .reset_index()
        .sort_values("mean", kind="mergesort")
    )
    fig_height = max(6.0, 0.28 * len(grouped) + 1.4)
    fig, ax = plt.subplots(figsize=(8.4, fig_height))
    colors = [_TOO_DEMOCRATIC if value >= 0 else _TOO_REPUBLICAN for value in grouped["mean"]]
    labels = [f"{row.state_po}  n={int(row.count)}" for row in grouped.itertuples(index=False)]
    ax.barh(labels, grouped["mean"], color=colors)
    ax.invert_yaxis()
    ax.axvline(0, color=_SLATE, linewidth=1)
    ax.set_xlabel("Mean signed error (percentage points)")
    ax.set_title("Mean poll-level signed error by state")
    ax.grid(axis="x", color=_GRID)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _by_pollster(pollsters: pd.DataFrame, path: Path) -> None:
    frame = pollsters.loc[pollsters["n_polls"] >= DISPLAY_MIN_POLLS].sort_values("mean_signed_error", kind="mergesort")
    fig_height = max(5.0, 0.32 * len(frame) + 1.4)
    fig, ax = plt.subplots(figsize=(8.6, fig_height))
    colors = [_TOO_DEMOCRATIC if value >= 0 else _TOO_REPUBLICAN for value in frame["mean_signed_error"]]
    labels = [f"{row.pollster}  n={int(row.n_polls)}" for row in frame.itertuples(index=False)]
    ax.barh(labels, frame["mean_signed_error"], color=colors)
    ax.invert_yaxis()
    ax.axvline(0, color=_SLATE, linewidth=1)
    ax.set_xlabel("Mean signed error (percentage points)")
    ax.set_title(f"Pollsters with at least {DISPLAY_MIN_POLLS} comparable polls")
    ax.grid(axis="x", color=_GRID)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _by_timing(included: pd.DataFrame, path: Path) -> None:
    from polling_blind_spot.analysis.polling_error import summarize_by_timing

    summary = summarize_by_timing(included)
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    if summary.empty:
        ax.set_axis_off()
    else:
        colors = [_TOO_DEMOCRATIC if value >= 0 else _TOO_REPUBLICAN for value in summary["mean_signed_error"]]
        labels = [f"{row.timing}\n(n={int(row.n)})" for row in summary.itertuples(index=False)]
        ax.bar(labels, summary["mean_signed_error"], color=colors)
        ax.axhline(0, color=_SLATE, linewidth=1)
        ax.set_ylabel("Mean signed error (percentage points)")
        ax.set_title("Signed error by days before the election")
        ax.grid(axis="y", color=_GRID)
        ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _calibration(races: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 6.2))
    x = races["poll_margin_two_party_mean"].astype(float)
    y = races["result_margin_two_party"].astype(float)
    ax.scatter(x, y, s=28, color=_SLATE, alpha=0.8, linewidths=0)
    low = min(float(x.min()), float(y.min()))
    high = max(float(x.max()), float(y.max()))
    pad = (high - low) * 0.05 + 1
    ax.plot([low - pad, high + pad], [low - pad, high + pad], color="#b45309", linewidth=1, label="Poll average = result")
    ax.set_xlim(low - pad, high + pad)
    ax.set_ylim(low - pad, high + pad)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Pre-election unweighted mean poll margin")
    ax.set_ylabel("Official two-candidate result margin")
    ax.set_title("Post-election check: poll average vs result")
    ax.legend(frameon=False, loc="upper left")
    ax.grid(color=_GRID)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
