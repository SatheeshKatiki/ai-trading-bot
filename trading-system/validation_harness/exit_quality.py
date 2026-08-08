"""Exit-quality and trend/rally-capture diagnostic.

Read-only analysis. Reconstructs each simulated trade's full option-premium
path — during the hold AND after the exit — and measures what a P&L table
cannot:

  MFE            maximum favourable excursion while the position was open
  capture %      realised / MFE — how much of the move we actually kept
  give-back      MFE - exit, in premium %
  continuation   best premium at +5 / +15 / +30 / +60 min AFTER the exit
  trend capture  realised vs the FULL move still available to end-of-day
  missed upside  best premium in the 60 min after exit, vs the exit price

Contract reconstruction is exact, not inferred
---------------------------------------------
The premium path in `harness.py` is a deterministic function of the
underlying close:  `calculate_option_price(spot, strike, dte, vol, type)`.
So the path can be replayed exactly — provided the contract is known
exactly. Parsing it back out of the Fyers symbol is NOT sufficient: a
monthly symbol (`NIFTY26FEB25700CE`) encodes no expiry DAY, and guessing
it mis-priced 106 of ema_rsi's 528 legs by up to Rs 76 of premium.

Instead we replay the harness's own `select_option(instrument, spot,
direction, itm_strikes, from_date)` call with the entry bar's spot and
date, which returns the real `OptionContract` including its true expiry,
and assert the resulting entry premium reproduces the recorded one.
`verify_reconstruction()` runs that check over a whole trade set; on
ema_rsi it reproduces all 528 legs with 0.0 error.

Legs vs positions
-----------------
Partial Profit Booking closes 50% of a position and leaves the rest
open, so one POSITION can produce several `SimTrade` LEGS. Anything about
"did we exit the trend too early" is a position-level question, so legs
are grouped back into positions by (symbol, entry_time); leg-level rows
are kept as well for exit-mechanism analysis.

"Premature exit" is defined mechanically, not by opinion: an exit is
premature when the premium went on to exceed the exit price by more than
one tick within the following 60 minutes — i.e. the position was closed
into a move that was still running.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Optional

import pandas as pd

from trading_bot.strategies.premium_selection.options_selector import (
    _WEEKLY_MONTH_CODE,
    calculate_option_price,
    select_option,
)

from .premium_simulator import DEFAULT_IV

__all__ = [
    "ParsedContract",
    "parse_option_symbol",
    "reconstruct_contract",
    "verify_reconstruction",
    "analyse_exit_quality",
]

_MONTH_ABBR = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}
_CODE_TO_MONTH = {v: k for k, v in _WEEKLY_MONTH_CODE.items()}

_WEEKLY_RE = re.compile(r"^[A-Z]+:([A-Z]+)(\d{2})([1-9OND])(\d{2})(\d+)(CE|PE)$")
_MONTHLY_RE = re.compile(r"^[A-Z]+:([A-Z]+)(\d{2})([A-Z]{3})(\d+)(CE|PE)$")

#: The engine settings `harness.py` instantiates `SmartExitEngine` with,
#: mirrored here so the diagnostic can report "when did trailing arm"
#: without re-running the backtest. Kept in one place so a drift between
#: this module and the harness is a one-line fix, not a hunt.
TRAILING_ACTIVATION_PCT = 1.0     # SmartExitEngine default
TRAILING_OFFSET_PCT = 0.35        # SmartExitEngine default
PARTIAL_TARGET_REWARD = 1.0       # SmartExitEngine default


@dataclass(frozen=True)
class ParsedContract:
    instrument: str
    expiry: date
    strike: float
    option_type: str


def parse_option_symbol(symbol: str) -> Optional[ParsedContract]:
    """Recover (instrument, expiry, strike, type) from a Fyers option
    symbol built by `options_selector._build_symbol`. Returns None if the
    symbol is not an option contract.

    NOTE the monthly-expiry limitation documented in the module docstring —
    prefer `reconstruct_contract`, which is exact.
    """
    m = _WEEKLY_RE.match(symbol)
    if m:
        instrument, yy, mcode, dd, strike, otype = m.groups()
        month = _CODE_TO_MONTH.get(mcode)
        if month is None:
            return None
        return ParsedContract(instrument, date(2000 + int(yy), month, int(dd)), float(strike), otype)

    m = _MONTHLY_RE.match(symbol)
    if m:
        instrument, yy, mon, strike, otype = m.groups()
        month = _MONTH_ABBR.get(mon)
        if month is None:
            return None
        # Monthly contracts encode no day; the expiry day is NOT recoverable
        # from the symbol alone. Last-day-of-month is an upper bound only.
        nxt = date(2000 + int(yy) + (month // 12), (month % 12) + 1, 1)
        return ParsedContract(instrument, nxt - pd.Timedelta(days=1).to_pytimedelta(), float(strike), otype)

    return None


def reconstruct_contract(
    trade, underlying: pd.DataFrame, instrument: str = "NIFTY", itm_strikes: int = 1
) -> Optional[ParsedContract]:
    """Recover the EXACT contract a trade was opened on by replaying the
    harness's own `select_option` call for the entry bar. Returns None if
    the entry bar is missing from `underlying` or the replay produces a
    different symbol (which would mean the trade set and the price data
    disagree — the caller should treat that as a hard error, not skip it)."""
    entry_t = pd.Timestamp(trade.entry_time)
    if entry_t not in underlying.index:
        return None
    spot = float(underlying.at[entry_t, "close"])
    contract = select_option(
        instrument, spot, trade.direction, itm_strikes=itm_strikes, from_date=entry_t.date()
    )
    if contract.symbol != trade.symbol:
        return None
    return ParsedContract(instrument, contract.expiry, float(contract.strike), contract.option_type)


def verify_reconstruction(trades, underlying: pd.DataFrame, instrument: str = "NIFTY",
                          vol: float = DEFAULT_IV, itm_strikes: int = 1) -> dict:
    """Prove the premium path can be replayed before any conclusion is drawn
    from it: re-price every leg's ENTRY bar from the reconstructed contract
    and compare against the premium the harness actually recorded."""
    worst = 0.0
    failed = 0
    for t in trades:
        contract = reconstruct_contract(t, underlying, instrument, itm_strikes)
        if contract is None:
            failed += 1
            continue
        entry_t = pd.Timestamp(t.entry_time)
        p = _premium_at(contract, float(underlying.at[entry_t, "close"]), entry_t, vol)
        worst = max(worst, abs(p - t.entry_premium))
    return {"legs": len(trades), "unreconstructable": failed, "max_entry_premium_error": worst}


def _premium_at(contract: ParsedContract, spot: float, when: pd.Timestamp, vol: float) -> float:
    dte = max((contract.expiry - when.date()).days, 0)
    return calculate_option_price(spot, contract.strike, dte, vol, contract.option_type)


def _premium_series(contract: ParsedContract, bars: pd.DataFrame, vol: float) -> pd.Series:
    return pd.Series(
        [_premium_at(contract, float(c), ts, vol) for ts, c in zip(bars.index, bars["close"])],
        index=bars.index,
    )


def _pct(a: float, b: float) -> float:
    """(a - b) / b as a percentage."""
    return (a - b) / b * 100.0 if b else float("nan")


def analyse_exit_quality(
    trades,
    underlying: pd.DataFrame,
    vol: float = DEFAULT_IV,
    horizons: Iterable[int] = (5, 15, 30, 60),
    instrument: str = "NIFTY",
    itm_strikes: int = 1,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (legs, positions).

    `legs`      — one row per `SimTrade` (a partial booking and the exit of
                  the remainder are two rows), for exit-MECHANISM analysis.
    `positions` — one row per real position (legs regrouped), for
                  trend-CAPTURE analysis: how much of the move that was
                  actually available did this position end up with.
    """
    horizons = tuple(horizons)
    idx = underlying.index

    # Group legs into positions. `SimTrade.entry_time` is carried unchanged
    # from `Position.entry_time` across a partial booking, so (symbol,
    # entry_time) identifies a position exactly.
    grouped: dict[tuple[str, Any], list] = {}
    for t in trades:
        grouped.setdefault((t.symbol, str(t.entry_time)), []).append(t)

    leg_rows: list[dict] = []
    pos_rows: list[dict] = []

    for (symbol, _entry_key), legs in grouped.items():
        legs = sorted(legs, key=lambda t: pd.Timestamp(t.exit_time))
        head = legs[0]
        contract = reconstruct_contract(head, underlying, instrument, itm_strikes)
        if contract is None:
            continue

        entry_t = pd.Timestamp(head.entry_time)
        entry_prem = head.entry_premium
        final = legs[-1]
        final_exit_t = pd.Timestamp(final.exit_time)

        # Full premium path for this contract from entry to the end of the
        # entry day. Intraday system — a position is never carried overnight,
        # so the day boundary is the honest limit of "what was available".
        day_bars = underlying.loc[(idx >= entry_t) & (idx.date == entry_t.date())]
        if day_bars.empty:
            continue
        day_prem = _premium_series(contract, day_bars, vol)

        # ── leg-level ────────────────────────────────────────────────
        for leg in legs:
            exit_t = pd.Timestamp(leg.exit_time)
            hold = day_prem.loc[(day_prem.index >= entry_t) & (day_prem.index <= exit_t)]
            if hold.empty:
                continue
            mfe, mae = hold.max(), hold.min()
            favourable = mfe - entry_prem
            row = {
                "symbol": symbol,
                "entry_time": entry_t,
                "exit_time": exit_t,
                "exit_reason": leg.exit_reason,
                "exit_reason_class": _classify_reason(leg.exit_reason),
                "entry": entry_prem,
                "exit": leg.exit_premium,
                "quantity": leg.quantity,
                "pnl": leg.pnl,
                "sl_band_label": leg.sl_band_label,
                "sl_method": leg.sl_method,
                "bars_held": len(hold) - 1,
                "mfe_pct": _pct(mfe, entry_prem),
                "mae_pct": _pct(mae, entry_prem),
                "realised_pct": _pct(leg.exit_premium, entry_prem),
                "capture_pct": ((leg.exit_premium - entry_prem) / favourable * 100.0)
                if favourable > 1e-9 else None,
                "giveback_pct": _pct(mfe, entry_prem) - _pct(leg.exit_premium, entry_prem),
            }
            # When did the percentage trailing stop ARM (profit >= activation)?
            hold_profit = (hold - entry_prem) / entry_prem * 100.0
            armed = hold_profit[hold_profit >= TRAILING_ACTIVATION_PCT]
            row["armed"] = not armed.empty
            row["bars_to_arm"] = (
                int((hold.index < armed.index[0]).sum()) if not armed.empty else None
            )
            row["bars_armed_before_exit"] = (
                int((hold.index >= armed.index[0]).sum()) - 1 if not armed.empty else None
            )
            row.update(_continuation(day_prem, exit_t, leg.exit_premium, horizons))
            leg_rows.append(row)

        # ── position-level ───────────────────────────────────────────
        hold = day_prem.loc[(day_prem.index >= entry_t) & (day_prem.index <= final_exit_t)]
        if hold.empty:
            continue
        mfe, mae = hold.max(), hold.min()
        favourable = mfe - entry_prem
        total_qty = sum(l.quantity for l in legs)
        total_pnl = sum(l.pnl for l in legs)
        # Quantity-weighted realised % — the honest single number for a
        # position exited in two pieces at different prices.
        realised_pct = total_pnl / (entry_prem * total_qty) * 100.0

        # "Trend still available": the best premium from entry to END OF DAY,
        # i.e. including everything after we were already flat. This is the
        # rally-capture denominator — the move the strategy could have had
        # without holding overnight and without any new signal.
        day_best = day_prem.max()
        day_favourable = day_best - entry_prem

        pos = {
            "symbol": symbol,
            "entry_time": entry_t,
            "exit_time": final_exit_t,
            "legs": len(legs),
            "partial_booked": any("Partial" in l.exit_reason for l in legs),
            "final_exit_reason": final.exit_reason,
            "final_exit_reason_class": _classify_reason(final.exit_reason),
            "sl_band_label": head.sl_band_label,
            "entry": entry_prem,
            "quantity": total_qty,
            "pnl": total_pnl,
            "holding_minutes": (final_exit_t - entry_t).total_seconds() / 60.0,
            "bars_held": len(hold) - 1,
            "mfe_pct": _pct(mfe, entry_prem),
            "mae_pct": _pct(mae, entry_prem),
            "realised_pct": realised_pct,
            "capture_pct": (realised_pct / (_pct(mfe, entry_prem)) * 100.0)
            if favourable > 1e-9 else None,
            "giveback_pct": _pct(mfe, entry_prem) - realised_pct,
            # trend / rally capture: realised vs the whole day's move
            "day_best_pct": _pct(day_best, entry_prem),
            "trend_capture_pct": (realised_pct / _pct(day_best, entry_prem) * 100.0)
            if day_favourable > 1e-9 else None,
        }
        exit_prem_equiv = final.exit_premium
        pos.update(_continuation(day_prem, final_exit_t, exit_prem_equiv, horizons))
        pos_rows.append(pos)

    legs_df = pd.DataFrame(leg_rows).sort_values("exit_time").reset_index(drop=True)
    pos_df = pd.DataFrame(pos_rows).sort_values("exit_time").reset_index(drop=True)
    return legs_df, pos_df


