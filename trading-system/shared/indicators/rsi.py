"""Relative Strength Index (RSI) indicator.

Provides a pure‑Python implementation compatible with ``pandas.Series`` or
``numpy.ndarray`` inputs. The calculation follows the classic Wilder method:
average gain/loss over ``window`` periods, then ``100 - 100/(1+RS)``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Union

SeriesOrArray = Union[pd.Series, np.ndarray, list]


def _to_series(data: SeriesOrArray) -> pd.Series:
    """Convert any acceptable input to a ``pandas.Series``.

    Preserves an existing index when possible; otherwise creates a default
    integer index.
    """
    if isinstance(data, pd.Series):
        return data
    return pd.Series(data)


def rsi(data: SeriesOrArray, window: int = 14) -> pd.Series:
    """Calculate the Relative Strength Index.

    Parameters
    ----------
    data: SeriesOrArray
        Price series (typically close prices).
    window: int, default 14
        Number of periods to use for the average gain/loss.

    Returns
    -------
    pandas.Series
        RSI values aligned with the input index. Only the very first
        entry is ``NaN`` (from the initial ``.diff()``) — average
        gain/loss use ``ewm(adjust=False)``, which starts producing a
        value immediately rather than waiting for ``window`` periods to
        accumulate, so it does NOT produce ``window`` leading ``NaN``
        entries the way a ``.rolling(window)`` average would. The first
        ``window`` non-NaN values are numerically valid but come from a
        still-converging average and are statistically less reliable
        than later values — callers that need those excluded (e.g. ML
        feature pipelines relying on ``dropna()`` to strip a warm-up
        period) must mask them explicitly; this function does not.
    """
    if window <= 0:
        raise ValueError("RSI window must be a positive integer")

    series = _to_series(data)
    # Compute price differences
    delta = series.diff()
    # Separate gains and losses
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Use Wilder's smoothing: exponential moving average with "adjust=False"
    avg_gain = gain.ewm(alpha=1 / window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False).mean()

    # Avoid division by zero – add epsilon to denominator
    rs = avg_gain / (avg_loss + 1e-9)
    rsi_series = 100 - (100 / (1 + rs))
    rsi_series = rsi_series.where(avg_loss != 0, 100.0)

    # NOTE: unlike a .rolling(window) average, ewm(adjust=False) does NOT
    # yield NaN for the first `window` points — it starts producing a
    # (still-converging, less reliable) value from the first non-NaN input.
    # See the docstring above for what this means for callers.
    return rsi_series
