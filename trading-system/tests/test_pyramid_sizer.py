"""Regression tests for shared/exits/pyramid_sizer.py's PyramidSizer.

Zero test coverage before this file. Found live on 2026-08-04: a bought
PUT position scaled in at a price BELOW entry, logged as "Profit hit
+0.36%" -- evaluate_scale() branched on position.side using the
short-underlying convention (side=-1 -> profit on price DECREASE), but
this system only ever BUYS options, so a bought PUT profits when its own
premium RISES, exactly like a bought CALL. Same bug class already fixed
in shared/exits/exit_engine.py on 2026-08-03.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from shared.exits import Position, PyramidSizer


def _put_position(entry_price=55.15, scales_done=0, **overrides):
    defaults = dict(
        symbol="NSE:NIFTY2680424550PE", side=-1, entry_price=entry_price,
        quantity=65, entry_time="2026-08-04T12:00:01", highest_price=entry_price,
        lowest_price=entry_price, stop_loss=entry_price * 0.995, target=entry_price * 1.035,
        scales_done=scales_done,
    )
    defaults.update(overrides)
    return Position(**defaults)


def _call_position(entry_price=100.0, scales_done=0, **overrides):
    defaults = dict(
        symbol="NSE:NIFTY26AUG24700CE", side=1, entry_price=entry_price,
        quantity=65, entry_time="2026-08-04T12:00:00", highest_price=entry_price,
        lowest_price=entry_price, stop_loss=entry_price * 0.995, target=entry_price * 1.035,
        scales_done=scales_done,
    )
    defaults.update(overrides)
    return Position(**defaults)


def test_put_does_not_scale_on_falling_premium():
    """The exact live-reproduced bug: a PUT's premium falling below entry
    must never be reported as profit worth scaling into."""
    sizer = PyramidSizer(pct_trigger=0.2, max_scales=2)
    pos = _put_position(entry_price=55.15)
    should_scale, reason = sizer.evaluate_scale(pos, current_price=54.95)
    assert should_scale is False


def test_put_scales_on_rising_premium():
    sizer = PyramidSizer(pct_trigger=0.2, max_scales=2)
    pos = _put_position(entry_price=55.15)
    # +0.2% of 55.15 = 0.1103 -> need current_price >= 55.2603
    should_scale, reason = sizer.evaluate_scale(pos, current_price=55.30)
    assert should_scale is True
    assert "Profit hit" in reason


def test_call_scales_on_rising_premium():
    sizer = PyramidSizer(pct_trigger=0.2, max_scales=2)
    pos = _call_position(entry_price=100.0)
    should_scale, reason = sizer.evaluate_scale(pos, current_price=100.25)
    assert should_scale is True


def test_call_does_not_scale_on_falling_premium():
    sizer = PyramidSizer(pct_trigger=0.2, max_scales=2)
    pos = _call_position(entry_price=100.0)
    should_scale, reason = sizer.evaluate_scale(pos, current_price=99.50)
    assert should_scale is False


def test_max_scales_respected():
    sizer = PyramidSizer(pct_trigger=0.2, max_scales=2)
    pos = _put_position(entry_price=55.15, scales_done=2)
    should_scale, reason = sizer.evaluate_scale(pos, current_price=100.0)
    assert should_scale is False


def test_second_scale_requires_more_profit_than_first():
    sizer = PyramidSizer(pct_trigger=0.2, max_scales=2)
    pos = _put_position(entry_price=55.15, scales_done=1)
    # First scale needed only +0.2% (~55.26); second scale needs +0.4% (~55.37).
    should_scale, reason = sizer.evaluate_scale(pos, current_price=55.30)
    assert should_scale is False
    should_scale, reason = sizer.evaluate_scale(pos, current_price=55.40)
    assert should_scale is True
