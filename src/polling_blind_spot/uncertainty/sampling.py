"""Simple-random-sample variance of a two-party polling margin.

The margin is the same two-candidate quantity used in the historical error
tables, in percentage points:

    100 * (Democratic share - Republican share) / (Democratic share + Republican share)

Democratic and Republican shares are the published percentages of the full
sample. Undecided and other responses are the remaining multinomial category.
They are not reassigned.

The variance is the delta-method variance under simple random sampling. It is
a function of the published sample size and the published percentages. It is
not a fitted parameter, and a missing sample size is not replaced.
"""

from __future__ import annotations

import math


def two_party_sampling_variance(
    dem_pct: float,
    rep_pct: float,
    sample_size: float,
) -> float | None:
    """Return the sampling variance of the two-party margin, in points squared.

    Percentages are on the published 0–100 scale. Returns None when the
    published numbers do not define a multinomial variance: a missing input,
    a non-positive sample size, a share outside 0–100, or Democratic and
    Republican shares that sum to 0 or to more than 100.
    """
    if not _finite(dem_pct) or not _finite(rep_pct) or not _finite(sample_size):
        return None
    if sample_size <= 0 or dem_pct < 0 or rep_pct < 0 or dem_pct > 100 or rep_pct > 100:
        return None
    dem = dem_pct / 100.0
    rep = rep_pct / 100.0
    decided = dem + rep
    if decided <= 0 or decided > 1:
        return None
    # Partial derivatives of (d - r) / (d + r). The other category drops out.
    d_dem = 2.0 * rep / decided**2
    d_rep = -2.0 * dem / decided**2
    var_dem = dem * (1.0 - dem) / sample_size
    var_rep = rep * (1.0 - rep) / sample_size
    cov = -dem * rep / sample_size
    variance_of_share_margin = (
        d_dem**2 * var_dem + d_rep**2 * var_rep + 2.0 * d_dem * d_rep * cov
    )
    if not math.isfinite(variance_of_share_margin) or variance_of_share_margin <= 0:
        return None
    return (100.0**2) * variance_of_share_margin


def _finite(value: float) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)
