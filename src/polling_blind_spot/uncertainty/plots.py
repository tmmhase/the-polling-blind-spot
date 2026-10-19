"""Figures for the polling-uncertainty model and its backtest.

These charts describe the fitted error distribution and whether historical
intervals covered the signed error. They are not maps of 2026 vote shares.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

_SLATE = "#334155"
_BLUE = "#2c7fb8"
_ORANGE = "#d95f0e"
_GREEN = "#2a9d8f"
_GRID = "#e2e8f0"
_CYCLE_COLORS = {2018: "#4c78a8", 2020: "#f58518", 2022: "#54a24b", 2024: "#e45756"}


def write_figures(
    posterior: pd.DataFrame,
    components: pd.DataFrame,
    simulations: pd.DataFrame,
    races: pd.DataFrame,
    coverage: pd.DataFrame,
    figure_dir: Path,
) -> list[str]:
    """Write the uncertainty figures and return their file names."""
    figure_dir.mkdir(parents=True, exist_ok=True)
    written = [
        _components(components, figure_dir / "variance_components.png"),
        _simulations(simulations, figure_dir / "predictive_error_distributions.png"),
        _backtest_scatter(races, figure_dir / "backtest_predicted_vs_actual.png"),
        _coverage(coverage, figure_dir / "backtest_coverage.png"),
    ]
    _posterior(posterior, figure_dir / "posterior_standard_deviations.png")
    written.append("posterior_standard_deviations.png")
    return written


def _posterior(posterior: pd.DataFrame, path: Path) -> None:
    columns = ["sd_race", "sd_house", "sd_cycle"]
    labels = ["Race", "Pollster within race", "Cycle"]
    fig, axes = plt.subplots(1, 3, figsize=(11.2, 3.8), sharey=True)
    for axis, column, label in zip(axes, columns, labels, strict=True):
        axis.hist(posterior[column], bins=30, color=_SLATE, edgecolor="white", linewidth=0.4)
        axis.axvline(posterior[column].median(), color=_ORANGE, linewidth=1.4)
        axis.set_title(label)
        axis.set_xlabel("Standard deviation (points)")
        axis.grid(axis="y", color=_GRID)
        axis.set_axisbelow(True)
    axes[0].set_ylabel("Posterior draws")
    fig.suptitle("Shared-error scales", fontsize=14)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _components(components: pd.DataFrame, path: Path) -> str:
    subset = components.loc[components["estimand"] == "unweighted"].copy()
    order = ["sampling", "house", "race", "cycle", "mean_parameter"]
    labels = {
        "sampling": "Sampling",
        "house": "Pollster within race",
        "race": "Race",
        "cycle": "Cycle",
        "mean_parameter": "Uncertainty in the mean",
    }
    designs = list(subset["design"].unique())
    fig, ax = plt.subplots(figsize=(10.4, 4.8))
    bottoms = {design: 0.0 for design in designs}
    colors = {
        "sampling": "#94a3b8",
        "house": _BLUE,
        "race": _ORANGE,
        "cycle": _GREEN,
        "mean_parameter": "#64748b",
    }
    x = list(range(len(designs)))
    for component in order:
        heights = []
        for design in designs:
            match = subset.loc[(subset["design"] == design) & (subset["component"] == component), "variance"]
            heights.append(float(match.iloc[0]) if len(match) else 0.0)
        ax.bar(
            x,
            heights,
            bottom=[bottoms[design] for design in designs],
            color=colors[component],
            width=0.72,
            label=labels[component],
        )
        for design, height in zip(designs, heights, strict=True):
            bottoms[design] += height
    ax.set_xticks(x, [_design_label(design) for design in designs])
    ax.set_ylabel("Predictive variance (points squared)")
    ax.set_title("Where the uncertainty of a late-poll average comes from")
    ax.legend(frameon=False, ncol=2)
    ax.grid(axis="y", color=_GRID)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return "variance_components.png"


def _simulations(simulations: pd.DataFrame, path: Path) -> str:
    designs = list(simulations["design"].unique())
    fig, axes = plt.subplots(1, len(designs), figsize=(11.4, 4.2), sharey=True)
    if len(designs) == 1:
        axes = [axes]
    for axis, design in zip(axes, designs, strict=True):
        values = simulations.loc[simulations["design"] == design, "error"]
        axis.hist(values, bins=40, color=_SLATE, edgecolor="white", linewidth=0.3)
        axis.axvline(0, color="#64748b", linewidth=1)
        axis.axvline(values.median(), color=_ORANGE, linewidth=1.4)
        axis.set_title(_design_label(design), fontsize=11)
        axis.set_xlabel("Signed error (points)")
        axis.grid(axis="y", color=_GRID)
        axis.set_axisbelow(True)
    axes[0].set_ylabel("Monte Carlo draws")
    fig.suptitle("Predictive distribution of the unweighted late-poll average", fontsize=14)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return "predictive_error_distributions.png"


def _backtest_scatter(races: pd.DataFrame, path: Path) -> str:
    subset = races.loc[
        (races["protocol"] == "leave_one_cycle_out") & (races["estimand"] == "unweighted")
    ].copy()
    fig, ax = plt.subplots(figsize=(7.2, 6.4))
    for cycle, group in subset.groupby("cycle"):
        color = _CYCLE_COLORS.get(int(cycle), _SLATE)
        ax.errorbar(
            group["pred_p50"],
            group["actual_error"],
            xerr=[group["pred_p50"] - group["pred_p025"], group["pred_p975"] - group["pred_p50"]],
            fmt="o",
            ms=4,
            color=color,
            ecolor=color,
            elinewidth=0.7,
            alpha=0.85,
            label=str(int(cycle)),
        )
    limit = float(
        max(
            subset["pred_p975"].max(),
            subset["actual_error"].max(),
            abs(subset["pred_p025"].min()),
            abs(subset["actual_error"].min()),
        )
    )
    limit = max(limit, 1) * 1.05
    ax.plot([-limit, limit], [-limit, limit], color="#64748b", linewidth=1)
    ax.axhline(0, color=_GRID, linewidth=1)
    ax.axvline(0, color=_GRID, linewidth=1)
    ax.set_xlim(-limit, limit)
    ax.set_ylim(-limit, limit)
    ax.set_xlabel("Predicted median error, fit without that cycle")
    ax.set_ylabel("Actual error of the unweighted poll average")
    ax.set_title("Leave-one-cycle-out backtest")
    ax.legend(title="Cycle", frameon=False)
    ax.set_aspect("equal", adjustable="box")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return "backtest_predicted_vs_actual.png"


def _coverage(coverage: pd.DataFrame, path: Path) -> str:
    subset = coverage.loc[
        (coverage["protocol"] == "leave_one_cycle_out")
        & (coverage["estimand"] == "unweighted")
        & (coverage["cycle"] != "all")
    ].copy()
    labels = subset["cycle"].astype(str).tolist()
    x = range(len(subset))
    width = 0.24
    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    ax.bar([i - width for i in x], subset["coverage_50"], width=width, color="#94a3b8", label="50% interval")
    ax.bar(list(x), subset["coverage_80"], width=width, color=_BLUE, label="80% interval")
    ax.bar([i + width for i in x], subset["coverage_95"], width=width, color=_ORANGE, label="95% interval")
    ax.axhline(0.50, color="#94a3b8", linewidth=0.8, linestyle="--")
    ax.axhline(0.80, color=_BLUE, linewidth=0.8, linestyle="--")
    ax.axhline(0.95, color=_ORANGE, linewidth=0.8, linestyle="--")
    ax.set_xticks(list(x), labels)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Share of contests covered")
    ax.set_xlabel("Held-out cycle")
    ax.set_title("Leave-one-cycle-out coverage of the unweighted mean")
    ax.legend(frameon=False, loc="lower right")
    ax.grid(axis="y", color=_GRID)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return "backtest_coverage.png"


def _design_label(design: str) -> str:
    labels = {
        "one_late_poll": "One late poll",
        "ten_late_polls_one_pollster": "Ten late polls,\none pollster",
        "ten_late_polls_ten_pollsters": "Ten late polls,\nten pollsters",
    }
    return labels.get(str(design), str(design))
