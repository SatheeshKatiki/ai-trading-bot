"""No-fixed-target architecture: `target <= 0` means unlimited upside.

The regression these lock down is severe and silent. `SmartExitEngine`
compared `current_price >= position.target` with no positivity guard, so a
target of 0.0 — the value that now means "no target", and also the value
`_load_positions` falls back to for any position restored without one — made
every long position report "Profit Target Hit" on its first tick and close
immediately at entry price.

main.py's own hard-TP interceptor already guarded on `target > 0`, so the two
exit layers disagreed about what zero meant. These tests pin the agreement.
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import pytest

from shared.exits import Position, SmartExitEngine


def _option_position(entry=120.0, stop_loss=104.0, target=0.0, quantity=75):
    return Position(
        symbol="NSE:NIFTY2580724500CE",
        side=1,
        entry_price=entry,
        quantity=quantity,
        entry_time="2026-08-06 10:15:00",
        highest_price=entry,
        lowest_price=entry,
        stop_loss=stop_loss,
        target=target,
    )


@pytest.fixture
def engine():
    # Trailing far out of reach so these tests isolate the target logic.
    return SmartExitEngine(trailing_activation_pct=9999.0, partial_target_reward=9999.0)


def test_zero_target_does_not_fire_at_entry(engine):
    position = _option_position(target=0.0)

    should_exit, reason, _ = engine.evaluate_exit(position, 120.0, "10:15:05", 5.0)

    assert should_exit is False, f"exited at entry with reason {reason!r}"


def test_zero_target_never_fires_however_far_price_runs(engine):
    position = _option_position(target=0.0)

    for price in (121.0, 150.0, 250.0, 1_000.0, 10_000.0):
        should_exit, reason, _ = engine.evaluate_exit(position, price, "10:20:00", 5.0)
        assert should_exit is False, (
            f"unlimited-upside position exited at {price} with reason {reason!r}"
        )


def test_negative_target_is_also_treated_as_no_target(engine):
    position = _option_position(target=-1.0)

    should_exit, _, _ = engine.evaluate_exit(position, 500.0, "10:20:00", 5.0)

    assert should_exit is False


def test_stop_loss_still_fires_with_no_target(engine):
    """Removing the target must not weaken the downside."""
    position = _option_position(stop_loss=104.0, target=0.0)

    should_exit, reason, qty = engine.evaluate_exit(position, 103.5, "10:20:00", 5.0)

    assert should_exit is True
    assert reason == "Stop-Loss Hit"
    assert qty is None  # full exit


def test_eod_exit_still_fires_with_no_target(engine):
    position = _option_position(target=0.0)

    should_exit, reason, _ = engine.evaluate_exit(position, 130.0, "15:20:00", 5.0)

    assert should_exit is True
    assert reason == "Time-based EOD Exit"


def test_a_real_positive_target_still_works(engine):
    """Non-option/legacy positions that do carry a target are unaffected."""
    position = _option_position(target=150.0)

    should_exit, reason, _ = engine.evaluate_exit(position, 151.0, "10:20:00", 5.0)

    assert should_exit is True
    assert reason == "Profit Target Hit"


def test_trailing_stop_takes_over_profit_management(engine):
    """With no target, the trailing stop is what ends a winning trade."""
    engine.trailing_activation_pct = 1.0
    engine.trailing_offset_pct = 0.35
    engine.atr_multiplier = 2.0
    position = _option_position(stop_loss=104.0, target=0.0)

    # Run up: no exit, and the stop ratchets up behind it.
    should_exit, _, _ = engine.evaluate_exit(position, 160.0, "10:20:00", 5.0)
    assert should_exit is False
    assert position.stop_loss > 104.0, "trailing stop did not ratchet"
    ratcheted = position.stop_loss

    # Give back enough and the ratcheted stop closes the trade. The reason
    # reads "Stop-Loss Hit" rather than "Trailing Stop-Loss Hit" because the
    # hard-stop check (step 3) sees the already-ratcheted level first — the
    # distinction is cosmetic; what matters is that the exit happened at a
    # trailing level well above entry, i.e. profit was managed by the trail
    # and not by a fixed target.
    should_exit, reason, _ = engine.evaluate_exit(position, ratcheted - 0.5, "10:25:00", 5.0)
    assert should_exit is True
    assert "Stop-Loss Hit" in reason
    assert ratcheted > position.entry_price, "exited below entry — not a managed win"


def test_partial_booking_still_works_and_moves_stop_to_breakeven():
    """Partial booking keys off R = |entry - stop|, not off the target, so it
    is unaffected by the target's removal."""
    engine = SmartExitEngine(
        trailing_activation_pct=9999.0,
        partial_target_reward=1.0,
        partial_booking_pct=50.0,
    )
    position = _option_position(entry=120.0, stop_loss=104.0, target=0.0, quantity=150)

    # 1R = ₹16, so ₹136 is the 1:1 level.
    should_exit, reason, qty = engine.evaluate_exit(position, 136.5, "10:20:00", 5.0)

    assert should_exit is True
    assert "Partial Profit Booking" in reason
    assert qty == 75
    assert position.stop_loss == pytest.approx(120.0)  # moved to breakeven
