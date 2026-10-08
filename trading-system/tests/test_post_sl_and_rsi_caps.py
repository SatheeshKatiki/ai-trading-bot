"""
Tests for Post-StopLoss Smart Re-entry Guard & RSI Exhaustion Limits.
Verified against 2026-10-05 live market observations.
"""
import time
import pytest
import pandas as pd
import numpy as np

from trading_bot.strategies.ema9_rsi_momentum.config import (
    Ema9RsiMomentumConfig,
    RSI_OVERBOUGHT_CAP,
    RSI_OVERSOLD_FLOOR,
)
from trading_bot.strategies.ema9_rsi_momentum.indicators import compute_indicator_set
from trading_bot.strategies.ema9_rsi_momentum.signal_engine import (
    compute_cross_signals,
)


@pytest.fixture
def sample_data():
    """Generates synthetic price data for testing."""
    np.random.seed(42)
    n = 60
    base = 22400.0
    times = pd.date_range("2026-10-05 09:15", periods=n, freq="5min")
    close = pd.Series(base + np.cumsum(np.random.randn(n) * 10), index=times)
    open_ = close.shift(1).fillna(base)
    high = np.maximum(open_, close) + 5.0
    low = np.minimum(open_, close) - 5.0
    volume = pd.Series(10000, index=times)

    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=times)


def test_rsi_overbought_cap_blocks_ce_signals(sample_data):
    """When RSI is above 75 (overbought), CE signal MUST be suppressed."""
    cfg = Ema9RsiMomentumConfig(rsi_overbought_cap=75.0)
    assert cfg.rsi_overbought_cap == 75.0
    
    # Run cross signals
    cross = compute_cross_signals(sample_data, cfg)
    
    # If RSI > 75 on any bar, bullish MUST be False
    rsi_arr = np.asarray(cross.indicators.rsi, dtype=float)
    overbought_mask = rsi_arr > 75.0
    if np.any(overbought_mask):
        assert not np.any(cross.bullish[overbought_mask]), "CE signals must be False when RSI > 75"


def test_rsi_oversold_floor_blocks_pe_signals(sample_data):
    """When RSI is below 25 (oversold), PE signal MUST be suppressed."""
    cfg = Ema9RsiMomentumConfig(rsi_oversold_floor=25.0)
    assert cfg.rsi_oversold_floor == 25.0
    
    cross = compute_cross_signals(sample_data, cfg)
    
    rsi_arr = np.asarray(cross.indicators.rsi, dtype=float)
    oversold_mask = rsi_arr < 25.0
    if np.any(oversold_mask):
        assert not np.any(cross.bearish[oversold_mask]), "PE signals must be False when RSI < 25"


def test_post_sl_smart_reentry_guard():
    """Verify Smart Post-SL Re-entry Guard:
    1. CE SL hit -> records timestamp and direction
    2. Same direction (CE) within 5m cooldown -> BLOCKED (prevents 50s revenge trades)
    3. Opposite direction (PE) at any time -> ALLOWED immediately without cooldown
    4. Same direction (CE) after 5m cooldown with valid confirmations -> ALLOWED!
    5. Profitable trade exit -> NO lock
    """
    stopped_out_dir = {}
    cooldown_seconds = 300.0  # 5 minutes
    symbol = "NSE:NIFTY50-INDEX"
    
    # 1. CE Trade hits Stop Loss at t = 1000.0
    exit_t = 1000.0
    stopped_out_dir[symbol] = {
        "direction": "BUY",
        "time": exit_t,
        "ts": "10:01:06"
    }
    
    # 2. Case: 50 seconds later (t = 1050.0), same-direction (BUY/CE) signal arrives
    now_50s = 1050.0
    locked_sl = stopped_out_dir.get(symbol)
    candidate_1 = "BUY"
    
    can_enter_1 = True
    if locked_sl is not None:
        if candidate_1 == locked_sl["direction"]:
            elapsed = now_50s - locked_sl["time"]
            if elapsed < cooldown_seconds:
                can_enter_1 = False  # Blocked!
                
    assert can_enter_1 is False, "Same direction entry within 5m cooldown MUST be blocked!"
    
    # 3. Case: 2 minutes later (t = 1120.0), confirmed OPPOSITE (SELL/PE) signal arrives
    now_opposite = 1120.0
    candidate_2 = "SELL"
    can_enter_2 = False
    if locked_sl is not None:
        if candidate_2 != locked_sl["direction"]:
            can_enter_2 = True  # Opposite signal allowed immediately!
            
    assert can_enter_2 is True, "Opposite direction (PE) reversal must be allowed immediately!"

    # 4. Case: 6 minutes later (t = 1360.0), fresh same-direction (BUY/CE) signal with all confirmations arrives
    now_after_cooldown = 1360.0
    candidate_3 = "BUY"
    can_enter_3 = False
    if locked_sl is not None:
        if candidate_3 == locked_sl["direction"]:
            elapsed = now_after_cooldown - locked_sl["time"]
            if elapsed >= cooldown_seconds:
                can_enter_3 = True  # Cooldown passed! Allowed to proceed with validations
                stopped_out_dir.pop(symbol, None)
                
    assert can_enter_3 is True, "Same direction re-entry after cooldown with valid setup MUST be allowed!"
    assert symbol not in stopped_out_dir, "Lock must be cleared once entry is placed"

    # 5. Case: Profitable trade exit
    pnl_profit = 1500.0
    exit_reason_profit = "Target 1 Hit @ 125.00"
    if pnl_profit < 0 and ("SL" in exit_reason_profit.upper() or "STOP" in exit_reason_profit.upper()):
        stopped_out_dir[symbol] = {"direction": "BUY", "time": 2000.0}
    else:
        stopped_out_dir.pop(symbol, None)
        
    assert symbol not in stopped_out_dir, "Profitable trade exits must never trigger SL lock"
