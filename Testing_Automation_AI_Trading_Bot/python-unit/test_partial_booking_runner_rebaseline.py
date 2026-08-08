"""Regression tests for the runner re-baseline at partial profit booking.

The defect (measured 2026-08-08 on `ema_rsi` over the 123-day validation
window, 397 positions, 131 of them partially booked):

`SmartExitEngine.evaluate_exit` books 50% of a position at 1:1
reward:risk and re-baselines the position's RISK — it moves the stop to
breakeven. It did NOT re-baseline `Position.max_pnl_pct`, the peak-profit
tracker that the percentage trailing stop (section 5b) measures give-back
against. Because section 4 returns as soon as booking fires, that tracker
still held the peak from the bar BEFORE booking — so the remaining half,
the "runner" whose entire job is to capture the trend, was born already
in give-back against a peak it never got to keep, and the 0.35
percentage-point allowance meant the next downtick could close it.

Measured consequence: runners survived a MEDIAN OF 2 BARS (10 minutes)
after booking, and 75.6% of them were closed by that trailing stop rather
than by a stop-loss, a target or the EOD cutoff. See
`validation_harness/results/exit_quality_ema_rsi.md`.

These tests pin the repair AND the surrounding behaviour it must not
disturb — booking still fires once, at the same ratio, for the same
quantity, and still moves the stop to breakeven.
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from shared.exits import Position, SmartExitEngine

MORNING = "2026-08-03 10:40:00"  # well before the default 15:15:00 EOD cutoff

#: Passed as `current_atr` to keep the ATR trailing stop (section 5) from
#: binding, so these tests exercise the PERCENTAGE trail in isolation.
#: Counter-intuitively this has to be LARGE, not zero: the ATR stop sits at
#: `highest_price - atr * multiplier`, so atr=0 puts it exactly ON the high
#: and closes the position on the very tick that makes a new high. A large
#: ATR pushes it below any price these tests use.
BIG_ATR = 1000.0


def _call_position(entry_price=100.0, stop_loss=95.0, target=9999.0, quantity=65, **overrides):
    """A bought CALL with a 5-point risk, so 1:1 booking fires at 105."""
    defaults = dict(
        symbol="NSE:NIFTY26AUG24700CE", side=1, entry_price=entry_price,
        quantity=quantity, entry_time="2026-08-03T10:00:00", highest_price=entry_price,
        lowest_price=entry_price, stop_loss=stop_loss, target=target,
    )
    defaults.update(overrides)
    return Position(**defaults)


def _engine(**overrides):
    defaults = dict(
        trailing_activation_pct=1.0, trailing_offset_pct=0.35,
        atr_multiplier=1.5, partial_booking_pct=50.0, partial_target_reward=1.0,
    )
    defaults.update(overrides)
    return SmartExitEngine(**defaults)


def _ramp_to_booking(engine, pos):
    """Walk a position up to the 1:1 booking level the way a real price path
    does — through bars that arm trailing and accumulate a peak BELOW the
    booking level (103, then 104.5), then the bar that books (105).

    This ordering is the whole point: booking fires in section 4 and returns
    before section 5 updates the peak, so at the moment of booking the peak
    is the PREVIOUS bar's 4.5%, not the current bar's 5%."""
    engine.evaluate_exit(pos, current_price=103.0, current_time=MORNING, current_atr=BIG_ATR)
    engine.evaluate_exit(pos, current_price=104.5, current_time=MORNING, current_atr=BIG_ATR)
    return engine.evaluate_exit(pos, current_price=105.0, current_time=MORNING, current_atr=BIG_ATR)


# ---------------------------------------------------------------------------
# The repair
# ---------------------------------------------------------------------------

def test_peak_is_carried_up_to_the_booking_bar():
    """Guards the premise of the test below: the peak really does reach
    4.5% before booking fires, so a reset to 0.0 is an observable change
    and not a coincidence of the setup."""
    engine = _engine()
    pos = _call_position()

    engine.evaluate_exit(pos, current_price=103.0, current_time=MORNING, current_atr=BIG_ATR)
    engine.evaluate_exit(pos, current_price=104.5, current_time=MORNING, current_atr=BIG_ATR)
    assert pos.max_pnl_pct == 4.5


def test_partial_booking_resets_the_peak_profit_tracker():
    engine = _engine()
    pos = _call_position()

    should_exit, reason, qty = _ramp_to_booking(engine, pos)

    assert should_exit is True
    assert "Partial Profit Booking" in reason
    assert qty == 32
    assert pos.max_pnl_pct == 0.0, "runner still carries the booked half's peak"


def test_runner_is_not_closed_on_the_downtick_after_booking():
    """The behavioural consequence, which is what actually cost the money.

    After booking at 105, the runner sits at +5%. A dip to 104 is a
    give-back of 1 point — MORE than the 0.35pp allowance measured against
    the stale 4.5% peak, which is exactly what used to close it, and less
    than nothing measured against a peak the runner has re-anchored to
    itself."""
    engine = _engine()
    pos = _call_position()
    _ramp_to_booking(engine, pos)
    pos.quantity -= 32  # caller books the 50%, leaving the runner

    should_exit, reason, _ = engine.evaluate_exit(
        pos, current_price=104.0, current_time=MORNING, current_atr=BIG_ATR
    )
    assert should_exit is False, f"runner closed right after booking: {reason}"


def test_runner_still_trails_from_its_own_peak_afterwards():
    """Re-baselining must restart trailing for the runner, not disable it.
    Once the runner sets its own new peak, a give-back beyond the offset
    from THAT peak must still close it."""
    engine = _engine()
    pos = _call_position()
    _ramp_to_booking(engine, pos)
    pos.quantity -= 32

    should_exit, _r, _q = engine.evaluate_exit(
        pos, current_price=120.0, current_time=MORNING, current_atr=BIG_ATR
    )
    assert should_exit is False
    assert pos.max_pnl_pct == 20.0

    should_exit, reason, _ = engine.evaluate_exit(
        pos, current_price=119.5, current_time=MORNING, current_atr=BIG_ATR
    )
    assert should_exit is True
    assert reason == "Trailing Stop-Loss Hit (Offset)"


def test_single_lot_path_books_to_breakeven_without_exiting():
    """`quantity == 1` books nothing (50% of 1 floors to 0) but still marks
    the position booked and moves the stop to breakeven — and, unlike the
    branch above, does NOT return, so control falls through to the trailing
    section which re-anchors the peak to the current bar anyway. The reset
    on that branch is therefore state hygiene rather than a behaviour
    change; what must hold is that the one-lot position is left booked, at
    breakeven, and open."""
    engine = _engine()
    pos = _call_position(quantity=1)

    engine.evaluate_exit(pos, current_price=103.0, current_time=MORNING, current_atr=BIG_ATR)
    should_exit, _reason, _qty = engine.evaluate_exit(
        pos, current_price=105.0, current_time=MORNING, current_atr=BIG_ATR
    )

    assert should_exit is False
    assert pos.is_partially_booked is True
    assert pos.stop_loss == 100.0


# ---------------------------------------------------------------------------
# What the repair must NOT change
# ---------------------------------------------------------------------------

def test_booking_still_fires_once_at_the_same_ratio_and_quantity():
    engine = _engine()
    pos = _call_position()

    should_exit, reason, qty = engine.evaluate_exit(
        pos, current_price=105.0, current_time=MORNING, current_atr=BIG_ATR
    )
    assert should_exit is True
    assert "Partial Profit Booking" in reason
    assert qty == 32                      # 50% of 65, floored
    assert pos.is_partially_booked is True
    assert pos.stop_loss == 100.0         # breakeven

    # Further profit must not re-trigger booking a second time.
    _should_exit, reason, _qty = engine.evaluate_exit(
        pos, current_price=112.0, current_time=MORNING, current_atr=BIG_ATR
    )
    assert "Partial Profit Booking" not in reason


def test_breakeven_stop_still_protects_the_runner():
    """The runner's downside protection is the breakeven stop set at
    booking. Re-baselining the peak must leave that intact."""
    engine = _engine()
    pos = _call_position()
    _ramp_to_booking(engine, pos)
    pos.quantity -= 32

    should_exit, reason, _ = engine.evaluate_exit(
        pos, current_price=99.5, current_time=MORNING, current_atr=BIG_ATR
    )
    assert should_exit is True
    assert reason == "Stop-Loss Hit"


def test_position_that_never_books_is_untouched():
    """A position that never reaches 1:1 must behave exactly as before —
    the peak keeps accumulating and the percentage trail fires off it."""
    engine = _engine()
    pos = _call_position(stop_loss=0.0)  # risk = 100 -> 1:1 is unreachable here

    engine.evaluate_exit(pos, current_price=104.0, current_time=MORNING, current_atr=BIG_ATR)
    assert pos.is_partially_booked is False
    assert pos.max_pnl_pct == 4.0

    should_exit, reason, _ = engine.evaluate_exit(
        pos, current_price=103.5, current_time=MORNING, current_atr=BIG_ATR
    )
    assert should_exit is True
    assert reason == "Trailing Stop-Loss Hit (Offset)"
