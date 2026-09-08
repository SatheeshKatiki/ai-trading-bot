"""Smart Exit System for managing open positions.

Implements advanced exit strategies including:
- Dynamic trailing stop-loss (ATR-based)
- Partial profit booking
- Time-based exit (EOD square-off)
- Volatility-based exit
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Represents an open trade position."""
    symbol: str
    side: int                # 1 for Long, -1 for Short
    entry_price: float
    quantity: int
    entry_time: str
    highest_price: float     # Highest price reached since entry (for long)
    lowest_price: float      # Lowest price reached since entry (for short)
    stop_loss: float         # Current stop-loss price
    target: float            # Current profit target
    is_partially_booked: bool = False
    scales_done: int = 0     # Number of times this position has been scaled into
    lot_size: int = 1        # Lot size for quantity rounding
    is_exiting: bool = False # Lock flag: True while background iceberg exit is in flight
    is_scaling: bool = False # Lock flag: True while a background pyramid scale-in is in flight
    sl_order_id: str = None  # Exchange ID for the active Hard SL order
    max_pnl_pct: float = 0.0 # Peak profit % reached since entry, for the percentage-based trailing stop

    # ── Dynamic Fibonacci trail (opt-in; see SmartExitEngine) ─────────
    # All default to "no plan", so a Position constructed anywhere else in
    # the codebase behaves exactly as before and the fib block is skipped.
    #: (0.5, 0.618, 1.0) extension levels expressed in UNDERLYING price.
    fib_levels: Optional[tuple] = None
    #: +1 = extensions project upward (CE), -1 = downward (PE).
    fib_direction: int = 0
    #: 0 = nothing reached, 1 = 0.5 reached, 2 = 0.618 reached.
    fib_stage: int = 0
    #: Option premium observed at the moment 0.5 was reached — this is the
    #: level the 0.618 trail locks in, so it has to be remembered.
    fib_premium_at_half: float = 0.0


def plan_fib_levels(swing_high: float, swing_low: float, direction: int):
    """Fibonacci EXTENSION levels for a breakout, in underlying price.

    The swing range is projected beyond the swing in the trade's
    direction: upward from the swing high for a CE, downward from the
    swing low for a PE. Anchoring each side to the extreme it is breaking
    makes the two directions exact mirrors — a CE at 0.618 and a PE at
    0.618 are the same distance travelled, measured the same way.

    Returns `(level_0_5, level_0_618, level_1_0)`, or None when the swing
    is degenerate (zero or inverted range), which a caller must treat as
    "no fib plan" rather than as levels sitting on top of each other.
    """
    span = float(swing_high) - float(swing_low)
    if not span > 0:
        return None
    if direction >= 0:
        return (swing_high + 0.5 * span, swing_high + 0.618 * span, swing_high + span)
    return (swing_low - 0.5 * span, swing_low - 0.618 * span, swing_low - span)


from shared.exits.exit_analyzer import ExitAnalyzerAgent


