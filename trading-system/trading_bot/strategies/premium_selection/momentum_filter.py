"""Momentum Filter — RSI strength, candle body analysis, and divergence rejection.

Only accept strong momentum candles. Reject weak, exhausted, or diverging setups.
"""
from __future__ import annotations
import pandas as pd
from shared.indicators import rsi, macd


def compute_momentum(
    df: pd.DataFrame,
    rsi_window: int = 14,
    rsi_call_thresh: float = 55,
    rsi_put_thresh: float = 45,
) -> pd.DataFrame:
    """
    Computes RSI, MACD, candle body ratio, and derives momentum signals.

    BUY CALL: RSI > rsi_call_thresh AND RSI rising
    BUY PUT : RSI < rsi_put_thresh  AND RSI falling

    Returns DataFrame with columns:
      - rsi, rsi_rising, rsi_falling
      - macd_bullish, macd_bearish
      - body_ratio       : candle body as % of total range
      - momentum_bullish : all bullish momentum conditions met
      - momentum_bearish : all bearish momentum conditions met
    """
    df = df.copy()

    # RSI
    df["rsi"] = rsi(df["close"], window=rsi_window)
    df["rsi_rising"]  = df["rsi"] > df["rsi"].shift(1)
    df["rsi_falling"] = df["rsi"] < df["rsi"].shift(1)

    # Reject RSI in the no-man's land (45–55 = choppy zone)
    rsi_call_ok = df["rsi"] > rsi_call_thresh
    rsi_put_ok  = df["rsi"] < rsi_put_thresh
    rsi_no_mans_land = (df["rsi"] >= rsi_put_thresh) & (df["rsi"] <= rsi_call_thresh)

    # MACD
    macd_df = macd(df["close"])
    df["macd_line"]    = macd_df["macd"]
    df["macd_signal"]  = macd_df["signal"]
    df["macd_hist"]    = macd_df["hist"]
    df["macd_bullish"] = (df["macd_line"] > df["macd_signal"]) & (df["macd_hist"] > 0)
    df["macd_bearish"] = (df["macd_line"] < df["macd_signal"]) & (df["macd_hist"] < 0)

    # Candle body strength (reject doji, spinning tops, indecision)
    candle_range = (df["high"] - df["low"]).replace(0, 1e-9)
    body = (df["close"] - df["open"]).abs()
    df["body_ratio"] = body / candle_range
    strong_body = df["body_ratio"] > 0.50   # Body must be > 50% of candle range

    # Exhaustion candle rejection: huge body after a long run = potential reversal
    # If the candle body is > 3x the 10-period average body — it's overextended
    avg_body = body.rolling(10, min_periods=1).mean()
    not_exhausted = body < (avg_body * 3.0)

    # Final momentum signals
    df["momentum_bullish"] = (
        rsi_call_ok &
        df["rsi_rising"] &
        df["macd_bullish"] &
        strong_body &
        not_exhausted &
        ~rsi_no_mans_land
    )

    df["momentum_bearish"] = (
        rsi_put_ok &
        df["rsi_falling"] &
        df["macd_bearish"] &
        strong_body &
        not_exhausted &
        ~rsi_no_mans_land
    )

    return df
