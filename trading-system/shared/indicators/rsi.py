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


from dataclasses import dataclass


@dataclass(frozen=True)
class RSISettings:
    """Exact RSI settings matching the user's TradingView configuration."""

    length: int = 14
    source: str = "close"
    calculate_divergence: bool = False
    smoothing_type: str = "EMA"
    smoothing_length: int = 20
    bb_stddev: float = 2.0
    timeframe: str = "Chart"
    wait_for_timeframe_closes: bool = True
    upper_band: float = 60.0
    middle_band: float = 50.0
    lower_band: float = 40.0


DEFAULT_RSI_SETTINGS = RSISettings()


def calculate_rsi_indicator(
    data: Union[pd.DataFrame, pd.Series, np.ndarray, list],
    length: int = DEFAULT_RSI_SETTINGS.length,
    source: str = DEFAULT_RSI_SETTINGS.source,
    smoothing_type: str = DEFAULT_RSI_SETTINGS.smoothing_type,
    smoothing_length: int = DEFAULT_RSI_SETTINGS.smoothing_length,
    bb_stddev: float = DEFAULT_RSI_SETTINGS.bb_stddev,
    upper_band: float = DEFAULT_RSI_SETTINGS.upper_band,
    middle_band: float = DEFAULT_RSI_SETTINGS.middle_band,
    lower_band: float = DEFAULT_RSI_SETTINGS.lower_band,
    calculate_divergence: bool = DEFAULT_RSI_SETTINGS.calculate_divergence,
    wait_for_timeframe_closes: bool = DEFAULT_RSI_SETTINGS.wait_for_timeframe_closes,
) -> pd.DataFrame:
    """Calculate the full RSI indicator suite with smoothing and exact levels.

    Parameters
    ----------
    data: DataFrame, Series, or array
        Input data. If a DataFrame is provided, extracts the column specified by `source`.
    length: int, default 14
        RSI lookback period.
    source: str, default "close"
        Column name to extract when a DataFrame is passed.
    smoothing_type: str, default "EMA"
        Smoothing MA type for RSI line ("EMA" or "SMA").
    smoothing_length: int, default 20
        Smoothing MA lookback length.
    bb_stddev: float, default 2.0
        Standard deviation multiplier if Bollinger Bands smoothing is used.
    upper_band: float, default 60.0
        Upper momentum band / overbought threshold.
    middle_band: float, default 50.0
        Midline momentum threshold.
    lower_band: float, default 40.0
        Lower momentum band / oversold threshold.
    calculate_divergence: bool, default False
        Whether divergence calculation is enabled.
    wait_for_timeframe_closes: bool, default True
        Whether calculations wait for closed candles.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns:
        - `rsi`: Raw RSI(14)
        - `rsi_ma`: Smoothed RSI-based MA (EMA 20)
        - `upper_band`: 60.0
        - `middle_band`: 50.0
        - `lower_band`: 40.0
        - `overbought`: boolean Series (`rsi >= upper_band`)
        - `oversold`: boolean Series (`rsi <= lower_band`)
        - `rsi_crossed_above_ma`: boolean Series (RSI crosses above RSI-MA)
        - `rsi_crossed_below_ma`: boolean Series (RSI crosses below RSI-MA)
    """
    if isinstance(data, pd.DataFrame):
        col = source.lower()
        if col in data.columns:
            series = data[col]
        elif source in data.columns:
            series = data[source]
        elif "close" in data.columns:
            series = data["close"]
        else:
            series = data.iloc[:, 0]
    else:
        series = _to_series(data)

    # 1. Base RSI calculation
    rsi_vals = rsi(series, window=length)

    # 2. Smoothing MA calculation
    if smoothing_type.upper() == "EMA":
        rsi_ma = rsi_vals.ewm(span=smoothing_length, adjust=False).mean()
    else:
        rsi_ma = rsi_vals.rolling(window=smoothing_length).mean()

    # 3. Vectorized crossover detection
    rsi_arr = rsi_vals.to_numpy()
    ma_arr = rsi_ma.to_numpy()

    cross_above = (rsi_arr > ma_arr) & np.r_[False, rsi_arr[:-1] <= ma_arr[:-1]]
    cross_below = (rsi_arr < ma_arr) & np.r_[False, rsi_arr[:-1] >= ma_arr[:-1]]

    result_df = pd.DataFrame(
        {
            "rsi": rsi_vals,
            "rsi_ma": rsi_ma,
            "upper_band": upper_band,
            "middle_band": middle_band,
            "lower_band": lower_band,
            "overbought": rsi_vals >= upper_band,
            "oversold": rsi_vals <= lower_band,
            "rsi_crossed_above_ma": cross_above,
            "rsi_crossed_below_ma": cross_below,
        },
        index=series.index,
    )
    return result_df


# Convenient alias
rsi_indicator = calculate_rsi_indicator

