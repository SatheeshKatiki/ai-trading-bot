"""The owner's exit ladder, and its wiring into every engine (2026-09-12).

The owner: "we use a trailing stop, so there is no fixed target -- if the
move has room the target should move up by itself, and the trailing stop
should keep moving up too, until the market reverses."

  rungs (gain over entry):  15   33   50   75   100   150   200
  stop once reached:         0   15   33   50    75   100   150    (0 = breakeven)

Measured before adoption (578 NIFTY sessions): 15-min ITM +1.99%/trade with
the fixed 33% target, +2.25% with this ladder; the best trade went from +31%
to +106%.

Audit findings this closes (live engine, trading_bot/main.py):
* option exits ran through SmartExitEngine, whose 0.35-point give-back --
  fed the dashboard's 0.5 / 0.35 as % of PREMIUM -- closed every winner
  within a tick or two of turning green;
* the ema9 reversal exit was imported and never called;
* the opening stop came from a generic premium-band table, not 15%.
"""

from __future__ import annotations

import inspect

import pytest

import _bootstrap
import ema9_variant_observer as ev
import paper_observer as po
from shared.exits.exit_engine import Position, SmartExitEngine
from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig
from trading_bot.strategies.ema9_rsi_momentum.exit_ladder import (
    DEFAULT_PROFIT_LADDER_PCT,
    initial_stop,
    ladder_levels,
    ratchet_stop,
    stop_reason,
)


# ---------------------------------------------------------------------------
# The ladder itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("best,stop,nxt", [
    (0.0, -15.0, 15.0), (14.9, -15.0, 15.0), (15.0, 0.0, 33.0), (32.0, 0.0, 33.0),
    (33.0, 15.0, 50.0), (60.0, 33.0, 75.0), (100.0, 75.0, 150.0), (250.0, 150.0, None),
])
def test_ladder_levels(best, stop, nxt):
    assert ladder_levels(best) == (stop, nxt)


def test_config_carries_the_ladder():
    cfg = Ema9RsiMomentumConfig()
    assert cfg.initial_sl_pct == 15.0
    assert tuple(cfg.profit_ladder_pct) == DEFAULT_PROFIT_LADDER_PCT
    tuned = Ema9RsiMomentumConfig.from_settings({"ema9_rsi_profit_ladder_pct": [20, 40, 80]})
    assert ladder_levels(45.0, tuned.profit_ladder_pct) == (20.0, 80.0)


def test_the_stop_only_ever_moves_up():
    stop, nxt = ratchet_stop(100.0, 85.0, 140.0)          # best +40% -> stop +15
    assert (stop, nxt) == (115.0, 150.0)
    again, _ = ratchet_stop(100.0, stop, 101.0)           # a lower "best" never loosens it
    assert again == 115.0


def test_prices_sit_on_the_tick_grid():
    assert initial_stop(196.65) == 167.15                 # 167.1525 rounded DOWN to 0.05
    stop, nxt = ratchet_stop(196.65, 167.15, 196.65 * 1.20)
    assert stop == 196.65 and nxt == round(196.65 * 1.33, 2)


def test_stop_reasons():
    assert stop_reason(100.0, 85.0) == "STOP LOSS"
    assert stop_reason(100.0, 100.0) == "BREAKEVEN STOP"
    assert stop_reason(100.0, 133.0).startswith("TRAILING STOP (+33%")


def test_bad_entry_is_rejected():
    with pytest.raises(ValueError):
        ratchet_stop(0.0, 0.0, 10.0)


# ---------------------------------------------------------------------------
# Paper books
# ---------------------------------------------------------------------------

def test_variant_book_has_no_target_exit():
    pos = {"entry_premium": 100.0, "sl_premium": 85.0, "tgt_premium": 115.0, "highest_premium": 100.0}
    assert ev.check_price_exits(pos, 150.0) is None        # the old 33% exit now just climbs
    assert pos["sl_premium"] == 133.0 and pos["tgt_premium"] == 175.0
    assert ev.check_price_exits(pos, 132.5).startswith("TRAILING STOP")


def test_main_book_runs_the_ladder():
    src = inspect.getsource(po.run_session)
    assert "ratchet_stop(" in src and "stop_reason(" in src
    assert "TARGET HIT" not in src


# ---------------------------------------------------------------------------
# Live engine
# ---------------------------------------------------------------------------

def _main_src():
    return (_bootstrap.TRADING_SYSTEM_ROOT / "trading_bot" / "main.py").read_text(encoding="utf-8")


def test_live_engine_has_an_ema9_option_branch():
    src = _main_src()
    branch = src[src.index("elif strategy_name == EMA9_RSI_MOMENTUM_STRATEGY_NAME and is_opt_pos:"):]
    branch = branch[:branch.index("\n                else:\n")]
    for needle in ("ratchet_stop(", "evaluate_protective_exit(", "update_exchange_sl(",
                   "exit_engine.eod_exit_time", "iloc[:-1]"):
        assert needle in branch, needle


def test_live_engine_opens_ema9_with_the_15pct_stop():
    src = _main_src()
    assert "initial_stop(\n                                    entry_premium" in src


def _option(symbol="NIFTY26SEP23300CE"):
    return Position(symbol=symbol, side=1, entry_price=100.0, quantity=65, entry_time="10:00:00",
                    highest_price=100.0, lowest_price=100.0, stop_loss=85.0, target=0.0, lot_size=65)


def test_smart_exit_no_longer_hair_triggers_option_winners():
    eng = SmartExitEngine(atr_multiplier=1.5, trailing_activation_pct=0.5, trailing_offset_pct=0.35)
    pos = _option()
    assert eng.evaluate_exit(pos, 101.0, "10:05:00", current_atr=5.0)[0] is False
    # A 0.40-point give-back from the +1% peak: this used to exit an option.
    assert eng.evaluate_exit(pos, 100.6, "10:06:00", current_atr=5.0)[0] is False


def test_smart_exit_still_uses_the_give_back_off_options():
    eng = SmartExitEngine(atr_multiplier=1.5, trailing_activation_pct=0.5, trailing_offset_pct=0.35)
    # Not RELIANCE: the engine's `"CE" in symbol` test reads RELIAN-CE as an option.
    pos = Position(symbol="NSE:INFY-EQ", side=1, entry_price=100.0, quantity=10, entry_time="10:00:00",
                   highest_price=100.0, lowest_price=100.0, stop_loss=95.0, target=0.0)
    eng.evaluate_exit(pos, 101.0, "10:05:00", current_atr=5.0)
    assert eng.evaluate_exit(pos, 100.6, "10:06:00", current_atr=5.0)[1] == "Trailing Stop-Loss Hit (Offset)"


# ---------------------------------------------------------------------------
# Expiry-day measurement (the owner's deliberate 0DTE setups)
# ---------------------------------------------------------------------------

def test_expiry_day_is_recorded(monkeypatch):
    import datetime

    import pytz
    now = pytz.timezone("Asia/Kolkata").localize(datetime.datetime(2026, 9, 15, 10, 0))
    assert ev.expiry_info("15-09-2026", now) == ("2026-09-15", True)
    assert ev.expiry_info("22-09-2026", now) == ("2026-09-22", False)
    assert ev.expiry_info(None, now) == (None, None)
