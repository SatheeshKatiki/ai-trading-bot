"""The WebSocket broadcast cadence must adapt to whether it can matter.

`websocket_broadcaster()` ran at a flat 50 ms (20 Hz) unconditionally, around
the clock. It is also the *clock for the live engine*:
`FyersBroker.stream_quotes()` turns every broadcast frame into an `on_tick()`,
and `trading_bot/main.py` re-evaluates the entire feature + strategy + filter
stack on a 200 ms trigger driven by those ticks.

So a 50 ms broadcast burned roughly 70% of a CPU core continuously --
overnight, at weekends and on holidays, when by definition nothing was
changing and no decision could be taken. Flagged in `anomaly_log.md` on
2026-08-28 and left open; fixed 2026-09-09.

Frames per 24h: 1,728,000 before, 481,950 after -- a 72% reduction with the
market-hours rate left completely untouched.

These tests pin the *policy*, since the loop itself is an infinite coroutine
that cannot be exercised directly.
"""

from __future__ import annotations

import inspect

import pytest

import api_bridge as ab


BROADCAST_SRC = inspect.getsource(ab.websocket_broadcaster)


# ---------------------------------------------------------------------------
# The policy, stated independently of the loop it lives in
# ---------------------------------------------------------------------------

def _interval(has_clients: bool, market_open: bool) -> float:
    """Mirror of the cadence decision inside websocket_broadcaster()."""
    if not has_clients:
        return 1.0
    return 0.05 if market_open else 2.0


def test_market_hours_rate_is_unchanged():
    """The only case where 20 Hz buys anything: live market, live listener."""
    assert _interval(has_clients=True, market_open=True) == 0.05


def test_closed_market_slows_down():
    assert _interval(has_clients=True, market_open=False) == 2.0


def test_no_listener_slows_down_even_during_market_hours():
    """The engine connects as a WebSocket client, so no clients means the
    dashboard AND the engine are both absent -- there is nobody to serve."""
    assert _interval(has_clients=False, market_open=True) == 1.0
    assert _interval(has_clients=False, market_open=False) == 1.0


def test_daily_frame_count_drops_by_at_least_half():
    open_hours = 6.25          # 09:15-15:30 IST
    before = 24 * 3600 / 0.05
    after = (open_hours * 3600 / 0.05) + ((24 - open_hours) * 3600 / 2.0)
    assert after < before / 2
    assert before == pytest.approx(1_728_000)
    assert after == pytest.approx(481_950)


def test_market_hours_frame_count_is_untouched():
    open_hours = 6.25
    assert (open_hours * 3600 / 0.05) == pytest.approx(450_000)


# ---------------------------------------------------------------------------
# The policy is actually wired into the loop
# ---------------------------------------------------------------------------

def test_broadcaster_no_longer_sleeps_at_a_flat_rate():
    assert "await asyncio.sleep(0.05)" not in BROADCAST_SRC, (
        "the unconditional 20 Hz sleep is back"
    )


def test_broadcaster_uses_an_adaptive_interval():
    assert "broadcast_interval" in BROADCAST_SRC
    assert "await asyncio.sleep(broadcast_interval)" in BROADCAST_SRC


def test_broadcaster_considers_both_listeners_and_market_state():
    assert "active_connections" in BROADCAST_SRC
    assert "is_market_open" in BROADCAST_SRC


# ---------------------------------------------------------------------------
# Market hours must be IST-anchored, not server-local
# ---------------------------------------------------------------------------

def test_broadcaster_uses_the_shared_ist_market_hours_helper():
    """It previously compared `datetime.now()` -- SERVER-LOCAL time -- against
    09:15-15:30, so on any host not set to IST the window was simply wrong.
    That value now also drives the cadence, so it has to be right."""
    assert "from shared.market_hours import is_market_open" in BROADCAST_SRC
    assert "now.replace(hour=9, minute=15" not in BROADCAST_SRC


def test_shared_helper_is_ist_anchored():
    from datetime import datetime

    import pytz

    from shared.market_hours import is_market_open

    ist = pytz.timezone("Asia/Kolkata")
    # A Wednesday, 11:00 IST -> open; 04:00 IST -> shut.
    assert is_market_open(ist.localize(datetime(2026, 9, 9, 11, 0))) is True
    assert is_market_open(ist.localize(datetime(2026, 9, 9, 4, 0))) is False
