"""Everything open must be closed at 15:15, tick or no tick (2026-09-19).

The owner asked for two guarantees: the 15:00 entry cutoff stays, and every
open position is fully exited by 15:15 with a Telegram confirmation.

The gap: in the live engine EVERY exit -- including the 15:15 cutoff -- lives
inside `on_tick`, so it only runs when a tick arrives. If the feed goes quiet
before the close (a Wi-Fi drop or a dropped broker socket, both of which have
happened on this machine) nothing closes the position and it is carried
overnight: gap risk plus a night of theta on a contract that may expire the
next day. The tick-staleness watchdog only warns; it never touches a position.

So a time-driven safety net drives the existing exit path instead of
duplicating it, and the decision of WHICH positions still need closing is a
pure function, testable without running the engine.
"""

from __future__ import annotations

import inspect
import pathlib

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import trading_bot.main as main_module


class _Pos:
    def __init__(self, is_exiting=False):
        self.is_exiting = is_exiting


EOD = "15:15:00"


# ---------------------------------------------------------------------------
# Which positions still need squaring off
# ---------------------------------------------------------------------------

def test_nothing_is_forced_before_the_cutoff():
    positions = {"NIFTY": _Pos()}
    assert main_module.positions_needing_eod_exit(positions, "14:59:59", EOD) == []


def test_everything_open_is_listed_at_the_cutoff():
    positions = {"NIFTY": _Pos(), "BANKNIFTY": _Pos()}
    assert sorted(main_module.positions_needing_eod_exit(positions, EOD, EOD)) == ["BANKNIFTY", "NIFTY"]


def test_it_keeps_listing_after_the_cutoff():
    """A feed that died at 15:10 must still be caught at 15:22."""
    positions = {"NIFTY": _Pos()}
    assert main_module.positions_needing_eod_exit(positions, "15:22:00", EOD) == ["NIFTY"]


def test_an_exit_already_in_flight_is_not_re_fired():
    """Double-exiting is its own incident -- is_exiting is the lock."""
    positions = {"NIFTY": _Pos(is_exiting=True), "BANKNIFTY": _Pos()}
    assert main_module.positions_needing_eod_exit(positions, EOD, EOD) == ["BANKNIFTY"]


def test_a_flat_book_needs_nothing():
    assert main_module.positions_needing_eod_exit({}, "15:30:00", EOD) == []


# ---------------------------------------------------------------------------
# The safety net itself
# ---------------------------------------------------------------------------

def _watchdog_src() -> str:
    src = inspect.getsource(main_module.run_live_bot)
    start = src.index("async def eod_squareoff_watchdog")
    return src[start:start + 4000]


def test_the_safety_net_is_time_driven_not_tick_driven():
    src = inspect.getsource(main_module.run_live_bot)
    assert "asyncio.create_task(eod_squareoff_watchdog())" in src
    body = _watchdog_src()
    assert "await asyncio.sleep(_EOD_CHECK_INTERVAL_S)" in body


def test_it_drives_the_existing_exit_path_rather_than_a_second_one():
    """One exit path: the stop cancel, the order and the books stay together."""
    body = _watchdog_src()
    assert "await on_tick(" in body
    assert "place_order" not in body, "the watchdog must not grow its own order logic"


def test_it_uses_a_freshly_fetched_price_never_a_remembered_one():
    body = _watchdog_src()
    assert "broker.get_market_data" in body
    assert "if ltp is None:" in body, "no price means no exit from here -- never invent one"


def test_an_unexitable_position_is_escalated_loudly():
    """If it cannot be closed here, the owner must be told to do it by hand."""
    body = _watchdog_src()
    assert "EOD SQUARE-OFF FAILED" in body
    assert "square these off" in body.lower() or "square off manually" in body.lower()
    assert "alerter.send_alert" in body


def test_the_watchdog_survives_its_own_errors():
    """A dead safety net is exactly what this exists to prevent."""
    body = _watchdog_src()
    assert "EOD square-off watchdog error" in body


# ---------------------------------------------------------------------------
# The confirmation the owner asked for
# ---------------------------------------------------------------------------

def test_the_live_engine_confirms_the_square_off_once():
    body = _watchdog_src()
    assert "All opened positions are closed" in body
    assert "confirmed = True" in body, "sent once, not every 30 seconds"
    assert "had_positions" in body, "a day with no trades must not claim a square-off"


def test_the_paper_observer_confirms_the_square_off_once():
    src = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "paper_observer.py").read_text(
        encoding="utf-8", errors="ignore")
    assert "All opened positions are closed" in src
    assert "eod_confirmed = True" in src
    # Only past the cutoff, only with nothing open, only if the day had trades.
    gate = src.index('if (not eod_confirmed and ist_time() >= EOD_CUTOFF')
    window = src[gate:gate + 300]
    assert "not active_positions" in window
    assert 'session_log["trades"]' in window


def test_both_engines_square_off_at_the_same_time():
    """15:15 in one place per engine -- not two different cutoffs."""
    observer = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "paper_observer.py").read_text(
        encoding="utf-8", errors="ignore")
    assert "EOD_CUTOFF   = datetime.time(15, 15)" in observer

    from shared.exits import exit_engine as ee
    assert "15:15" in inspect.signature(ee.SmartExitEngine.__init__).parameters["eod_exit_time"].default
