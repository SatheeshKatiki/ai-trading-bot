"""ADX — Average Directional Index indicator.

Provides both the raw ADX line and the full DMI suite (+DI, -DI, ADX).

References
----------
* Wilder, J. W. (1978). New Concepts in Technical Trading Systems.
* Standard ADX implementation: 14-period Wilder smoothing (RMA / EWM).

Usage
-----
    from shared.indicators import adx, dmi

    # Scalar ADX only (most common — strategy filter)
    adx_series = adx(df, window=14)

    # Full DMI (+DI, -DI, ADX)
    dmi_df = dmi(df, window=14)
    trend_strength = dmi_df["adx"]
    bullish_di     = dmi_df["plus_di"]
    bearish_di     = dmi_df["minus_di"]
"""

from __future__ import annotations

import pandas as pd


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------

def _wilder_smooth(series: pd.Series, window: int) -> pd.Series:
    """Wilder's smoothing (equivalent to EMA with alpha = 1/window)."""
    return series.ewm(alpha=1.0 / window, adjust=False).mean()


def dmi(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """Full Directional Movement Index (+DI, -DI, ADX).

    Parameters
    ----------
    df : pd.DataFrame
        Must contain ``high``, ``low``, ``close`` columns.
    window : int
        Wilder smoothing period (default 14).

    Returns
    -------
    pd.DataFrame with columns:
        ``plus_di``  — Positive directional indicator (0–100 scale)
        ``minus_di`` — Negative directional indicator (0–100 scale)
        ``adx``      — Average Directional Index (0–100 scale)
    """
    high  = df["high"]
    low   = df["low"]
    close = df["close"]

    # True Range
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    # Directional Movement
    up_move   = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm  = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    # Wilder-smoothed ATR, +DM, -DM
    atr_smooth      = _wilder_smooth(tr,       window)
    plus_dm_smooth  = _wilder_smooth(plus_dm,  window)
    minus_dm_smooth = _wilder_smooth(minus_dm, window)

    # Directional Indicators (0–100 normalised)
    plus_di  = 100.0 * plus_dm_smooth  / atr_smooth.replace(0, float("nan"))
    minus_di = 100.0 * minus_dm_smooth / atr_smooth.replace(0, float("nan"))

    # DX and ADX
    di_sum  = (plus_di + minus_di).replace(0, float("nan"))
    dx      = 100.0 * (plus_di - minus_di).abs() / di_sum
    adx_val = _wilder_smooth(dx, window)

    return pd.DataFrame({
        "plus_di":  plus_di.fillna(0),
        "minus_di": minus_di.fillna(0),
        "adx":      adx_val.fillna(0),
    }, index=df.index)


def adx(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Return only the ADX series (trend strength, 0–100).

    Convenience wrapper around :func:`dmi` for strategies that only need the
    scalar ADX value (e.g. ``adx > 20`` for trending-market filter).

    Parameters
    ----------
    df : pd.DataFrame
        Must contain ``high``, ``low``, ``close`` columns.
    window : int
        Wilder smoothing period (default 14).

    Returns
    -------
    pd.Series — ADX values (0–100). Values above 25 indicate a strong trend.
    """
    return dmi(df, window=window)["adx"]
