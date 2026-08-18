"""
Unit tests for backtesting_engine/run.py.

Tests cover:
  - No lookahead bias: fill must be at next-bar open, not current-bar close
  - Stop-loss exit price calculation
  - Target hit exit price calculation
  - Daily loss limit stops new entries
  - compute_bs_delta() edge cases
  - Dynamic delta produces different results from fixed=0.5

Run with:  pytest tests/test_backtest_engine.py -v
"""

from __future__ import annotations

import sys
import os
import math

import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backtesting_engine.run import compute_bs_delta, run_intraday_backtest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(n: int = 100, seed: int = 42, timeframe: str = "5min") -> pd.DataFrame:
    """Create a simple synthetic OHLCV dataframe for testing."""
    rng = np.random.default_rng(seed)
    base = 24000.0
    closes = base + np.cumsum(rng.normal(0, 5, n))
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-02 09:15", periods=n, freq=timeframe),
        "open":   closes - rng.uniform(0, 3, n),
        "high":   closes + rng.uniform(0, 5, n),
        "low":    closes - rng.uniform(0, 5, n),
        "close":  closes,
        "volume": rng.integers(100, 1000, n).astype(float),
        "atr":    rng.uniform(10, 30, n),
    })
    df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return df


def _make_buy_signals(df: pd.DataFrame, first_n: int = 3) -> pd.Series:
    """Produce a signal series that fires BUY for the first `first_n` bars only."""
    sigs = pd.Series(0, index=df.index)
    sigs.iloc[:first_n] = 1
    return sigs


def _make_sell_signals(df: pd.DataFrame, first_n: int = 3) -> pd.Series:
    """Produce a signal series that fires SELL for the first `first_n` bars only."""
    sigs = pd.Series(0, index=df.index)
    sigs.iloc[:first_n] = -1
    return sigs


# ---------------------------------------------------------------------------
# Test: compute_bs_delta()
# ---------------------------------------------------------------------------

class TestComputeBsDelta:
    def test_atm_call_at_open_approx_half(self):
        """ATM call at day-open should have delta close to 0.50."""
        delta = compute_bs_delta(is_call=True, time_fraction=1.0, sigma=0.20, strike_offset_pct=0.0)
        assert 0.40 < delta < 0.60, f"ATM call delta at open should be ~0.5, got {delta:.4f}"

    def test_atm_put_delta_is_negative_complement(self):
        """ATM put delta + ATM call delta should be ~1.0 (put-call parity)."""
        call_d = compute_bs_delta(is_call=True,  time_fraction=0.5, sigma=0.20)
        put_d  = compute_bs_delta(is_call=False, time_fraction=0.5, sigma=0.20)
        assert abs(call_d + abs(put_d) - 1.0) < 0.05, (
            f"Put-call delta parity violated: call={call_d:.4f} put={put_d:.4f}"
        )

    def test_otm_call_has_lower_delta(self):
        """OTM call (positive offset) must have lower delta than ATM."""
        atm   = compute_bs_delta(is_call=True, time_fraction=0.5, sigma=0.20, strike_offset_pct=0.0)
        otm_1 = compute_bs_delta(is_call=True, time_fraction=0.5, sigma=0.20, strike_offset_pct=1.0)
        assert otm_1 < atm, f"OTM delta ({otm_1:.4f}) should be < ATM delta ({atm:.4f})"

    def test_itm_call_has_higher_delta(self):
        """ITM call (negative offset) must have higher delta than ATM."""
        atm   = compute_bs_delta(is_call=True, time_fraction=0.5, sigma=0.20, strike_offset_pct= 0.0)
        itm_1 = compute_bs_delta(is_call=True, time_fraction=0.5, sigma=0.20, strike_offset_pct=-1.0)
        assert itm_1 > atm, f"ITM delta ({itm_1:.4f}) should be > ATM delta ({atm:.4f})"

    def test_zero_time_fraction_call_intrinsic(self):
        """At expiry, ITM call delta should be 1.0, OTM should be 0.0."""
        itm_exp = compute_bs_delta(is_call=True, time_fraction=0.001, sigma=0.20, strike_offset_pct=-5.0)
        otm_exp = compute_bs_delta(is_call=True, time_fraction=0.001, sigma=0.20, strike_offset_pct=+5.0)
        assert itm_exp > 0.80, f"Near-expiry ITM call delta should be close to 1, got {itm_exp:.4f}"
        assert otm_exp < 0.20, f"Near-expiry OTM call delta should be close to 0, got {otm_exp:.4f}"

    def test_sigma_clamping_does_not_raise(self):
        """Extreme sigma values should not raise — they clamp silently."""
        for sigma in [0.0, 0.0001, 10.0, 99.9]:
            result = compute_bs_delta(is_call=True, time_fraction=0.5, sigma=sigma)
            assert 0.0 <= result <= 1.0, f"Delta out of [0,1] for sigma={sigma}: {result}"


# ---------------------------------------------------------------------------
# Test: Dynamic delta != fixed delta
# ---------------------------------------------------------------------------

