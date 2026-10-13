"""Unit tests for EMA 9 / Fibo OTE Momentum Pro Strategy (Pure Price Action Primary)."""

import numpy as np
import pandas as pd
import pytest

from trading_bot.strategies.registry import registry
from trading_bot.strategies.ema9_fibo_smc_momentum import (
    STRATEGY_NAME,
    STRATEGY_LABEL,
    generate_signals,
    evaluate_protective_exit,
    evaluate_price_action_exit,
    PriceActionExitResult,
    Ema9FiboSmcMomentumConfig,
)
from trading_bot.strategies.ema9_fibo_smc_momentum.indicators import (
    calculate_fibonacci_levels,
    detect_exhaustion_wick,
    detect_rejection_wick,
    detect_rsi_divergence,
    detect_structure_swings,
    detect_swing_points,
    is_in_fibo_ote_zone,
)


def _make_test_df(n: int = 120, trend: str = "bullish") -> pd.DataFrame:
    """Creates synthetic 5-minute OHLCV candles."""
    dates = pd.date_range("2026-10-12 09:15", periods=n, freq="5min")
    step = 4.0 if trend == "bullish" else -4.0 if trend == "bearish" else 0.0
    rng = np.random.default_rng(42)
    base = 22500.0 + np.arange(n) * step + rng.normal(0, 1.5, n)

    df = pd.DataFrame({
        "open": base - 1.0,
        "high": base + 4.0,
        "low": base - 4.0,
        "close": base,
        "volume": rng.integers(1000, 10000, n),
    }, index=dates)
    return df


def test_registry_registration():
    """Verify that the new strategy is cleanly registered and existing strategy is intact."""
    registered = registry.registered_strategies
    assert "ema9_fibo_smc_momentum" in registered, "New strategy not auto-discovered!"
    assert "ema9_rsi_momentum" in registered, "Existing EMA9 strategy was disturbed!"
    assert STRATEGY_NAME == "ema9_fibo_smc_momentum"
    assert STRATEGY_LABEL == "EMA 9 / Fibo OTE Momentum Pro"


def test_fibonacci_math_calculation():
    """Test OTE and extension levels calculation."""
    swing_high = 22600.0
    swing_low = 22400.0

    # Bullish (Buying Calls on Discount Pullback)
    fibo_ce = calculate_fibonacci_levels(swing_high, swing_low, direction=1)
    assert fibo_ce is not None
    assert fibo_ce["equilibrium"] == 22500.0           # 50%
    assert fibo_ce["sweet_spot"] == 22459.0            # 70.5%
    assert fibo_ce["ote_low"] == 22476.0               # 62%
    assert fibo_ce["ote_high"] == 22442.0              # 79%
    assert fibo_ce["tp2"] == 22654.4                   # 1.272 extension
    assert fibo_ce["tp3"] == 22723.6                   # 1.618 golden extension


def test_is_in_fibo_ote_zone():
    """Test detection of candle retesting the 0.62 - 0.79 OTE zone."""
    swing_high = 22600.0
    swing_low = 22400.0

    assert is_in_fibo_ote_zone(
        bar_high=22510.0, bar_low=22460.0, bar_close=22480.0,
        swing_high=swing_high, swing_low=swing_low, direction=1
    ) is True

    assert is_in_fibo_ote_zone(
        bar_high=22550.0, bar_low=22520.0, bar_close=22540.0,
        swing_high=swing_high, swing_low=swing_low, direction=1
    ) is False


def test_rejection_wick_detection():
    """Test candlestick rejection wick indicating institutional absorption."""
    # Bullish Hammer / Pinbar: high=100, low=80, open=95, close=98 (lower wick = 95 - 80 = 15; span = 20; ratio = 75%)
    high = np.array([100.0])
    low = np.array([80.0])
    open_ = np.array([95.0])
    close = np.array([98.0])

    assert bool(detect_rejection_wick(high, low, open_, close, direction=1, min_wick_ratio=0.30)[0]) is True
    # Bearish Shooting star should be False for CE
    assert bool(detect_rejection_wick(high, low, open_, close, direction=-1, min_wick_ratio=0.30)[0]) is False


def test_exhaustion_wick_detection():
    """Test exhaustion wick detection at key resistance/support."""
    # Shooting Star at resistance: high=100, low=80, open=82, close=84 (upper wick = 100 - 84 = 16; span = 20; ratio = 80%)
    high = np.array([100.0])
    low = np.array([80.0])
    open_ = np.array([82.0])
    close = np.array([84.0])

    # For open CE position (direction=1), upper wick indicates exhaustion
    assert bool(detect_exhaustion_wick(high, low, open_, close, direction=1, min_ratio=0.40)[0]) is True


