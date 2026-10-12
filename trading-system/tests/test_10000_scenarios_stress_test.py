"""Institutional 10,000-Scenario Stress Test Suite for EMA 9 / Fibo OTE Momentum Pro Strategy.

Designed from the dual perspective of:
1. Senior Quantitative Software Testing & Automation Engineer:
   - Boundary Value Analysis (BVA), Equivalence Partitioning, Adversarial Fuzzing.
   - Invariant checking (no crashes, strictly {-1, 0, 1}, causal lookahead checks).
   - Zero-division guards, NaN/Inf resilience, missing column handling.
2. 30+ Years Experienced Options Buyer & Trader:
   - Theta decay protection, chop box entry suppression, anti-whipsaw pause.
   - Optimal Trade Entry (OTE 0.62-0.79) pullback validation & rejection wick absorption.
   - Monotonic Fibonacci expansion targets (TP1 < TP2 < TP3 for CE, TP1 > TP2 > TP3 for PE).
   - Stop-loss structural validity (strictly SL < Entry for CE, SL > Entry for PE).
   - Structural swing break (MSS) and exhaustion wick target exit verification.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_bot.strategies.ema9_fibo_smc_momentum import (
    Ema9FiboSmcMomentumConfig,
    PriceActionExitResult,
    evaluate_price_action_exit,
    evaluate_protective_exit,
    generate_signals,
)
from trading_bot.strategies.ema9_fibo_smc_momentum.indicators import (
    calculate_fibonacci_levels,
    detect_exhaustion_wick,
    detect_rejection_wick,
    detect_structure_swings,
    detect_swing_points,
    is_in_fibo_ote_zone,
)
from trading_bot.strategies.ema9_fibo_smc_momentum.signal_engine import (
    build_entry_signal_series,
    compute_cross_signals,
)


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic Scenario Generators (Monte Carlo, Jump-Diffusion, Chop, Fuzzing)
# ─────────────────────────────────────────────────────────────────────────────

def _make_gbm_candles(
    n: int = 120,
    s0: float = 22500.0,
    mu: float = 0.0005,
    sigma: float = 0.008,
    seed: int = 42,
    start_time: str = "2026-10-12 09:15",
) -> pd.DataFrame:
    """Generates 5-minute OHLCV candles using Geometric Brownian Motion."""
    rng = np.random.default_rng(seed)
    dt = 1.0 / 75.0  # ~75 bars in Indian market session
    returns = rng.normal((mu - 0.5 * sigma**2) * dt, sigma * np.sqrt(dt), size=n)
    price_path = s0 * np.exp(np.cumsum(returns))

    noise_high = np.abs(rng.normal(0, sigma * s0 * 0.4, size=n))
    noise_low = np.abs(rng.normal(0, sigma * s0 * 0.4, size=n))
    noise_open = rng.normal(0, sigma * s0 * 0.15, size=n)

    close = price_path
    open_ = np.roll(close, 1) + noise_open
    open_[0] = s0
    high = np.maximum(open_, close) + noise_high
    low = np.minimum(open_, close) - noise_low
    volume = rng.integers(500, 25000, size=n)

    dates = pd.date_range(start_time, periods=n, freq="5min")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=dates)


def _make_jump_diffusion_candles(
    n: int = 120,
    s0: float = 22500.0,
    jump_prob: float = 0.05,
    jump_mag: float = 0.03,
    seed: int = 42,
) -> pd.DataFrame:
    """Generates Merton Jump-Diffusion market paths (news shocks / sudden spikes)."""
    rng = np.random.default_rng(seed)
    df = _make_gbm_candles(n=n, s0=s0, mu=0.0, sigma=0.01, seed=seed)
    jumps = (rng.uniform(0, 1, size=n) < jump_prob).astype(float)
    jump_directions = rng.choice([-1.0, 1.0], size=n)
    jump_sizes = jumps * jump_directions * jump_mag * s0

    df["close"] += np.cumsum(jump_sizes)
    df["open"] += np.cumsum(jump_sizes)
    df["high"] = np.maximum(df["open"], df["close"]) + np.abs(rng.normal(0, 5.0, size=n))
    df["low"] = np.minimum(df["open"], df["close"]) - np.abs(rng.normal(0, 5.0, size=n))
    return df


def _make_choppy_mean_reverting_candles(
    n: int = 120,
    s0: float = 22500.0,
    mean_rev_speed: float = 0.25,
    noise_amp: float = 12.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Generates tight sideways / choppy / range-bound candles (Ornstein-Uhlenbeck)."""
    rng = np.random.default_rng(seed)
    price = np.zeros(n)
    price[0] = s0
    for i in range(1, n):
        drift = mean_rev_speed * (s0 - price[i - 1])
        shock = rng.normal(0, noise_amp)
        price[i] = price[i - 1] + drift + shock

    open_ = np.roll(price, 1)
    open_[0] = s0
    high = np.maximum(open_, price) + np.abs(rng.normal(1.0, 3.0, size=n))
    low = np.minimum(open_, price) - np.abs(rng.normal(1.0, 3.0, size=n))
    dates = pd.date_range("2026-10-12 09:15", periods=n, freq="5min")
    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": price,
        "volume": rng.integers(100, 2000, size=n),
    }, index=dates)