class SmartExitEngine:
    """Engine for determining when to exit a position.

    Combines multiple exit strategies:
    1. Hard Stop-Loss / Profit Target
    2. AI Exit Analyzer (Multi-Factor Peak Protection & Adaptive Exits)
    3. ATR Trailing Stop
    4. Time-based End-of-Day Exit
    5. Partial Profit Booking
    """

    def __init__(
        self,
        atr_multiplier: float = 2.0,
        trailing_activation_pct: float = 1.0,
        trailing_offset_pct: float = 0.35,
        eod_exit_time: str = "15:15:00",
        partial_booking_pct: float = 50.0,
        partial_target_reward: float = 1.0,
        use_dynamic_fib_trail: bool = False,
        enable_exit_analyzer: bool = False,
        exit_analyzer_kwargs: Optional[dict] = None,
    ):
        """
        Parameters
        ----------
        atr_multiplier : float
            Multiplier for ATR to set trailing stop distance.
        trailing_activation_pct : float
            Profit percentage required before trailing stop activates.
        trailing_offset_pct : float
            Percentage points given back from the peak profit % before the
            percentage-based trailing stop fires.
        eod_exit_time : str
            Time (HH:MM:SS) to square off all intraday positions.
        partial_booking_pct : float
            Percentage of position to close at partial target.
        partial_target_reward : float
            Reward-to-risk ratio at which to take partial profit.
        enable_exit_analyzer : bool
            Enable AI Exit Analyzer Agent for multi-factor peak protection.
        exit_analyzer_kwargs : dict, optional
            Tuning passed straight to ``ExitAnalyzerAgent`` (min_peak_profit_pts,
            min_peak_profit_pct, max_giveback_pct, urgency_threshold, factor
            weights). Previously the agent was constructed with no arguments at
            all, so `ema9_rsi_momentum/config.py`'s MIN_PEAK_PROFIT_PTS /
            MAX_GIVEBACK_PCT / URGENCY_THRESHOLD were declared but reached
            nothing -- the knobs turned, but were not connected.
        """
        self.atr_multiplier = atr_multiplier
        self.trailing_activation_pct = trailing_activation_pct
        self.trailing_offset_pct = trailing_offset_pct
        self.eod_exit_time = eod_exit_time
        self.partial_booking_pct = partial_booking_pct
        self.partial_target_reward = partial_target_reward
        self.use_dynamic_fib_trail = use_dynamic_fib_trail
        self.enable_exit_analyzer = enable_exit_analyzer
        self.exit_analyzer = ExitAnalyzerAgent(**(exit_analyzer_kwargs or {}))

    def evaluate_exit(
        self,
        position: Position,
        current_price: float,
        current_time: str,  # HH:MM:SS format expected for intraday
        current_atr: float,
        underlying_price: Optional[float] = None,
        underlying_favourable: Optional[float] = None,
        df: Optional[pd.DataFrame] = None,
    ) -> tuple[bool, str, Optional[int]]:
        """Evaluate if the position should be exited or partially booked.

        Parameters
        ----------
        position : Position
            The open position to evaluate.
        current_price : float
            Latest price of the asset.
        current_time : str
            Current time (e.g., '14:30:00').
        current_atr : float
            Current Average True Range.

        Returns
        -------
        tuple[bool, str, Optional[int]]
            (Should Exit, Reason, Quantity to Exit).
            If Should Exit is True and Quantity is None, exit full position.
        """
        # `position.side` encodes the directional bet for options (CE=+1/
        # PE=-1), not "long vs short the instrument" -- this system only
        # ever BUYS options (see main.py's entry sizing: "Option buying
        # means we buy premium, so target is UP and SL is DOWN" -- true for
        # both CE and PE). A bought PUT still profits when ITS OWN premium
        # rises, exactly like a bought CALL, so every directional check
        # below must treat an option position as side=1 regardless of its
        # actual side value. `position.side` itself is left untouched --
        # callers elsewhere still need its original CE/PE meaning. Root-
        # caused 2026-08-03: with the real side=-1 (short-the-underlying)
        # convention, this function would fire "Stop-Loss Hit" on almost
        # any in-band price for a PUT, since its stop_loss sits BELOW entry
        # (option convention) while this function expected it ABOVE entry
        # (short-underlying convention).
        is_option = "CE" in position.symbol or "PE" in position.symbol
        effective_side = 1 if is_option else position.side

        # 1. Update position extremes for trailing stop
        if effective_side == 1:
            position.highest_price = max(position.highest_price, current_price)
        elif effective_side == -1:
            position.lowest_price = min(position.lowest_price, current_price)

        # 2. Time-based exit (EOD Square-off)
        # Extract time part if current_time contains date (e.g., "YYYY-MM-DD HH:MM:SS")
        time_only = current_time.split(" ")[-1] if " " in current_time else current_time
        if time_only >= self.eod_exit_time:
            logger.info("EOD Exit triggered for %s at %s", position.symbol, current_time)
            return True, "Time-based EOD Exit", None

        # 2b. Dynamic Fibonacci trail — OPT-IN, anchored to the UNDERLYING.
        #
        # Deliberately placed after the EOD square-off (a time stop must
        # still win) and BEFORE the hard stop-loss check below, so that a
        # stop this block ratchets upward is honoured by the existing
        # check on the very same evaluation rather than a bar later.
        #
        # Why the underlying and not the premium: the option's premium is
        # a function of spot, time and vol, so a premium-anchored "target"
        # silently moves with theta and IV. The trade thesis is about
        # where the INDEX goes, so the levels are expressed there and only
        # the resulting stop is expressed in premium.
        #
        # `underlying_favourable` is the intrabar extreme in the trade's
        # direction (bar high for CE, low for PE). Using it means a target
        # touched inside a candle is detected rather than missed because
        # the candle happened to close back below it — the "candle-close
        # only" behaviour that would erase realised option profits. Live,
        # where this is evaluated per tick, the two arguments are simply
        # the same current price.
        if (
            self.use_dynamic_fib_trail
            and position.fib_levels
            and underlying_price is not None
        ):
            probe = underlying_favourable if underlying_favourable is not None else underlying_price
            l50, l618, l100 = position.fib_levels
            up = position.fib_direction >= 0

            def _reached(level: float) -> bool:
                return probe >= level if up else probe <= level

            if _reached(l100):
                return True, "Fib 1.0 Target Hit", None

            # At most ONE stage advances per evaluation. Without this, a
            # single large bar that clears both 0.5 and 0.618 would record
            # the 0.5 premium and immediately trail the stop up to it —
            # i.e. to the current price — stopping the position out on the
            # spot for no reason.
            if position.fib_stage < 1 and _reached(l50):
                position.fib_stage = 1
                position.fib_premium_at_half = current_price
                # Cost-to-cost. Ratchet only: an option stop never loosens.
                position.stop_loss = max(position.stop_loss, position.entry_price)
                logger.info(
                    "FIB 0.5 reached for %s (underlying %.2f) — SL to breakeven %.2f",
                    position.symbol, probe, position.stop_loss,
                )
            elif position.fib_stage < 2 and _reached(l618):
                position.fib_stage = 2
                if position.fib_premium_at_half > 0:
                    position.stop_loss = max(position.stop_loss, position.fib_premium_at_half)
                    logger.info(
                        "FIB 0.618 reached for %s (underlying %.2f) — SL trailed to the "
                        "premium held at 0.5 (%.2f)",
                        position.symbol, probe, position.stop_loss,
                    )

        # 3. Hard Stop-Loss and Profit Target
        #
        # `target <= 0` means "no fixed profit target" — the position is left
        # to the trailing stop and the rest of this engine, with unlimited
        # upside. Option entries are written that way deliberately (see
        # main.py's entry path and shared/risk/option_stop_loss.py).
        #
        # The guard is load-bearing, not defensive padding: without it, a
        # target of 0.0 makes `current_price >= position.target` true on the
        # very first tick of every long position, closing it instantly and
        # reporting "Profit Target Hit". main.py's own hard-TP interceptor
        # already guarded on `target > 0`; this engine did not, so the two
        # exit layers disagreed about what a zero target meant.
        has_target = position.target is not None and position.target > 0
        if effective_side == 1:
            if current_price <= position.stop_loss:
                return True, "Stop-Loss Hit", None
            if has_target and current_price >= position.target:
                return True, "Profit Target Hit", None
        elif effective_side == -1:
            if current_price >= position.stop_loss:
                return True, "Stop-Loss Hit", None
            if has_target and current_price <= position.target:
                return True, "Profit Target Hit", None

        # 4. Partial Profit Booking
        #
        # Both branches below re-baseline the position: the stop moves to
        # breakeven, and `max_pnl_pct` — the peak-profit tracker the
        # percentage trailing stop in 5b measures give-back against — is
        # reset so the remaining "runner" trails from its OWN peak.
        #
        # Why the reset is load-bearing (2026-08-08): it used to keep the
        # peak the BOOKED half had already reached, so the runner was born
        # deep in give-back against a peak it never got to keep. 5b exits
        # once profit falls `trailing_offset_pct` (0.35 points by default)
        # below `max_pnl_pct`, while booking fires at 1:1 reward:risk —
        # far above that offset. The runner was therefore eligible to be
        # closed on the very next tick that ticked down.
        #
        # Measured on ema_rsi over the 123-day validation window (397
        # positions, 131 partially booked): runners survived a MEDIAN OF 2
        # BARS after booking, and 75.6% were closed by that trailing stop
        # rather than by a stop, a target or the EOD cutoff. See
        # validation_harness/results/exit_quality_ema_rsi.md.
        #
        # Full 123-day re-validation, every strategy with a cached
        # baseline (net, then max drawdown %):
        #   ema_rsi                202,040 -> 211,316   20.84 -> 19.01
        #   institutional_momentum  78,397 ->  88,511   16.74 -> 15.12
        #   enhanced_ai            -16,160 ->  14,711   55.31 -> 46.97
        #   MARL_Ultra             130,399 -> 149,120   41.26 -> 40.34
        #   buy_the_dip             74,102 ->  68,485   22.05 -> 22.05
        #   ultra_meta_dip_swarm    58,036 ->  53,892   24.99 -> 25.50
        # Four improve on return AND drawdown. The two mean-reversion
        # strategies give up ~7% of net — their edge is a fast bounce, so
        # the premature runner exit suited them by accident — but neither
        # leaves its drawdown gate. Applied to every strategy rather than
        # opted into per strategy because it is a state-consistency
        # defect, not a preference.
        if not position.is_partially_booked:
            risk = abs(position.entry_price - position.stop_loss)
            if risk > 0:
                if effective_side == 1:
                    unrealized_reward = current_price - position.entry_price
                else:
                    unrealized_reward = position.entry_price - current_price

                if (unrealized_reward / risk) >= self.partial_target_reward:
                    qty_to_book = int(position.quantity * (self.partial_booking_pct / 100))
                    if qty_to_book > 0:
                        position.is_partially_booked = True
                        # Move stop loss to breakeven after partial booking
                        position.stop_loss = position.entry_price
                        position.max_pnl_pct = 0.0  # runner trails from its own peak (see above)
                        return True, f"Partial Profit Booking (1:{self.partial_target_reward})", qty_to_book
                    elif position.quantity == 1:
                        position.is_partially_booked = True
                        position.stop_loss = position.entry_price
                        position.max_pnl_pct = 0.0  # runner trails from its own peak (see above)
                        import logging
                        logging.getLogger(__name__).info("Single lot partial target reached. Trailing SL to breakeven for %s", position.symbol)

        # 4b. AI Exit Analyzer Agent (Autonomous Multi-Factor Peak Protection)
        # Evaluates peak giveback, fast EMA9 break, RSI exhaustion, and volume deceleration.
        profit_pct = 0.0
        if effective_side == 1:
            profit_pct = (current_price - position.entry_price) / position.entry_price * 100
        else:
            profit_pct = (position.entry_price - current_price) / position.entry_price * 100

        if self.enable_exit_analyzer and profit_pct > 0:
            analysis = self.exit_analyzer.evaluate(
                entry_price=position.entry_price,
                current_price=current_price,
                highest_price=position.highest_price,
                lowest_price=position.lowest_price,
                # P&L space: a bought option profits when its own premium
                # rises, CE and PE alike -- same convention as everything
                # else in this function.
                direction=effective_side,
                # `df` is the UNDERLYING index frame (see main.py's call
                # site), so the momentum factors must be read against the
                # trade's thesis direction, not its premium direction.
                # position.side keeps the real CE=+1 / PE=-1 meaning; without
                # this a winning PUT (index falling, premium rising) would
                # score every confirming down-bar as a reversal and exit into
                # its own trend.
                underlying_direction=position.side if is_option else effective_side,
                df=df,
                is_option_premium=is_option,
            )
            if analysis.should_exit:
                logger.info("AI Exit Analyzer triggered for %s: %s", position.symbol, analysis.reason)
                return True, f"AI Exit Analyzer ({analysis.mode}): {analysis.reason}", None

            # Ratchet stop-loss upwards if the agent calculated a tighter trailing lock
            if analysis.suggested_sl is not None:
                if effective_side == 1 and analysis.suggested_sl > position.stop_loss:
                    position.stop_loss = analysis.suggested_sl
                elif effective_side == -1 and analysis.suggested_sl < position.stop_loss:
                    position.stop_loss = analysis.suggested_sl

        # 5. ATR Trailing Stop (Activates only after a certain profit percentage)
        if profit_pct >= self.trailing_activation_pct:
            if effective_side == 1:
                # Trailing stop for Long
                trailing_stop = position.highest_price - (current_atr * self.atr_multiplier)
                # Only move stop loss UP
                if trailing_stop > position.stop_loss:
                    position.stop_loss = trailing_stop
            elif effective_side == -1:
                # Trailing stop for Short
                trailing_stop = position.lowest_price + (current_atr * self.atr_multiplier)
                # Only move stop loss DOWN
                if trailing_stop < position.stop_loss:
                    position.stop_loss = trailing_stop

            # Check trailing stop immediately after updating
            if effective_side == 1 and current_price <= position.stop_loss:
                return True, "Trailing Stop-Loss Hit", None
            if effective_side == -1 and current_price >= position.stop_loss:
                return True, "Trailing Stop-Loss Hit", None

            # 5b. Percentage-based trailing stop (the "Trail Offset" dashboard
            # setting) — runs alongside the ATR-based trailing stop above,
            # whichever fires first wins. Tracks the peak profit % reached
            # since activation and exits once profit has given back more
            # than trailing_offset_pct from that peak.
            #
            # Suppressed when the dynamic fib trail is active, because the
            # two are competing trailing mechanisms and this one always
            # wins: `trailing_offset_pct` is a give-back in percentage
            # POINTS of P&L, and measured on real option paths 92.4% of
            # individual 5-minute bars move the premium by more than the
            # entire 0.35pp allowance on their own (see
            # validation_harness/results/exit_quality_ema_rsi.md). It is
            # therefore "exit on the first close below the peak", which is
            # precisely the behaviour the fib trail exists to replace —
            # leaving it on would let it cut every runner long before any
            # extension level could be reached. The ATR trail above stays
            # active: it is scaled in the option's own premium units and
            # acts as a genuine safety net rather than a hair trigger.
            if not self.use_dynamic_fib_trail:
                position.max_pnl_pct = max(position.max_pnl_pct, profit_pct)
                if profit_pct <= position.max_pnl_pct - self.trailing_offset_pct:
                    return True, "Trailing Stop-Loss Hit (Offset)", None

        return False, "", None
