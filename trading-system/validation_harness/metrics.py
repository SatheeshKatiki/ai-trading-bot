"""Performance metrics battery computed from a `harness.BacktestResult`.

Pure functions, no I/O — takes a `list[SimTrade]`, returns a plain dict so
callers (the per-regime runner, the report generator) don't need to know
this module's internals.
"""
from __future__ import annotations

from typing import Any

from .harness import SimTrade

__all__ = ["compute_metrics"]


def compute_metrics(trades: list[SimTrade], initial_capital: float) -> dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {
            "trade_count": 0, "net_profit": 0.0, "net_profit_pct": 0.0,
            "profit_factor": None, "win_rate_pct": None, "expectancy": None,
            "max_drawdown_pct": 0.0, "recovery_factor": None,
            "max_consecutive_losses": 0, "avg_trade": None,
            "avg_holding_minutes": None, "avg_risk_reward": None,
        }

    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    net_profit = sum(pnls)
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    win_rate = len(wins) / n * 100.0

    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

    avg_win = (gross_profit / len(wins)) if wins else 0.0
    avg_loss = (gross_loss / len(losses)) if losses else 0.0
    win_prob = len(wins) / n
    loss_prob = len(losses) / n
    expectancy = (win_prob * avg_win) - (loss_prob * avg_loss)

    # Equity curve + drawdown, trade-sequenced (not time-sequenced — trades
    # are already chronological since the harness walks bars in order).
    equity = initial_capital
    peak = initial_capital
    max_dd_pct = 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        if peak > 0:
            dd_pct = (peak - equity) / peak * 100.0
            max_dd_pct = max(max_dd_pct, dd_pct)

    max_dd_abs = max_dd_pct / 100.0 * initial_capital if max_dd_pct else 0.0
    recovery_factor = (net_profit / max_dd_abs) if max_dd_abs > 0 else (float("inf") if net_profit > 0 else 0.0)

    max_consec_losses = 0
    running = 0
    for p in pnls:
        if p <= 0:
            running += 1
            max_consec_losses = max(max_consec_losses, running)
        else:
            running = 0

    avg_trade = net_profit / n
    avg_holding = sum(t.holding_minutes for t in trades) / n

    # Realized risk:reward — average win size in units of average loss
    # size (the standard "R-multiple" reading of win/loss magnitude,
    # not a per-trade recomputation of the initial SL distance, which
    # SimTrade doesn't carry).
    avg_risk_reward = (avg_win / avg_loss) if avg_loss > 0 else None

    return {
        "trade_count": n,
        "net_profit": round(net_profit, 2),
        "net_profit_pct": round(net_profit / initial_capital * 100.0, 2) if initial_capital else 0.0,
        "profit_factor": round(profit_factor, 2) if profit_factor not in (float("inf"),) else "Infinity",
        "win_rate_pct": round(win_rate, 1),
        "expectancy": round(expectancy, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "recovery_factor": round(recovery_factor, 2) if recovery_factor not in (float("inf"),) else "Infinity",
        "max_consecutive_losses": max_consec_losses,
        "avg_trade": round(avg_trade, 2),
        "avg_holding_minutes": round(avg_holding, 1),
        "avg_risk_reward": round(avg_risk_reward, 2) if avg_risk_reward is not None else None,
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
    }
