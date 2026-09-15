"""The dashboard's per-position EXIT must reach the engine (2026-09-16).

The owner exits one live position from the dashboard. Before this, the UI
POSTed straight to /api/order/execute -- which places a counter-order at the
broker and nothing more. api_bridge and main.py are SEPARATE processes sharing
only files, so the engine never learned the position was gone: it kept
managing it, would try to exit it again (a double sell), and left its
exchange-resident stop-loss working against a position no longer held. On a
bought option that stop is a SELL, so triggering it opens a naked short.

The exit now travels as a request file the engine consumes:

    UI -> POST /api/positions/exit
            1. place the counter-order (same path as any manual order)
            2. append the symbol to config/exit_requests.json
    main.py on_tick -> _take_exit_requests()  (read AND clear)
                    -> close_requested_positions(): cancel the stop, record
                       the trade, drop the position

Ordering is deliberate: placing first and queueing second means a failure
after the fill is recovered by the 60s reconciler, whereas queueing first and
failing to place would make the engine forget a position the broker still
holds.

close_requested_positions is a closure inside run_live_bot -- like
emergency_flatten_all_positions it cannot be imported, so its wiring is
source-asserted here and its behaviour is covered by the pieces it reuses
(compute_reconciliation, _cancel_orphaned_stop), which are tested directly in
test_reconciliation.py and test_main_reconcile_broker_state.py.
"""

from __future__ import annotations

import inspect
import json

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import trading_bot.main as main_module


# ---------------------------------------------------------------------------
# _take_exit_requests -- read AND clear, exactly once
# ---------------------------------------------------------------------------

def test_a_request_is_read_and_consumed_exactly_once(tmp_path, monkeypatch):
    path = tmp_path / "exit_requests.json"
    path.write_text(json.dumps(["NSE:NIFTY2681824400PE"]), encoding="utf-8")
    monkeypatch.setattr(main_module, "_EXIT_REQUESTS_PATH", path)

    assert main_module._take_exit_requests() == ["NSE:NIFTY2681824400PE"]
    assert not path.exists(), "the file must be cleared by its consumer"
    assert main_module._take_exit_requests() == [], "a request must never be acted on twice"


def test_several_requests_come_back_together(tmp_path, monkeypatch):
    path = tmp_path / "exit_requests.json"
    path.write_text(json.dumps(["A-CE", "B-PE"]), encoding="utf-8")
    monkeypatch.setattr(main_module, "_EXIT_REQUESTS_PATH", path)

    assert main_module._take_exit_requests() == ["A-CE", "B-PE"]


def test_no_file_is_the_normal_case(tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "_EXIT_REQUESTS_PATH", tmp_path / "absent.json")
    assert main_module._take_exit_requests() == []


def test_a_corrupt_request_file_never_breaks_the_tick_loop(tmp_path, monkeypatch):
    """This runs inside on_tick -- it must fail quiet, not raise."""
    path = tmp_path / "exit_requests.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(main_module, "_EXIT_REQUESTS_PATH", path)

    assert main_module._take_exit_requests() == []


def test_blank_entries_are_ignored(tmp_path, monkeypatch):
    path = tmp_path / "exit_requests.json"
    path.write_text(json.dumps(["", "NSE:NIFTY2681824400PE", None]), encoding="utf-8")
    monkeypatch.setattr(main_module, "_EXIT_REQUESTS_PATH", path)

    assert main_module._take_exit_requests() == ["NSE:NIFTY2681824400PE"]


# ---------------------------------------------------------------------------
# Wiring inside run_live_bot
# ---------------------------------------------------------------------------

def test_the_tick_loop_consumes_exit_requests():
    src = inspect.getsource(main_module.run_live_bot)
    assert "exit_requests = _take_exit_requests()" in src
    assert "await close_requested_positions(exit_requests)" in src


def test_an_exit_request_is_honoured_even_when_the_engine_is_halted():
    """Halting must not strand the cleanup of a position already closed."""
    src = inspect.getsource(main_module.run_live_bot)
    consume = src.index("exit_requests = _take_exit_requests()")
    halt = src.index('if not settings.get("is_active", True):')
    assert consume < halt, "exit requests must be handled before the is_active halt"


def test_the_stop_is_cancelled_before_the_position_is_dropped():
    """Dropping first would discard sl_order_id and orphan the stop."""
    src = inspect.getsource(main_module.run_live_bot)
    body = src[src.index("async def close_requested_positions"):]
    body = body[:body.index("async def emergency_flatten_all_positions")]
    assert "_cancel_orphaned_stop(" in body
    assert body.index("_cancel_orphaned_stop(") < body.index("del active_positions[")


def test_the_request_matches_the_traded_contract_not_the_dict_key():
    """active_positions is keyed by the UNDERLYING; matching the key alone
    would never find an option position."""
    src = inspect.getsource(main_module.run_live_bot)
    body = src[src.index("async def close_requested_positions"):]
    assert "p.symbol == wanted or k == wanted" in body


def test_the_position_is_locked_against_the_tick_exit_path():
    src = inspect.getsource(main_module.run_live_bot)
    body = src[src.index("async def close_requested_positions"):]
    assert "pos.is_exiting = True" in body
