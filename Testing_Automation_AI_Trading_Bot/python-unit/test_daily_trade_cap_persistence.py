"""Regression tests for the live engine's daily-trade-cap restart
persistence (trading_bot/main.py's _count_trades_already_executed_today).

Root-cause fix (found live, 2026-08-05): RiskManager.trades_today is a
pure in-memory list that always starts empty, unlike daily_pnl/equity
(already fixed for this same restart-persistence reason on 2026-08-05).
Any restart during a trading day silently reset the day's trade count to
zero, letting the engine place MORE real trades than the configured daily
cap intended -- confirmed live: a routine bug-fix redeploy let 3 additional
trades through after the real 3-trade cap had already been hit hours
earlier. This function reconstructs today's real trade count from
state.db's raw per-leg trade rows so it can be restored across a restart.
"""
import sys
from pathlib import Path

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from trading_bot.main import _count_trades_already_executed_today


TODAY = "2026-08-05"


def _row(symbol, side, time, price=100.0):
    return {"symbol": symbol, "side": side, "price": price, "time": time, "qty": 65}


def test_counts_option_sell_rows_as_completed_exits():
    trades = [
        _row("NSE:NIFTY2681124550PE", "BUY", f"{TODAY}T09:20:00+05:30"),
        _row("NSE:NIFTY2681124550PE", "SELL", f"{TODAY}T09:25:00+05:30"),
        _row("NSE:NIFTY2681124600CE", "BUY", f"{TODAY}T10:00:00+05:30"),
        _row("NSE:NIFTY2681124600CE", "SELL", f"{TODAY}T10:05:00+05:30"),
    ]
    assert _count_trades_already_executed_today(trades, TODAY) == 2


def test_does_not_count_entry_buy_rows():
    trades = [_row("NSE:NIFTY2681124550PE", "BUY", f"{TODAY}T09:20:00+05:30")]
    assert _count_trades_already_executed_today(trades, TODAY) == 0


def test_ignores_trades_from_a_different_day():
    trades = [
        _row("NSE:NIFTY2681124550PE", "SELL", "2026-08-04T09:25:00+05:30"),
        _row("NSE:NIFTY2681124550PE", "SELL", f"{TODAY}T09:25:00+05:30"),
    ]
    assert _count_trades_already_executed_today(trades, TODAY) == 1


def test_ignores_non_option_symbols():
    # Only options are counted -- this system only ever buys options, so a
    # non-option SELL row isn't a real exit under the current strategy set.
    trades = [_row("NSE:NIFTY50-INDEX", "SELL", f"{TODAY}T09:25:00+05:30")]
    assert _count_trades_already_executed_today(trades, TODAY) == 0


def test_counts_partial_scale_out_exits_separately():
    # A scaled position can exit in multiple SELL legs -- each one is a
    # separate risk_manager.record_trade() call and must count separately.
    trades = [
        _row("NSE:NIFTY2681124550PE", "BUY", f"{TODAY}T09:20:00+05:30"),
        _row("NSE:NIFTY2681124550PE", "SELL", f"{TODAY}T09:25:00+05:30"),
        _row("NSE:NIFTY2681124550PE", "SELL", f"{TODAY}T09:30:00+05:30"),
    ]
    assert _count_trades_already_executed_today(trades, TODAY) == 2


def test_empty_trades_list_counts_zero():
    assert _count_trades_already_executed_today([], TODAY) == 0


def test_reproduces_the_live_incident_scenario():
    # The exact shape of today's real trades: 3 completed round trips
    # (6 rows) before a restart -- the cap must see 3, not 0.
    trades = [
        _row("NSE:NIFTY2681124550PE", "BUY", f"{TODAY}T13:45:00+05:30"),
        _row("NSE:NIFTY2681124550PE", "SELL", f"{TODAY}T13:45:02+05:30"),
        _row("NSE:NIFTY2681124550PE", "BUY", f"{TODAY}T13:45:07+05:30"),
        _row("NSE:NIFTY2681124550PE", "SELL", f"{TODAY}T13:45:07+05:30"),
        _row("NSE:NIFTY2681124550PE", "BUY", f"{TODAY}T13:45:10+05:30"),
        _row("NSE:NIFTY2681124550PE", "SELL", f"{TODAY}T13:45:16+05:30"),
    ]
    assert _count_trades_already_executed_today(trades, TODAY) == 3


if __name__ == "__main__":
    test_counts_option_sell_rows_as_completed_exits()
    test_does_not_count_entry_buy_rows()
    test_ignores_trades_from_a_different_day()
    test_ignores_non_option_symbols()
    test_counts_partial_scale_out_exits_separately()
    test_empty_trades_list_counts_zero()
    test_reproduces_the_live_incident_scenario()
    print("All daily-trade-cap persistence tests passed.")