def _classify_reason(reason: str) -> str:
    """Collapse an exit reason to its mechanism. Deliberately keeps the
    ATR trailing stop and the percentage ("Offset") trailing stop APART —
    they are two independent mechanisms inside `SmartExitEngine` and the
    whole question here is which one is actually doing the exiting."""
    if reason.startswith("Trailing Stop-Loss Hit (Offset)"):
        return "trail_offset"
    if reason.startswith("Trailing Stop-Loss Hit"):
        return "trail_atr"
    if reason.startswith("Partial Profit Booking"):
        return "partial"
    if reason.startswith("Stop-Loss Hit"):
        return "stop"
    if reason.startswith("Profit Target Hit"):
        return "target"
    if reason.startswith("Time-based EOD"):
        return "eod"
    return reason.lower()


def _continuation(day_prem: pd.Series, exit_t: pd.Timestamp, exit_prem: float,
                  horizons: tuple[int, ...]) -> dict:
    """Post-exit continuation. Same trading day only — carrying the
    comparison overnight would compare against a gap the strategy could
    never have participated in."""
    out: dict = {}
    after = day_prem.loc[day_prem.index > exit_t]
    for h in horizons:
        window = after.loc[after.index <= exit_t + pd.Timedelta(minutes=h)]
        out[f"cont_{h}m_pct"] = _pct(window.max(), exit_prem) if not window.empty else None
    if after.empty:
        out["missed_upside_pct"] = None
        out["premature"] = None
        out["minutes_to_best_after_exit"] = None
    else:
        w60 = after.loc[after.index <= exit_t + pd.Timedelta(minutes=60)]
        best = w60.max() if not w60.empty else None
        out["missed_upside_pct"] = _pct(best, exit_prem) if best is not None else None
        out["premature"] = bool(best > exit_prem + 0.05) if best is not None else None
        out["minutes_to_best_after_exit"] = (
            (after.idxmax() - exit_t).total_seconds() / 60.0
        )
    return out
