"""Tests for the opt-in execution-realism layer.

Two obligations, and they pull in opposite directions:

* **Backward compatibility.** With realism off — the default — the
  harness must take the exact code path it always took. Every published
  result in this repository was produced that way, and a silent change
  would invalidate all of them at once.
* **The modelling must actually bite.** An opt-in realism layer that
  quietly does nothing is worse than none, because it manufactures
  confidence. So the ON tests assert direction and magnitude, not merely
  that a flag was accepted.

The audit these exist for (2026-08-10) measured three omissions: no
friction of any kind, `days_to_expiry` held constant within a session so
intraday theta was never charged, and `select_option`'s Greeks Guard
reading the machine clock (computing -426 days to expiry when replaying a
genuine 0 DTE session).
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from datetime import date, datetime, time

import numpy as np
import pandas as pd
import pytest

from trading_bot.strategies.premium_selection.options_selector import (
    calculate_option_price,
    select_option,
)
from validation_harness.harness import run_strategy_backtest
from validation_harness.market_realism import (
    NIFTY_RETAIL,
    REALISTIC,
    FrictionModel,
    RealismConfig,
    fractional_dte,
)


def _market(days=6, bars_per_day=75, start="2026-03-02", seed=4):
    """Trending intraday sessions, enough to produce entries and exits."""
    rng = np.random.default_rng(seed)
    frames = []
    base = 24_000.0
    for d in range(days):
        day = pd.Timestamp(start) + pd.Timedelta(days=d)
        idx = pd.date_range(day + pd.Timedelta(hours=9, minutes=15),
                            periods=bars_per_day, freq="5min")
        close = base + np.linspace(0, 90, bars_per_day) + rng.normal(0, 6, bars_per_day).cumsum()
        frames.append(pd.DataFrame(
            {"open": close, "high": close + 6, "low": close - 6, "close": close,
             "volume": rng.uniform(1e5, 3e5, bars_per_day)}, index=idx))
        base = float(close[-1])
    return pd.concat(frames)


def _run(realism=None, strategy="structure_break"):
    return run_strategy_backtest(strategy, _market(), realism=realism)


def _pnl(result):
    return sum(t.pnl for t in result.trades)


# ─────────────────────────────────────────────────────────────────────
# A. Backward compatibility — the default path must not move
# ─────────────────────────────────────────────────────────────────────

def test_default_is_none_for_every_new_parameter():
    import inspect

    params = inspect.signature(run_strategy_backtest).parameters
    assert params["realism"].default is None
    assert params["risk_config"].default is None


def test_realism_none_and_inert_config_are_bit_identical():
    """`RealismConfig()` with nothing enabled must reproduce `None`
    exactly — otherwise merely constructing the object changes results."""
    off = _run(None)
    inert = _run(RealismConfig())

    assert len(off.trades) == len(inert.trades)
    assert _pnl(off) == pytest.approx(_pnl(inert), abs=1e-9)
    for a, b in zip(off.trades, inert.trades):
        assert a.entry_premium == pytest.approx(b.entry_premium, abs=1e-12)
        assert a.exit_premium == pytest.approx(b.exit_premium, abs=1e-12)
        assert a.pnl == pytest.approx(b.pnl, abs=1e-12)
        assert a.exit_reason == b.exit_reason


def test_default_run_charges_no_friction_at_all():
    off = _run(None)
    assert off.friction_charges == 0.0
    assert off.friction_spread == 0.0


def test_default_run_is_deterministic_across_repeats():
    """Guards against any wall-clock or RNG dependence sneaking into the
    default path — the exact defect class found in the Greeks Guard."""
    a, b = _run(None), _run(None)
    assert [t.pnl for t in a.trades] == [t.pnl for t in b.trades]
    assert [t.entry_premium for t in a.trades] == [t.entry_premium for t in b.trades]


def test_an_empty_friction_model_is_treated_as_off():
    """`FrictionModel()` is all-zero; it must not start charging spread of
    zero width and rounding P&L differently."""
    off = _run(None)
    zeroed = _run(RealismConfig(friction=FrictionModel()))
    assert _pnl(off) == pytest.approx(_pnl(zeroed), abs=1e-9)


# ─────────────────────────────────────────────────────────────────────
# B. Friction must bite, in the right direction and the right size
# ─────────────────────────────────────────────────────────────────────

def test_friction_reduces_pnl_and_records_what_it_charged():
    off = _run(None)
    on = _run(RealismConfig(friction=NIFTY_RETAIL))

    assert on.friction_charges > 0
    assert on.friction_spread > 0
    assert _pnl(on) < _pnl(off), "friction must cost money"


def test_buy_fills_above_mid_and_sell_fills_below():
    f = NIFTY_RETAIL
    assert f.buy_fill(160.0) > 160.0
    assert f.sell_fill(160.0) < 160.0
    assert f.buy_fill(160.0) - 160.0 == pytest.approx(160.0 - f.sell_fill(160.0))


def test_sell_fill_never_goes_negative():
    """A proportional spread on a near-worthless option must not invent a
    credit."""
    assert FrictionModel(half_spread_pct=0.9).sell_fill(0.10) >= 0.0


def test_charges_scale_with_quantity_and_are_never_negative():
    one = NIFTY_RETAIL.charges(160.0, 170.0, 65)
    two = NIFTY_RETAIL.charges(160.0, 170.0, 130)
    assert 0 < one < two
    # Brokerage is flat, so doubling quantity less than doubles charges.
    assert two < 2 * one


def test_charges_match_a_hand_computed_round_trip():
    """Pins the rate card. If someone edits a rate, this fails loudly
    rather than silently re-pricing every future result."""
    f = NIFTY_RETAIL
    buy, sell, qty = 160.0, 170.0, 65
    buy_to, sell_to = buy * qty, sell * qty
    turnover = buy_to + sell_to
    brokerage = 40.0
    exchange = turnover * 0.000495
    sebi = turnover * 0.000001
    stt = sell_to * 0.000625
    stamp = buy_to * 0.00003
    gst = (brokerage + exchange + sebi) * 0.18
    expected = brokerage + exchange + sebi + stt + stamp + gst
    assert f.charges(buy, sell, qty) == pytest.approx(expected)


def test_entry_stop_is_derived_from_the_fill_not_the_mid():
    """If the stop were computed off the mid while the fill is worse, the
    risk reported would not be the risk taken."""
    off = _run(None)
    on = _run(RealismConfig(friction=NIFTY_RETAIL))
    if not off.trades or not on.trades:
        pytest.skip("fixture produced no trades")
    assert on.trades[0].entry_premium > off.trades[0].entry_premium


# ─────────────────────────────────────────────────────────────────────
# C. Intraday theta
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("dte", [0, 1, 2, 4, 6])
def test_fractional_dte_matches_time_remaining_to_the_expiry_close(dte):
    expiry = date(2026, 3, 20)
    ts = pd.Timestamp(expiry) - pd.Timedelta(days=dte) + pd.Timedelta(hours=9, minutes=45)
    got = fractional_dte(expiry, ts)
    expected = dte + (15.5 - 9.75) / 24.0
    assert got == pytest.approx(expected, abs=1e-9)


def test_fractional_dte_decreases_through_the_session():
    expiry = date(2026, 3, 20)
    morning = fractional_dte(expiry, pd.Timestamp("2026-03-20 09:45"))
    midday = fractional_dte(expiry, pd.Timestamp("2026-03-20 12:00"))
    close = fractional_dte(expiry, pd.Timestamp("2026-03-20 15:30"))
    assert morning > midday > close
    assert close == 0.0


def test_fractional_dte_is_never_negative_after_expiry():
    assert fractional_dte(date(2026, 3, 20), pd.Timestamp("2026-03-21 09:15")) == 0.0


def test_intraday_theta_actually_decays_a_held_option():
    """Spot unchanged, time passing: the premium must fall. Under the
    default integer DTE it cannot, which is the defect."""
    expiry = date(2026, 3, 20)
    spot, strike = 24_000.0, 23_950.0
    t0 = pd.Timestamp("2026-03-20 09:45")
    t1 = pd.Timestamp("2026-03-20 10:30")

    p0 = calculate_option_price(spot, strike, fractional_dte(expiry, t0), 0.15, "CE")
    p1 = calculate_option_price(spot, strike, fractional_dte(expiry, t1), 0.15, "CE")
    assert p1 < p0

    legacy0 = calculate_option_price(spot, strike, max((expiry - t0.date()).days, 0), 0.15, "CE")
    legacy1 = calculate_option_price(spot, strike, max((expiry - t1.date()).days, 0), 0.15, "CE")
    assert legacy0 == legacy1, "integer DTE cannot decay intraday — the defect"


def test_intraday_theta_changes_backtest_economics():
    off = _run(None)
    on = _run(RealismConfig(intraday_theta=True))
    assert [t.entry_premium for t in on.trades] != [t.entry_premium for t in off.trades] \
        or [t.exit_premium for t in on.trades] != [t.exit_premium for t in off.trades]


# ─────────────────────────────────────────────────────────────────────
# D. Simulated clock / DTE correctness in select_option
# ─────────────────────────────────────────────────────────────────────

def test_select_option_default_still_uses_the_wall_clock():
    """Backward compatibility: omitting `as_of` must behave exactly as
    before, so historical replays are unchanged."""
    import inspect

    assert inspect.signature(select_option).parameters["as_of"].default is None


def test_as_of_makes_days_to_expiry_reflect_the_simulated_session():
    """The audit's finding: replaying 2025-06-10 (a genuine 0 DTE
    session) the guard computed -426 days from the machine clock. With
    `as_of` it evaluates the replayed session instead."""
    sim = date(2025, 6, 10)
    before_2pm = select_option("NIFTY", 24_000, "CE", itm_strikes=1,
                               from_date=sim, as_of=datetime(2025, 6, 10, 11, 0))
    after_2pm = select_option("NIFTY", 24_000, "CE", itm_strikes=1,
                              from_date=sim, as_of=datetime(2025, 6, 10, 14, 30))

    assert before_2pm.expiry == sim, "fixture must be a real 0 DTE session"
    # The Greeks Guard fires only after 14:00 on expiry day.
    assert before_2pm.itm_offset == 1
    assert after_2pm.itm_offset == 2
    assert after_2pm.strike < before_2pm.strike, "CE guard must go deeper ITM"


def test_guard_does_not_fire_when_expiry_is_not_today():
    sim = date(2026, 8, 7)  # 4 days to a 2026-08-11 expiry
    c = select_option("NIFTY", 24_000, "CE", itm_strikes=1,
                      from_date=sim, as_of=datetime(2026, 8, 7, 14, 30))
    assert c.expiry != sim
    assert c.itm_offset == 1


def test_put_guard_goes_deeper_itm_upward():
    sim = date(2025, 6, 10)
    c = select_option("NIFTY", 24_000, "PE", itm_strikes=1,
                      from_date=sim, as_of=datetime(2025, 6, 10, 14, 30))
    atm = select_option("NIFTY", 24_000, "PE", itm_strikes=1,
                        from_date=sim, as_of=datetime(2025, 6, 10, 11, 0))
    assert c.strike > atm.strike


# ─────────────────────────────────────────────────────────────────────
# E. The bundled preset
# ─────────────────────────────────────────────────────────────────────

def test_realistic_preset_enables_all_three_corrections():
    assert REALISTIC.friction is NIFTY_RETAIL
    assert REALISTIC.intraday_theta is True
    assert REALISTIC.simulated_clock is True
    assert REALISTIC.is_active is True
    assert RealismConfig().is_active is False
