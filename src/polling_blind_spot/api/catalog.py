"""Load the committed analysis tables for the dashboard API.

Every count and statistic is read from ``outputs/``. Nothing in this module
invents a poll, a vote total, or a 2026 margin.
"""

from __future__ import annotations

import csv
import json
import os
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from polling_blind_spot.api.sources import (
    COMPONENT_LABELS,
    DESIGN_LABELS,
    EXCLUSION_LABELS,
    PARAMETER_LABELS,
    PARAMETER_UNITS,
    POPULATION_LABELS,
    SENATE_STATES,
    SOURCES,
    TIMING_ORDER,
)

HISTORICAL_BIN_START = -24.0
HISTORICAL_BIN_STOP = 24.0
HISTORICAL_BIN_STEP = 2.0
SIMULATION_BIN_START = -24.0
SIMULATION_BIN_STOP = 24.0
SIMULATION_BIN_STEP = 2.0

SIMULATION_NOTE = (
    "Quantiles and histogram counts summarize posterior predictive draws of signed "
    "polling error. Each roster is stylized: every poll is late, and every poll uses "
    "the historical median simple-random-sample variance. A draw is a possible polling "
    "error, not an observed poll and not an election result."
)

MAP_NOTE = (
    "mean_signed_error is the mean of question-level signed two-party errors in "
    "summary_by_state.csv. Positive means the scored questions were more Democratic "
    "than the official two-candidate margin. n_questions is that file's n_polls column: "
    "one row is one scored question, so a poll with several questions is counted more than once."
)

COUNT_NOTE = (
    "n_questions counts scored question rows. summary_by_state.csv and "
    "summary_by_pollster.csv store that count in a column named n_polls."
)


class CatalogError(FileNotFoundError):
    """A committed output the dashboard needs is missing."""