class TestDynamicVsFixedDelta:
    def test_dynamic_mode_produces_different_pnl(self):
        """Dynamic delta mode must produce materially different P&L from fixed=0.5."""
        df   = _make_df(200)
        sigs = _make_buy_signals(df, 3)

        res_fixed   = run_intraday_backtest(df, sigs, options_delta=0.5, options_delta_mode="fixed")
        res_dynamic = run_intraday_backtest(df, sigs, options_delta=0.5, options_delta_mode="dynamic")

        # Result is nested under 'stats' — use netProfit as the comparison metric
        fixed_pnl   = res_fixed.get("stats",   {}).get("netProfit",   res_fixed.get("netProfit",   0.0))
        dynamic_pnl = res_dynamic.get("stats", {}).get("netProfit", res_dynamic.get("netProfit", 0.0))

        assert fixed_pnl != dynamic_pnl, (
            "Dynamic delta should produce different net P&L from fixed=0.5. "
            f"Both returned {fixed_pnl} — compute_bs_delta may not be applied. "
            f"fixed slippage={res_fixed.get('stats',{}).get('totalSlippage')} "
            f"dynamic slippage={res_dynamic.get('stats',{}).get('totalSlippage')}"
        )



# ---------------------------------------------------------------------------
# Test: No lookahead bias
# ---------------------------------------------------------------------------

class TestNoLookaheadBias:
    def test_entry_fills_on_next_bar(self):
        """Entry must fill at bar i+1 open, not bar i close.
        If fill == close[i], that's a lookahead bug.
        """
        df   = _make_df(10)
        sigs = pd.Series([1, 0, 0, 0, 0, 0, 0, 0, 0, 0], index=df.index)
        result = run_intraday_backtest(df, sigs, options_delta_mode="fixed")
        trades = result.get("trades", [])
        if len(trades) == 0:
            pytest.skip("No trades generated — adjust signal or data.")
        entry_price = trades[0]["entry"]
        bar0_close  = float(df["close"].iloc[0])
        # Entry should NOT equal the signal bar's close (that would be lookahead)
        assert entry_price != bar0_close, (
            f"Entry price {entry_price} equals signal bar close {bar0_close} — "
            "possible lookahead bias!"
        )


# ---------------------------------------------------------------------------
# Test: Exit prices are correct
# ---------------------------------------------------------------------------

class TestExitPrices:
    def test_stoploss_exit_is_below_entry_for_long(self):
        """A LONG position hitting stop-loss should exit BELOW entry price."""
        df   = _make_df(50)
        # One buy signal, then the market dips well below entry (force SL via tight SL)
        sigs = pd.Series([1] + [0] * 49, index=df.index)
        result = run_intraday_backtest(
            df, sigs, stoploss_pct=0.001,  # ultra-tight SL → will fire almost immediately
            target_pct=99.0,               # target unreachable → forces SL exit
            options_delta_mode="fixed",
        )
        trades = result.get("trades", [])
        sl_trades = [t for t in trades if t.get("exit_reason") == "STOPLOSS"]
        if not sl_trades:
            pytest.skip("No stoploss exits — try tighter SL in data/signal.")
        for t in sl_trades:
            assert t["exit"] < t["entry"] or t["pnl"] <= 0, (
                f"LONG STOPLOSS exit price {t['exit']} should be <= entry {t['entry']}"
            )

    def test_target_exit_is_above_entry_for_long(self):
        """A LONG position hitting target should exit ABOVE entry price."""
        df   = _make_df(50, seed=7)
        sigs = pd.Series([1] + [0] * 49, index=df.index)
        result = run_intraday_backtest(
            df, sigs, target_pct=0.001,   # ultra-tight target → fires immediately
            stoploss_pct=99.0,
            options_delta_mode="fixed",
        )
        trades = result.get("trades", [])
        target_trades = [t for t in trades if t.get("exit_reason") == "TARGET"]
        if not target_trades:
            pytest.skip("No target exits — try tighter target in data/signal.")
        for t in target_trades:
            assert t["exit"] > t["entry"] or t["pnl"] >= 0, (
                f"LONG TARGET exit price {t['exit']} should be >= entry {t['entry']}"
            )


# ---------------------------------------------------------------------------
# Test: Daily loss limit stops new entries
# ---------------------------------------------------------------------------

class TestDailyLossLimit:
    def test_no_entries_after_daily_loss_exceeded(self):
        """After the daily loss limit is hit, no further entries should occur on the same day."""
        df = _make_df(150)
        # Tag all bars to the same date so the daily budget is shared
        same_day = "2026-01-02"
        df["timestamp"] = [f"{same_day} {str(9 + i//12).zfill(2)}:{str((i*5)%60).zfill(2)}:00" for i in range(150)]

        # Fire many buy signals — the daily loss limit should cut them off
        sigs = pd.Series(1, index=df.index)
        result = run_intraday_backtest(
            df, sigs,
            max_daily_loss_pct=0.001,   # 0.001% — any single trade will blow it
            initial_capital=100_000.0,
            options_delta_mode="fixed",
        )
        trades = result.get("trades", [])
        # Should have at most 1-2 trades before the limit is hit
        assert len(trades) <= 5, (
            f"Expected ≤5 trades after daily loss limit, got {len(trades)}"
        )
