"""Momentum 15/5 — 15-minute trend bias, 5-minute event entry.

Scope of THIS module
--------------------
Entry signal generation only. It emits {-1, 0, +1} through the standard
registry contract and owns no position, no stop and no exit. Everything
after the signal is the shared production pipeline's job
(`select_option`, `resolve_initial_stop`, `RiskManager`,
`SmartExitEngine`), unchanged and unspecialised.

That boundary is deliberate. The one strategy in this repository that
took its own exit path — `institutional_momentum` via
`TieredExitManager` — had an exit branch that raised `UnboundLocalError`
on every single evaluation for its entire life, swallowed by a broad
`except`, so its partial booking, runner trail, exhaustion lock and AI
early-exit never executed once. A parallel exit engine is the most
expensive failure mode this codebase has produced.

The rules
---------
**15-minute bias** (completed candles only)
    close > EMA20  -> CE-only bias
    close < EMA20  -> PE-only bias

**5-minute entry**, event-triggered
    EMA9/EMA20 crossover is the EVENT. It stays valid for the crossover
    candle plus 2 more (a 3-candle confirmation window).
    Within that window, on some candle j, all of:
      * RSI(14) > 50 for CE, < 50 for PE
      * ADX(14) > 20 and rising
      * RSI has crossed its own EMA20 in the correct direction within
        +/-1 candle of the crossover
      * the 15-minute bias agrees
    Conditions need NOT land on the same candle — the crossover, the RSI
    cross and the confirmation may each occur on different bars inside
    the window.

**One entry per direction per session.** Not a cooldown bolted on
afterwards: the crossover is an event, and the first confirmed instance
in a direction is that session's entry.

**DTE >= 2.** Sessions whose nearest weekly expiry is 0 or 1 day away
emit nothing. Measured 2026-08-10: at 0 DTE a single day of theta is
851% of the entire banded stop and 257% at 1 DTE, against 66-91% at
4-6 DTE. This is a mechanical property of the instrument, not a
backtest-fitted filter.

Timing semantics — why the signal lands one bar after confirmation
------------------------------------------------------------------
Live, `main.py` evaluates `signals.iloc[-1]` on the bar still FORMING.
A rule keyed to the current bar's close therefore means "price touched
this level at some instant" live, but "the bar closed here" in a
backtest — two different strategies sharing one name. Every condition
here is evaluated on completed candles only and the signal is emitted on
the following bar, so live and backtest are semantically identical. The
forward half of the "+/-1 candle" RSI tolerance is only honoured once
that candle has actually completed, so no rule ever reads a bar that had
not yet happened.

Parameters are the specification, not a search
----------------------------------------------
9/20, RSI 14 vs its EMA20 around the 50 midline, ADX 14 above 20 and
rising, a 3-candle window and a +/-1 candle tolerance are all given by
the strategy definition. None was swept, and none should be tuned
against a backtest without evidence that survives costs, theta and a
regime split.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from shared.indicators import adx as _adx
from shared.indicators import ema as _ema
from shared.indicators import rsi as _rsi

logger = logging.getLogger(__name__)

STRATEGY_NAME = "momentum_15_5"

# ── Specification constants ───────────────────────────────────────────
BIAS_TIMEFRAME = "15min"
BIAS_EMA = 20
EMA_FAST, EMA_SLOW = 9, 20
RSI_WINDOW, RSI_EMA_WINDOW, RSI_MIDLINE = 14, 20, 50.0
ADX_WINDOW, ADX_MIN = 14, 20.0
#: Crossover candle + 2 subsequent candles.
CONFIRM_WINDOW = 3
#: RSI/RSI-EMA cross may lead or lag the price crossover by one candle.
RSI_CROSS_TOLERANCE = 1
#: Minimum days to expiry for the contract this signal will be filled on.
MIN_DTE = 2

__all__ = ["STRATEGY_NAME", "MIN_DTE", "generate_signals"]


def _bias_series(df: pd.DataFrame) -> np.ndarray:
    """+1 / -1 / 0 bias from the last COMPLETED 15-minute candle.

    Resampled with `label='right', closed='right'`, so a bar stamped
    09:30 covers (09:15, 09:30] and is complete at 09:30. Re-indexing
    onto the 5-minute grid with forward-fill therefore never exposes a
    15-minute bar before it has closed.
    """
    agg = df.resample(BIAS_TIMEFRAME, label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()
    if len(agg) < BIAS_EMA + 1:
        return np.zeros(len(df), dtype=int)

    bias = np.sign(agg["close"] - _ema(agg["close"], BIAS_EMA)).fillna(0).astype(int)
    return bias.reindex(df.index, method="ffill").fillna(0).astype(int).to_numpy()


def _session_dte(day) -> int:
    """Days to the nearest weekly expiry for a session. Pure and
    date-driven, so it resolves identically live and in replay."""
    from trading_bot.strategies.premium_selection.options_selector import _next_expiry

    d = day.date() if hasattr(day, "date") else day
    return (_next_expiry("NIFTY", d) - d).days


def generate_signals(df: pd.DataFrame, **kwargs) -> pd.Series:
    """Return a {-1, 0, +1} signal Series aligned to `df` (5-minute bars).

    +1 = enter CE, -1 = enter PE, 0 = nothing.
    """
    n = len(df)
    signals = np.zeros(n, dtype=int)
    if n == 0 or not isinstance(df.index, pd.DatetimeIndex):
        return pd.Series(signals, index=df.index, dtype=int)

    min_dte = int(kwargs.get("min_dte", MIN_DTE))
    close = df["close"]
    if n < max(EMA_SLOW, RSI_WINDOW + RSI_EMA_WINDOW, ADX_WINDOW * 2) + 2:
        return pd.Series(signals, index=df.index, dtype=int)

    ema_f = _ema(close, EMA_FAST).to_numpy(dtype=float)
    ema_s = _ema(close, EMA_SLOW).to_numpy(dtype=float)
    rsi_v = _rsi(close, RSI_WINDOW)
    rsi_e = _ema(rsi_v, RSI_EMA_WINDOW)
    rsi_arr = rsi_v.to_numpy(dtype=float)
    rsi_ema_arr = rsi_e.to_numpy(dtype=float)
    adx_arr = _adx(df, ADX_WINDOW).to_numpy(dtype=float)
    bias = _bias_series(df)

    # ── events and per-bar conditions, all on completed candles ────────
    above = ema_f > ema_s
    cross_up = np.r_[False, above[1:] & ~above[:-1]]
    cross_dn = np.r_[False, ~above[1:] & above[:-1]]

    r_above = rsi_arr > rsi_ema_arr
    rsi_cross_up = np.r_[False, r_above[1:] & ~r_above[:-1]]
    rsi_cross_dn = np.r_[False, ~r_above[1:] & r_above[:-1]]

    adx_ok = np.r_[False, (adx_arr[1:] > ADX_MIN) & (adx_arr[1:] > adx_arr[:-1])]

    dates = df.index.normalize().to_numpy()
    day_of_bar = pd.Series(dates).to_numpy()

    # DTE gate, resolved once per session rather than per bar.
    eligible_day = {}
    for day in pd.unique(dates):
        try:
            eligible_day[day] = _session_dte(pd.Timestamp(day)) >= min_dte
        except Exception:  # never let expiry lookup break signal generation
            logger.warning("momentum_15_5: expiry lookup failed for %s", day)
            eligible_day[day] = False

    taken: set = set()  # (session, direction) already entered

    for k in np.flatnonzero(cross_up | cross_dn):
        direction = 1 if cross_up[k] else -1
        session = day_of_bar[k]
        if not eligible_day.get(session, False):
            continue
        if (session, direction) in taken:
            continue

        rsi_cross = rsi_cross_up if direction == 1 else rsi_cross_dn
        lo = max(k - RSI_CROSS_TOLERANCE, 0)

        for j in range(k, min(k + CONFIRM_WINDOW, n - 1)):
            # Never evaluate across a session boundary.
            if day_of_bar[j] != session:
                break
            # The forward half of the RSI tolerance is only usable once
            # that candle has completed — anything later than j would be
            # look-ahead.
            hi = min(k + RSI_CROSS_TOLERANCE, j)
            if not rsi_cross[lo:hi + 1].any():
                continue
            if not adx_ok[j]:
                continue
            if bias[j] != direction:
                continue
            rsi_ok = (rsi_arr[j] > RSI_MIDLINE) if direction == 1 else (rsi_arr[j] < RSI_MIDLINE)
            if not rsi_ok:
                continue

            # Act on the NEXT bar: every condition above used completed
            # candles, so this is the first bar on which the engine could
            # genuinely have acted, live or in replay.
            entry = j + 1
            if day_of_bar[entry] != session:
                break
            if signals[entry] != 0:
                break
            signals[entry] = direction
            taken.add((session, direction))
            break

    return pd.Series(signals, index=df.index, dtype=int)