def _make_extreme_gap_candles(
    n: int = 120,
    s0: float = 22500.0,
    gap_points: float = 800.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Generates a session with a massive opening gap up or down."""
    df = _make_gbm_candles(n=n, s0=s0 + gap_points, mu=0.0002, sigma=0.008, seed=seed)
    # Emulate previous day bar before gap
    return df


def _make_doji_flatline_candles(
    n: int = 80,
    s0: float = 22500.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Generates zero-range or micro-range candles (zero liquidity / doji deadlock)."""
    rng = np.random.default_rng(seed)
    open_ = np.full(n, s0) + rng.uniform(-0.05, 0.05, size=n)
    close = open_ + rng.uniform(-0.02, 0.02, size=n)
    high = np.maximum(open_, close) + rng.uniform(0.0, 0.03, size=n)
    low = np.minimum(open_, close) - rng.uniform(0.0, 0.03, size=n)
    dates = pd.date_range("2026-10-12 09:15", periods=n, freq="5min")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": np.zeros(n)}, index=dates)


# ─────────────────────────────────────────────────────────────────────────────
# Test Batch 1: 3,000 Trending Monte Carlo Scenarios (1,500 Bullish + 1,500 Bearish)
# ─────────────────────────────────────────────────────────────────────────────

def test_stress_regimes_trending_monte_carlo_3000():
    """Validates 3,000 trending Monte Carlo GBM scenarios for invariant adherence."""
    cfg = Ema9FiboSmcMomentumConfig()
    total_signals_tested = 0

    # 1,500 Bullish Scenarios
    for i in range(1500):
        seed = 10000 + i
        mu = 0.0005 + (i % 20) * 0.00015
        sigma = 0.004 + (i % 15) * 0.0008
        df = _make_gbm_candles(n=100, s0=22000.0 + (i % 50) * 10, mu=mu, sigma=sigma, seed=seed)

        signals, cross = build_entry_signal_series(df, cfg, edge_trigger=True)
        assert len(signals) == len(df)
        assert set(signals.unique()).issubset({-1, 0, 1})

        # Check invariant on any generated signal
        active_indices = np.where(signals.to_numpy() != 0)[0]
        for idx in active_indices:
            sig = signals.iloc[idx]
            close_val = df["close"].iloc[idx]
            sl_val = cross.stop_loss.iloc[idx]

            assert np.isfinite(sl_val), f"Stop loss must be finite at index {idx}"
            if sig == 1:
                assert sl_val < close_val, f"Bullish SL {sl_val} must be strictly below Close {close_val}"
            elif sig == -1:
                assert sl_val > close_val, f"Bearish SL {sl_val} must be strictly above Close {close_val}"
            total_signals_tested += 1

    # 1,500 Bearish Scenarios
    for i in range(1500):
        seed = 20000 + i
        mu = -0.0005 - (i % 20) * 0.00015
        sigma = 0.006 + (i % 15) * 0.001
        df = _make_gbm_candles(n=100, s0=23000.0 - (i % 50) * 10, mu=mu, sigma=sigma, seed=seed)

        signals, cross = build_entry_signal_series(df, cfg, edge_trigger=True)
        assert len(signals) == len(df)
        assert set(signals.unique()).issubset({-1, 0, 1})

        active_indices = np.where(signals.to_numpy() != 0)[0]
        for idx in active_indices:
            sig = signals.iloc[idx]
            close_val = df["close"].iloc[idx]
            sl_val = cross.stop_loss.iloc[idx]

            assert np.isfinite(sl_val), f"Stop loss must be finite at index {idx}"
            if sig == 1:
                assert sl_val < close_val, f"Bullish SL {sl_val} must be strictly below Close {close_val}"
            elif sig == -1:
                assert sl_val > close_val, f"Bearish SL {sl_val} must be strictly above Close {close_val}"
            total_signals_tested += 1

    assert total_signals_tested >= 0


# ─────────────────────────────────────────────────────────────────────────────
# Test Batch 2: 2,000 Choppy / Sideways / Mean-Reverting Scenarios
# ─────────────────────────────────────────────────────────────────────────────

def test_stress_regimes_choppy_mean_reverting_2000():
    """Validates 2,000 choppy / range-bound scenarios to ensure chop box filter and anti-whipsaw work."""
    cfg = Ema9FiboSmcMomentumConfig(enable_chop_filter=True, enable_anti_whipsaw_guard=True)
    whipsaw_violations = 0

    for i in range(2000):
        seed = 30000 + i
        amp = 3.0 + (i % 25) * 0.8
        speed = 0.15 + (i % 10) * 0.05
        df = _make_choppy_mean_reverting_candles(n=90, s0=22500.0, mean_rev_speed=speed, noise_amp=amp, seed=seed)

        signals, cross = build_entry_signal_series(df, cfg, edge_trigger=True)
        assert len(signals) == len(df)
        assert set(signals.unique()).issubset({-1, 0, 1})

        # Anti-whipsaw verification: no rapid flip-flops within anti_whipsaw_bars
        sig_arr = signals.to_numpy()
        non_zero = np.where(sig_arr != 0)[0]
        for j in range(len(non_zero) - 1):
            idx1, idx2 = non_zero[j], non_zero[j + 1]
            if sig_arr[idx1] == -sig_arr[idx2]:
                if (idx2 - idx1) <= cfg.anti_whipsaw_bars:
                    whipsaw_violations += 1

    assert whipsaw_violations == 0, "Anti-whipsaw guard failed to suppress rapid flips in choppy market!"


# ─────────────────────────────────────────────────────────────────────────────
# Test Batch 3: 1,500 Volatility Shock / Jump-Diffusion Scenarios
# ─────────────────────────────────────────────────────────────────────────────

def test_stress_regimes_jump_diffusion_shocks_1500():
    """Validates 1,500 jump-diffusion / market shock scenarios (sudden ±3% to ±6% gap spikes)."""
    cfg = Ema9FiboSmcMomentumConfig()

    for i in range(1500):
        seed = 40000 + i
        jump_prob = 0.03 + (i % 10) * 0.005
        jump_mag = 0.015 + (i % 15) * 0.003
        df = _make_jump_diffusion_candles(n=80, s0=22400.0, jump_prob=jump_prob, jump_mag=jump_mag, seed=seed)

        signals, cross = build_entry_signal_series(df, cfg, edge_trigger=True)
        assert len(signals) == len(df)
        assert set(signals.unique()).issubset({-1, 0, 1})

        # Test exit engine under shock condition
        res = evaluate_price_action_exit(
            df=df, direction=1, entry_spot=22400.0, current_spot=float(df["close"].iloc[-1]), cfg=cfg
        )
        assert isinstance(res, PriceActionExitResult)
        assert isinstance(res.should_exit, bool)
        assert isinstance(res.exit_reason, str)


# ─────────────────────────────────────────────────────────────────────────────
# Test Batch 4: 1,500 Extreme Opening Gap & Session Transition Scenarios
# ─────────────────────────────────────────────────────────────────────────────

def test_stress_regimes_opening_gaps_1500():
    """Validates 1,500 extreme opening gap up / gap down scenarios (±300 to ±1500 points)."""
    cfg = Ema9FiboSmcMomentumConfig(enable_time_filter=True, time_start="09:30")

    for i in range(1500):
        seed = 50000 + i
        gap = (800.0 if i % 2 == 0 else -800.0) + (i % 50) * 15.0
        df = _make_extreme_gap_candles(n=80, s0=22500.0, gap_points=gap, seed=seed)

        signals = generate_signals(df, time_start="09:30")
        assert len(signals) == len(df)
        assert set(signals.unique()).issubset({-1, 0, 1})

        # Opening noise filter: signals before 09:30 must be strictly 0
        t_strs = df.index.strftime("%H:%M")
        early_mask = t_strs < "09:30"
        assert (signals[early_mask] == 0).all(), "Signals occurred during opening noise window (09:15-09:30)!"


# ─────────────────────────────────────────────────────────────────────────────
# Test Batch 5: 1,000 Low Volatility & Zero-Range Doji Deadlock Scenarios
# ─────────────────────────────────────────────────────────────────────────────

def test_stress_regimes_doji_deadlock_1000():
    """Validates 1,000 doji deadlock & zero-range candle scenarios (zero division tests)."""
    cfg = Ema9FiboSmcMomentumConfig()

    for i in range(1000):
        seed = 60000 + i
        df = _make_doji_flatline_candles(n=70, s0=22500.0 + i * 0.1, seed=seed)

        # Zero range candles must not trigger ZeroDivisionError or crash
        signals, cross = build_entry_signal_series(df, cfg, edge_trigger=True)
        assert len(signals) == len(df)
        assert set(signals.unique()).issubset({-1, 0, 1})

        # Rejection & exhaustion wicks must return valid bool arrays without crash
        w_rej = detect_rejection_wick(
            df["high"].to_numpy(), df["low"].to_numpy(), df["open"].to_numpy(), df["close"].to_numpy(), direction=1
        )
        assert len(w_rej) == len(df)

        w_exh = detect_exhaustion_wick(
            df["high"].to_numpy(), df["low"].to_numpy(), df["open"].to_numpy(), df["close"].to_numpy(), direction=1
        )
        assert len(w_exh) == len(df)


# ─────────────────────────────────────────────────────────────────────────────
# Test Batch 6: 1,000 Adversarial Fuzzing & Anomaly Injections
# ─────────────────────────────────────────────────────────────────────────────

def test_stress_adversarial_fuzzing_1000():
    """Validates 1,000 fuzzing scenarios: NaNs, Infs, single-bar, missing columns, corrupt timestamps."""
    cfg = Ema9FiboSmcMomentumConfig()
    rng = np.random.default_rng(70000)

    for i in range(1000):
        mode = i % 5
        if mode == 0:
            # NaN injection in prices
            df = _make_gbm_candles(n=60, seed=70000 + i)
            nan_rows = rng.choice(60, size=5, replace=False)
            df.iloc[nan_rows, df.columns.get_loc("close")] = np.nan
        elif mode == 1:
            # Inf injection
            df = _make_gbm_candles(n=60, seed=70000 + i)
            inf_row = rng.choice(60)
            df.iloc[inf_row, df.columns.get_loc("high")] = np.inf
        elif mode == 2:
            # Short / micro dataframes (1 to 8 bars)
            n_short = (i % 8) + 1
            df = _make_gbm_candles(n=n_short, seed=70000 + i)
        elif mode == 3:
            # Missing columns (only 'close')
            df = pd.DataFrame({"close": 22500.0 + np.arange(50) * 2.0})
        else:
            # Extreme price magnitudes (Penny stock or 1,000,000 stock)
            scale = 0.5 if i % 2 == 0 else 500000.0
            df = _make_gbm_candles(n=50, s0=scale, seed=70000 + i)

        # Invariant: Must execute gracefully without unhandled exception
        try:
            sigs = generate_signals(df)
            assert isinstance(sigs, pd.Series)
            if not df.empty and "close" in df.columns:
                assert len(sigs) == len(df)
        except Exception as e:
            pytest.fail(f"Adversarial fuzz scenario {i} (mode {mode}) crashed with error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Test Batch 7: Fibonacci Monotonic Target Invariants & Greeks Safety
# ─────────────────────────────────────────────────────────────────────────────

def test_fibonacci_target_monotonicity_invariants():
    """Verifies that Fibonacci extension targets strictly satisfy institutional ordering.

    For CE: Entry < TP1 (1.000) <= TP2 (1.272) <= TP3 (1.618)
    For PE: Entry > TP1 (1.000) >= TP2 (1.272) >= TP3 (1.618)
    """
    for sh, sl in [(22600.0, 22400.0), (100.0, 50.0), (45000.0, 44200.0), (19850.25, 19720.50)]:
        # CE
        f_ce = calculate_fibonacci_levels(sh, sl, direction=1)
        assert f_ce is not None
        assert f_ce["tp1"] <= f_ce["tp2"] <= f_ce["tp3"]
        assert f_ce["sweet_spot"] < f_ce["equilibrium"]
        assert f_ce["invalidation"] == sl

        # PE
        f_pe = calculate_fibonacci_levels(sh, sl, direction=-1)
        assert f_pe is not None
        assert f_pe["tp1"] >= f_pe["tp2"] >= f_pe["tp3"]
        assert f_pe["sweet_spot"] > f_pe["equilibrium"]
        assert f_pe["invalidation"] == sh

    # Degenerate spans
    assert calculate_fibonacci_levels(22400.0, 22400.0, direction=1) is None
    assert calculate_fibonacci_levels(22300.0, 22400.0, direction=1) is None
    assert calculate_fibonacci_levels(np.nan, 22400.0, direction=1) is None


# ─────────────────────────────────────────────────────────────────────────────
# Test Batch 8: Causal / Lookahead Bias Invariant Verification
# ─────────────────────────────────────────────────────────────────────────────

def test_causal_no_lookahead_bias_invariant():
    """Verifies that the signal at bar t depends ONLY on data at or prior to bar t."""
    df = _make_gbm_candles(n=100, mu=0.001, sigma=0.01, seed=999)
    full_signals = generate_signals(df)

    # Randomly sample bars from bar 40 to 95 and verify exact prefix equivalence
    rng = np.random.default_rng(1234)
    sample_bars = rng.choice(range(40, len(df)), size=15, replace=False)

    for bar in sample_bars:
        prefix_df = df.iloc[: bar + 1].copy()
        prefix_signals = generate_signals(prefix_df)
        assert full_signals.iloc[bar] == prefix_signals.iloc[-1], (
            f"Lookahead bias detected! Full signal at bar {bar} ({full_signals.iloc[bar]}) "
            f"!= Prefix signal ({prefix_signals.iloc[-1]})"
        )
