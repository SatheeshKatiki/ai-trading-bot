"""End of day is a review, not a guillotine (owner's rule, 2026-09-22).

Until now every open position was closed at 15:15 regardless of what it was
doing. The owner asked for something a trader would actually do: at 15:15
look at each position, let one that is still running keep going to 15:25, and
close everything by then.

Measured over 675 sessions, costs calibrated from real option premiums:

                                     NIFTY      SENSEX
  close everything at 15:15        +11,150     -37,841
  close everything at 15:25         +7,415     -37,507
  extend only runners (within 3%)  +12,428     -37,463
  extend only runners (within 5%)  +12,005     -37,297

Extending everything loses money; extending only what is still at its high
makes money. The rule is not "trade later", it is "do not interrupt a move
that is still going".

Also covered: the expiry-day late entry, and the overnight carry -- which is
off, needs very strong evidence, and can never happen on an expiry day.
"""

from __future__ import annotations

import datetime
import pathlib

import pytest

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from shared.eod_policy import (
    CARRY,
    CLOSE_NOW,
    EXTEND,
    HOLD_OPEN,
    decide_eod,
    expiry_late_entry_allowed,
)
from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig


def _cfg(**over) -> Ema9RsiMomentumConfig:
    return Ema9RsiMomentumConfig(**over)


def _t(hhmm: str) -> datetime.time:
    hh, mm = hhmm.split(":")
    return datetime.time(int(hh), int(mm))


# ---------------------------------------------------------------------------
# The 15:15 review
# ---------------------------------------------------------------------------

def test_nothing_is_reviewed_before_the_review_time():
    v = decide_eod(_t("15:14"), gain_pct=30, giveback_pct=0, strength="STRONG", cfg=_cfg())
    assert v.action == HOLD_OPEN
    assert not v.must_close


def test_a_runner_still_near_its_high_is_extended():
    v = decide_eod(_t("15:16"), gain_pct=22, giveback_pct=2, strength="STRONG", cfg=_cfg())
    assert v.action == EXTEND
    assert "held to 15:25" in v.reason


def test_a_position_that_has_faded_off_its_high_is_closed():
    """The whole point is not interrupting a move that is STILL going."""
    v = decide_eod(_t("15:16"), gain_pct=22, giveback_pct=9, strength="STRONG", cfg=_cfg())
    assert v.must_close
    assert "off its high" in v.reason


def test_a_losing_position_is_never_extended():
    v = decide_eod(_t("15:16"), gain_pct=-4, giveback_pct=0, strength="VERY_STRONG", cfg=_cfg())
    assert v.must_close
    assert "not in profit" in v.reason


def test_a_flat_position_is_not_a_runner():
    assert decide_eod(_t("15:16"), 0.0, 0.0, "STRONG", _cfg()).must_close


def test_a_runner_whose_signal_reversed_is_closed():
    """A runner that has lost its trend is not a runner."""
    v = decide_eod(_t("15:16"), gain_pct=30, giveback_pct=1, strength="STRONG",
                   cfg=_cfg(), reversed_signal=True)
    assert v.must_close
    assert "reversed" in v.reason


def test_the_allowed_giveback_is_configurable():
    args = dict(gain_pct=22, giveback_pct=9, strength="STRONG")
    assert decide_eod(_t("15:16"), cfg=_cfg(), **args).must_close
    assert decide_eod(_t("15:16"), cfg=_cfg(eod_runner_giveback_pct=12.0), **args).action == EXTEND


def test_the_review_and_hard_times_are_configurable():
    cfg = _cfg(eod_review_time="15:05", eod_hard_time="15:20")
    assert decide_eod(_t("15:04"), 30, 1, "STRONG", cfg).action == HOLD_OPEN
    assert decide_eod(_t("15:06"), 30, 1, "STRONG", cfg).action == EXTEND
    assert decide_eod(_t("15:21"), 30, 1, "STRONG", cfg).must_close


# ---------------------------------------------------------------------------
# The 15:25 hard stop
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gain,strength", [(5, "NONE"), (60, "VERY_STRONG"), (200, "VERY_STRONG")])
def test_everything_closes_at_the_hard_time_by_default(gain, strength):
    v = decide_eod(_t("15:26"), gain, 0, strength, _cfg())
    assert v.must_close
    assert "hard square-off" in v.reason


def test_an_extended_runner_still_dies_at_the_hard_time():
    assert decide_eod(_t("15:25"), 80, 0, "VERY_STRONG", _cfg()).must_close


# ---------------------------------------------------------------------------
# Overnight carry: off, strict, and never on expiry day
# ---------------------------------------------------------------------------

def test_carry_is_off_by_default():
    assert decide_eod(_t("15:26"), 100, 0, "VERY_STRONG", _cfg()).must_close


