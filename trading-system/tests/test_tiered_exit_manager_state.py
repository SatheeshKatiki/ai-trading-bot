"""Regression tests for TieredExitManager's highest_price/lowest_price
attribute lifecycle (trading_bot/strategies/momentum_strategy/exit_manager.py).

Root-cause fix (Low audit finding): highest_price/lowest_price were never
declared in __init__ -- only set inside close_position() -- and read
elsewhere via `getattr(self, 'highest_price', current_price)`. Besides
being fragile (any future direct `self.highest_price` access before
close_position()/evaluate() had run would raise AttributeError),
open_position() never reset these, so a second position on a reused
manager instance inherited highest_price=0.0 left over from the
previous position's close_position() call instead of starting fresh
at its own entry price.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from trading_bot.strategies.momentum_strategy.exit_manager import TieredExitManager


def test_fresh_instance_has_highest_and_lowest_price_attrs():
    mgr = TieredExitManager()
    assert mgr.highest_price == 0.0
    assert mgr.lowest_price == float('inf')


def test_open_position_sets_highest_and_lowest_to_entry_price():
    mgr = TieredExitManager()
    mgr.open_position(entry_price=100.0, stop_loss=90.0, total_lots=10, direction=1)
    assert mgr.highest_price == 100.0
    assert mgr.lowest_price == 100.0


def test_second_position_does_not_inherit_stale_highest_price():
    """Sabotage regression: without the open_position() reset, this second
    position would start with highest_price=0.0 (left over from
    close_position()) instead of its own entry price of 250.0."""
    mgr = TieredExitManager()
    mgr.open_position(entry_price=100.0, stop_loss=90.0, total_lots=10, direction=1)
    mgr.highest_price = 180.0  # simulate price having run up during position 1
    mgr.close_position()
    assert mgr.highest_price == 0.0  # close_position() resets to neutral

    mgr.open_position(entry_price=250.0, stop_loss=240.0, total_lots=5, direction=1)
    assert mgr.highest_price == 250.0
    assert mgr.lowest_price == 250.0


def test_evaluate_tracks_highest_price_without_getattr():
    mgr = TieredExitManager()
    mgr.open_position(entry_price=100.0, stop_loss=90.0, total_lots=10, direction=1)
    import pandas as pd
    df = pd.DataFrame({"close": [100.0] * 15})
    mgr.evaluate(current_price=120.0, df_5min=df)
    assert mgr.highest_price == 120.0
    mgr.evaluate(current_price=110.0, df_5min=df)
    assert mgr.highest_price == 120.0  # doesn't decrease on pullback


if __name__ == "__main__":
    test_fresh_instance_has_highest_and_lowest_price_attrs()
    test_open_position_sets_highest_and_lowest_to_entry_price()
    test_second_position_does_not_inherit_stale_highest_price()
    test_evaluate_tracks_highest_price_without_getattr()
    print("All TieredExitManager state tests passed.")
