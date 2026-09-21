"""
RSI Divergence & Momentum Engine — Institutional Reversal & Trend Continuation Detector.

Key Features:
1. Wilder's Smoothed Relative Strength Index (RSI 14)
2. Algorithmic Pivot-Based Divergence Detector:
   - Regular Bullish Divergence (Price Lower Low + RSI Higher Low -> Institutional Exhaustion Reversal)
   - Regular Bearish Divergence (Price Higher High + RSI Lower High -> Institutional Exhaustion Reversal)
   - Hidden Bullish Divergence (Price Higher Low + RSI Lower Low -> Trend Continuation)
   - Hidden Bearish Divergence (Price Lower High + RSI Higher High -> Trend Continuation)
3. Momentum Regimes:
   - Overbought (>= 70) / Oversold (<= 30)
   - 50-Level Equilibrium Crossovers
4. Zero Lookahead Bias: Verified on confirmed closed swing points.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class DivergenceType(Enum):
    REGULAR_BULLISH = "REGULAR_BULLISH"
    REGULAR_BEARISH = "REGULAR_BEARISH"
    HIDDEN_BULLISH = "HIDDEN_BULLISH"
    HIDDEN_BEARISH = "HIDDEN_BEARISH"


@dataclass
class DivergenceEvent:
    bar_index: int
    timestamp: Any
    divergence_type: DivergenceType
    is_bullish: bool
    is_hidden: bool
    price_pivots: Tuple[float, float]  # (prev_price, curr_price)
    rsi_pivots: Tuple[float, float]      # (prev_rsi, curr_rsi)
    confidence: float = 1.0


@dataclass
class RSIDivergenceResult:
    current_rsi: float
    is_overbought: bool
    is_oversold: bool
    above_neutral: bool  # RSI > 50
    active_events: List[DivergenceEvent] = field(default_factory=list)
    latest_bullish_div: Optional[DivergenceEvent] = None
    latest_bearish_div: Optional[DivergenceEvent] = None


def calculate_wilders_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    """Computes standard Wilder's Smoothed RSI."""
    n = len(close)
    rsi = np.full(n, 50.0, dtype=float)
    if n <= period:
        return rsi

    diff = np.diff(close)
    gains = np.maximum(diff, 0.0)
    losses = np.maximum(-diff, 0.0)

    # First average
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    if avg_loss == 0:
        rsi[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period + 1, n):
        gain = gains[i - 1]
        loss = losses[i - 1]

        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))

    return rsi


