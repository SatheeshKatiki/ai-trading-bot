"""Whether to act on a signal, for whichever strategy the user selected.

The UI lets the user pick a strategy and a chart timeframe. Two of the
owner's rules are about *when and how well* an entry is taken rather than
about any one strategy's maths, and they have to hold whatever is selected:

  * **timing** -- a signal on a bar that has not closed is not final yet, so
    the entry waits for the last seconds of the bar unless momentum is
    already strong. This needs nothing but price and a clock, so it applies
    to every strategy.
  * **entry quality** -- how good the setup is, graded HIGH / MEDIUM / LOW.
    This one IS strategy-specific: "did the candle touch both EMAs" means
    nothing to a strategy with no EMAs in it.

So a strategy may publish its own grader as a module-level
``assess_entry_quality(df, direction, settings)`` returning an object with
``priority`` and ``take``. This layer calls it when it exists and skips
grading when it does not, rather than forcing one strategy's idea of quality
onto the rest. ``ema9_rsi_momentum`` publishes one; the others do not yet,
and are gated on timing alone.

Nothing here decides *direction* -- that is the strategy's job. This only
answers "act on it now, or not yet".
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any, Optional

from shared.timeframes import settings_timeframe, timeframe_label

#: Grades, weakest to strongest. A strategy that publishes no grader reports
#: UNGRADED -- which is taken, not skipped: absence of a grader is not a
#: reason to refuse a signal the strategy itself produced.
PRIORITY_HIGH = "HIGH"
PRIORITY_MEDIUM = "MEDIUM"
PRIORITY_LOW = "LOW"
UNGRADED = "UNGRADED"


@dataclass(frozen=True)
class EntryDecision:
    """The answer, plus enough of the why to put in a log line."""

    take: bool
    priority: str
    reason: str
    timeframe_minutes: int
    strategy: str

    def __str__(self) -> str:                      # for log lines
        verdict = "take" if self.take else "hold"
        return f"{verdict} [{self.priority}] {self.reason}"


def _grader(strategy_name: str):
    """The selected strategy's own entry grader, or None if it has no view."""
    try:
        import importlib
        module = importlib.import_module(f"trading_bot.strategies.{strategy_name}")
    except Exception:
        return None
    return getattr(module, "assess_entry_quality", None)


def grade_entry(strategy_name: str, df, direction: int,
                settings: Optional[dict] = None) -> tuple[str, Optional[Any]]:
    """Grade the latest bar's setup using the selected strategy's own rules.

    Returns ``(priority, detail)``. A strategy with no grader returns
    ``(UNGRADED, None)`` -- it is not penalised for not having an opinion.
    """
    grader = _grader(strategy_name)
    if grader is None:
        return UNGRADED, None
    try:
        result = grader(df, direction, settings or {})
    except Exception:
        return UNGRADED, None
    if result is None:
        return UNGRADED, None
    priority = getattr(result, "priority", None)
    if priority is None:
        return UNGRADED, result
    return str(priority), result


def decide(strategy_name: str, df, direction: int, strength: str,
           settings: Optional[dict] = None,
           now: Optional[_dt.datetime] = None) -> EntryDecision:
    """Act on this signal now, or hold it?

    `direction` is +1 for a long/CE and -1 for a short/PE; `strength` is the
    momentum label the caller already has. The timeframe comes from the
    user's own UI selection, so a 15-minute chart waits for a 15-minute bar.

    Order matters: quality first, because a setup the strategy itself grades
    LOW should be dropped outright rather than held until the bar closes and
    then taken anyway.
    """
    settings = settings or {}
    minutes = settings_timeframe(settings)
    now = now or _dt.datetime.now()

    priority, _ = grade_entry(strategy_name, df, direction, settings)
    if priority == PRIORITY_LOW:
        return EntryDecision(
            take=False, priority=priority, strategy=strategy_name,
            timeframe_minutes=minutes,
            reason=(f"{strategy_name} grades this setup LOW -- a wick touch "
                    f"with neither trend agreement nor RSI separation"))

    # ── Institutional Exhaustion Filter (RSI Guard) ──
    # Option buyers must never buy CE into extreme overbought exhaustion (RSI > 75)
    # or PE into extreme oversold exhaustion (RSI < 25)
    try:
        if df is not None and "close" in df.columns and len(df) >= 14:
            from shared.indicators import rsi as _calc_rsi
            _rsi_series = _calc_rsi(df["close"], 14)
            _rsi_val = float(_rsi_series.iloc[-1])
            _rsi_cap = float(settings.get("rsi_overbought_cap", 75.0))
            _rsi_floor = float(settings.get("rsi_oversold_floor", 25.0))
            if direction > 0 and _rsi_val > _rsi_cap:
                return EntryDecision(
                    take=False, priority=PRIORITY_LOW, strategy=strategy_name,
                    timeframe_minutes=minutes,
                    reason=f"RSI {_rsi_val:.1f} is overbought (> {_rsi_cap:.0f}) -- CE entry blocked to prevent buying at top"
                )
            if direction < 0 and _rsi_val < _rsi_floor:
                return EntryDecision(
                    take=False, priority=PRIORITY_LOW, strategy=strategy_name,
                    timeframe_minutes=minutes,
                    reason=f"RSI {_rsi_val:.1f} is oversold (< {_rsi_floor:.0f}) -- PE entry blocked to prevent selling at bottom"
                )
    except Exception:
        pass

    allowed, why = _timing(now, strength, minutes, settings)
    return EntryDecision(take=allowed, priority=priority, reason=why,
                         timeframe_minutes=minutes, strategy=strategy_name)


def _timing(now: _dt.datetime, strength: str, minutes: int,
            settings: dict) -> tuple[bool, str]:
    """The bar-close confirmation rule, for any strategy.

    Delegates to ema9_rsi_momentum's implementation, which is where the rule
    is written down and tested; the config it builds carries only the generic
    knobs (bar size, confirmation window, strength floor), so nothing
    EMA-specific leaks into a strategy that has no EMAs.
    """
    try:
        from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig
        from trading_bot.strategies.ema9_rsi_momentum.signal_engine import entry_timing_gate
        cfg = Ema9RsiMomentumConfig.from_settings(settings, timeframe_minutes=minutes)
        return entry_timing_gate(now, strength, cfg, bar_minutes=minutes)
    except Exception as exc:                       # never block a live entry on this
        return True, f"timing gate unavailable on {timeframe_label(minutes)} ({exc})"
