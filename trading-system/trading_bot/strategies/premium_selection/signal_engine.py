"""Premium Signal Engine — Master Orchestrator.

Combines all 8 filter layers into a single, institutional-grade trade signal.

Philosophy: TRADE LESS, TRADE BETTER.
- Every layer must independently confirm
- One weak layer = NO TRADE
- Capital protection > Trade frequency
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional

import pandas as pd

from .trend_filter      import compute_trend
from .momentum_filter   import compute_momentum
from .volume_filter     import compute_volume
from .volatility_filter import compute_volatility
from .market_structure  import compute_market_structure
from .no_trade_filter   import compute_no_trade_conditions
from .options_selector  import select_option, calculate_lots, OptionContract


# ──────────────────────────────────────────────
# Signal result container
# ──────────────────────────────────────────────
@dataclass
class PremiumSignal:
    """Structured output from the Premium Signal Engine."""
    direction: Literal["BUY_CALL", "BUY_PUT", "NO_TRADE"]
    confidence: float           # 0.0 – 1.0 composite score
    ai_confidence: float        # From the AI filter model
    option: Optional[OptionContract] = None

    # Layer-by-layer breakdown for dashboard display
    layers_passed: dict = field(default_factory=dict)
    reject_reason: str = ""

    @property
    def is_tradeable(self) -> bool:
        return self.direction != "NO_TRADE" and self.confidence >= 0.75

    def __str__(self) -> str:
        if self.direction == "NO_TRADE":
            return f"NO_TRADE | Reason: {self.reject_reason}"
        opt = self.option.symbol if self.option else "N/A"
        return (
            f"{self.direction} | "
            f"Option: {opt} | "
            f"Confidence: {self.confidence:.0%} | "
            f"AI: {self.ai_confidence:.0%}"
        )


# ──────────────────────────────────────────────
# Premium Signal Engine
# ──────────────────────────────────────────────
class PremiumSignalEngine:
    """
    Institutional-grade multi-layer trade filtering engine.

    Usage::

        engine = PremiumSignalEngine(instrument="NIFTY", capital=100_000)
        signal = engine.evaluate(df, ai_confidence=0.87)
        if signal.is_tradeable:
            print(signal.option.symbol)  # Place order on this symbol
    """

    def __init__(
        self,
        instrument: str = "NIFTY",
        capital: float = 100_000.0,
        min_ai_confidence: float = 0.75,
        itm_strikes: int = 1,       # 1 = slight ITM for liquidity
        rsi_call_thresh: float = 55,
        rsi_put_thresh: float = 45,
    ):
        self.instrument        = instrument.upper()
        self.capital           = capital
        self.min_ai_confidence = min_ai_confidence
        self.itm_strikes       = itm_strikes
        self.rsi_call_thresh   = rsi_call_thresh
        self.rsi_put_thresh    = rsi_put_thresh

    def evaluate(
        self,
        df: pd.DataFrame,
        ai_confidence: float = 1.0,
    ) -> PremiumSignal:
        """
        Run all filter layers on the latest bar of ``df``.

        Parameters
        ----------
        df             : OHLCV DataFrame (minimum 200 bars for EMA200)
        ai_confidence  : confidence score from the AI filter model (0.0–1.0)

        Returns
        -------
        PremiumSignal — contains direction, option contract, and full layer breakdown.
        """
        if len(df) < 200:
            return PremiumSignal(
                direction="NO_TRADE",
                confidence=0.0,
                ai_confidence=ai_confidence,
                reject_reason="Insufficient data (need 200+ bars for EMA200)",
            )

        # ── Layer 0: AI Confidence Gate ───────────────────────────────
        if ai_confidence < self.min_ai_confidence:
            return PremiumSignal(
                direction="NO_TRADE",
                confidence=0.0,
                ai_confidence=ai_confidence,
                reject_reason=f"AI confidence {ai_confidence:.0%} < threshold {self.min_ai_confidence:.0%}",
            )

        # ── Run all filter computations ───────────────────────────────
        # Single copy here; individual filter functions do NOT copy again
        # since we pass the same mutable frame through the pipeline.
        df = df.copy()
        df = compute_trend(df)
        df = compute_momentum(df, rsi_call_thresh=self.rsi_call_thresh, rsi_put_thresh=self.rsi_put_thresh)
        df = compute_volume(df)
        df = compute_volatility(df)
        df = compute_market_structure(df)
        df = compute_no_trade_conditions(df)

        # Get the LAST bar (current signal)
        row = df.iloc[-1]

        # ── Layer 1: No-Trade Guard ───────────────────────────────────
        if row.get("no_trade", False):
            reason = "No-trade condition: "
            if row.get("in_no_trade_window", False):
                reason += "restricted time window"
            elif row.get("is_sideways", False):
                reason += "sideways market"
            else:
                reason += "choppy/non-trending market"
            return PremiumSignal(
                direction="NO_TRADE", confidence=0.0,
                ai_confidence=ai_confidence, reject_reason=reason,
            )

        # ── Layer 2: Volatility Guard ─────────────────────────────────
        if not row.get("volatility_ok", True):
            return PremiumSignal(
                direction="NO_TRADE", confidence=0.0,
                ai_confidence=ai_confidence, reject_reason="Volatility out of tradeable range (too low or news spike)",
            )

        # ── Determine direction ───────────────────────────────────────
        bullish = (
            row.get("trend_bullish", False) and
            row.get("momentum_bullish", False) and
            row.get("volume_confirmed", False) and
            row.get("vol_expanding", False) and
            row.get("structure_bullish", False)
        )

        bearish = (
            row.get("trend_bearish", False) and
            row.get("momentum_bearish", False) and
            row.get("volume_confirmed", False) and
            row.get("vol_expanding", False) and
            row.get("structure_bearish", False)
        )

        if not bullish and not bearish:
            # Build detailed reject reason
            reasons = []
            if not row.get("trend_bullish", False) and not row.get("trend_bearish", False):
                reasons.append("trend not aligned")
            if not row.get("momentum_bullish", False) and not row.get("momentum_bearish", False):
                reasons.append("momentum weak")
            if not row.get("volume_confirmed", False):
                reasons.append("volume insufficient")
            if not row.get("structure_bullish", False) and not row.get("structure_bearish", False):
                reasons.append("no valid market structure")
            return PremiumSignal(
                direction="NO_TRADE", confidence=0.0,
                ai_confidence=ai_confidence,
                reject_reason="; ".join(reasons) or "Layers not aligned",
            )

        # ── Composite Confidence Score ────────────────────────────────
        # Weighted average of all layers (normalized 0–1)
        direction = "BUY_CALL" if bullish else "BUY_PUT"
        opt_type  = "CE" if bullish else "PE"

        layers = {
            "trend":      1.0 if (row.get("trend_bullish") if bullish else row.get("trend_bearish")) else 0.0,
            "momentum":   1.0 if (row.get("momentum_bullish") if bullish else row.get("momentum_bearish")) else 0.0,
            "volume":     min(row.get("vol_ratio", 1.0) / 2.0, 1.0),
            "volatility": 1.0 if row.get("vol_expanding", False) else 0.5,
            "structure":  1.0 if (row.get("structure_bullish") if bullish else row.get("structure_bearish")) else 0.0,
            "ai":         ai_confidence,
        }

        weights = {"trend": 0.20, "momentum": 0.20, "volume": 0.15,
                   "volatility": 0.10, "structure": 0.20, "ai": 0.15}

        composite = sum(layers[k] * weights[k] for k in layers)
        composite = min(composite, 1.0)

        # Final threshold: composite must be ≥ 0.75 to be premium
        if composite < 0.75:
            return PremiumSignal(
                direction="NO_TRADE", confidence=composite,
                ai_confidence=ai_confidence,
                reject_reason=f"Composite score {composite:.0%} below premium threshold 75%",
                layers_passed=layers,
            )

        # ── Options Selection ─────────────────────────────────────────
        spot = float(row["close"])
        contract = select_option(
            instrument=self.instrument,
            spot_price=spot,
            direction=opt_type,
            itm_strikes=self.itm_strikes,
        )

        return PremiumSignal(
            direction=direction,
            confidence=composite,
            ai_confidence=ai_confidence,
            option=contract,
            layers_passed=layers,
        )


def generate_signals(
    df: pd.DataFrame,
    instrument: str = "NIFTY",
    ema_fast: int = 20,
    ema_slow: int = 50,
    rsi_window: int = 14,
    rsi_buy_thresh: float = 55,
    rsi_sell_thresh: float = 45,
    **kwargs,
) -> pd.Series:
    """
    Drop-in compatible generate_signals() for the strategy registry.

    Runs the PremiumSignalEngine on a rolling basis, returning a
    standard pd.Series of 1 (BUY CALL), -1 (BUY PUT), 0 (NO TRADE).

    Note: For live trading, use PremiumSignalEngine.evaluate() directly
    to get the full PremiumSignal with option contract details.
    """
    if len(df) < 205:
        return pd.Series(0, index=df.index, dtype=int)

    engine = PremiumSignalEngine(
        instrument=instrument,
        rsi_call_thresh=rsi_buy_thresh,
        rsi_put_thresh=rsi_sell_thresh,
    )

    signals = pd.Series(0, index=df.index, dtype=int)

    # Only evaluate the last bar for efficiency in live mode
    # For backtesting, evaluate each bar with a rolling window
    for i in range(200, len(df)):
        window = df.iloc[max(0, i - 250): i + 1].reset_index(drop=True)
        sig = engine.evaluate(window, ai_confidence=1.0)
        if sig.direction == "BUY_CALL":
            signals.iloc[i] = 1
        elif sig.direction == "BUY_PUT":
            signals.iloc[i] = -1

    return signals