def calculate_rsi_divergences(
    df: pd.DataFrame,
    period: int = 14,
    lookback_pivot: int = 5,
    max_divergence_bars: int = 40,
    overbought: float = 70.0,
    oversold: float = 30.0
) -> Tuple[pd.DataFrame, RSIDivergenceResult]:
    """
    Detects Regular and Hidden RSI Divergences.

    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with columns ['high', 'low', 'close'].
    period : int
        RSI lookback period (default: 14).
    lookback_pivot : int
        Bars on each side required to confirm a swing point (default: 5).
    max_divergence_bars : int
        Maximum distance between two pivots to form a valid divergence (default: 40).
    overbought : float
        Overbought threshold (default: 70.0).
    oversold : float
        Oversold threshold (default: 30.0).

    Returns:
    --------
    Tuple[pd.DataFrame, RSIDivergenceResult]:
        DataFrame enriched with RSI and divergence series, and structured analysis result.
    """
    if df.empty or len(df) < (period + lookback_pivot * 2):
        empty_res = RSIDivergenceResult(
            current_rsi=50.0,
            is_overbought=False,
            is_oversold=False,
            above_neutral=True
        )
        return df.copy(), empty_res

    res_df = df.copy()
    res_df.rename(columns={c: c.lower() for c in res_df.columns}, inplace=True)

    highs = res_df['high'].to_numpy(dtype=float)
    lows = res_df['low'].to_numpy(dtype=float)
    closes = res_df['close'].to_numpy(dtype=float)
    timestamps = res_df.index.tolist()
    n = len(res_df)

    rsi = calculate_wilders_rsi(closes, period=period)
    res_df['rsi'] = rsi

    # Detect price pivots
    from shared.indicators.smart_money_concepts import detect_pivots
    p_highs, p_lows = detect_pivots(highs, lows, length=lookback_pivot)

    # Detect RSI pivots
    rsi_highs, rsi_lows = detect_pivots(rsi, rsi, length=lookback_pivot)

    events: List[DivergenceEvent] = []
    reg_bull_series = np.zeros(n, dtype=bool)
    reg_bear_series = np.zeros(n, dtype=bool)
    hid_bull_series = np.zeros(n, dtype=bool)
    hid_bear_series = np.zeros(n, dtype=bool)

    confirmed_low_pivots: List[Tuple[int, float, float]] = []   # (index, price, rsi)
    confirmed_high_pivots: List[Tuple[int, float, float]] = []  # (index, price, rsi)

    # Evaluate sequentially
    for i in range(n):
        conf_idx = i - lookback_pivot
        if conf_idx >= 0:
            if p_lows[conf_idx]:
                confirmed_low_pivots.append((conf_idx, lows[conf_idx], rsi[conf_idx]))
                # Check Bullish Divergences against preceding low pivots
                if len(confirmed_low_pivots) >= 2:
                    curr_idx, curr_price, curr_rsi = confirmed_low_pivots[-1]
                    prev_idx, prev_price, prev_rsi = confirmed_low_pivots[-2]

                    if (curr_idx - prev_idx) <= max_divergence_bars:
                        # 1. Regular Bullish: Price Lower Low, RSI Higher Low
                        if curr_price < prev_price and curr_rsi > prev_rsi:
                            event = DivergenceEvent(
                                bar_index=i,
                                timestamp=timestamps[i],
                                divergence_type=DivergenceType.REGULAR_BULLISH,
                                is_bullish=True,
                                is_hidden=False,
                                price_pivots=(prev_price, curr_price),
                                rsi_pivots=(prev_rsi, curr_rsi),
                                confidence=0.85 if prev_rsi <= oversold else 0.70
                            )
                            events.append(event)
                            reg_bull_series[i] = True

                        # 2. Hidden Bullish: Price Higher Low, RSI Lower Low
                        elif curr_price > prev_price and curr_rsi < prev_rsi:
                            event = DivergenceEvent(
                                bar_index=i,
                                timestamp=timestamps[i],
                                divergence_type=DivergenceType.HIDDEN_BULLISH,
                                is_bullish=True,
                                is_hidden=True,
                                price_pivots=(prev_price, curr_price),
                                rsi_pivots=(prev_rsi, curr_rsi),
                                confidence=0.80
                            )
                            events.append(event)
                            hid_bull_series[i] = True

            if p_highs[conf_idx]:
                confirmed_high_pivots.append((conf_idx, highs[conf_idx], rsi[conf_idx]))
                # Check Bearish Divergences against preceding high pivots
                if len(confirmed_high_pivots) >= 2:
                    curr_idx, curr_price, curr_rsi = confirmed_high_pivots[-1]
                    prev_idx, prev_price, prev_rsi = confirmed_high_pivots[-2]

                    if (curr_idx - prev_idx) <= max_divergence_bars:
                        # 3. Regular Bearish: Price Higher High, RSI Lower High
                        if curr_price > prev_price and curr_rsi < prev_rsi:
                            event = DivergenceEvent(
                                bar_index=i,
                                timestamp=timestamps[i],
                                divergence_type=DivergenceType.REGULAR_BEARISH,
                                is_bullish=False,
                                is_hidden=False,
                                price_pivots=(prev_price, curr_price),
                                rsi_pivots=(prev_rsi, curr_rsi),
                                confidence=0.85 if prev_rsi >= overbought else 0.70
                            )
                            events.append(event)
                            reg_bear_series[i] = True

                        # 4. Hidden Bearish: Price Lower High, RSI Higher High
                        elif curr_price < prev_price and curr_rsi > prev_rsi:
                            event = DivergenceEvent(
                                bar_index=i,
                                timestamp=timestamps[i],
                                divergence_type=DivergenceType.HIDDEN_BEARISH,
                                is_bullish=False,
                                is_hidden=True,
                                price_pivots=(prev_price, curr_price),
                                rsi_pivots=(prev_rsi, curr_rsi),
                                confidence=0.80
                            )
                            events.append(event)
                            hid_bear_series[i] = True

    res_df['rsi_reg_bull_div'] = reg_bull_series
    res_df['rsi_reg_bear_div'] = reg_bear_series
    res_df['rsi_hid_bull_div'] = hid_bull_series
    res_df['rsi_hid_bear_div'] = hid_bear_series

    curr_val = float(rsi[-1]) if len(rsi) > 0 else 50.0
    latest_bull = next((e for e in reversed(events) if e.is_bullish), None)
    latest_bear = next((e for e in reversed(events) if not e.is_bullish), None)

    analysis = RSIDivergenceResult(
        current_rsi=curr_val,
        is_overbought=curr_val >= overbought,
        is_oversold=curr_val <= oversold,
        above_neutral=curr_val >= 50.0,
        active_events=events,
        latest_bullish_div=latest_bull,
        latest_bearish_div=latest_bear
    )

    return res_df, analysis
