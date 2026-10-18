"""Bayesian polling-error model, simulations, and historical backtests.

Election results enter only as the signed errors of contests in the training
set. A predictive interval for a roster does not read that roster's result.
"""

from polling_blind_spot.uncertainty.engine import run_uncertainty_engine

__all__ = ["run_uncertainty_engine"]
