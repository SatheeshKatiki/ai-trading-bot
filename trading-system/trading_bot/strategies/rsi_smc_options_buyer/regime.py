"""Market regime, reused rather than re-derived.

Two existing implementations answer this question already, and this module
calls both instead of writing a third:

* ``MarketRegimeDetector`` (``momentum_strategy/regime_detector.py``) --
  ADX trend state, Bollinger expansion/compression phase, ATR/VIX volatility
  class and a 0-100 regime score with a NO_TRADE / REDUCED_EXPOSURE /
  FULL_ALLOCATION action.
* ``_choppiness_index`` (``premium_selection/no_trade_filter.py``) -- the
  0-100 choppiness measure, where > 61.8 is the conventional chop threshold.

Both are imported read-only and neither is modified, so
``institutional_momentum`` and ``premium`` are behaviourally untouched. That
import is a deliberate cross-strategy coupling: if either implementation
changes, this strategy changes with it. ``test_rsi_smc_regime_coupling.py``
pins the contract (the column names and value domains relied on here) so such
a change breaks a test rather than silently altering live behaviour.

Regime is used to decide WHICH setup is allowed, not merely whether to trade:

* trending  -> continuation setups (BOS in the direction of the HTF bias)
* ranging   -> reversal setups (CHoCH after a liquidity sweep)
* choppy / wrong-volatility -> no trade at all

``MarketRegimeDetector.detect_vectorized`` takes a ``daily_vix`` argument and
defaults it to 15.0. India VIX is not available on the strategy evaluation
path -- ``main.py`` fetches it separately and does not pass it into
``registry.run_strategy`` -- so the default is used, which makes the ATR term
the effective volatility discriminator. That is a documented limitation, not
an oversight: inventing a VIX here would be fabricating market data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

#: Column contract relied on from MarketRegimeDetector.detect_vectorized.
#: Asserted by the coupling test.
REQUIRED_REGIME_COLUMNS = ("state", "phase", "volatility", "regime_score", "action")

TRENDING = "TRENDING"
SIDEWAYS = "SIDEWAYS"
NO_TRADE_ACTION = "NO_TRADE"
HIGH_VOLATILITY = "HIGH"


@dataclass(frozen=True)
class RegimeView:
    """Per-bar regime arrays, aligned positionally to the source frame."""

    trending: np.ndarray
    ranging: np.ndarray
    score: np.ndarray
    high_volatility: np.ndarray
    choppiness: np.ndarray
    #: Regime permits trading at all (score above floor, not choppy, not a
    #: volatility blow-off). Direction and setup type are decided elsewhere.
    tradeable: np.ndarray


def _flat(n: int, value: bool) -> np.ndarray:
    return np.full(n, value, dtype=bool)


def compute(df: pd.DataFrame, cfg) -> RegimeView:
    """Regime classification for every bar.

    Fails SAFE: if either borrowed implementation cannot be imported or
    raises, the regime is reported as not tradeable. A strategy that cannot
    tell a trend from chop should not be taking trades, and silently assuming
    "tradeable" would be the dangerous default.
    """
    n = len(df)
    if n == 0:
        empty_b = np.zeros(0, dtype=bool)
        empty_f = np.zeros(0, dtype=float)
        return RegimeView(empty_b, empty_b.copy(), empty_f, empty_b.copy(),
                          empty_f.copy(), empty_b.copy())

    try:
        from trading_bot.strategies.momentum_strategy.regime_detector import (
            MarketRegimeDetector,
        )
        detector = MarketRegimeDetector()
        table = detector.detect_vectorized(df)
        missing = [c for c in REQUIRED_REGIME_COLUMNS if c not in table.columns]
        if missing:
            raise KeyError(f"MarketRegimeDetector no longer reports {missing}")
        state = table["state"].to_numpy()
        volatility = table["volatility"].to_numpy()
        score = table["regime_score"].to_numpy(dtype=float)
        action = table["action"].to_numpy()
    except Exception as exc:
        logger.warning(
            "rsi_smc_options_buyer: regime detection unavailable (%s) -- "
            "treating every bar as NOT tradeable.", exc,
        )
        return RegimeView(
            trending=_flat(n, False), ranging=_flat(n, False),
            score=np.zeros(n, dtype=float), high_volatility=_flat(n, True),
            choppiness=np.full(n, np.nan, dtype=float), tradeable=_flat(n, False),
        )

    try:
        from trading_bot.strategies.premium_selection.no_trade_filter import (
            _choppiness_index,
        )
        choppiness = _choppiness_index(df).to_numpy(dtype=float)
    except Exception as exc:
        logger.warning(
            "rsi_smc_options_buyer: choppiness index unavailable (%s) -- "
            "treating every bar as choppy.", exc,
        )
        choppiness = np.full(n, 100.0, dtype=float)

    trending = state == TRENDING
    ranging = state == SIDEWAYS
    high_vol = volatility == HIGH_VOLATILITY

    # NaN choppiness means "not enough history to judge", which is not the
    # same as "calm" -- treat it as blocking, consistent with failing safe.
    not_choppy = np.isfinite(choppiness) & (choppiness <= float(cfg.choppiness_max))

    tradeable = (
        (score >= float(cfg.min_regime_score))
        & (action != NO_TRADE_ACTION)
        & ~high_vol
        & not_choppy
        & (trending | ranging)
    )

    return RegimeView(
        trending=trending,
        ranging=ranging,
        score=score,
        high_volatility=high_vol,
        choppiness=choppiness,
        tradeable=tradeable,
    )


__all__ = ["RegimeView", "compute", "REQUIRED_REGIME_COLUMNS",
           "TRENDING", "SIDEWAYS", "NO_TRADE_ACTION", "HIGH_VOLATILITY"]
