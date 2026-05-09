"""Exponential Moving Average (EMA) indicator.

Provides a simple wrapper around ``pandas.Series.ewm`` that returns the EMA
for a given ``window`` size. The function works on both ``pandas.Series``
and ``numpy.ndarray`` inputs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Union

SeriesOrArray = Union[pd.Series, np.ndarray, list]


def ema(data: SeriesOrArray, window: int) -> pd.Series:
    """Calculate the exponential moving average.

    Parameters
    ----------
    data: SeriesOrArray
        Historical price/price‑related series.
    window: int
        Length of the EMA window (e.g., 20 for EMA20).

    Returns
    -------
    pandas.Series
        EMA series aligned with the input index. ``NaN`` values are produced
        for the first ``window - 1`` entries, matching pandas' default behavior.
    """
    # Convert to pandas Series preserving the original index if possible
    if isinstance(data, pd.Series):
        series = data
    else:
        series = pd.Series(data)

    if window <= 0:
        raise ValueError("EMA window must be a positive integer")

    return series.ewm(span=window, adjust=False).mean()
