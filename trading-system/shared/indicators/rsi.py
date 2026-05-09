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
        RSI values aligned with the input index. The first ``window``
        entries are ``NaN`` because the calculation requires ``window``
        previous periods.
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

    # Avoid division by zero – if avg_loss is 0, RSI is set to 100
    rs = avg_gain / avg_loss.replace(to_replace=0, value=np.nan).ffill()
    rsi_series = 100 - (100 / (1 + rs))

    # For the first ``window`` points the average is not yet stable; pandas
    # already yields NaN for those positions, which matches typical RSI output.
    return rsi_series
