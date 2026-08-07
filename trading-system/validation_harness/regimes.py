"""Classifies historical date ranges into market regimes so each
strategy's backtest can be sliced and evaluated per-regime, not just as
one aggregate number.

Pure, deterministic, computed directly from the same underlying OHLCV
used for backtesting — no external data source. Classification is
necessarily heuristic (there is no ground-truth "this day was trending"
label) but uses standard, explainable technical measures rather than
anything ad hoc.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from shared.indicators.adx import adx

__all__ = ["classify_daily_regimes", "REGIME_NAMES"]

REGIME_NAMES = ("trending", "sideways", "high_volatility", "low_volatility", "gap_day")


def classify_daily_regimes(df: pd.DataFrame) -> pd.Series:
    """Returns a Series indexed by calendar date, one regime label per
    day (a day can only carry one label here — gap_day takes priority
    since it's the most specific/rare condition, then trending/sideways
    from ADX, then high/low volatility as a fallback bucket for whatever
    doesn't clearly fit the other two).

    Parameters
    ----------
    df
        Intraday OHLCV with a DatetimeIndex (the same frame passed to
        `harness.run_strategy_backtest`).

    Note on minimum history
    -----------------------
    ADX's 14-period Wilder smoothing needs real room to converge — on a
    short series (tested down to ~15 trading days) the still-converging
    early values can dominate the whole classification, misreading even a
    genuinely choppy/mean-reverting series as "trending" throughout.
    Verified against this repository's real ~14-month NIFTY history (290
    trading days) to produce a sane, diverse distribution across all five
    regimes; treat classifications on a much shorter window (well under
    ~60 trading days) with reduced confidence.
    """
    daily = df.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    if daily.empty:
        return pd.Series(dtype=object)

    daily_adx = adx(daily, window=14) if len(daily) >= 15 else pd.Series(np.nan, index=daily.index)
    daily_range_pct = (daily["high"] - daily["low"]) / daily["close"] * 100.0
    prev_close = daily["close"].shift(1)
    gap_pct = ((daily["open"] - prev_close) / prev_close * 100.0).abs()

    range_median = daily_range_pct.median()
    range_p75 = daily_range_pct.quantile(0.75)
    range_p25 = daily_range_pct.quantile(0.25)

    labels = []
    for ts in daily.index:
        this_adx = daily_adx.get(ts, np.nan)
        this_gap = gap_pct.get(ts, 0.0)
        this_range = daily_range_pct.get(ts, range_median)

        if pd.notna(this_gap) and this_gap >= 0.5:
            labels.append("gap_day")
        elif pd.notna(this_adx) and this_adx >= 25:
            labels.append("trending")
        elif pd.notna(this_adx) and this_adx < 18:
            labels.append("sideways")
        elif this_range >= range_p75:
            labels.append("high_volatility")
        elif this_range <= range_p25:
            labels.append("low_volatility")
        else:
            labels.append("sideways")

    return pd.Series(labels, index=[ts.date() for ts in daily.index])


def slice_by_regime(df: pd.DataFrame, regime_labels: pd.Series, regime: str) -> pd.DataFrame:
    """Return only the bars from `df` whose calendar date is labeled
    `regime`."""
    dates = set(regime_labels[regime_labels == regime].index)
    if not dates:
        return df.iloc[0:0]
    mask = df.index.map(lambda ts: (ts.date() if hasattr(ts, "date") else ts) in dates)
    return df[mask]
