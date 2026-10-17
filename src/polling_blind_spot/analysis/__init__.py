"""Historical Senate polling-error analysis.

Election results are joined after a poll is scored. They are not written back
onto the cleaned poll tables, and they are not an input to pre-election
averages.
"""

from polling_blind_spot.analysis.polling_error import run_historical_polling_error

__all__ = ["run_historical_polling_error"]