def test_carry_when_enabled_needs_a_big_gain_and_the_strongest_momentum():
    on = _cfg(allow_overnight_carry=True)
    assert decide_eod(_t("15:26"), 100, 0, "VERY_STRONG", on).action == CARRY
    assert decide_eod(_t("15:26"), 10, 0, "VERY_STRONG", on).must_close    # gain too small
    assert decide_eod(_t("15:26"), 100, 0, "STRONG", on).must_close        # not strong enough
    assert decide_eod(_t("15:26"), 100, 0, "VERY_STRONG", on,
                      reversed_signal=True).must_close                    # trend gone


def test_carry_says_out_loud_that_gap_risk_is_unhedged():
    v = decide_eod(_t("15:26"), 100, 0, "VERY_STRONG", _cfg(allow_overnight_carry=True))
    assert "gap risk" in v.reason


def test_carry_never_happens_on_an_expiry_day():
    """The contract expires -- there is nothing to carry."""
    v = decide_eod(_t("15:26"), 300, 0, "VERY_STRONG",
                   _cfg(allow_overnight_carry=True), is_expiry_day=True)
    assert v.must_close
    assert "expiry day" in v.reason


# ---------------------------------------------------------------------------
# Expiry-day late entry
# ---------------------------------------------------------------------------

def test_a_late_entry_needs_an_expiry_day():
    ok, why = expiry_late_entry_allowed(_t("15:18"), "VERY_STRONG", _cfg(), is_expiry_day=False)
    assert not ok and "not an expiry day" in why


def test_a_late_entry_on_expiry_day_needs_the_strongest_momentum():
    assert expiry_late_entry_allowed(_t("15:18"), "VERY_STRONG", _cfg(), True)[0]
    assert not expiry_late_entry_allowed(_t("15:18"), "STRONG", _cfg(), True)[0]
    assert not expiry_late_entry_allowed(_t("15:18"), "NORMAL", _cfg(), True)[0]


def test_a_late_entry_stops_at_the_expiry_cutoff():
    assert not expiry_late_entry_allowed(_t("15:26"), "VERY_STRONG", _cfg(), True)[0]


def test_late_entry_can_be_switched_off():
    ok, why = expiry_late_entry_allowed(_t("15:18"), "VERY_STRONG",
                                        _cfg(expiry_late_entry=False), True)
    assert not ok and "switched off" in why


# ---------------------------------------------------------------------------
# The live engine uses it, and fails safe
# ---------------------------------------------------------------------------

class _Pos:
    def __init__(self, entry, last, best, exiting=False, reversed_=False):
        self.entry_price, self.current_price, self.highest_price = entry, last, best
        self.is_exiting, self.signal_reversed = exiting, reversed_
        self.momentum_strength = "STRONG"


def test_the_engine_holds_a_runner_and_closes_the_rest():
    import trading_bot.main as main_module
    positions = {
        "RUNNER": _Pos(100.0, 130.0, 131.0),        # +30%, 0.8% off its high
        "FADED": _Pos(100.0, 110.0, 140.0),         # +10% but 21% off its high
        "LOSER": _Pos(100.0, 92.0, 101.0),          # in loss
    }
    due = main_module.positions_needing_eod_exit(
        positions, "15:16:00", "15:15:00", cfg=_cfg())
    assert sorted(due) == ["FADED", "LOSER"]


def test_the_engine_closes_everything_at_the_hard_time():
    import trading_bot.main as main_module
    positions = {"RUNNER": _Pos(100.0, 180.0, 181.0)}
    assert main_module.positions_needing_eod_exit(
        positions, "15:26:00", "15:15:00", cfg=_cfg()) == ["RUNNER"]


def test_without_a_policy_the_engine_closes_everything_as_before():
    """Closing is the safe failure -- a policy that cannot be read must not
    leave positions open."""
    import trading_bot.main as main_module
    positions = {"RUNNER": _Pos(100.0, 180.0, 181.0)}
    assert main_module.positions_needing_eod_exit(
        positions, "15:16:00", "15:15:00", cfg=None) == ["RUNNER"]


def test_an_exit_already_in_flight_is_still_never_re_fired():
    import trading_bot.main as main_module
    positions = {"GOING": _Pos(100.0, 90.0, 101.0, exiting=True)}
    assert main_module.positions_needing_eod_exit(
        positions, "15:26:00", "15:15:00", cfg=_cfg()) == []


def test_the_watchdog_passes_the_policy_and_the_expiry_flag():
    src = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "trading_bot", "main.py").read_text(
        encoding="utf-8", errors="ignore")
    assert "_eod_policy_cfg()" in src
    assert "is_expiry_day=_expiry_today()" in src


def test_an_unknown_expiry_never_opens_the_wider_branches():
    """Unknown must count as 'not expiry': both branches it guards WIDEN what
    the bot may do, and a guess must never be what opens them."""
    src = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "shared", "eod_policy.py").read_text(
        encoding="utf-8", errors="ignore")
    start = src.index("def is_expiry_day")
    assert "return None" in src[start:]
    engine = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "trading_bot", "main.py").read_text(
        encoding="utf-8", errors="ignore")
    body = engine[engine.index("def _expiry_today"):][:700]
    assert "is True" in body, "only a definite expiry counts"
    assert "return False" in body
