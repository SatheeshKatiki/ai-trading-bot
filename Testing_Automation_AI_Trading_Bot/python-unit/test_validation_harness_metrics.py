"""Unit tests for validation_harness/metrics.py -- the metrics battery
computed from a list of SimTrade for the Production Strategy Validation
Framework.
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from validation_harness.harness import SimTrade
from validation_harness.metrics import compute_metrics


def _trade(pnl: float, holding_minutes: float = 10.0) -> SimTrade:
    return SimTrade(
        symbol="NSE:NIFTY2681126950PE", direction="PE",
        entry_time="2026-08-07T10:00:00", entry_premium=100.0,
        exit_time="2026-08-07T10:10:00", exit_premium=100.0 + pnl,
        quantity=1, lot_size=65, pnl=pnl, exit_reason="Stop-Loss Hit",
        holding_minutes=holding_minutes, sl_method="banded", sl_band_label="₹100-150",
    )


def test_no_trades_returns_zeroed_neutral_metrics():
    m = compute_metrics([], 100_000.0)
    assert m["trade_count"] == 0
    assert m["net_profit"] == 0.0
    assert m["profit_factor"] is None
    assert m["win_rate_pct"] is None


def test_all_winners_gives_infinite_profit_factor():
    trades = [_trade(100.0), _trade(200.0)]
    m = compute_metrics(trades, 100_000.0)
    assert m["profit_factor"] == "Infinity"
    assert m["win_rate_pct"] == 100.0
    assert m["net_profit"] == 300.0


def test_all_losers_gives_zero_profit_factor():
    trades = [_trade(-100.0), _trade(-50.0)]
    m = compute_metrics(trades, 100_000.0)
    assert m["profit_factor"] == 0.0
    assert m["win_rate_pct"] == 0.0
    assert m["net_profit"] == -150.0


def test_mixed_trades_profit_factor_and_win_rate():
    trades = [_trade(100.0), _trade(100.0), _trade(-50.0)]
    m = compute_metrics(trades, 100_000.0)
    assert m["trade_count"] == 3
    assert m["win_rate_pct"] == round(2 / 3 * 100, 1)
    assert m["profit_factor"] == round(200.0 / 50.0, 2)
    assert m["net_profit"] == 150.0


def test_max_drawdown_computed_from_equity_curve():
    # +1000, then -2000 (drawdown from peak 101000 to 99000 = ~1.98%), then +500
    trades = [_trade(1000.0), _trade(-2000.0), _trade(500.0)]
    m = compute_metrics(trades, 100_000.0)
    expected_dd_pct = round((101_000 - 99_000) / 101_000 * 100, 2)
    assert m["max_drawdown_pct"] == expected_dd_pct


def test_max_consecutive_losses_counts_correctly():
    trades = [_trade(10), _trade(-1), _trade(-1), _trade(-1), _trade(10), _trade(-1)]
    m = compute_metrics(trades, 100_000.0)
    assert m["max_consecutive_losses"] == 3


def test_a_zero_pnl_trade_counts_as_a_loss_not_a_win():
    """pnl <= 0 is the loss bucket (matches RiskManager.record_trade's own
    `if trade.pnl < 0` vs this module's `<= 0` convention deliberately --
    a breakeven trade is not a statistical win)."""
    trades = [_trade(0.0), _trade(10.0)]
    m = compute_metrics(trades, 100_000.0)
    assert m["win_rate_pct"] == 50.0


def test_expectancy_matches_hand_computed_value():
    trades = [_trade(100.0), _trade(100.0), _trade(-50.0), _trade(-50.0)]
    m = compute_metrics(trades, 100_000.0)
    # win_prob=0.5, avg_win=100, loss_prob=0.5, avg_loss=50
    # expectancy = 0.5*100 - 0.5*50 = 25
    assert m["expectancy"] == 25.0


def test_avg_holding_minutes():
    trades = [_trade(10, holding_minutes=10.0), _trade(10, holding_minutes=30.0)]
    m = compute_metrics(trades, 100_000.0)
    assert m["avg_holding_minutes"] == 20.0
