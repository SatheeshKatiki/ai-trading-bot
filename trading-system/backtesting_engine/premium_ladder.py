"""Backtest ema9_rsi_momentum on ITS OWN exits, on the option premium.

``/api/backtest`` and grid_search ran every strategy through
``run_intraday_backtest``, whose exits are in UNDERLYING percent -- the
dashboard's stoploss 0.6% / target 2.5% -- scaled by delta. A backtest of
ema9 therefore tested a strategy nobody trades. This engine applies the
strategy's real exits to a premium path:

* SL ``initial_sl_pct`` (15%) under entry, then the owner's ratcheting
  ladder (``exit_ladder.py``) -- no fixed target;
* the EMA/RSI reversal on closed bars (``compute_reversal_signals``);
* the 15:15 square-off; one position at a time; the daily trade cap and the
  daily loss stop.

Premium model, stated rather than hidden: ATM, delta 0.5; premium at entry
= ``option_premium_pct`` of spot (run.py's OPTION_COST_PROFILES); each bar
moves it by delta x spot move and decays it by ``option_theta_pct_per_day``
across the 375-minute session; entry pays half the round-trip spread and
exit gives up the other half. Within a bar the adverse extreme is taken
first. Gamma and IV changes are not modelled -- the paper books measure
those on live quotes. This is the same model as the harness behind every
number in the anomaly log.
"""

from __future__ import annotations

import statistics
from typing import List, Optional

import numpy as np
import pandas as pd

from backtesting_engine.run import _compute_profit_factor, option_cost_profile
from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig
from trading_bot.strategies.ema9_rsi_momentum.exit_ladder import ladder_levels, stop_reason
from trading_bot.strategies.ema9_rsi_momentum.signal_engine import compute_reversal_signals

DELTA = 0.5
SESSION_MINUTES = 375.0
EOD_CUTOFF = "15:15"


