"""Regression tests for shared/exits/exit_engine.py's SmartExitEngine.

This is the hard SL/target/trailing-stop/EOD-square-off decision engine
behind every non-institutional_momentum strategy's exit path (trading_bot/
main.py's on_tick() calls SmartExitEngine.evaluate_exit() directly). It had
zero test coverage anywhere in the suite before this file -- found during
the 2026-08-03 production-readiness audit while validating a fix to what
price gets fed into this function (previously the underlying index price
for option positions; now the option's own live premium). These tests
exercise the decision logic itself directly, independent of that price-
sourcing fix, using realistic option-premium-scale numbers from that day's
actual trade (entry 75.05, SL 74.71, TGT 77.68 -- a PE, side=-1).
"""
import sys
from pathlib import Path

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from shared.exits import Position, SmartExitEngine


def _put_position(entry_price=75.05, stop_loss=74.712275, target=77.67675, **overrides):
    """A bought PUT: side=-1 encodes the bearish directional bet, not
    'short the contract' -- this system only ever buys options."""
    defaults = dict(
        symbol="NSE:NIFTY2680424600PE", side=-1, entry_price=entry_price,
        quantity=65, entry_time="2026-08-03T10:34:10", highest_price=entry_price,
        lowest_price=entry_price, stop_loss=stop_loss, target=target,
    )
    defaults.update(overrides)
    return Position(**defaults)


def _call_position(entry_price=100.0, stop_loss=95.0, target=115.0, **overrides):
    """A bought CALL: side=1."""
    defaults = dict(
        symbol="NSE:NIFTY26AUG24700CE", side=1, entry_price=entry_price,
        quantity=65, entry_time="2026-08-03T10:00:00", highest_price=entry_price,
        lowest_price=entry_price, stop_loss=stop_loss, target=target,
    )
    defaults.update(overrides)
    return Position(**defaults)


MORNING = "2026-08-03 10:40:00"  # well before the default 15:15:00 EOD cutoff


def _engine(**overrides):
    defaults = dict(trailing_activation_pct=9999.0)  # off unless a test wants it
    defaults.update(overrides)
    return SmartExitEngine(**defaults)


# ---------------------------------------------------------------------------
# Hard stop-loss / target
# ---------------------------------------------------------------------------

def test_put_stop_loss_hit_when_premium_falls_to_sl():
    """A bought PUT's stop-loss sits BELOW entry in premium terms -- same
    convention as a bought CALL, since profiting requires the PREMIUM
    itself to rise regardless of which contract type was bought (matches
    main.py's own entry sizing: SL is always entry*(1-sl_pct), target is
    always entry*(1+target_pct), for both CE and PE)."""
    engine = _engine()
    pos = _put_position()
    should_exit, reason, qty = engine.evaluate_exit(pos, current_price=74.0, current_time=MORNING, current_atr=1.0)
    assert should_exit is True
    assert reason == "Stop-Loss Hit"
    assert qty is None  # full exit


def test_put_target_hit_when_premium_rises_to_target():
    engine = _engine()
    pos = _put_position()
    should_exit, reason, qty = engine.evaluate_exit(pos, current_price=77.70, current_time=MORNING, current_atr=1.0)
    assert should_exit is True
    assert reason == "Profit Target Hit"


def test_put_no_exit_when_price_between_sl_and_target():
    engine = _engine()
    pos = _put_position()
    should_exit, reason, qty = engine.evaluate_exit(pos, current_price=75.20, current_time=MORNING, current_atr=1.0)
    assert should_exit is False


def test_call_stop_loss_hit_when_premium_falls_below_sl():
    engine = _engine()
    pos = _call_position()
    should_exit, reason, qty = engine.evaluate_exit(pos, current_price=94.0, current_time=MORNING, current_atr=1.0)
    assert should_exit is True
    assert reason == "Stop-Loss Hit"