def repo_root() -> Path:
    override = os.environ.get("POLLING_BLIND_SPOT_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3]


def histogram(values: list[float], start: float, stop: float, step: float) -> dict[str, Any]:
    """Equal-width bins on ``[start, stop]``, with the right edge in the last bin."""
    n_bins = int(round((stop - start) / step))
    if n_bins <= 0:
        raise ValueError("histogram step must be positive and smaller than the span")
    counts = [0] * n_bins
    underflow = 0
    overflow = 0
    for value in values:
        if value < start:
            underflow += 1
            continue
        if value > stop:
            overflow += 1
            continue
        index = int((value - start) / step)
        if index >= n_bins:
            index = n_bins - 1
        counts[index] += 1
    return {
        "start": start,
        "stop": stop,
        "step": step,
        "edges": [round(start + index * step, 4) for index in range(n_bins + 1)],
        "counts": counts,
        "underflow": underflow,
        "overflow": overflow,
        "n": len(values),
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise CatalogError(f"Missing committed output: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise CatalogError(f"Missing committed output: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _num(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return round(float(value), 4)


def _int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(float(value))


def _bool(value: str | None) -> bool:
    return (value or "").strip().lower() == "true"


def _describe(values: list[float]) -> dict[str, float | int | None]:
    n = len(values)
    if n == 0:
        return {
            "n_questions": 0,
            "mean_signed_error": None,
            "median_signed_error": None,
            "mae": None,
        }
    ordered = sorted(values)
    if n % 2:
        median = ordered[n // 2]
    else:
        median = (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    mean = sum(values) / n
    mae = sum(abs(value) for value in values) / n
    return {
        "n_questions": n,
        "mean_signed_error": round(mean, 4),
        "median_signed_error": round(median, 4),
        "mae": round(mae, 4),
    }


def _error_record(row: dict[str, str]) -> dict[str, Any]:
    return {
        "n": _int(row["n"]) if "n" in row else _int(row.get("n_polls", "")),
        "mean_signed_error": _num(row["mean_signed_error"]),
        "median_signed_error": _num(row["median_signed_error"]),
        "std_signed_error": _num(row["std_signed_error"]),
        "mae": _num(row["mae"]),
        "rmse": _num(row["rmse"]),
        "p10": _num(row["p10"]),
        "p25": _num(row["p25"]),
        "p75": _num(row["p75"]),
        "p90": _num(row["p90"]),
    }


class Catalog:
    """In-memory view of the historical-error and uncertainty outputs."""

    def __init__(self, root: Path):
        self.root = root
        historical = root / "outputs" / "historical_polling_error"
        uncertainty = root / "outputs" / "uncertainty"
        self.questions = _read_csv(historical / "poll_errors.csv")
        self.state_rows = _read_csv(historical / "summary_by_state.csv")
        self.pollster_rows = _read_csv(historical / "summary_by_pollster.csv")
        self.cycle_rows = _read_csv(historical / "summary_by_cycle.csv")
        self.timing_rows = _read_csv(historical / "summary_by_timing.csv")
        self.population_rows = _read_csv(historical / "summary_by_population.csv")
        self.overall_rows = _read_csv(historical / "summary_overall.csv")
        self.race_rows = _read_csv(historical / "race_errors.csv")
        self.exclusion_rows = _read_csv(historical / "exclusions.csv")
        self.analysis = _read_json(historical / "analysis_report.json")
        self.model = _read_json(uncertainty / "model_report.json")
        self.posterior_rows = _read_csv(uncertainty / "posterior_summary.csv")
        self.simulation_rows = _read_csv(uncertainty / "simulation_quantiles.csv")
        self.simulation_draws = _read_csv(uncertainty / "simulation_draws.csv")
        self.variance_rows = _read_csv(uncertainty / "variance_decomposition.csv")
        self.backtest_rows = _read_csv(uncertainty / "backtest_coverage.csv")
        self.sensitivity_rows = _read_csv(uncertainty / "prior_sensitivity.csv")
        self._states = {code: name for code, name in SENATE_STATES}
        self._questions_by_state: dict[str, list[dict[str, str]]] = defaultdict(list)
        self._errors_by_method: dict[str, list[float]] = defaultdict(list)
        self._method_by_pollster: dict[str, Counter[str]] = defaultdict(Counter)
        for row in self.questions:
            self._questions_by_state[row["state_po"]].append(row)
            method = row["methodology"].strip() or "(missing)"
            group = "Mixed methods" if "/" in method else method
            self._errors_by_method[group].append(float(row["error_two_party"]))
            self._method_by_pollster[row["pollster_key"]][method] += 1

    def overview(self) -> dict[str, Any]:
        by_slice = {row["slice"]: row for row in self.overall_rows}
        posterior = {row["parameter"]: row for row in self.posterior_rows}
        preparation = self.model["preparation"]
        return {
            "scored_questions": len(self.questions),
            "distinct_poll_ids": len({row["poll_id"] for row in self.questions}),
            "races": len(self.race_rows),
            "states_with_scored_questions": len(self.state_rows),
            "count_note": COUNT_NOTE,
            "error_definition": self.analysis["error_definition"],
            "margin_definition": self.analysis["margin_definition"],
            "poll_level": _error_record(by_slice["all_included_polls"]),
            "race_level_unweighted_mean": _error_record(by_slice["all_matched_races"]),
            "slices": [
                {"slice": row["slice"], "unit": row["unit"], **_error_record(row)}
                for row in self.overall_rows
            ],
            "cycles": [self._cycle(row) for row in self._ordered_cycles()],
            "model": {
                "equation": self.model["model"],
                "seed": self.model["sampler"]["seed"],
                "burn_in": self.model["sampler"]["burn_in"],
                "draws": self.model["sampler"]["draws"],
                "thin": self.model["sampler"]["thin"],
                "n_polls_modeled": preparation["n_polls"],
                "n_questions_kept": preparation["n_questions_kept"],
                "median_sample_size": preparation["median_sample_size"],
                "median_sampling_variance": round(float(preparation["median_sampling_variance"]), 4),
                "mu_p50": _num(posterior["mu"]["p50"]),
                "sd_race_p50": _num(posterior["sd_race"]["p50"]),
                "sd_house_p50": _num(posterior["sd_house"]["p50"]),
                "sd_cycle_p50": _num(posterior["sd_cycle"]["p50"]),
                "phi_p50": _num(posterior["phi"]["p50"]),
            },
        }

    def map_payload(self) -> dict[str, Any]:
        by_state = {row["state_po"]: row for row in self.state_rows}
        exclusions: dict[str, Counter[str]] = defaultdict(Counter)
        for row in self.exclusion_rows:
            exclusions[row["state_po"]][row["reason"]] += 1
        states = []
        for code, name in SENATE_STATES:
            row = by_state.get(code)
            reason_counts = exclusions.get(code, Counter())
            states.append(
                {
                    "state_po": code,
                    "state_name": row["state_name"] if row else name,
                    "has_scored_questions": row is not None,
                    "n_questions": _int(row["n_polls"]) if row else 0,
                    "n_races": _int(row["n_races"]) if row else 0,
                    "mean_signed_error": _num(row["mean_signed_error"]) if row else None,
                    "median_signed_error": _num(row["median_signed_error"]) if row else None,
                    "mae": _num(row["mae"]) if row else None,
                    "rmse": _num(row["rmse"]) if row else None,
                    "exclusions": [
                        {
                            "reason": reason,
                            "label": EXCLUSION_LABELS.get(reason, reason),
                            "n_questions": count,
                        }
                        for reason, count in sorted(reason_counts.items())
                    ],
                }
            )
        return {
            "cycles": [2018, 2020, 2022, 2024],
            "map_note": MAP_NOTE,
            "score_note": (
                "The choropleth is the 2018–2024 historical error. "
                "2026 contests stay unscored, and no state is given a 2026 polling average."
            ),
            "states": states,
        }

    def state_detail(self, state_po: str) -> dict[str, Any]:
        code = state_po.upper()
        if code not in self._states:
            return {}
        summary = next((row for row in self.state_rows if row["state_po"] == code), None)
        map_row = next(row for row in self.map_payload()["states"] if row["state_po"] == code)
        questions = sorted(
            self._questions_by_state.get(code, []),
            key=lambda row: (row["end_date"], row["question_id"]),
        )
        races = [
            self._race(row)
            for row in self.race_rows
            if row["state_po"] == code
        ]
        races.sort(key=lambda row: (row["election_year"], row["stage"], row["contest_id"]))
        return {
            "state_po": code,
            "state_name": map_row["state_name"],
            "has_scored_questions": summary is not None,
            "summary": None
            if summary is None
            else {
                "n_questions": _int(summary["n_polls"]),
                "n_races": _int(summary["n_races"]),
                **{key: value for key, value in _error_record(summary).items() if key != "n"},
            },
            "exclusions": map_row["exclusions"],
            "result_role": (
                "result_margin_two_party is the official two-candidate margin of this "
                "historical contest. Race averages were computed from poll margins first, "
                "and the result was subtracted afterward. The value is a comparison line, "
                "not a 2026 estimate."
            ),
            "races": races,
            "questions": [self._question(row) for row in questions],
        }

    def errors(self) -> dict[str, Any]:
        values = [float(row["error_two_party"]) for row in self.questions]
        return {
            "definition": self.analysis["error_definition"],
            "histogram": histogram(values, HISTORICAL_BIN_START, HISTORICAL_BIN_STOP, HISTORICAL_BIN_STEP),
            "poll_level": _error_record(
                next(row for row in self.overall_rows if row["slice"] == "all_included_polls")
            ),
            "cycles": [self._cycle(row) for row in self._ordered_cycles()],
            "timing": [self._timing(row) for row in self._ordered_timing()],
        }

    def pollsters(self, min_questions: int = 1) -> dict[str, Any]:
        groups = []
        for name, values in self._errors_by_method.items():
            groups.append({"methodology": name, **_describe(values)})
        groups.sort(key=lambda row: (-int(row["n_questions"]), str(row["methodology"])))
        population = []
        for row in self.population_rows:
            code = row["population"]
            population.append(
                {
                    "population": code,
                    "label": POPULATION_LABELS.get(code, code),
                    **_error_record(row),
                }
            )
        firms = []
        for row in self.pollster_rows:
            n_questions = _int(row["n_polls"]) or 0
            if n_questions < min_questions:
                continue
            modal, modal_n = self._modal_methodology(row["pollster_key"])
            firms.append(
                {
                    "pollster_key": row["pollster_key"],
                    "pollster": row["pollster"],
                    "n_questions": n_questions,
                    "n_races": _int(row["n_races"]),
                    "n_cycles": _int(row["n_cycles"]),
                    "mean_signed_error": _num(row["mean_signed_error"]),
                    "median_signed_error": _num(row["median_signed_error"]),
                    "mae": _num(row["mae"]),
                    "rmse": _num(row["rmse"]),
                    "modal_methodology": modal,
                    "modal_methodology_questions": modal_n,
                }
            )
        firms.sort(key=lambda row: (-int(row["n_questions"]), row["pollster"]))
        return {
            "count_note": COUNT_NOTE,
            "methodology_rule": (
                "Each scored question keeps its published methodology string when that "
                "string contains no slash. A slash-separated string is counted once under "
                "Mixed methods. A blank string is (missing). The groups partition the "
                "scored questions. They are not design effects."
            ),
            "population_note": (
                "Population labels follow the codes used in preprocessing: "
                "lv likely voters, rv registered voters, v voters, a adults."
            ),
            "methodology": groups,
            "population": population,
            "pollsters": firms,
        }

    def uncertainty(self) -> dict[str, Any]:
        draws: dict[str, list[float]] = defaultdict(list)
        for row in self.simulation_draws:
            draws[row["design"]].append(float(row["error"]))
        designs = []
        for row in self.simulation_rows:
            design = row["design"]
            sample = draws.get(design, [])
            designs.append(
                {
                    "design": design,
                    "label": DESIGN_LABELS.get(design, design),
                    "n_polls": _int(row["n_polls"]),
                    "n_pollsters": _int(row["n_pollsters"]),
                    "n_draws": _int(row["n_draws"]),
                    "mean": _num(row["mean"]),
                    "sd": _num(row["sd"]),
                    "p025": _num(row["p025"]),
                    "p10": _num(row["p10"]),
                    "p25": _num(row["p25"]),
                    "p50": _num(row["p50"]),
                    "p75": _num(row["p75"]),
                    "p90": _num(row["p90"]),
                    "p975": _num(row["p975"]),
                    "histogram": histogram(
                        sample,
                        SIMULATION_BIN_START,
                        SIMULATION_BIN_STOP,
                        SIMULATION_BIN_STEP,
                    ),
                }
            )
        posterior = []
        for row in self.posterior_rows:
            name = row["parameter"]
            posterior.append(
                {
                    "parameter": name,
                    "label": PARAMETER_LABELS.get(name, name),
                    "unit": PARAMETER_UNITS.get(name, "points"),
                    "mean": _num(row["mean"]),
                    "p05": _num(row["p05"]),
                    "p50": _num(row["p50"]),
                    "p95": _num(row["p95"]),
                    "ess": _num(row["ess"]),
                }
            )
        variance = []
        for row in self.variance_rows:
            if row["estimand"] != "unweighted":
                continue
            component = row["component"]
            variance.append(
                {
                    "design": row["design"],
                    "label": DESIGN_LABELS.get(row["design"], row["design"]),
                    "component": component,
                    "component_label": COMPONENT_LABELS.get(component, component),
                    "variance": _num(row["variance"]),
                    "share": _num(row["share"]),
                    "sd_if_only_this_component": _num(row["sd_if_only_this_component"]),
                    "predictive_sd": _num(row["predictive_sd"]),
                }
            )
        return {
            "simulation_note": SIMULATION_NOTE,
            "equation": self.model["model"],
            "error_definition": self.model["error_definition"],
            "preparation": {
                "n_questions": self.model["preparation"]["n_questions"],
                "n_questions_kept": self.model["preparation"]["n_questions_kept"],
                "n_questions_excluded": self.model["preparation"]["n_questions_excluded"],
                "exclusions_by_reason": self.model["preparation"]["exclusions_by_reason"],
                "n_polls": self.model["preparation"]["n_polls"],
                "n_races": self.model["preparation"]["n_races"],
                "n_pollster_race_groups": self.model["preparation"]["n_pollster_race_groups"],
                "median_sample_size": self.model["preparation"]["median_sample_size"],
                "median_sampling_variance": round(
                    float(self.model["preparation"]["median_sampling_variance"]), 4
                ),
            },
            "priors": self.model["priors"],
            "sampler": self.model["sampler"],
            "posterior": posterior,
            "designs": designs,
            "variance_unweighted": variance,
            "backtest": [
                {
                    "protocol": row["protocol"],
                    "estimand": row["estimand"],
                    "cycle": row["cycle"],
                    "n_races": _int(row["n_races"]),
                    "coverage_50": _num(row["coverage_50"]),
                    "coverage_80": _num(row["coverage_80"]),
                    "coverage_95": _num(row["coverage_95"]),
                    "mean_width_95": _num(row["mean_width_95"]),
                    "mean_pit": _num(row["mean_pit"]),
                    "mean_actual_error": _num(row["mean_actual_error"]),
                    "mean_predicted_median": _num(row["mean_predicted_median"]),
                }
                for row in self.backtest_rows
            ],
            "prior_sensitivity": [
                {
                    "half_cauchy_scale": _num(row["half_cauchy_scale"]),
                    "parameter": row["parameter"],
                    "label": PARAMETER_LABELS.get(row["parameter"], row["parameter"]),
                    "p50": _num(row["p50"]),
                    "p05": _num(row["p05"]),
                    "p95": _num(row["p95"]),
                }
                for row in self.sensitivity_rows
            ],
            "leakage_controls": list(self.model["leakage_controls"]),
            "limitations": list(self.model["limitations"]),
        }

    def notes(self) -> dict[str, Any]:
        return {
            "sources": SOURCES,
            "inclusion_rules": list(self.analysis["inclusion_rules"]),
            "analysis_leakage_controls": list(self.analysis["leakage_controls"]),
            "model_leakage_controls": list(self.model["leakage_controls"]),
            "limitations": list(self.model["limitations"]),
            "error_definition": self.analysis["error_definition"],
            "margin_definition": self.analysis["margin_definition"],
            "model": self.model["model"],
            "priors": self.model["priors"],
            "sampler": self.model["sampler"],
        }

    def _ordered_cycles(self) -> list[dict[str, str]]:
        return sorted(self.cycle_rows, key=lambda row: int(row["cycle"]))

    def _ordered_timing(self) -> list[dict[str, str]]:
        order = {label: index for index, label in enumerate(TIMING_ORDER)}
        return sorted(self.timing_rows, key=lambda row: order.get(row["timing"], 99))

    def _cycle(self, row: dict[str, str]) -> dict[str, Any]:
        return {
            "cycle": int(row["cycle"]),
            "n_questions": _int(row["n_polls"]),
            "n_races": _int(row["n_races"]),
            **{key: value for key, value in _error_record(row).items() if key != "n"},
        }

    def _timing(self, row: dict[str, str]) -> dict[str, Any]:
        return {"timing": row["timing"], **_error_record(row)}

    def _race(self, row: dict[str, str]) -> dict[str, Any]:
        return {
            "contest_id": row["contest_id"],
            "cycle": int(row["cycle"]),
            "election_year": int(row["election_year"]),
            "stage": row["stage"],
            "special": _bool(row["special"]),
            "dem_candidate": row["dem_candidate_result"],
            "rep_candidate": row["rep_candidate_result"],
            "n_questions": _int(row["n_polls"]),
            "poll_margin_two_party_mean": _num(row["poll_margin_two_party_mean"]),
            "result_margin_two_party": _num(row["result_margin_two_party"]),
            "error_of_unweighted_mean": _num(row["error_of_unweighted_mean"]),
            "result_unofficial": _bool(row["result_unofficial"]),
        }

    def _question(self, row: dict[str, str]) -> dict[str, Any]:
        sample = _num(row["sample_size"])
        if isinstance(sample, float) and sample.is_integer():
            sample = int(sample)
        return {
            "question_id": row["question_id"],
            "poll_id": row["poll_id"],
            "pollster": row["pollster"],
            "cycle": int(row["cycle"]),
            "contest_id": row["contest_id"],
            "stage": row["stage"],
            "end_date": row["end_date"],
            "days_before_election": _int(row["days_before_election"]),
            "sample_size": sample,
            "population": row["population"] or None,
            "methodology": row["methodology"] or None,
            "dem_candidate": row["dem_candidate_poll"],
            "rep_candidate": row["rep_candidate_poll"],
            "poll_margin_two_party": _num(row["poll_margin_two_party"]),
            "result_margin_two_party": _num(row["result_margin_two_party"]),
            "error_two_party": _num(row["error_two_party"]),
        }

    def _modal_methodology(self, pollster_key: str) -> tuple[str | None, int]:
        counts = self._method_by_pollster.get(pollster_key)
        if not counts:
            return None, 0
        method, count = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]
        return method, count


@lru_cache(maxsize=1)
def get_catalog() -> Catalog:
    return Catalog(repo_root())
