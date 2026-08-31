"""EMA9/RSI Momentum — Premium Health / Decay monitoring and Exit Signal.

Owns the two concerns the spec keeps separate from the entry rules:

* **Premium Health/Decay** — classifies how an already-open position's
  option premium has moved since entry (LOW/MODERATE/HIGH/CRITICAL).
* **Exit Signal** — the EMA/RSI reversal ("EXIT CE"/"EXIT PE") protection
  layer, combined with premium decay + momentum per the spec's explicit
  rule: "Do not treat premium decay alone as an exit signal."

This module does NOT touch Stop-Loss, Target, or Money Management — those
stay exactly as implemented in ``shared/exits/exit_engine.py`` and
``shared/risk/``. It only ever *adds* an extra, independent check that
``trading_bot/main.py`` consults alongside (never instead of) the existing
``SmartExitEngine.evaluate_exit()`` call for this strategy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .config import Ema9RsiMomentumConfig
from .signal_engine import (
    classify_momentum_strength,
    compute_cross_signals,
    momentum_strength_upgrade,
)

logger = logging.getLogger(__name__)

LOW = "LOW"
MODERATE = "MODERATE"
HIGH = "HIGH"
CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class PremiumHealth:
    """Premium decay / option-health snapshot for an open position."""

    entry_premium: float
    current_premium: float
    pct_change: float          # e.g. -12.5 means the premium is down 12.5%
    decay_level: str           # LOW / MODERATE / HIGH / CRITICAL
    dte: Optional[int] = None
    iv: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None

    @property
    def spread_pct(self) -> Optional[float]:
        """Bid/ask spread as a % of mid-price, if both sides are known."""
        if self.bid and self.ask and (self.bid + self.ask) > 0:
            mid = (self.bid + self.ask) / 2.0
            return (self.ask - self.bid) / mid * 100.0
        return None


def classify_decay(pct_change: float, cfg: Ema9RsiMomentumConfig) -> str:
    """Classify premium % change into the spec's four decay bands.

    Boundaries are inclusive on their "healthier" side: ``pct_change``
    at or above ``decay_low_pct`` (default -10%) is LOW — this also
    covers a premium that is flat or has gained, which is not decay at
    all but is obviously no worse than "LOW".
    """
    if pct_change >= cfg.decay_low_pct:
        return LOW
    if pct_change >= cfg.decay_moderate_pct:
        return MODERATE
    if pct_change >= cfg.decay_high_pct:
        return HIGH
    return CRITICAL


def build_premium_health(
    entry_premium: float,
    current_premium: float,
    cfg: Ema9RsiMomentumConfig,
    dte: Optional[int] = None,
    iv: Optional[float] = None,
    bid: Optional[float] = None,
    ask: Optional[float] = None,
) -> PremiumHealth:
    pct_change = ((current_premium - entry_premium) / entry_premium * 100.0) if entry_premium else 0.0
    return PremiumHealth(
        entry_premium=entry_premium,
        current_premium=current_premium,
        pct_change=pct_change,
        decay_level=classify_decay(pct_change, cfg),
        dte=dte,
        iv=iv,
        bid=bid,
        ask=ask,
    )


@dataclass(frozen=True)
class ProtectiveExitResult:
    """Output of :func:`evaluate_protective_exit`.

    ``should_exit`` is True ONLY for a genuine EMA/RSI reversal — the
    spec's own "EXIT CE"/"EXIT PE" rule. Premium decay, on its own, never
    sets ``should_exit``; it only ever contributes to ``warning``/``reason``
    for a human (or a future automated layer) to act on, per the spec's
    "do not treat premium decay alone as an exit signal" instruction.
    """

    should_exit: bool = False
    warning: bool = False
    reason: str = ""
    momentum_strength: str = "NONE"
    premium_health: Optional[PremiumHealth] = None


def evaluate_protective_exit(
    df: pd.DataFrame,
    side: int,
    entry_premium: float,
    current_premium: float,
    cfg: Ema9RsiMomentumConfig,
    dte: Optional[int] = None,
    iv: Optional[float] = None,
    bid: Optional[float] = None,
    ask: Optional[float] = None,
) -> ProtectiveExitResult:
    """Evaluate the EMA/RSI reversal protection + premium-decay warning for
    an open CE (``side=1``) or PE (``side=-1``) position.

    ``df`` is the underlying's own closed-candle OHLCV history (the same
    ``aggregator.get_latest_dataframe(sym)`` frame ``main.py`` already
    builds for every symbol) — entry/exit signals are always generated
    from the SPOT chart per the spec, never from the option's own candles.
    """
    if df is None or len(df) < 2 or side not in (1, -1):
        return ProtectiveExitResult()

    cross = compute_cross_signals(df, cfg)
    rsi_series = cross.indicators.rsi
    rsi_now = float(rsi_series.iloc[-1]) if not rsi_series.empty else float("nan")

    momentum = classify_momentum_strength(rsi_now, side, cfg)
    health = build_premium_health(entry_premium, current_premium, cfg, dte=dte, iv=iv, bid=bid, ask=ask)

    # ── EXIT CE: EMA9<EMA20 + RSI<RSI-EMA20 on the same candle ──
    # ── EXIT PE: EMA9>EMA20 + RSI>RSI-EMA20 on the same candle ──
    reversal = bool(cross.bearish[-1]) if side == 1 else bool(cross.bullish[-1])

    if reversal:
        opt_label = "CE" if side == 1 else "PE"
        reason = (
            f"EXIT {opt_label}: EMA{cfg.ema_fast} crossed "
            f"{'below' if side == 1 else 'above'} EMA{cfg.ema_slow} and RSI{cfg.rsi_length} "
            f"is {'below' if side == 1 else 'above'} RSI-EMA{cfg.rsi_ma_length} "
            f"(premium {health.pct_change:+.1f}%, decay {health.decay_level})."
        )
        logger.warning(reason)
        return ProtectiveExitResult(
            should_exit=True, warning=True, reason=reason,
            momentum_strength=momentum, premium_health=health,
        )

    upgrade = momentum_strength_upgrade(rsi_series, side, cfg)
    if upgrade:
        logger.info(
            "Momentum strength upgraded to %s for open %s position (RSI=%.1f, premium %+.1f%%, decay %s).",
            upgrade, "CE" if side == 1 else "PE", rsi_now, health.pct_change, health.decay_level,
        )

    if health.decay_level in (HIGH, CRITICAL):
        reason = (
            f"Premium Decay Warning ({health.decay_level}, {health.pct_change:+.1f}%) on open "
            f"{'CE' if side == 1 else 'PE'} position — momentum is {momentum}. "
            "No EMA/RSI reversal yet, so this is a protective warning, not a forced exit; "
            "combine with DTE/IV and manual judgement before acting."
        )
        logger.warning(reason)
        return ProtectiveExitResult(
            should_exit=False, warning=True, reason=reason,
            momentum_strength=momentum, premium_health=health,
        )

    logger.debug(
        "Holding %s position: no reversal, decay=%s (%+.1f%%), momentum=%s.",
        "CE" if side == 1 else "PE", health.decay_level, health.pct_change, momentum,
    )
    return ProtectiveExitResult(
        should_exit=False, warning=False, reason="",
        momentum_strength=momentum, premium_health=health,
    )