def test_call_target_hit_when_premium_rises_to_target():
    engine = _engine()
    pos = _call_position()
    should_exit, reason, qty = engine.evaluate_exit(pos, current_price=116.0, current_time=MORNING, current_atr=1.0)
    assert should_exit is True
    assert reason == "Profit Target Hit"


# ---------------------------------------------------------------------------
# EOD square-off — must preempt everything else, including a profitable
# in-band position that hasn't hit SL or target
# ---------------------------------------------------------------------------

def test_eod_exit_fires_after_cutoff_even_mid_band():
    engine = _engine()
    pos = _put_position()  # price 75.20 is between SL (74.71) and TGT (77.68) -- no hard exit would fire
    should_exit, reason, qty = engine.evaluate_exit(pos, current_price=75.20, current_time="2026-08-03 15:15:01", current_atr=1.0)
    assert should_exit is True
    assert reason == "Time-based EOD Exit"


def test_eod_exit_does_not_fire_one_second_before_cutoff():
    engine = _engine()
    pos = _put_position()
    should_exit, reason, qty = engine.evaluate_exit(pos, current_price=75.20, current_time="2026-08-03 15:14:59", current_atr=1.0)
    assert should_exit is False


def test_eod_cutoff_handles_datetime_with_date_prefix():
    """current_time can arrive as 'YYYY-MM-DD HH:MM:SS' -- must extract just
    the time portion, not string-compare the whole thing (which would always
    be False since a full datetime string never equals '15:15:00')."""
    engine = _engine()
    pos = _put_position()
    should_exit, reason, qty = engine.evaluate_exit(pos, current_price=75.20, current_time="2026-08-03 21:20:04", current_atr=1.0)
    assert should_exit is True
    assert reason == "Time-based EOD Exit"


# ---------------------------------------------------------------------------
# highest_price / lowest_price tracking (what the earlier bug left frozen
# at entry_price all day for option positions, since they never received a
# real premium on any tick)
# ---------------------------------------------------------------------------

def test_highest_price_tracked_for_put_position():
    """A bought PUT is tracked like a bought CALL internally (highest_price,
    not lowest_price) -- it profits when its own premium rises, same as a
    CALL. Only a genuine short-the-underlying position tracks lowest_price."""
    engine = _engine()
    pos = _put_position(target=9999.0)  # keep it in-band so it doesn't exit
    engine.evaluate_exit(pos, current_price=76.0, current_time=MORNING, current_atr=1.0)
    assert pos.highest_price == 76.0
    engine.evaluate_exit(pos, current_price=75.20, current_time=MORNING, current_atr=1.0)
    assert pos.highest_price == 76.0  # must not move back down


def test_highest_price_tracked_for_call_position():
    engine = _engine()
    pos = _call_position()
    engine.evaluate_exit(pos, current_price=110.0, current_time=MORNING, current_atr=1.0)
    assert pos.highest_price == 110.0
    engine.evaluate_exit(pos, current_price=105.0, current_time=MORNING, current_atr=1.0)
    assert pos.highest_price == 110.0  # must not move back down


# ---------------------------------------------------------------------------
# Trailing stop (ATR-based) — activates only after trailing_activation_pct
# profit, then only ever ratchets the stop in the favorable direction
# ---------------------------------------------------------------------------

def test_trailing_stop_activates_and_ratchets_for_call():
    # partial_target_reward set high so partial-booking (a separate feature)
    # doesn't interfere with isolating the trailing-stop mechanism.
    engine = _engine(trailing_activation_pct=1.0, atr_multiplier=1.0, partial_target_reward=999.0)
    # SL far away so only the trailing stop can fire here.
    pos = _call_position(entry_price=100.0, stop_loss=0.0, target=9999.0)

    # +5% profit, activates trailing (>= 1.0%). ATR=1.0 -> trailing_stop = 105 - 1.0 = 104.
    should_exit, reason, qty = engine.evaluate_exit(pos, current_price=105.0, current_time=MORNING, current_atr=1.0)
    assert should_exit is False
    assert pos.stop_loss == 104.0

    # Price pulls back to 104 exactly -> the ratcheted stop is hit. (The hard
    # SL check in section 3 re-reads this same, now-trailed stop_loss value
    # on this next call, so it reports "Stop-Loss Hit" -- the dedicated
    # "Trailing Stop-Loss Hit" label is only reachable within the exact same
    # call that ratchets the stop, which can't happen since the newly
    # computed trailing level is always strictly below a fresh high. Exiting
    # at the correct, ratcheted price is what matters financially.)
    should_exit, reason, qty = engine.evaluate_exit(pos, current_price=104.0, current_time=MORNING, current_atr=1.0)
    assert should_exit is True
    assert reason == "Stop-Loss Hit"


