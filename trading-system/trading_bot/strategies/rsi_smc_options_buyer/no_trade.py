"""Every reason this strategy refuses to trade, each with a name.

No-trade is a decision, not an absence of one. Every veto here returns a
string, so a session that took no trades can be explained from the log rather
than guessed at -- the failure mode where "the bot looks alive and simply
never trades" is the one this module exists to make impossible.

Vetoes are per-bar boolean arrays so they compose with the entry conditions
in exactly the same way, and so each one can be held out individually in a
test. The scalar instrument gate is separate because it applies to the whole
frame.
"""

from __future__ import annotations

import datetime as _dt
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .config import RsiSmcConfig, _symbol_key

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NoTradeView:
    """Per-bar vetoes plus a human-readable reason for the latest bar."""

    #: True where NO entry may be taken, for any reason.
    blocked: np.ndarray
    #: veto name -> per-bar mask, for diagnostics and holdout tests.
    reasons: Dict[str, np.ndarray]

    def reason_at(self, index: int) -> str:
        """Why bar ``index`` was refused, or an empty string if it was not."""
        if index < 0 or index >= self.blocked.shape[0] or not self.blocked[index]:
            return ""
        firing = [name for name, mask in self.reasons.items() if bool(mask[index])]
        return ", ".join(firing) if firing else "blocked"


def instrument_reason(symbol: Optional[str], cfg: RsiSmcConfig) -> str:
    """Why this strategy may not trade ``symbol`` at all, or "".

    This is an OPTIONS BUYING strategy. ``main.py`` only auto-maps a signal to
    an option contract when the symbol looks like an index
    (``option_mapping_required`` at the entry path tests for ``"INDEX" in s``
    or a NIFTY/SENSEX prefix). An equity symbol therefore does NOT get mapped,
    ``is_option_trade`` is False, and the trade would be taken as EQUITY with
    percentage SL/target -- a different instrument class than this strategy
    was designed, measured or risk-modelled for. Refusing at the source is the
    only way to make that structurally impossible from here.
    """
    if not symbol:
        return ""
    if cfg.instrument_allowed(symbol):
        return ""
    return (
        f"instrument {_symbol_key(symbol)} is not one of "
        f"{tuple(cfg.allowed_instruments)} -- this strategy only buys index options"
    )


def _parse_hhmm(value: str, fallback: _dt.time) -> _dt.time:
    try:
        hour, minute = str(value).split(":")[:2]
        return _dt.time(int(hour), int(minute))
    except Exception:
        return fallback


def _time_window_mask(index: pd.Index, n: int, cfg: RsiSmcConfig) -> np.ndarray:
    """True where the bar falls OUTSIDE the strategy's trading window.

    A frame with no timestamps cannot be windowed; those bars are not blocked
    on this ground, because refusing everything on a missing index would hide
    a data problem behind a trading rule. The freshness and minimum-bars
    vetoes are what catch a malformed frame.
    """
    if not isinstance(index, pd.DatetimeIndex) or n == 0:
        return np.zeros(n, dtype=bool)
    start = _parse_hhmm(cfg.time_start, _dt.time(9, 25))
    end = _parse_hhmm(cfg.time_end, _dt.time(15, 0))
    minutes = index.hour * 60 + index.minute
    lo = start.hour * 60 + start.minute
    hi = end.hour * 60 + end.minute
    return np.asarray((minutes < lo) | (minutes > hi), dtype=bool)


def evaluate(df: pd.DataFrame, cfg: RsiSmcConfig, regime_view, atr: np.ndarray,
             symbol: Optional[str] = None) -> NoTradeView:
    """All per-bar vetoes.

    Parameters
    ----------
    regime_view
        A :class:`regime.RegimeView`; its ``tradeable`` array already folds in
        the regime score floor, the choppiness ceiling and the high-volatility
        class.
    atr
        ATR aligned to ``df``, used for the volatility-band veto in
        percentage-of-price terms so it means the same thing on NIFTY and on
        SENSEX.
    """
    n = len(df)
    reasons: Dict[str, np.ndarray] = {}
    if n == 0:
        return NoTradeView(np.zeros(0, dtype=bool), reasons)

    close = df["close"].to_numpy(dtype=float)

    # 1. Not enough history for the SMC engine to use its configured lookback.
    too_short = np.zeros(n, dtype=bool)
    if n < cfg.min_bars:
        too_short[:] = True
    else:
        too_short[: cfg.min_bars] = True
    reasons["insufficient_history"] = too_short

    # 2. Regime refuses (score floor, chop, volatility class, unknown state).
    reasons["regime"] = ~np.asarray(regime_view.tradeable, dtype=bool)

    # 3. Volatility outside the tradeable band, in % of price.
    with np.errstate(divide="ignore", invalid="ignore"):
        atr_pct = np.where(close > 0, np.asarray(atr, dtype=float) / close, np.nan)
    reasons["volatility_band"] = ~(
        np.isfinite(atr_pct)
        & (atr_pct >= float(cfg.atr_pct_min))
        & (atr_pct <= float(cfg.atr_pct_max))
    )

    # 4. Outside the trading window.
    reasons["time_window"] = _time_window_mask(df.index, n, cfg)

    # 5. Malformed bars. A non-positive or non-finite price is a feed defect,
    #    not a trading opportunity -- the same class of problem that sent a
    #    0.0 spot price into Black-Scholes on 2026-08-25.
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    reasons["invalid_bar"] = ~(
        np.isfinite(close) & (close > 0)
        & np.isfinite(highs) & np.isfinite(lows)
        & (highs >= lows)
    )

    # 6. Duplicate timestamps. The bar is still evaluated positionally, but a
    #    repeated label means the feed delivered the same interval twice and
    #    the later copy is not a new observation.
    duplicate = np.zeros(n, dtype=bool)
    if isinstance(df.index, pd.DatetimeIndex) and n > 1:
        values = df.index.to_numpy()
        duplicate[1:] = values[1:] == values[:-1]
    reasons["duplicate_bar"] = duplicate

    blocked = np.zeros(n, dtype=bool)
    for mask in reasons.values():
        blocked |= mask

    return NoTradeView(blocked=blocked, reasons=reasons)


__all__ = ["NoTradeView", "evaluate", "instrument_reason"]
