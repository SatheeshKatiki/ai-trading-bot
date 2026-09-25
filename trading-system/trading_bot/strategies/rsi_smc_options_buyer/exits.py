"""Exits for RSI_SMC_OPTIONS_BUYER_V1 (the M1 branch).

Four ways a position ends, checked in this order:

1. **EOD square-off** at the engine's own cutoff. FIRST, always.
2. **Premium stop**, a ladder that only ratchets up and never widens.
3. **Structural invalidation** -- the underlying traded back through the level
   whose sweep was the reason for the trade.
4. **Structure reversal** -- an opposite BOS/CHoCH on closed underlying bars.

There is no fixed profit target. That is the owner's ratified design: the stop
keeps stepping up while the move has room, and the trade ends on the stop, a
reversal, or the clock.

Why EOD is first
----------------
``SmartExitEngine.evaluate_exit`` is where the 15:15 cutoff lives, and a
strategy branch that handles its own exits never calls it. Both existing
bypass branches had to re-add the cutoff for exactly this reason --
``institutional_momentum`` shipped without it and, in ``main.py``'s own words,
"had nothing at all to close it at the end of the session", carrying overnight
gap risk plus a night of theta on a contract that might expire the next day.

The two price scales, and why they never meet
---------------------------------------------
An option position has TWO price series and mixing them is a defect this
repository has already paid for (2026-08-07 audit sec 2.1: index-point ATR fed
into premium-scale trailing math).

* **Premium scale** -- entry, current price, stop, ladder rungs. Every
  computation here is a PERCENTAGE of the entry premium, so no ATR of any kind
  enters it. ``main.py`` resolves premium-scale ATR via ``resolve_option_atr``
  for the engine's own trailing; this module neither receives nor wants it.
* **Underlying scale** -- structure, swept levels, the invalidation buffer.
  ATR here is computed from the underlying frame and is used ONLY to compare
  against underlying prices.

:func:`evaluate` deliberately does not accept a premium ATR argument, so the
mistake is not available to make.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

# The owner's ladder, reused rather than reimplemented. These are pure
# functions with no module state, so importing them cannot change
# ema9_rsi_momentum's behaviour in any way; it just means there is one ladder
# in this repository instead of two that can silently diverge.
from trading_bot.strategies.ema9_rsi_momentum.exit_ladder import (
    initial_stop,
    ratchet_stop,
    stop_reason,
)

from . import structure as _structure
from .config import RsiSmcConfig

logger = logging.getLogger(__name__)

#: Bounded record of which closed bar each symbol's reversal check last ran
#: on, so the check runs once per newly closed bar instead of on every tick.
_MAX_REVERSAL_KEYS = 32
_REVERSAL_CHECKED: "OrderedDict[str, Any]" = OrderedDict()


@dataclass(frozen=True)
class ExitDecision:
    """What to do with an open position right now."""

    should_exit: bool
    reason: str
    #: The ratcheted premium stop. Always >= the stop passed in.
    new_stop: float
    #: The next ladder rung as a premium price, or None past the top rung.
    next_rung: Optional[float]


def opening_stop(entry_premium: float, cfg: RsiSmcConfig, tick: float = 0.05) -> float:
    """The opening premium stop, ``initial_sl_pct`` under entry."""
    return initial_stop(entry_premium, float(cfg.initial_sl_pct), tick)


def structural_invalidation(direction: int, swept_extreme: float,
                            underlying_atr: float, cfg: RsiSmcConfig) -> float:
    """The UNDERLYING price at which the reason for the trade is dead.

    For a CE the setup was a sell-side sweep, so the invalidation sits below
    the swept extreme by ``sl_atr_buffer`` ATR; for a PE it is the mirror. If
    the underlying trades back through this, the sweep did not hold and the
    premise is gone regardless of what the premium has done.

    ``underlying_atr`` MUST be an underlying-scale ATR. See the module
    docstring.
    """
    if not np.isfinite(swept_extreme) or not np.isfinite(underlying_atr):
        return float("nan")
    buffer = float(cfg.sl_atr_buffer) * float(underlying_atr)
    return float(swept_extreme - buffer) if direction > 0 else float(swept_extreme + buffer)


def _closed_bars(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Resample to the strategy's timeframe and drop the still-forming bar.

    Same treatment ``main.py`` already applies before handing a frame to
    ``TieredExitManager`` and the exit analyser, and for the same reason: a
    candle-close rule fed the forming bar becomes an intrabar-noise trigger
    that cuts runners early.
    """
    if df is None or df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return pd.DataFrame()
    resampled = df.resample(f"{int(minutes)}min", label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()
    if len(resampled) > 1:
        resampled = resampled.iloc[:-1]
    return resampled


def _reversal_due(symbol: str, last_closed) -> bool:
    """True once per newly closed bar for this symbol."""
    key = symbol or "?"
    if _REVERSAL_CHECKED.get(key) == last_closed:
        return False
    _REVERSAL_CHECKED[key] = last_closed
    _REVERSAL_CHECKED.move_to_end(key)
    while len(_REVERSAL_CHECKED) > _MAX_REVERSAL_KEYS:
        _REVERSAL_CHECKED.popitem(last=False)
    return True


def structure_reversed(df_underlying: pd.DataFrame, direction: int,
                       cfg: RsiSmcConfig, symbol: Optional[str] = None) -> bool:
    """Has the underlying's structure turned against an open position?

    Reads only CLOSED bars of the strategy's own timeframe, and only the
    causal ``smc_bos`` / ``smc_choch`` series -- never any end-of-frame field
    (see :mod:`structure`). Runs at most once per newly closed bar.
    """
    frame = _closed_bars(df_underlying, cfg.timeframe_minutes)
    if len(frame) < cfg.min_bars:
        return False
    if not _reversal_due(symbol or "?", frame.index[-1]):
        return False

    view = _structure.build(frame, cfg, symbol=f"exit:{symbol}" if symbol else None)
    window = max(1, int(cfg.confirm_window))
    tail = slice(max(0, view.n - window), view.n)
    if direction > 0:
        return bool((view.choch[tail] < 0).any() or (view.bos[tail] < 0).any())
    return bool((view.choch[tail] > 0).any() or (view.bos[tail] > 0).any())


def evaluate(
    *,
    df_underlying: Optional[pd.DataFrame],
    direction: int,
    entry_premium: float,
    current_premium: float,
    best_premium: float,
    current_stop: float,
    now_hms: str,
    eod_time: str,
    cfg: RsiSmcConfig,
    underlying_price: Optional[float] = None,
    invalidation_price: Optional[float] = None,
    symbol: Optional[str] = None,
    tick: float = 0.05,
) -> ExitDecision:
    """The whole exit decision for one open option position.

    Keyword-only on purpose: this is called from a branch inside a 2,000-line
    tick handler, and a positional mix-up between two price scales is exactly
    the class of bug the module docstring is about.

    Never raises for ordinary bad input -- a malformed premium yields "hold
    with the stop unchanged" rather than an exception, because the caller's
    fallback is the shared exit engine and a raise there is misread as a
    WebSocket disconnect (see ``main.py``'s M1 branch).
    """
    side = 1 if direction > 0 else -1
    stop = float(current_stop or 0.0)

    # 1. EOD square-off. FIRST, before anything else can decide otherwise.
    time_only = now_hms.split(" ")[-1] if " " in (now_hms or "") else (now_hms or "")
    if eod_time and time_only >= eod_time:
        return ExitDecision(True, "Time-based EOD Exit", stop, None)

    if not (entry_premium and entry_premium > 0):
        return ExitDecision(False, "", stop, None)

    # 2. Premium ladder. Percentages of entry premium only -- no ATR, so no
    #    scale can be mixed in here.
    best = max(float(best_premium or 0.0), float(current_premium or 0.0))
    try:
        new_stop, next_rung = ratchet_stop(
            float(entry_premium), stop, best,
            tuple(cfg.profit_ladder_pct), float(cfg.initial_sl_pct), tick,
        )
    except Exception as exc:                       # pragma: no cover - guard
        logger.error("rsi_smc_options_buyer: ladder failed (%s) -- stop unchanged.", exc)
        return ExitDecision(False, "", stop, None)

    if current_premium is not None and current_premium > 0 and current_premium <= new_stop:
        return ExitDecision(
            True,
            f"{stop_reason(float(entry_premium), new_stop)} "
            f"(LTP {float(current_premium):.2f} <= SL {new_stop:.2f})",
            new_stop, next_rung,
        )

    # 3. Structural invalidation on the UNDERLYING. The level whose sweep was
    #    the reason for the trade has been traded back through.
    if (cfg.use_structural_stop and underlying_price is not None
            and invalidation_price is not None and np.isfinite(invalidation_price)):
        broken = (underlying_price <= invalidation_price if side > 0
                  else underlying_price >= invalidation_price)
        if broken:
            return ExitDecision(
                True,
                f"Structural invalidation (underlying {float(underlying_price):.2f} "
                f"through {float(invalidation_price):.2f})",
                new_stop, next_rung,
            )

    # 4. Structure reversal on closed underlying bars.
    try:
        if df_underlying is not None and structure_reversed(df_underlying, side, cfg, symbol):
            return ExitDecision(True, "Structure reversal (opposite BOS/CHoCH)", new_stop, next_rung)
    except Exception as exc:                       # pragma: no cover - guard
        logger.error("rsi_smc_options_buyer: reversal check failed (%s) -- holding.", exc)

    return ExitDecision(False, "", new_stop, next_rung)


def reset_state() -> None:
    """Clear the per-symbol reversal bookkeeping. For tests and session
    boundaries."""
    _REVERSAL_CHECKED.clear()


__all__ = [
    "ExitDecision",
    "evaluate",
    "opening_stop",
    "structural_invalidation",
    "structure_reversed",
    "reset_state",
]
