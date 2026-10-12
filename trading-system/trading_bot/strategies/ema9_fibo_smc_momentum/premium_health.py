"""Premium health and Price Action protective exit evaluation for EMA 9 / Fibo OTE Momentum Pro."""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from trading_bot.strategies.ema9_rsi_momentum.premium_health import (
    PremiumHealth,
    ProtectiveExitResult,
    build_premium_health,
    classify_decay,
)
from trading_bot.strategies.ema9_rsi_momentum.premium_health import (
    evaluate_protective_exit as _evaluate_protective_exit_base,
)
from trading_bot.strategies.ema9_fibo_smc_momentum.config import Ema9FiboSmcMomentumConfig
from trading_bot.strategies.ema9_fibo_smc_momentum.signal_engine import (
    evaluate_price_action_exit,
)

logger = logging.getLogger(__name__)

__all__ = [
    "PremiumHealth",
    "ProtectiveExitResult",
    "build_premium_health",
    "classify_decay",
    "evaluate_protective_exit",
]


def evaluate_protective_exit(
    df: pd.DataFrame,
    side: int,
    entry_premium: float,
    current_premium: float,
    cfg: Ema9FiboSmcMomentumConfig,
    dte: Optional[int] = None,
    iv: Optional[float] = None,
    bid: Optional[float] = None,
    ask: Optional[float] = None,
) -> ProtectiveExitResult:
    """Evaluates Pure Price Action exit first (MSS break, target exhaustion, RSI divergence),
    falling back to base reversal check.
    """
    if df is None or len(df) < 2 or side not in (1, -1):
        return ProtectiveExitResult()

    health = build_premium_health(
        entry_premium, current_premium, cfg, dte=dte, iv=iv, bid=bid, ask=ask
    )

    # 1. Pure Price Action Exit (Primary)
    if getattr(cfg, "price_action_primary", True):
        close_arr = df["close"].to_numpy()
        entry_spot = close_arr[0] if len(close_arr) else 0.0
        current_spot = close_arr[-1] if len(close_arr) else 0.0

        pa_res = evaluate_price_action_exit(
            df=df,
            direction=side,
            entry_spot=entry_spot,
            current_spot=current_spot,
            cfg=cfg,
            entry_premium=entry_premium,
            current_premium=current_premium,
        )
        if pa_res.should_exit:
            logger.info("PRICE ACTION EXIT TRIGGERED | %s", pa_res.exit_reason)
            return ProtectiveExitResult(
                should_exit=True,
                warning=True,
                reason=pa_res.exit_reason,
                momentum_strength="EXHAUSTED",
                premium_health=health,
            )

    # 2. Fall back to standard reversal check if price action structure is still intact
    return _evaluate_protective_exit_base(
        df=df,
        side=side,
        entry_premium=entry_premium,
        current_premium=current_premium,
        cfg=cfg,
        dte=dte,
        iv=iv,
        bid=bid,
        ask=ask,
    )
