"""Unit and integration tests for the user's custom TradingView setup in ema9_rsi_momentum.

Validates:
1. Reversal Entry: 9/20 EMA crossover with CM Ultimate MA yellow candle.
2. Pullback/Retest Entry: Ongoing trend with 9 EMA retest yellow candle.
3. Chop Box Filter: Flat, compressed 9/20 EMA zones (Purple 'No Trade' Box) suppress false signals.
4. Adaptive Dynamic Stop Loss: Large candle anchors to candle extreme, small candle anchors to 20 EMA +/- buffer.
5. Multi-Instrument Auto-Dynamic Scaling: Proportional adaptation across NIFTY, BANKNIFTY, SENSEX, and Stocks.
6. Trigger Timing: Strict 10-second bar close entry window.
"""

import datetime
import numpy as np
import pandas as pd
import pytest

from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig
from trading_bot.strategies.ema9_rsi_momentum.indicators import compute_indicator_set, IndicatorSet
from trading_bot.strategies.ema9_rsi_momentum.signal_engine import (
    compute_cross_signals,
    detect_chop_box,
    compute_adaptive_stop_loss_series,
    check_entry_timing,
    build_entry_signal_series,
)
from trading_bot.strategies._signal_utils import edge_trigger


def create_ohlc_bars(prices: list[float], bar_ranges: list[float] | None = None, start_time: str = "2026-10-02 09:20") -> pd.DataFrame:
    """Helper to build a DataFrame of OHLCV bars from a close price sequence."""
    n = len(prices)
    times = pd.date_range(start_time, periods=n, freq="5min")
    close = pd.Series(prices, index=times, dtype=float)
    open_ = close.shift(1).fillna(close.iloc[0])

    if bar_ranges is None:
        high = np.maximum(open_, close) + 2.0
        low = np.minimum(open_, close) - 2.0
    else:
        half_range = np.asarray(bar_ranges) / 2.0
        mid = (open_ + close) / 2.0
        high = mid + half_range
        low = mid - half_range

    volume = pd.Series(10000.0, index=times)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=times)


def test_1_reversal_entry_fires_on_cross_and_yellow_bar():
    """Test 1: Fresh 9/20 EMA crossover with CM Ultimate MA yellow candle generates entry."""
    # Build 50 bars declining, then sharp reversal up
    prices = [24000.0 - i * 5.0 for i in range(35)]
    # Sharp reversal upward to produce 9 EMA crossing above 20 EMA
    prices += [prices[-1] + (i + 1) * 20.0 for i in range(25)]
    df = create_ohlc_bars(prices)

    cfg = Ema9RsiMomentumConfig(enable_touch_filter=False, enable_adx_filter=False)
    cross = compute_cross_signals(df, cfg)

    # Bullish signal should fire on the reversal
    assert np.any(cross.bullish)
    first_bullish = np.where(cross.bullish)[0][0]
    # Verify the signal occurred after the warm-up and during the upward surge
    assert first_bullish >= 35


def test_2_pullback_entry_fires_in_active_trend():
    """Test 2: Trend continuation pullback (Setup B) fires when price retests 9 EMA in uptrend."""
    np.random.seed(123)
    n = 60
    noise = np.random.randn(n) * 3.0
    trend = np.linspace(0, 100, n)
    prices = [24000.0 + trend[i] + noise[i] for i in range(n)]
    # Dip back to 9 EMA (pullback) at bar 45
    prices[45] -= 15.0
    prices[46] -= 20.0
    # Sharp bounce at bar 47 (yellow bounce candle)
    prices[47] += 30.0
    prices[48] += 40.0
    df = create_ohlc_bars(prices)

    cfg = Ema9RsiMomentumConfig(enable_touch_filter=False, enable_adx_filter=False, enable_pullback_entries=True)
    cross = compute_cross_signals(df, cfg)

    # Signals should fire during the trend continuation after pullback
    assert np.any(cross.bullish)


def test_3_chop_box_suppresses_false_signals():
    """Test 3: Flat compression (Purple 'No Trade' Box) suppresses false yellow candles."""
    # 50 warmup bars of subtle drift, then 30 bars of completely flat sideways chop (+/- 0.5 pts)
    prices = [24000.0 + i * 0.2 for i in range(40)]
    prices += [24008.0 + (0.3 if i % 2 == 0 else -0.3) for i in range(30)]
    df = create_ohlc_bars(prices)

    cfg = Ema9RsiMomentumConfig(enable_chop_filter=True, chop_atr_mult=0.50, chop_slope_threshold=0.30)
    ind = compute_indicator_set(df)
    is_chop = detect_chop_box(df, ind, cfg)

    # The flat sideways bars must be flagged as chop box
    assert np.any(is_chop[40:])

    # Full cross signals must suppress trades during chop
    cross = compute_cross_signals(df, cfg)
    assert not np.any(cross.bullish[40:])
    assert not np.any(cross.bearish[40:])


