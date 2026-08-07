"""Enhanced AI + Multi-Factor Strategy.

This module implements the requested multi-layer confirmation strategy:
1. 9 EMA & 20 EMA Crossover
2. RSI Momentum
3. MACD Trend
4. Volume Strength
5. SMC (Smart Money Concepts)
6. Option Chain Analysis (Simulated)
"""

from __future__ import annotations

import logging

import pandas as pd

from shared.indicators import ema, rsi, macd, smc_features, simulate_option_chain_sentiment

logger = logging.getLogger(__name__)

STRATEGY_NAME = "enhanced_ai"

def _volume_filter(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """Return a boolean mask where volume exceeds its average."""
    if "volume" not in df.columns or df["volume"].nunique() <= 1:
        return pd.Series(True, index=df.index)
    vol_avg = df["volume"].rolling(window=lookback, min_periods=1).mean()
    return df["volume"] > vol_avg

#: RSI midline. The bull and bear RSI confirmations must not overlap —
#: see the root-cause note in generate_signals().
RSI_MIDLINE = 50.0


def generate_signals(
    df: pd.DataFrame,
    ema_fast: int = 9,
    ema_slow: int = 20,
    rsi_window: int = 14,
    rsi_buy_thresh: float = RSI_MIDLINE,
    rsi_sell_thresh: float = RSI_MIDLINE,
    **kwargs,
) -> pd.Series:
    """Generate BUY CALL / BUY PUT signals with multi-layer confirmation.

    BUY CALL: RSI above the midline (momentum genuinely bullish)
    BUY PUT : RSI below the midline (momentum genuinely bearish)

    Root cause fixed 2026-08-08 (backlog #2): these thresholds used to be
    40 and 60, i.e. `rsi > 40` for bull and `rsi < 60` for bear. Those
    ranges OVERLAP across the whole 40-60 band, which is where RSI spends
    most of its life — measured on the real validation window, the RSI
    layer awarded a confirmation point to **both** directions on 50.6% of
    bars, and awarded at least one point on 100.0% of bars (it was never
    silent). A "confirmation" that confirms both directions at once
    carries zero information, yet it counted toward the 5-of-6 threshold
    exactly like a genuine one — effectively lowering the real bar to
    4-of-5 and systematically admitting under-confirmed signals. Splitting
    at the midline preserves the intended philosophy (RSI momentum
    confirmation) while making the layer actually discriminate: at most
    one side can claim the point.
    """
    # Guard against the overlap being reintroduced via settings/callers.
    # Overlapping thresholds are the defect above, not a tuning choice.
    if rsi_buy_thresh < rsi_sell_thresh:
        logger.warning(
            "enhanced_ai: overlapping RSI thresholds (buy=%s, sell=%s) award a "
            "confirmation point to both directions simultaneously and cannot "
            "discriminate — collapsing both to the midline (%s).",
            rsi_buy_thresh, rsi_sell_thresh, RSI_MIDLINE,
        )
        rsi_buy_thresh = rsi_sell_thresh = RSI_MIDLINE

    
    # 1. EMA Crossover
    df["ema_fast"] = ema(df["close"], window=ema_fast)
    df["ema_slow"] = ema(df["close"], window=ema_slow)
    ema_bullish = df["ema_fast"] > df["ema_slow"]
    ema_bearish = df["ema_fast"] < df["ema_slow"]
    
    # 2. RSI Validation — must be DIRECTIONAL (see docstring root-cause note)
    # BUY CALL: RSI above the midline. BUY PUT: RSI below it.
    df["rsi"] = rsi(df["close"], window=rsi_window)
    rsi_bullish = df["rsi"] > rsi_buy_thresh
    rsi_bearish = df["rsi"] < rsi_sell_thresh
    
    # 3. MACD Validation
    macd_df = macd(df["close"])
    macd_bullish = macd_df["macd"] > macd_df["signal"]
    macd_bearish = macd_df["macd"] < macd_df["signal"]
    
    # 4. Volume Validation
    vol_bullish = _volume_filter(df)
    vol_bearish = vol_bullish # Both need strong volume
    
    # 5. Smart Money Concept (SMC) Validation
    df_smc = smc_features(df)
    # We require either a Bullish FVG or a Bullish Break of Structure
    smc_bullish = df_smc["bullish_fvg"] | df_smc["bos_bullish"]
    smc_bearish = df_smc["bearish_fvg"] | df_smc["bos_bearish"]
    
    # 6. Option Chain Validation
    opt_chain = simulate_option_chain_sentiment(df)
    opt_bullish = opt_chain == 1
    opt_bearish = opt_chain == -1
    
    # Score each condition (1 point per confirmation)
    # Require min 5 of 6 confirmations — prevents over-filtering while
    # maintaining institutional conviction (6/6 AND killed all signals)
    bull_score = (
        ema_bullish.astype(int) +
        rsi_bullish.astype(int) +
        macd_bullish.astype(int) +
        vol_bullish.astype(int) +
        smc_bullish.astype(int) +
        opt_bullish.astype(int)
    )
    bear_score = (
        ema_bearish.astype(int) +
        rsi_bearish.astype(int) +
        macd_bearish.astype(int) +
        vol_bearish.astype(int) +
        smc_bearish.astype(int) +
        opt_bearish.astype(int)
    )

    MIN_CONFIRMATIONS = 5   # 5 of 6 layers must agree

    signals = pd.Series(0, index=df.index, dtype=int)
    signals[bull_score >= MIN_CONFIRMATIONS] = 1
    signals[bear_score >= MIN_CONFIRMATIONS] = -1

    return signals