def test_trailing_stop_never_moves_backwards_for_call():
    engine = _engine(trailing_activation_pct=1.0, atr_multiplier=1.0, partial_target_reward=999.0)
    pos = _call_position(entry_price=100.0, stop_loss=0.0, target=9999.0)

    engine.evaluate_exit(pos, current_price=110.0, current_time=MORNING, current_atr=1.0)
    sl_after_peak = pos.stop_loss
    assert sl_after_peak == 109.0

    # Price dips (but not enough to hit the trailing stop) -- stop_loss must not loosen.
    engine.evaluate_exit(pos, current_price=109.5, current_time=MORNING, current_atr=1.0)
    assert pos.stop_loss == sl_after_peak


def test_trailing_stop_activates_and_ratchets_for_put():
    """A bought PUT trails exactly like a bought CALL (tracks highest_price,
    ratchets the stop upward as premium rises) -- it is never treated like a
    genuine short position internally."""
    engine = _engine(trailing_activation_pct=1.0, atr_multiplier=1.0, partial_target_reward=999.0)
    pos = _put_position(entry_price=75.05, stop_loss=0.0, target=9999.0)

    # Premium rises to 80 (profit for a bought option, CE or PE alike).
    # ATR=1.0 -> trailing_stop = 80 - 1.0 = 79.
    should_exit, reason, qty = engine.evaluate_exit(pos, current_price=80.0, current_time=MORNING, current_atr=1.0)
    assert should_exit is False
    assert pos.stop_loss == 79.0

    # Premium pulls back to 79 -> ratcheted stop hit.
    should_exit, reason, qty = engine.evaluate_exit(pos, current_price=79.0, current_time=MORNING, current_atr=1.0)
    assert should_exit is True
    assert reason == "Stop-Loss Hit"


# ---------------------------------------------------------------------------
# Partial profit booking
# ---------------------------------------------------------------------------

def test_partial_profit_booking_triggers_at_configured_reward_ratio():
    engine = _engine(partial_booking_pct=50.0, partial_target_reward=1.0)
    # risk = entry(100) - stop_loss(95) = 5. Reward 5 at 1:1 -> current_price 105.
    pos = _call_position(entry_price=100.0, stop_loss=95.0, target=9999.0, quantity=65)

    should_exit, reason, qty = engine.evaluate_exit(pos, current_price=105.0, current_time=MORNING, current_atr=0.0)
    assert should_exit is True
    assert "Partial Profit Booking" in reason
    assert qty == 32  # 50% of 65, floored
    assert pos.is_partially_booked is True
    assert pos.stop_loss == 100.0  # moved to breakeven


def test_partial_profit_booking_only_fires_once():
    engine = _engine(partial_booking_pct=50.0, partial_target_reward=1.0)
    pos = _call_position(entry_price=100.0, stop_loss=95.0, target=9999.0, quantity=65)

    engine.evaluate_exit(pos, current_price=105.0, current_time=MORNING, current_atr=0.0)
    assert pos.is_partially_booked is True

    # Even further in profit -- must not re-trigger partial booking a second time.
    should_exit, reason, qty = engine.evaluate_exit(pos, current_price=110.0, current_time=MORNING, current_atr=0.0)
    assert "Partial Profit Booking" not in reason