def test_4_adaptive_dynamic_stop_loss():
    """Test 4: Large candles anchor SL to candle extreme; small candles anchor SL to 20 EMA +/- buffer."""
    # Create 40 bars baseline
    prices = [24000.0 + i * 5.0 for i in range(40)]
    # Bar 40 has a HUGE candle range (60 points), ATR is ~5 points -> Large Candle
    # Bar 41 has a TINY candle range (3 points), ATR is ~5 points -> Small Candle
    bar_ranges = [10.0] * 40 + [60.0, 3.0]
    prices += [prices[-1] + 30.0, prices[-1] + 5.0]
    df = create_ohlc_bars(prices, bar_ranges=bar_ranges)

    cfg = Ema9RsiMomentumConfig(adaptive_sl_enabled=True, large_candle_atr_mult=1.0, sl_buffer_atr_mult=0.20)
    ind = compute_indicator_set(df)

    # Signal on bar 40 (Large Candle) and bar 41 (Small Candle)
    signals = np.zeros(len(df), dtype=int)
    signals[40] = 1   # CE Buy on large candle
    signals[41] = 1   # CE Buy on small candle

    sl_series = compute_adaptive_stop_loss_series(df, ind, cfg, signals)

    atr_40 = float(ind.atr.iloc[40])
    low_40 = float(df["low"].iloc[40])
    ema20_41 = float(ind.ema_slow.iloc[41])
    atr_41 = float(ind.atr.iloc[41])

    # Bar 40 (Large): SL anchored near candle low: low_40 - (0.05 * atr_40)
    expected_large_sl = round(low_40 - 0.05 * atr_40, 2)
    assert abs(sl_series.iloc[40] - expected_large_sl) < 1.0

    # Bar 41 (Small): SL anchored near 20 EMA: ema20_41 - (0.20 * atr_41)
    expected_small_sl = round(ema20_41 - 0.20 * atr_41, 2)
    assert abs(sl_series.iloc[41] - expected_small_sl) < 1.0


def test_5_multi_instrument_auto_dynamic_scaling():
    """Test 5: Adaptive SL and Chop Filter scale proportionally across NIFTY, BANKNIFTY, SENSEX, and Stocks."""
    instruments = {
        "NIFTY": {"base": 24000.0, "step": 5.0, "candle_size": 25.0},
        "BANKNIFTY": {"base": 51000.0, "step": 18.0, "candle_size": 85.0},
        "SENSEX": {"base": 80000.0, "step": 25.0, "candle_size": 130.0},
        "RELIANCE": {"base": 2900.0, "step": 1.0, "candle_size": 4.5},
    }

    cfg = Ema9RsiMomentumConfig(adaptive_sl_enabled=True)

    for name, params in instruments.items():
        prices = [params["base"] + i * params["step"] for i in range(45)]
        ranges = [params["candle_size"] * 0.8] * 44 + [params["candle_size"] * 1.5]
        df = create_ohlc_bars(prices, bar_ranges=ranges)
        ind = compute_indicator_set(df)

        signals = np.zeros(len(df), dtype=int)
        signals[-1] = 1  # CE Buy on last bar
        sl_series = compute_adaptive_stop_loss_series(df, ind, cfg, signals)

        # SL must be calculated and sit below entry price proportionally
        last_sl = sl_series.iloc[-1]
        last_close = df["close"].iloc[-1]
        assert not np.isnan(last_sl), f"{name} SL should not be NaN"
        assert last_sl < last_close, f"{name} SL ({last_sl}) must be below close ({last_close})"

        # Risk in points should scale with instrument price level
        risk_pts = last_close - last_sl
        assert risk_pts > 0
        if name == "SENSEX":
            assert risk_pts > 50.0  # SENSEX risk is tens of points
        elif name == "RELIANCE":
            assert risk_pts < 10.0  # Stock risk is small single-digit rupees


def test_6_strict_10_second_bar_close_timing():
    """Test 6: check_entry_timing allows entry strictly within the last 10 seconds of the candle."""
    cfg = Ema9RsiMomentumConfig(entry_confirm_seconds=10, require_bar_close_window=True)

    # 5-minute candle ending at 09:25:00
    # At 09:24:40 (20s remaining) -> NOT allowed
    now_early = datetime.datetime(2026, 10, 2, 9, 24, 40)
    allowed_early, reason_early = check_entry_timing(now_early, "VERY_STRONG", cfg, bar_minutes=5)
    assert allowed_early is False
    assert "waiting" in reason_early.lower()

    # At 09:24:52 (8s remaining <= 10s window) -> ALLOWED
    now_in_window = datetime.datetime(2026, 10, 2, 9, 24, 52)
    allowed_win, reason_win = check_entry_timing(now_in_window, "NORMAL", cfg, bar_minutes=5)
    assert allowed_win is True
    assert "confirmation window" in reason_win.lower()
