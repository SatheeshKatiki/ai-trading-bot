"""Regression test for trading_bot.main._save_positions()'s atomic-write
recovery under an interrupted write.

_save_positions() already writes active_positions.json atomically
(tempfile.mkstemp + os.replace, with a 5-attempt retry for the real,
previously-observed WinError 5 "Access is denied" case -- see the
2026-08-03 root-cause comment in main.py and
test_save_positions_numpy_safety.py for that side). No test previously
proved the actual safety property that atomic-write pattern exists for:
if the write is interrupted (crash, persistent OSError, os.replace never
completing) at any point before the rename, the previous, last-good file
on disk must be left completely intact -- _load_positions() on the next
start must recover it, not crash and not silently lose the position.
"""
import json

import pytest

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from shared.exits import Position
from trading_bot.main import _save_positions, _load_positions
import trading_bot.main as main_module


def _make_position(symbol="NSE:NIFTY2681824400PE", stop_loss=76.8):
    return Position(
        symbol=symbol, side=-1, entry_price=90.9, quantity=260,
        entry_time="2026-08-13T13:35:14", highest_price=90.9, lowest_price=90.9,
        stop_loss=stop_loss, target=0.0,
    )


def test_a_persistently_failing_replace_leaves_the_last_good_file_intact(tmp_path, monkeypatch):
    """Simulates a write interrupted throughout the entire retry window
    (e.g. a crash/persistent lock right as os.replace would run) --
    exactly the failure mode the 5-attempt retry exists for, pushed past
    its limit. The file on disk before this call must still be exactly
    what _load_positions() recovers afterward."""
    positions_path = tmp_path / "active_positions.json"
    monkeypatch.setattr(main_module, "_POSITIONS_PATH", positions_path)

    good_position = _make_position()
    _save_positions({good_position.symbol: good_position})
    original_bytes = positions_path.read_bytes()
    assert positions_path.is_file()

    def _always_fail_replace(*args, **kwargs):
        raise OSError("simulated: WinError 5 Access is denied (persistent)")

    monkeypatch.setattr(main_module.os, "replace", _always_fail_replace)

    interrupted_position = _make_position(stop_loss=1.0)  # would corrupt the SL if it landed
    _save_positions({interrupted_position.symbol: interrupted_position})  # must not raise -- logs and returns

    # The file on disk must be byte-for-byte what it was before the
    # failed write attempt -- os.replace() never succeeded, so the
    # original file was never touched.
    assert positions_path.read_bytes() == original_bytes

    # No leftover temp file either -- _save_positions' own cleanup path
    # (`if os.path.exists(temp_path): os.unlink(temp_path)`) must have run.
    leftovers = list(tmp_path.glob("active_positions_tmp_*"))
    assert leftovers == []

    loaded = _load_positions()
    assert good_position.symbol in loaded
    assert loaded[good_position.symbol].stop_loss == 76.8  # the GOOD value, not 1.0


def test_an_orphaned_temp_file_from_a_real_process_kill_does_not_confuse_the_next_load(tmp_path, monkeypatch):
    """A more literal crash: the process dies after tempfile.mkstemp but
    before os.replace ever even runs (no exception path, just gone) --
    the temp file is left behind, orphaned, forever. This must not be
    mistaken for the real active_positions.json by the next load."""
    positions_path = tmp_path / "active_positions.json"
    monkeypatch.setattr(main_module, "_POSITIONS_PATH", positions_path)

    good_position = _make_position()
    _save_positions({good_position.symbol: good_position})
    original_bytes = positions_path.read_bytes()

    # Simulate the orphaned temp file a real kill-mid-write would leave.
    orphan = tmp_path / "active_positions_tmp_orphaned123.json"
    orphan.write_text(json.dumps({"CORRUPTED": "half-written garbage"}), encoding="utf-8")

    loaded = _load_positions()

    assert positions_path.read_bytes() == original_bytes
    assert good_position.symbol in loaded
    assert "CORRUPTED" not in loaded
    assert loaded[good_position.symbol].stop_loss == 76.8
