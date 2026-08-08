"""Entry-quality diagnostic: is the signal right, and is it on time?

Read-only analysis, and deliberately EXIT-INDEPENDENT. Every headline
number here is computed from the option-premium path and the position's
own initial risk R, not from what the exit engine happened to do — so a
bad exit cannot be mistaken for a bad entry, and vice versa.

The core measure is FIRST TOUCH OF +/-1R
----------------------------------------
For each position, walk the premium path forward from entry and record
which happens first: premium >= entry + R (a "win-first" entry) or
premium <= entry - R (a "loss-first" entry), where R is the position's
real initial stop distance from `resolve_initial_stop` — the same number
the live system risks. Neither, if the day ends first.

This is the classic first-touch test and it isolates the entry: it asks
only "did the market go our way before it went against us, by the amount
we were actually risking". A strategy whose entries are genuinely
predictive wins that race more often than it loses it, whatever the exit
rule does afterwards.

`false_entry` is then defined mechanically as `loss_first` — the market
moved a full risk unit against the signal before it ever moved one in
the signal's favour.

Signal reconstruction is verified, not assumed
----------------------------------------------
`ema_rsi`'s signals depend on the window they are computed over, and
`run_validation.run_strategy_day_isolated` computes them per day on a
30-calendar-day warm-up window. This module reproduces that windowing
exactly and calls the REAL `generate_signals`, then asserts that every
cached trade's entry bar carries a non-zero signal of the matching
direction. `verify_signal_alignment()` reports that check.

Indicator components (EMA gap, RSI, Supertrend and its age, volume
ratio) are recomputed alongside with the same `shared.indicators`
functions the strategy itself imports, so "which component was actually
carrying the signal" can be answered per entry.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd

from shared.indicators import ema, rsi, supertrend
from shared.risk import resolve_initial_stop
from trading_bot.strategies.ema_rsi_strategy import (
    generate_signals,
    _volume_filter,
)

from .exit_quality import _premium_series, reconstruct_contract
from .premium_simulator import DEFAULT_IV

__all__ = [
    "build_signal_frame",
    "verify_signal_alignment",
    "annotate_entries",
    "first_touch_outcomes",
    "find_missed_runs",
]

#: Must match `run_validation._WARMUP_CALENDAR_DAYS` — the diagnostic is
#: worthless if it computes indicators over a different window than the
#: run it is describing.
WARMUP_CALENDAR_DAYS = 30

#: Strategy defaults, mirrored so the component breakdown can say how far
#: past its threshold each condition was. Kept next to each other so a
#: drift from the strategy's own defaults is a one-line fix.
EMA_FAST, EMA_SLOW, RSI_WINDOW = 20, 50, 14
RSI_BUY_THRESH, RSI_SELL_THRESH = 55.0, 45.0
ST_PERIOD, ST_MULTIPLIER = 10, 3.0


def build_signal_frame(df: pd.DataFrame, settings: Optional[dict] = None) -> pd.DataFrame:
    """Reproduce, day by day, exactly what the day-isolated validation run
    saw: signals from the real `generate_signals` over a 30-calendar-day
    warm-up window, restricted to the target day, plus the indicator state
    that produced them.

    `settings` is forwarded to `registry.run_strategy` semantics — pass the
    production `enable_*_filter` flags to see the live entry path rather
    than the harness's unfiltered one.
    """
    settings = dict(settings or {})
    rows = []
    for day in sorted(set(df.index.date)):
        window_start = pd.Timestamp(day) - pd.Timedelta(days=WARMUP_CALENDAR_DAYS)
        window = df.loc[str(window_start.date()):str(day)]
        if (window.index.date == day).sum() < 5:
            continue

        # The real signal, through the real registry path (which is where
        # the institutional filters live), so filters-on vs filters-off is
        # a settings change here and not a reimplementation.
        from trading_bot.strategies.registry import registry
        result = registry.run_strategy("ema_rsi", window, **settings)
        signals = result[0] if isinstance(result, tuple) else result

        close = window["close"]
        ema_f = ema(close, window=EMA_FAST)
        ema_s = ema(close, window=EMA_SLOW)
        rsi_s = rsi(close, window=RSI_WINDOW)
        st = supertrend(window, period=ST_PERIOD, multiplier=ST_MULTIPLIER)
        st_dir = st["direction"]
        vol_ok = _volume_filter(window)

        # Age of the current Supertrend leg and of the current EMA regime,
        # in bars — "how long has this setup already been running", which
        # is the entry-timing question.
        st_age = st_dir.groupby((st_dir != st_dir.shift()).cumsum()).cumcount()
        ema_state = np.sign(ema_f - ema_s)
        ema_age = ema_state.groupby((ema_state != ema_state.shift()).cumsum()).cumcount()

        # The raw LEVEL condition, before the strategy's edge-trigger and
        # before any institutional filter — "would a level-triggered
        # strategy have been in this trade". Needed to tell "the
        # edge-trigger suppressed a setup" apart from "there was no setup",
        # which are very different findings when explaining a missed rally.
        bull = (ema_f > ema_s) & (rsi_s > RSI_BUY_THRESH) & (st_dir == 1) & vol_ok
        bear = (ema_f < ema_s) & (rsi_s < RSI_SELL_THRESH) & (st_dir == -1) & vol_ok
        level = pd.Series(
            np.select([bear.to_numpy(), bull.to_numpy()], [-1, 1], default=0),
            index=window.index, dtype=int,
        )

        frame = pd.DataFrame({
            "signal": signals,
            "level_signal": level,
            "close": close,
            "ema_fast": ema_f,
            "ema_slow": ema_s,
            "ema_gap_pct": (ema_f - ema_s) / ema_s * 100.0,
            "ema_age_bars": ema_age,
            "rsi": rsi_s,
            "st_dir": st_dir,
            "st_age_bars": st_age,
            "st_line": st["supertrend"] if "supertrend" in st else np.nan,
            "volume_ok": vol_ok,
            "vol_ratio": window["volume"] / window["volume"].rolling(20, min_periods=1).mean(),
        })
        rows.append(frame.loc[frame.index.date == day])

    return pd.concat(rows) if rows else pd.DataFrame()


def verify_signal_alignment(trades, sig: pd.DataFrame) -> dict:
    """Every cached entry must land on a bar this module reconstructs as a
    signal of the same direction. Anything else means the reconstruction
    and the run disagree, and nothing below it can be trusted."""
    seen, matched, missing_bar, wrong_dir = set(), 0, 0, 0
    for t in trades:
        key = (t.symbol, str(t.entry_time))
        if key in seen:
            continue
        seen.add(key)
        ts = pd.Timestamp(t.entry_time)
        if ts not in sig.index:
            missing_bar += 1
            continue
        want = 1 if t.direction == "CE" else -1
        if int(sig.at[ts, "signal"]) == want:
            matched += 1
        else:
            wrong_dir += 1
    return {"positions": len(seen), "matched": matched,
            "entry_bar_not_in_frame": missing_bar, "signal_direction_mismatch": wrong_dir}


def annotate_entries(trades, sig: pd.DataFrame, underlying: pd.DataFrame,
                     settings: Optional[dict] = None) -> pd.DataFrame:
    """One row per POSITION with its entry-time indicator state, its real
    initial risk R, its first-touch outcome, and the underlying's forward
    move at several horizons."""
    settings = dict(settings or {})
    grouped: dict[tuple, list] = {}
    for t in trades:
        grouped.setdefault((t.symbol, str(t.entry_time)), []).append(t)

    idx = underlying.index
    rows = []
    for (symbol, _k), legs in grouped.items():
        legs = sorted(legs, key=lambda t: pd.Timestamp(t.exit_time))
        head = legs[0]
        ts = pd.Timestamp(head.entry_time)
        if ts not in sig.index:
            continue
        contract = reconstruct_contract(head, underlying)
        if contract is None:
            continue

        entry_prem = head.entry_premium
        sl = resolve_initial_stop(entry_prem, settings)
        risk = entry_prem - sl.sl_price

        day_bars = underlying.loc[(idx > ts) & (idx.date == ts.date())]
        if day_bars.empty:
            continue
        prem = _premium_series(contract, day_bars, DEFAULT_IV)

        s = sig.loc[ts]
        direction = head.direction
        sign = 1.0 if direction == "CE" else -1.0
        row = {
            "symbol": symbol, "entry_time": ts, "direction": direction,
            "exit_time": pd.Timestamp(legs[-1].exit_time),
            "date": ts.date(), "hour": ts.hour, "minute_of_day": ts.hour * 60 + ts.minute,
            "entry_premium": entry_prem, "risk": risk, "risk_pct": risk / entry_prem * 100.0,
            "sl_band_label": head.sl_band_label,
            "pnl": sum(l.pnl for l in legs),
            "final_exit_reason": legs[-1].exit_reason,
            # ── indicator state at the entry bar ──
            "ema_gap_pct": float(s["ema_gap_pct"]),
            # Signed so a bigger number always means "more confirmation for
            # the direction actually taken", CE or PE alike.
            "ema_gap_signed": float(s["ema_gap_pct"]) * sign,
            "ema_age_bars": int(s["ema_age_bars"]),
            "rsi": float(s["rsi"]),
            "rsi_margin": (float(s["rsi"]) - RSI_BUY_THRESH) if direction == "CE"
                          else (RSI_SELL_THRESH - float(s["rsi"])),
            "st_age_bars": int(s["st_age_bars"]),
            "vol_ratio": float(s["vol_ratio"]) if pd.notna(s["vol_ratio"]) else np.nan,
            "close_at_entry": float(s["close"]),
            # How far price already sits beyond the fast EMA — "have we
            # already missed the move" in the strategy's own terms.
            "stretch_pct": (float(s["close"]) - float(s["ema_fast"])) / float(s["ema_fast"]) * 100.0 * sign,
        }
        row.update(first_touch_outcomes(prem, entry_prem, risk))

        # Underlying forward move in the signalled direction.
        for h in (5, 15, 30, 60):
            w = day_bars.loc[day_bars.index <= ts + pd.Timedelta(minutes=h)]
            if w.empty:
                row[f"und_{h}m_pct"] = None
                continue
            row[f"und_{h}m_pct"] = (float(w["close"].iloc[-1]) - row["close_at_entry"]) / row["close_at_entry"] * 100.0 * sign
        best = day_bars["close"].max() if direction == "CE" else day_bars["close"].min()
        row["und_best_rest_of_day_pct"] = (
            (float(best) - row["close_at_entry"]) / row["close_at_entry"] * 100.0 * sign
        )
        rows.append(row)

    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)


def first_touch_outcomes(prem: pd.Series, entry_premium: float, risk: float) -> dict:
    """Which came first from this entry — +1R or -1R?

    Exit-independent by construction: it reads the premium path the
    position actually had, and the risk unit the system actually took,
    and ignores what closed the trade."""
    if risk <= 0 or prem.empty:
        return {"first_touch": "none", "bars_to_first_touch": None,
                "mfe_r": None, "mae_r": None}
    up, down = entry_premium + risk, entry_premium - risk
    hit_up = np.where(prem.to_numpy() >= up)[0]
    hit_dn = np.where(prem.to_numpy() <= down)[0]
    i_up = hit_up[0] if len(hit_up) else None
    i_dn = hit_dn[0] if len(hit_dn) else None

    if i_up is None and i_dn is None:
        outcome, bars = "none", None
    elif i_dn is None or (i_up is not None and i_up < i_dn):
        outcome, bars = "win_first", int(i_up) + 1
    else:
        outcome, bars = "loss_first", int(i_dn) + 1

    return {
        "first_touch": outcome,
        "bars_to_first_touch": bars,
        "mfe_r": (prem.max() - entry_premium) / risk,
        "mae_r": (prem.min() - entry_premium) / risk,
    }


def find_missed_runs(sig: pd.DataFrame, entries: pd.DataFrame,
                     min_move_pct: float = 0.30, max_minutes: int = 90) -> pd.DataFrame:
    """Find sustained intraday moves in the UNDERLYING and record whether
    the strategy was positioned for each one.

    A "run" is a move of at least `min_move_pct` in the index completed
    within `max_minutes`, measured forward from each bar and de-overlapped
    greedily by size. Coverage is judged by whether any position was OPEN
    in the matching direction at any point during the run — being in the
    trade is what matters, not whether a signal existed.
    """
    out = []
    for day, day_sig in sig.groupby(sig.index.date):
        closes = day_sig["close"]
        n = len(closes)
        vals = closes.to_numpy()
        times = closes.index
        cands = []
        for i in range(n):
            j_max = np.searchsorted(times, times[i] + pd.Timedelta(minutes=max_minutes), side="right")
            if j_max <= i + 1:
                continue
            seg = vals[i:j_max]
            up_pct = (seg.max() - vals[i]) / vals[i] * 100.0
            dn_pct = (seg.min() - vals[i]) / vals[i] * 100.0
            if up_pct >= min_move_pct:
                cands.append((up_pct, i, int(i + seg.argmax()), "CE"))
            if -dn_pct >= min_move_pct:
                cands.append((-dn_pct, i, int(i + seg.argmin()), "PE"))

        cands.sort(reverse=True)
        taken: list[tuple[int, int, str]] = []
        for size, i, j, direction in cands:
            if any(not (j < a or i > b) and d == direction for a, b, d in taken):
                continue
            taken.append((i, j, direction))
            out.append({"date": day, "start": times[i], "end": times[j],
                        "direction": direction, "move_pct": size,
                        "minutes": (times[j] - times[i]).total_seconds() / 60.0})

    runs = pd.DataFrame(out)
    if runs.empty or entries.empty:
        return runs

    # Was a position in the right direction OPEN at any point during the
    # run? Overlap, not entry-timing: a position opened before the run
    # started and still held through it captured that run.
    covered, overlap_pct = [], []
    for _, r in runs.iterrows():
        e = entries[(entries.direction == r.direction) & (entries.date == r.date)]
        hit = e[(e.entry_time <= r.end) & (e.exit_time >= r.start)]
        covered.append(not hit.empty)
        if hit.empty or r.end == r.start:
            overlap_pct.append(0.0)
        else:
            span = (r.end - r.start).total_seconds()
            held = sum(
                max(0.0, (min(x.exit_time, r.end) - max(x.entry_time, r.start)).total_seconds())
                for x in hit.itertuples()
            )
            overlap_pct.append(min(100.0, held / span * 100.0))
    runs["covered"] = covered
    runs["held_pct_of_run"] = overlap_pct
    return runs
