"""Regression test for trading_bot.main._save_positions()'s handling of
numpy scalar types.

Root-cause fix (found running the live engine in paper mode for the
first time this session): position sizing runs through pandas/numpy
internally, so Position.quantity/entry_price etc. can arrive here as
numpy.int64/float64 rather than native Python types. json.dump() only
accepts native types and raised "Object of type int64 is not JSON
serializable" on literally the very first paper-trade entry the engine
attempted — silently failing to persist the position at all (caught by
_save_positions' own broad except, logged as an error, execution
continued with an in-memory-only position).
"""
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import numpy as np

from shared.exits import Position
from trading_bot.main import _save_positions, _load_positions
import trading_bot.main as main_module


def test_save_positions_with_numpy_scalars_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "_POSITIONS_PATH", tmp_path / "active_positions.json")

    pos = Position(
        symbol="NSE:NIFTY5026AUG0624350CE",
        side=np.int64(1),
        entry_price=np.float64(150.25),
        quantity=np.int64(65),
        entry_time="2026-08-02T21:55:05",
        highest_price=np.float64(150.25),
        lowest_price=np.float64(150.25),
        stop_loss=np.float64(140.0),
        target=np.float64(160.0),
    )

    _save_positions({pos.symbol: pos})

    # The whole point: this must be real, valid JSON on disk, not silently
    # skipped by _save_positions' broad except-and-log-error path.
    raw = (tmp_path / "active_positions.json").read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed[pos.symbol]["quantity"] == 65
    assert parsed[pos.symbol]["entry_price"] == 150.25
    assert isinstance(parsed[pos.symbol]["quantity"], int)
    assert isinstance(parsed[pos.symbol]["side"], int)


def test_save_then_load_round_trip_preserves_values(tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "_POSITIONS_PATH", tmp_path / "active_positions.json")

    pos = Position(
        symbol="NSE:NIFTY50-INDEX", side=np.int64(-1), entry_price=np.float64(24177.05),
        quantity=np.int64(65), entry_time="2026-08-02T21:55:05",
        highest_price=np.float64(24177.05), lowest_price=np.float64(24177.05),
        stop_loss=np.float64(24276.11), target=np.float64(23239.35),
    )
    _save_positions({pos.symbol: pos})

    loaded = _load_positions()
    assert pos.symbol in loaded
    assert loaded[pos.symbol].quantity == 65
    assert loaded[pos.symbol].side == -1
    assert loaded[pos.symbol].entry_price == 24177.05
