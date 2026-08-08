"""Counterfactual exit replay — isolates the exit mechanism.

Holds every ENTRY the strategy actually took fixed (same bar, same
contract, same premium, same initial stop, same quantity) and re-runs
ONLY `SmartExitEngine` over the same reconstructed premium path under a
different engine configuration.

Why this exists: a full harness re-run changes exit times, which changes
when the strategy is next flat, which changes which later signals become
trades, which changes position sizing through `RiskManager`. That is the
right way to measure a shipped change — and it is the wrong way to
*attribute* a difference to the exit rule, because entry composition
moved too. This replay answers the narrower question exactly: given the
identical set of positions, what does each exit rule do?

It is a SCREEN, not a verdict. Anything it likes must still be proved by
a full 123-day validation run.

The replay is faithful, not approximate: it drives the real
`SmartExitEngine`, the real `Position`, the real `resolve_option_atr`,
and premium candles built exactly as `harness.py` builds them
(open=high=low=close=premium, one per 5-minute bar).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from shared.exits.exit_engine import Position, SmartExitEngine
from shared.risk import resolve_initial_stop, resolve_option_atr

from .exit_quality import _premium_at, _premium_series, reconstruct_contract
from .premium_simulator import DEFAULT_IV

__all__ = ["ReplayPosition", "replay_positions", "summarise_replay"]


@dataclass
class ReplayLeg:
    exit_time: pd.Timestamp
    exit_premium: float
    quantity: int
    reason: str
    pnl: float


@dataclass
class ReplayPosition:
    symbol: str
    entry_time: pd.Timestamp
    entry_premium: float
    quantity: int
    legs: list


def _positions_from_trades(trades) -> list[dict]:
    """Regroup `SimTrade` legs back into the positions that produced them,
    recovering each position's ORIGINAL full quantity (a partial booking
    splits it across legs)."""
    grouped: dict[tuple, list] = {}
    for t in trades:
        grouped.setdefault((t.symbol, str(t.entry_time)), []).append(t)
    out = []
    for (symbol, _k), legs in grouped.items():
        legs = sorted(legs, key=lambda t: pd.Timestamp(t.exit_time))
        head = legs[0]
        out.append({
            "trade": head,
            "symbol": symbol,
            "entry_time": pd.Timestamp(head.entry_time),
            "entry_premium": head.entry_premium,
            "quantity": sum(l.quantity for l in legs),
            "lot_size": head.lot_size,
        })
    return sorted(out, key=lambda p: p["entry_time"])


def replay_positions(
    trades,
    underlying: pd.DataFrame,
    engine_kwargs: Optional[dict] = None,
    settings: Optional[dict] = None,
    vol: float = DEFAULT_IV,
    instrument: str = "NIFTY",
    itm_strikes: int = 1,
) -> list[ReplayPosition]:
    settings = dict(settings or {})
    engine = SmartExitEngine(**{"atr_multiplier": 1.5, "partial_booking_pct": 50.0,
                                **(engine_kwargs or {})})
    idx = underlying.index
    results: list[ReplayPosition] = []

    for p in _positions_from_trades(trades):
        contract = reconstruct_contract(p["trade"], underlying, instrument, itm_strikes)
        if contract is None:
            continue
        entry_t, entry_prem = p["entry_time"], p["entry_premium"]
        day_bars = underlying.loc[(idx > entry_t) & (idx.date == entry_t.date())]
        if day_bars.empty:
            continue
        prem_path = _premium_series(contract, day_bars, vol)

        sl = resolve_initial_stop(entry_prem, settings)
        pos = Position(
            symbol=p["symbol"], side=1, entry_price=entry_prem, quantity=p["quantity"],
            entry_time=entry_t.isoformat(), highest_price=entry_prem, lowest_price=entry_prem,
            stop_loss=sl.sl_price, target=0.0, lot_size=p["lot_size"],
        )
        candles = [{"timestamp": entry_t, "open": entry_prem, "high": entry_prem,
                    "low": entry_prem, "close": entry_prem, "volume": 0}]
        legs: list[ReplayLeg] = []

        for ts, premium in prem_path.items():
            candles.append({"timestamp": ts, "open": premium, "high": premium,
                            "low": premium, "close": premium, "volume": 0})
            option_df = pd.DataFrame(candles).set_index("timestamp")
            atr = resolve_option_atr(option_df, premium, settings).atr_value
            should_exit, reason, exit_qty = engine.evaluate_exit(
                pos, premium, ts.strftime("%H:%M:%S"), atr
            )
            if not should_exit:
                continue
            qty = exit_qty or pos.quantity
            legs.append(ReplayLeg(ts, premium, qty, reason, (premium - entry_prem) * qty))
            if qty >= pos.quantity:
                break
            pos.quantity -= qty

        if not legs or sum(l.quantity for l in legs) < p["quantity"]:
            # Never fully closed inside the day's remaining bars — close at the
            # last available premium, mirroring the harness's END_OF_DATA path.
            remaining = p["quantity"] - sum(l.quantity for l in legs)
            if remaining > 0 and len(prem_path):
                last_t, last_p = prem_path.index[-1], float(prem_path.iloc[-1])
                legs.append(ReplayLeg(last_t, last_p, remaining, "END_OF_DATA",
                                      (last_p - entry_prem) * remaining))

        results.append(ReplayPosition(p["symbol"], entry_t, entry_prem, p["quantity"], legs))

    return results


def summarise_replay(positions: list[ReplayPosition], underlying: pd.DataFrame,
                     vol: float = DEFAULT_IV, instrument: str = "NIFTY",
                     itm_strikes: int = 1) -> dict:
    """Aggregate P&L / capture stats for one replay configuration.

    NOTE `max_drawdown_pct` here is a per-position-sequence drawdown on the
    replayed P&L stream with the entry set held fixed. It is comparable
    BETWEEN replay configurations, and is NOT the same quantity as the
    validation report's drawdown (which is produced by the day-isolated
    run with its own risk manager). Never quote it against that.
    """
    rows = []
    for p in positions:
        pnl = sum(l.pnl for l in p.legs)
        realised_pct = pnl / (p.entry_premium * p.quantity) * 100.0
        final = p.legs[-1] if p.legs else None
        rows.append({
            "symbol": p.symbol, "entry_time": p.entry_time,
            "exit_time": final.exit_time if final else None,
            "pnl": pnl, "realised_pct": realised_pct,
            "final_reason": final.reason if final else None,
            "legs": len(p.legs),
            "holding_minutes": ((final.exit_time - p.entry_time).total_seconds() / 60.0)
            if final else None,
        })
    df = pd.DataFrame(rows).sort_values("exit_time")
    wins, losses = df[df.pnl > 0], df[df.pnl < 0]
    equity = df.pnl.cumsum()
    peak = equity.cummax()
    return {
        "positions": len(df),
        "net_pnl": df.pnl.sum(),
        "win_rate": (df.pnl > 0).mean() * 100.0,
        "profit_factor": (wins.pnl.sum() / abs(losses.pnl.sum())) if len(losses) and losses.pnl.sum() else float("inf"),
        "avg_win": wins.pnl.mean() if len(wins) else 0.0,
        "avg_loss": losses.pnl.mean() if len(losses) else 0.0,
        "median_realised_pct": df.realised_pct.median(),
        "median_hold_min": df.holding_minutes.median(),
        "max_drawdown_pct": ((peak - equity).max() / 100_000.0 * 100.0) if len(df) else 0.0,
        "reason_mix": df.final_reason.value_counts().to_dict(),
        "_df": df,
    }