def _frame(df: pd.DataFrame) -> pd.DataFrame:
    """OHLC indexed by bar time (the handler's frame carries a 'datetime' column)."""
    out = df.copy()
    out.columns = [str(c).lower() for c in out.columns]
    if "datetime" in out.columns:
        out.index = pd.DatetimeIndex(pd.to_datetime(out["datetime"]))
    elif not isinstance(out.index, pd.DatetimeIndex):
        raise ValueError("premium-ladder backtest needs a 'datetime' column or a DatetimeIndex")
    for col in ("open", "high", "low", "close"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def run_premium_ladder_backtest(
    df: pd.DataFrame,
    signals,
    symbol: str = "NIFTY",
    initial_capital: float = 100_000.0,
    quantity: int = 65,
    max_daily_trades: int = 6,
    max_daily_loss_pct: float = 3.0,
    commission_per_trade: float = 20.0,
    settings: Optional[dict] = None,
    rejection_logs: Optional[list] = None,
    bar_minutes: float = 5.0,
) -> dict:
    """Same result shape as ``run_intraday_backtest``: stats, equityCurve,
    trades, rejectionLogs. ``signals`` is aligned to ``df`` by position."""
    cfg = Ema9RsiMomentumConfig.from_settings(settings or {})
    cost = option_cost_profile(symbol)
    premium_pct = float(cost["option_premium_pct"])
    spread_pct = float(cost["option_spread_pct"])
    theta_pct_day = float(cost["option_theta_pct_per_day"])

    frame = _frame(df)
    sig = np.asarray(getattr(signals, "values", signals), dtype=float)
    sig = np.nan_to_num(sig).astype(int)
    n = min(len(frame), len(sig))
    rev = compute_reversal_signals(frame, cfg)
    bull, bear = np.asarray(rev.bullish, dtype=bool), np.asarray(rev.bearish, dtype=bool)
    high, low, close = frame["high"].to_numpy(), frame["low"].to_numpy(), frame["close"].to_numpy()
    times = frame.index
    hhmm = times.strftime("%H:%M")
    day = times.normalize()
    loss_limit = initial_capital * max_daily_loss_pct / 100.0

    capital = initial_capital
    trades: List[dict] = []
    equity = [{"name": str(times[0]) if n else "", "value": round(capital, 2)}]
    day_trades: dict = {}
    day_pnl: dict = {}
    spread_total = theta_total = brokerage_total = 0.0

    i = 0
    while i < n - 1:
        side = sig[i]
        if side == 0 or hhmm[i] >= EOD_CUTOFF or day[i + 1] != day[i]:
            i += 1
            continue
        d = day[i]
        if day_trades.get(d, 0) >= max_daily_trades or day_pnl.get(d, 0.0) <= -loss_limit:
            i += 1
            continue

        spot0 = close[i]
        prem0 = spot0 * premium_pct / 100.0
        to_pct = DELTA / prem0 * 100.0
        stop_pct, best, exit_pct, reason = -cfg.initial_sl_pct, 0.0, None, ""
        k = i + 1
        while k < n and day[k] == d:
            decay = theta_pct_day * (k - i) * bar_minutes / SESSION_MINUTES
            fav = ((high[k] - spot0) if side > 0 else (spot0 - low[k])) * to_pct - decay
            adv = ((spot0 - low[k]) if side > 0 else (high[k] - spot0)) * to_pct + decay
            at_close = (close[k] - spot0) * side * to_pct - decay
            if -adv <= stop_pct:
                exit_pct, reason = stop_pct, stop_reason(100.0, 100.0 + stop_pct)
                break
            if (bear if side > 0 else bull)[k]:
                exit_pct, reason = at_close, "REVERSAL EXIT"
                break
            if hhmm[k] >= EOD_CUTOFF:
                exit_pct, reason = at_close, "EOD 15:15"
                break
            best = max(best, fav)
            stop_pct = max(stop_pct, ladder_levels(best, cfg.profit_ladder_pct, cfg.initial_sl_pct)[0])
            k += 1
        if exit_pct is None:                       # data ended inside the session
            k = min(k, n) - 1
            decay = theta_pct_day * (k - i) * bar_minutes / SESSION_MINUTES
            exit_pct, reason = (close[k] - spot0) * side * to_pct - decay, "END OF DATA"

        entry_prem = prem0 * (1 + spread_pct / 200.0)
        exit_prem = max(0.05, prem0 * (1 + exit_pct / 100.0)) * (1 - spread_pct / 200.0)
        pnl = (exit_prem - entry_prem) * quantity - 2 * commission_per_trade
        capital += pnl
        spread_total += prem0 * spread_pct / 100.0 * quantity
        theta_total += prem0 * theta_pct_day * (k - i) * bar_minutes / SESSION_MINUTES / 100.0 * quantity
        brokerage_total += 2 * commission_per_trade
        trades.append({
            "id": f"T-{len(trades) + 1}",
            "type": "BUY" if side > 0 else "SELL",       # BUY = call, SELL = put, as the UI reads it
            "entry": round(entry_prem, 2),
            "exit": round(exit_prem, 2),
            "qty": quantity,
            "scales": 0,
            "pnl": round(pnl, 2),
            "time": str(times[i]),
            "exit_time": str(times[k]),
            "score": 0,
            "exit_reason": reason,
            "return_pct": round((exit_prem - entry_prem) / entry_prem * 100.0, 2),
            "best_pct": round(best, 2),
        })
        equity.append({"name": str(times[k]), "value": round(capital, 2)})
        day_trades[d] = day_trades.get(d, 0) + 1
        day_pnl[d] = day_pnl.get(d, 0.0) + pnl
        i = k + 1

    return {
        "stats": _stats(trades, equity, initial_capital, capital, cfg, cost, brokerage_total,
                        spread_total, theta_total, bar_minutes, len(set(day[:n])) if n else 0),
        "equityCurve": equity,
        "trades": trades,
        "rejectionLogs": rejection_logs or [],
    }


def _stats(trades, equity, initial_capital, capital, cfg, cost, brokerage, spread, theta, bar_minutes, days):
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    values = np.array([e["value"] for e in equity], dtype=float)
    max_dd = float((np.maximum.accumulate(values) - values).max()) if len(values) else 0.0
    daily: dict = {}
    for t in trades:
        daily[t["time"][:10]] = daily.get(t["time"][:10], 0.0) + t["pnl"]
    dvals = list(daily.values())
    sd = statistics.pstdev(dvals) if len(dvals) > 1 else 0.0
    downside = [v for v in dvals if v < 0]
    dd_sd = statistics.pstdev(downside) if len(downside) > 1 else 0.0
    mean_day = statistics.mean(dvals) if dvals else 0.0
    return {
        "exitModel": "premium_ladder",
        "profitFactor": _compute_profit_factor(sum(wins), abs(sum(losses))),
        "winRate": f"{(len(wins) / len(trades) * 100):.1f}" if trades else "0.0",
        "totalTrades": len(trades),
        "totalTradingDays": days,
        "successTrades": len(wins),
        "failedTrades": len(losses),
        "stoplossTrades": sum(1 for t in trades if t["exit_reason"] == "STOP LOSS"),
        "maxDrawdown": -round(max_dd, 2),
        "netProfit": round(capital - initial_capital, 2),
        "avgWinScore": "0.0",
        "avgLossScore": "0.0",
        "expectancy": round(statistics.mean(pnls), 2) if pnls else 0.0,
        "sharpeRatio": round(mean_day / sd * np.sqrt(252), 2) if sd > 0 else 0.0,
        "sortinoRatio": round(mean_day / dd_sd * np.sqrt(252), 2) if dd_sd > 0 else 0.0,
        "targetPct": None,                               # no fixed target: the ladder
        "stoplossPct": cfg.initial_sl_pct,
        "profitLadderPct": list(cfg.profit_ladder_pct),
        "exitMix": {r: sum(1 for t in trades if t["exit_reason"] == r) for r in {t["exit_reason"] for t in trades}},
        "donchianPeriod": None,
        "totalBrokerage": round(brokerage, 2),
        "totalSlippage": 0.0,
        "totalSpreadCost": round(spread, 2),
        "totalThetaCost": round(theta, 2),
        "optionCostsModelled": True,
        "optionCostParams": {
            "premium_pct": cost["option_premium_pct"],
            "spread_pct": cost["option_spread_pct"],
            "theta_pct_per_day": cost["option_theta_pct_per_day"],
            "bar_minutes": bar_minutes,
            "delta": DELTA,
        },
        "compoundingEnabled": False,
        "maxCompoundFactorReached": 1.0,
    }
