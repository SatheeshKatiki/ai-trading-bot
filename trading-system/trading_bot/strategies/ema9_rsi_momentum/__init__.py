"""EMA9/RSI Momentum Strategy — independent Entry Logic module.

Implements ONLY the entry-signal rules specified for this strategy:

* EMA 9 / EMA 20 crossover on the spot chart
* RSI 14 vs its own EMA 20 smoothing, crossing the same bar as the EMA
* RSI 40/50/60 momentum-strength bands (informational, logged alongside
  every signal — never an independent trigger)

Everything else this strategy needs already exists and is reused, not
reimplemented:

* **ATM CE/PE selection** — ``trading_bot/strategies/premium_selection/
  options_selector.py::select_option`` — ``trading_bot/main.py`` already
  auto-maps ANY non-``institutional_momentum``/``premium`` strategy's
  index signal to the ATM option at the spot price seen at signal time,
  so registering ``generate_signals`` here is enough; no separate ATM
  logic is added.
* **Stop-Loss / Target / Money Management / Position Sizing** —
  ``shared/exits/exit_engine.py`` (``SmartExitEngine``) and
  ``shared/risk/`` (``RiskManager``, ``resolve_initial_stop``,
  ``resolve_option_atr``) — untouched, and already run generically for
  every registered strategy via ``main.py``'s existing tick loop.
* **Institutional filters / AI confidence gate / sentiment breaker** —
  applied globally by ``registry.run_strategy`` / ``main.py`` exactly as
  for every other strategy; this module declares neither
  ``OWNS_INSTITUTIONAL_FILTERS`` nor ``SKIP_INSTITUTIONAL_FILTERS``, so
  the default (apply them) is unchanged.

The only genuinely new integration point is the EMA/RSI reversal
*protection* layer (``evaluate_protective_exit``, in ``premium_health.py``)
run from ``main.py`` ALONGSIDE (never instead of) the existing
``SmartExitEngine`` for open positions on this strategy — see the
`STRATEGY_NAME` guard in ``main.py``'s exit-evaluation block.
"""

from __future__ import annotations

import logging
from collections import deque

import pandas as pd

from trading_bot.strategies._signal_utils import edge_trigger

from .config import Ema9RsiMomentumConfig
from .premium_health import (
    PremiumHealth,
    ProtectiveExitResult,
    build_premium_health,
    classify_decay,
    evaluate_protective_exit as _evaluate_protective_exit,
)
from .signal_engine import (
    CrossSignals,
    build_entry_signal_series,
    classify_momentum_strength,
)

logger = logging.getLogger(__name__)

STRATEGY_NAME = "ema9_rsi_momentum"

__all__ = [
    "STRATEGY_NAME",
    "generate_signals",
    "evaluate_protective_exit",
    "Ema9RsiMomentumConfig",
    "PremiumHealth",
    "ProtectiveExitResult",
    "build_premium_health",
    "classify_decay",
    "classify_momentum_strength",
    "CrossSignals",
]

# Bounded dedup guard so a signal candle that repeatedly fails downstream
# gates (AI confidence / market hours / sentiment / EOD cutoff) doesn't log
# the same "signal generated" line on every ~200ms re-evaluation until the
# next candle closes. Keyed on (bar timestamp, direction), which is unique
# enough across symbols in practice; a hash collision only costs one
# skipped duplicate log line, never a wrong trading decision — this deque
# only gates logging, not the returned signal series.
_MAX_LOGGED_SIGNALS = 128
_logged_signal_bars: deque = deque(maxlen=_MAX_LOGGED_SIGNALS)
_logged_signal_bars_set: set = set()


def _log_once_per_bar(key) -> bool:
    if key in _logged_signal_bars_set:
        return False
    if len(_logged_signal_bars) == _MAX_LOGGED_SIGNALS:
        _logged_signal_bars_set.discard(_logged_signal_bars[0])
    _logged_signal_bars.append(key)
    _logged_signal_bars_set.add(key)
    return True


def generate_signals(
    df: pd.DataFrame,
    ema_fast: int = 9,
    ema_slow: int = 20,
    rsi_length: int = 14,
    rsi_ma_length: int = 20,
    rsi_band_normal: float = 40.0,
    rsi_band_strong: float = 50.0,
    rsi_band_very_strong: float = 60.0,
    enable_adx_filter: bool = True,
    min_adx: float = 18.0,
    enable_time_filter: bool = True,
    time_start: str = "09:25",
    time_end: str = "15:00",
    enable_touch_filter: bool = True,
    **kwargs,
) -> pd.Series:
    """Registry entry point. Returns a ``pandas.Series`` of ``1`` (CE buy),
    ``-1`` (PE buy), or ``0`` (no trade), aligned to ``df``'s index.
    """
    cfg = Ema9RsiMomentumConfig(
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        rsi_length=rsi_length,
        rsi_ma_length=rsi_ma_length,
        rsi_band_normal=rsi_band_normal,
        rsi_band_strong=rsi_band_strong,
        rsi_band_very_strong=rsi_band_very_strong,
        enable_adx_filter=enable_adx_filter,
        min_adx=min_adx,
        enable_time_filter=enable_time_filter,
        time_start=time_start,
        time_end=time_end,
        enable_touch_filter=enable_touch_filter,
        **{k: v for k, v in kwargs.items() if k in Ema9RsiMomentumConfig.__dataclass_fields__},
    )

    if df is None or df.empty or "close" not in df.columns:
        return pd.Series(dtype=int)

    signals, cross = build_entry_signal_series(df, cfg, edge_trigger)

    latest_direction = int(signals.iloc[-1]) if len(signals) else 0
    if latest_direction != 0:
        bar_key = (df.index[-1], latest_direction)
        if _log_once_per_bar(bar_key):
            ind = cross.indicators
            rsi_now = float(ind.rsi.iloc[-1])
            momentum = classify_momentum_strength(rsi_now, latest_direction, cfg)
            side_label = "CE" if latest_direction == 1 else "PE"
            logger.info(
                "ENTRY %s | EMA%d %.2f %s EMA%d %.2f | RSI%d %.2f %s RSI-of-EMA%d %.2f | "
                "Momentum: %s | Reason: EMA/RSI crossover confirmed on the same closed candle.",
                side_label,
                cfg.ema_fast, float(ind.ema_fast.iloc[-1]), ">" if latest_direction == 1 else "<", cfg.ema_slow, float(ind.ema_slow.iloc[-1]),
                cfg.rsi_length, rsi_now, "above" if latest_direction == 1 else "below", cfg.ema_slow, float(ind.rsi_ma.iloc[-1]),
                momentum,
            )

    return signals


def evaluate_protective_exit(
    df: pd.DataFrame,
    side: int,
    entry_premium: float,
    current_premium: float,
    settings: dict | None = None,
    **overrides,
) -> ProtectiveExitResult:
    """``main.py``-facing wrapper: builds the config from a flat settings
    dict (``ema9_rsi_*`` keys, see ``config.py``) and delegates to
    :func:`premium_health.evaluate_protective_exit`.

    This is the ONLY function ``main.py`` needs to call for this
    strategy's exit protection layer; it never touches ``SmartExitEngine``
    or ``RiskManager`` state, and its ``should_exit=False`` result never
    prevents the existing SL/Target/trailing checks from running.
    """
    cfg = Ema9RsiMomentumConfig.from_settings(settings, **overrides)
    return _evaluate_protective_exit(df, side, entry_premium, current_premium, cfg)
