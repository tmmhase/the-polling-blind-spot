"""Cleaning and feature construction for Senate polling tables.

Raw downloads stay in ``data/raw``. This package writes a separate cleaned
representation and does not impute unpublished percentages, dates, or names.
"""

from polling_blind_spot.preprocess.pipeline import run_preprocessing

__all__ = ["run_preprocessing"]
