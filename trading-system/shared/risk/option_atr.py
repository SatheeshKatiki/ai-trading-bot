"""Option-premium-scale ATR for trailing-stop sizing.

Root cause this exists for
--------------------------
`SmartExitEngine`'s ATR-based trailing stop (and `momentum_strategy`'s
independent `TieredExitManager._evaluate_exhaustion()`) were both being fed
an ATR computed from the *underlying index's* own candle range — typically
100-375+ NIFTY index points — then subtracted directly from
`position.highest_price`, which for an option position is the *premium*
(₹15-2400 in real trades). An index-point quantity has no defined
relationship to a premium-rupee quantity: for low-premium/low-delta
contracts the resulting trailing distance was always deeply negative (the
ATR-trailing layer never tightened the stop at all), and for high-premium/
high-delta contracts the same index-point distance could be comparable to
the premium itself (the layer could fire on unrelated index chop). See
`docs/STRATEGY_AUDIT_2026-08-07.md` §2.1 and
`docs/ATR_TRAILING_STOP_DESIGN_2026-08-07.md` for the full comparison of
candidate fixes.

Design
------
Spot data is for entry-signal generation only. Every option-position
exit/risk decision must be sized in the option's own premium units.
`resolve_option_atr()` is the single source of truth for that: it computes
a genuine Wilder-smoothed ATR(14) from the option contract's *own* rolling
premium candles (reusing `shared/indicators/atr.py`'s already-correct
implementation — no second ATR formula, no duplicate math) once enough
candle history has accumulated since the position was opened, and falls
back to the premium-banded distance table already shipped for the initial
stop (`shared/risk/option_stop_loss.py::resolve_stop_points`) during the
unavoidable cold-start window right after entry, when a position hasn't
been open long enough to have 14 of its own candles yet. The underlying
index's ATR is never consulted here, in either branch.

This module is pure: no I/O, no broker calls, no logging side effects,
same convention as `option_stop_loss.py`. It does not create, feed, or
manage the option's candle series itself — see `trading_bot/main.py`'s
exit-check loop for how premium samples are fed into the shared
`CandleAggregator` and how this function's result gets consumed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

import pandas as pd

from shared.indicators.atr import atr as _atr
from shared.risk.option_stop_loss import resolve_stop_points

__all__ = ["MIN_CANDLES_FOR_OPTION_ATR", "OptionAtrDecision", "resolve_option_atr"]

#: Minimum number of the option's own candles required before its ATR(14)
#: is trusted. Below this, `atr()`'s EWM-based smoothing is still numerically
#: defined but too short-lived to be a meaningful volatility read for a
#: brand-new contract's history -- the premium-banded proxy is used instead.
MIN_CANDLES_FOR_OPTION_ATR = 14


@dataclass(frozen=True)
class OptionAtrDecision:
    """The resolved ATR-equivalent trailing-cushion size, with everything
    needed to log/audit which path produced it."""

    atr_value: float          # premium-rupee distance to use as "ATR"
    source: str                # "option_atr" | "premium_proxy"
    candles_available: int     # how many of the option's own candles existed


def resolve_option_atr(
    option_candles: Optional[pd.DataFrame],
    current_premium: float,
    settings: Optional[Mapping[str, Any]] = None,
) -> OptionAtrDecision:
    """Resolve the ATR-equivalent trailing-cushion distance for an option
    position, in premium rupees.

    Parameters
    ----------
    option_candles
        The option contract's own OHLC candles (same shape as
        `CandleAggregator.get_latest_dataframe()` — columns
        `open`/`high`/`low`/`close`/`volume`), built from premium samples
        collected since the position was opened. May be `None` or empty
        immediately after entry, before any candle has closed.
    current_premium
        The option's current live premium. Used for the cold-start
        fallback (and as the reference point `resolve_stop_points` bands
        against) — never combined with `option_candles` in the same
        computation, so there's no risk of a partial index/premium mix.
    settings
        Forwarded to `resolve_stop_points` for the cold-start fallback
        (recognises the same `option_sl_*` keys as the initial stop).

    Returns
    -------
    OptionAtrDecision
    """
    n = 0 if option_candles is None else len(option_candles)

    if n >= MIN_CANDLES_FOR_OPTION_ATR:
        atr_series = _atr(option_candles, window=MIN_CANDLES_FOR_OPTION_ATR)
        candidate = atr_series.iloc[-1]
        if pd.notna(candidate) and candidate > 0:
            return OptionAtrDecision(atr_value=float(candidate), source="option_atr", candles_available=n)

    # Cold start (not enough of the option's own candle history yet) or a
    # degenerate ATR read (e.g. a flat premium run) -- bridge with the
    # same premium-banded distance already used for the initial stop.
    # Never the underlying index's ATR.
    proxy = resolve_stop_points(current_premium, settings)
    return OptionAtrDecision(atr_value=proxy, source="premium_proxy", candles_available=n)