def test_price_action_exit_structural_break():
    """Test Price Action exit on Market Structure Break (MSS)."""
    df = _make_test_df(60, trend="bullish")
    cfg = Ema9FiboSmcMomentumConfig()

    # In intact uptrend, should not exit
    res_hold = evaluate_price_action_exit(
        df=df, direction=1, entry_spot=22500.0, current_spot=22700.0, cfg=cfg
    )
    assert res_hold.should_exit is False

    # Simulate sudden breakdown bar breaching recent Higher Low
    df_break = df.copy()
    recent_low = df_break["low"].min()
    # Force last bar to close below recent low
    df_break.iloc[-1, df_break.columns.get_loc("close")] = recent_low - 50.0

    res_exit = evaluate_price_action_exit(
        df=df_break, direction=1, entry_spot=22500.0, current_spot=recent_low - 50.0, cfg=cfg
    )
    assert res_exit.should_exit is True
    assert "Structural Swing Break" in res_exit.exit_reason


def test_opening_range_filter_suppression():
    """Verify that signals before 09:30 are blocked by default."""
    df = _make_test_df(80, trend="bullish")
    signals = generate_signals(df, time_start="09:30")
    assert isinstance(signals, pd.Series)
    assert len(signals) == len(df)

    t_strs = df.index.strftime("%H:%M")
    early_mask = t_strs < "09:30"
    assert (signals[early_mask] == 0).all(), "Signals occurred before 09:30!"


def test_generate_signals_execution():
    """Test full signal generation pipeline across bullish and bearish series."""
    df_bull = _make_test_df(100, trend="bullish")
    sig_bull = generate_signals(df_bull, price_action_primary=True)
    assert set(sig_bull.unique()).issubset({-1, 0, 1})

    df_bear = _make_test_df(100, trend="bearish")
    sig_bear = generate_signals(df_bear, price_action_primary=True)
    assert set(sig_bear.unique()).issubset({-1, 0, 1})


def test_config_fields_and_from_settings():
    """Verify that Ema9FiboSmcMomentumConfig has all required execution fields and handles settings dicts cleanly."""
    cfg = Ema9FiboSmcMomentumConfig.from_settings({
        "timeframe": "15 Min",
        "initial_sl_pct": 12.5,
        "decay_low_pct": -8.0,
    })
    assert cfg.initial_sl_pct == 12.5
    assert cfg.timeframe_minutes == 15
    assert cfg.decay_low_pct == -8.0
    assert hasattr(cfg, "profit_ladder_pct")
    assert hasattr(cfg, "decay_moderate_pct")
    assert hasattr(cfg, "decay_high_pct")


def test_evaluate_protective_exit_with_dict_and_decay():
    """Verify that evaluate_protective_exit accepts a raw settings dictionary and evaluates cleanly without AttributeError."""
    df = _make_test_df(60, trend="bullish")
    raw_settings = {
        "timeframe": "5 Min",
        "price_action_primary": True,
        "initial_sl_pct": 15.0,
    }
    # Test CE side
    res_ce = evaluate_protective_exit(
        df=df,
        side=1,
        entry_premium=100.0,
        current_premium=95.0,
        settings=raw_settings,
    )
    assert res_ce is not None
    assert isinstance(res_ce.should_exit, bool)

    # Test PE side
    res_pe = evaluate_protective_exit(
        df=df,
        side=-1,
        entry_premium=100.0,
        current_premium=95.0,
        settings=raw_settings,
    )
    assert res_pe is not None
    assert isinstance(res_pe.should_exit, bool)


def test_ladder_ratchet_stop():
    """Verify the exit ladder ratchet stops correctly step up and never move backwards."""
    from trading_bot.strategies.ema9_fibo_smc_momentum.exit_ladder import initial_stop, ratchet_stop
    entry = 100.0
    sl = initial_stop(entry, initial_sl_pct=15.0, tick=0.05)
    assert sl == 85.0

    # Premium moves to 120 (+20% -> hits 15% rung -> SL moves to breakeven 100.0)
    ladder = (15.0, 33.0, 50.0, 75.0, 100.0)
    new_sl, next_rung = ratchet_stop(entry, current_stop=sl, best_price=120.0, rungs=ladder, initial_sl_pct=15.0)
    assert new_sl == 100.0
    assert next_rung == 133.0

    # Premium moves to 140 (+40% -> hits 33% rung -> SL moves to 115.0)
    new_sl, next_rung = ratchet_stop(entry, current_stop=new_sl, best_price=140.0, rungs=ladder, initial_sl_pct=15.0)
    assert new_sl == 115.0
    assert next_rung == 150.0


def test_position_key_normalization_and_safe_pop():
    """Verify that normalized instrument matching catches aliases and pop() removes cleanly without KeyError."""
    from shared.instruments import normalize_instrument

    active_positions = {
        "NIFTY50": {"symbol": "NSE:NIFTY26OCT22500CE", "qty": 65},
    }

    sym = "NSE:NIFTY50-INDEX"
    # Key lookup simulation
    found_key = None
    for k in active_positions:
        if k == sym or normalize_instrument(k) == normalize_instrument(sym):
            found_key = k
            break

    assert found_key == "NIFTY50"

    # Safe removal
    active_positions.pop(found_key, None)
    active_positions.pop(sym, None)
    assert len(active_positions) == 0

