"""Regression tests for `SmartExitEngine`'s opt-in Fibonacci trail.

Two obligations pulling opposite ways, same as the realism layer:

* the extension must be **invisible** when off — six existing strategies
  route through this engine and their published results must not move;
* it must **actually work** when on, or it manufactures confidence.

The architectural rule this exists to honour: no parallel exit engine.
`institutional_momentum` took its own exit path and its exits never once
executed for the strategy's entire life. So the fib logic lives inside
`SmartExitEngine`, behind a default-False flag, reading two default-None
arguments.
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import inspect

import pytest

from shared.exits.exit_engine import Position, SmartExitEngine, plan_fib_levels


def _pos(entry=200.0, sl=170.0, qty=65, symbol="NSE:NIFTY2680724000CE", **kw):
    p = Position(
        symbol=symbol, side=1, entry_price=entry, quantity=qty,
        entry_time="2026-03-20T09:30:00", highest_price=entry, lowest_price=entry,
        stop_loss=sl, target=0.0, lot_size=65,
    )
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def _ce_plan():
    # swing 23,900-24,000 -> span 100; CE extensions project up from 24,000
    return plan_fib_levels(24_000.0, 23_900.0, 1)


def _pe_plan():
    return plan_fib_levels(24_000.0, 23_900.0, -1)


# ─────────────────────────────────────────────────────────────────────
# Level mathematics
# ─────────────────────────────────────────────────────────────────────

def test_ce_extensions_project_up_from_the_swing_high():
    assert _ce_plan() == pytest.approx((24_050.0, 24_061.8, 24_100.0))


def test_pe_extensions_project_down_from_the_swing_low():
    assert _pe_plan() == pytest.approx((23_850.0, 23_838.2, 23_800.0))


def test_ce_and_pe_are_exact_mirrors():
    """A CE at 0.618 and a PE at 0.618 must be the same distance
    travelled, measured the same way."""
    ce, pe = _ce_plan(), _pe_plan()
    for c, p in zip(ce, pe):
        assert (c - 24_000.0) == pytest.approx(23_900.0 - p)


def test_degenerate_swing_yields_no_plan():
    """Zero or inverted range must be "no plan", not levels stacked on
    top of each other."""
    assert plan_fib_levels(24_000.0, 24_000.0, 1) is None
    assert plan_fib_levels(23_900.0, 24_000.0, 1) is None


# ─────────────────────────────────────────────────────────────────────
# Backward compatibility — the default path must not move
# ─────────────────────────────────────────────────────────────────────

def test_flag_and_new_arguments_all_default_to_off():
    assert inspect.signature(SmartExitEngine.__init__).parameters[
        "use_dynamic_fib_trail"].default is False
    params = inspect.signature(SmartExitEngine.evaluate_exit).parameters
    assert params["underlying_price"].default is None
    assert params["underlying_favourable"].default is None


def test_position_defaults_carry_no_fib_plan():
    p = _pos()
    assert p.fib_levels is None and p.fib_direction == 0
    assert p.fib_stage == 0 and p.fib_premium_at_half == 0.0


def test_engine_with_trail_off_ignores_a_plan_entirely():
    """Even a position carrying levels, with the underlying far past 1.0,
    must be untouched when the flag is off."""
    off = SmartExitEngine()
    p = _pos(fib_levels=_ce_plan(), fib_direction=1)
    _should_exit, reason, _ = off.evaluate_exit(
        p, 210.0, "11:00:00", 5.0, underlying_price=25_000.0, underlying_favourable=25_000.0
    )
    # The ATR trail legitimately moves `stop_loss` here — that is
    # pre-existing behaviour. What must be untouched is the fib state.
    assert "Fib" not in reason
    assert p.fib_stage == 0 and p.fib_premium_at_half == 0.0


def test_trail_on_but_no_underlying_supplied_is_inert():
    """Callers that never pass the underlying (i.e. every existing one)
    keep their behaviour even if the flag is somehow enabled."""
    on = SmartExitEngine(use_dynamic_fib_trail=True)
    p = _pos(fib_levels=_ce_plan(), fib_direction=1)
    _should_exit, reason, _ = on.evaluate_exit(p, 210.0, "11:00:00", 5.0)
    assert "Fib" not in reason
    assert p.fib_stage == 0 and p.fib_premium_at_half == 0.0


def test_trail_on_without_a_plan_is_inert():
    on = SmartExitEngine(use_dynamic_fib_trail=True)
    p = _pos()
    _should_exit, reason, _ = on.evaluate_exit(p, 210.0, "11:00:00", 5.0, underlying_price=25_000.0)
    assert "Fib" not in reason
    assert p.fib_stage == 0


# ─────────────────────────────────────────────────────────────────────
# The trail itself
# ─────────────────────────────────────────────────────────────────────

def _on():
    return SmartExitEngine(use_dynamic_fib_trail=True)


def test_half_level_moves_stop_to_breakeven_and_records_the_premium():
    p = _pos(fib_levels=_ce_plan(), fib_direction=1)
    _on().evaluate_exit(
        p, 232.0, "11:00:00", 5.0, underlying_price=24_050.0, underlying_favourable=24_050.0
    )
    assert p.fib_stage == 1
    assert p.fib_premium_at_half == pytest.approx(232.0)
    # Cost-to-cost at minimum. The ATR trail may legitimately push it
    # higher on the same evaluation; it must never sit below breakeven.
    assert p.stop_loss >= p.entry_price


def test_618_level_trails_the_stop_to_the_premium_held_at_half():
    """Isolated from the engine's other mechanisms on purpose: a wide
    initial stop keeps 1:1 partial booking from firing (it would reset the
    stop to breakeven), and a near-zero ATR keeps the ATR trail from
    setting a higher stop of its own. What is under test is the fib
    contribution alone."""
    e = _on()
    # `is_partially_booked=True` so the 1:1 booking rule (which resets the
    # stop to breakeven) is already spent and cannot mask the fib stop.
    p = _pos(entry=200.0, sl=20.0, is_partially_booked=True,
             fib_levels=_ce_plan(), fib_direction=1)
    e.evaluate_exit(p, 232.0, "11:00:00", 0.01, underlying_price=24_050.0, underlying_favourable=24_050.0)
    assert p.fib_premium_at_half == pytest.approx(232.0)
    e.evaluate_exit(p, 240.0, "11:05:00", 0.01, underlying_price=24_062.0, underlying_favourable=24_062.0)
    assert p.fib_stage == 2
    # At least the premium held at 0.5. The ATR trail may independently
    # sit higher (it ratchets from the running peak) — the fib guarantee
    # is a floor, not an exact value.
    assert p.stop_loss >= 232.0, "locks in at least the premium held at 0.5"


def test_one_stage_advances_per_evaluation():
    """A single bar clearing 0.5 AND 0.618 must not record the 0.5
    premium and immediately trail the stop up to it — that would stop the
    position out at the current price for no reason."""
    p = _pos(fib_levels=_ce_plan(), fib_direction=1)
    should_exit, _, _ = _on().evaluate_exit(
        p, 245.0, "11:00:00", 5.0, underlying_price=24_070.0, underlying_favourable=24_070.0
    )
    assert should_exit is False
    assert p.fib_stage == 1
    assert p.stop_loss < 245.0, "stop must never be set to the current price"


def test_full_target_exits_the_whole_position():
    p = _pos(fib_levels=_ce_plan(), fib_direction=1)
    should_exit, reason, qty = _on().evaluate_exit(
        p, 260.0, "11:00:00", 5.0, underlying_price=24_100.0, underlying_favourable=24_100.0
    )
    assert should_exit is True
    assert reason == "Fib 1.0 Target Hit"
    assert qty is None


def test_intrabar_extreme_triggers_even_when_the_close_falls_back():
    """The rule the brief calls for: a candle-close-only mechanism must
    not erase a target the price actually reached."""
    p = _pos(fib_levels=_ce_plan(), fib_direction=1)
    should_exit, reason, _ = _on().evaluate_exit(
        p, 250.0, "11:00:00", 5.0,
        underlying_price=24_010.0,        # closed back below every level
        underlying_favourable=24_100.0,   # but touched 1.0 inside the bar
    )
    assert should_exit is True and reason == "Fib 1.0 Target Hit"


def test_put_side_triggers_on_downward_extensions():
    p = _pos(symbol="NSE:NIFTY2680724000PE", fib_levels=_pe_plan(), fib_direction=-1)
    e = _on()
    e.evaluate_exit(p, 232.0, "11:00:00", 5.0, underlying_price=23_850.0, underlying_favourable=23_850.0)
    assert p.fib_stage == 1 and p.stop_loss >= p.entry_price
    should_exit, reason, _ = e.evaluate_exit(
        p, 260.0, "11:05:00", 5.0, underlying_price=23_800.0, underlying_favourable=23_800.0
    )
    assert should_exit is True and reason == "Fib 1.0 Target Hit"


def test_stop_only_ever_ratchets_up():
    """An already-tighter stop must not be loosened by a fib stage."""
    # Stop already ABOVE entry, wide enough that partial booking (which
    # resets the stop to breakeven) cannot fire, and ATR ~0 so only the
    # fib block can move it.
    p = _pos(entry=200.0, sl=205.0, is_partially_booked=True,
             fib_levels=_ce_plan(), fib_direction=1)
    _on().evaluate_exit(p, 232.0, "11:00:00", 0.01,
                        underlying_price=24_050.0, underlying_favourable=24_050.0)
    # The invariant is that a stop NEVER loosens. Breakeven (200) is below
    # the existing 205, so the fib block must not apply it; the ATR trail
    # may still ratchet it further up, which is pre-existing behaviour.
    assert p.stop_loss >= 205.0, "breakeven must not loosen a tighter stop"


def test_eod_still_wins_over_the_fib_target():
    """A time stop must outrank a profit target — the position has to be
    flat at the cutoff regardless."""
    p = _pos(fib_levels=_ce_plan(), fib_direction=1)
    should_exit, reason, _ = _on().evaluate_exit(
        p, 260.0, "15:20:00", 5.0, underlying_price=24_100.0, underlying_favourable=24_100.0
    )
    assert should_exit is True and reason == "Time-based EOD Exit"


def test_updated_stop_is_honoured_on_the_same_evaluation():
    """The fib block sits before the hard-SL check, so a stop it raises
    must bite immediately rather than a bar later."""
    e = _on()
    p = _pos(fib_levels=_ce_plan(), fib_direction=1)
    e.evaluate_exit(p, 232.0, "11:00:00", 5.0, underlying_price=24_050.0, underlying_favourable=24_050.0)
    # Premium now below breakeven while the underlying holds above 0.5.
    should_exit, reason, _ = e.evaluate_exit(
        p, 195.0, "11:05:00", 5.0, underlying_price=24_055.0, underlying_favourable=24_055.0
    )
    assert should_exit is True and reason == "Stop-Loss Hit"


# ─────────────────────────────────────────────────────────────────────
# Strategy declaration
# ─────────────────────────────────────────────────────────────────────

def test_only_momentum_15_5_opts_in():
    """Every other strategy module must be silent on the flag, or it
    would inherit an exit policy it was never validated with."""
    import importlib
    import pkgutil

    import trading_bot.strategies as pkg

    opted = []
    for mod in pkgutil.iter_modules(pkg.__path__):
        try:
            m = importlib.import_module(f"trading_bot.strategies.{mod.name}")
        except Exception:
            continue
        if getattr(m, "USE_DYNAMIC_FIB_TRAIL", False):
            opted.append(mod.name)
    assert opted == ["momentum_15_5"], opted


def test_percentage_giveback_trail_is_suppressed_only_when_fib_is_on():
    """The two are competing trailing mechanisms and the 0.35pp giveback
    always wins (92.4% of 5-min bars move a premium by more than the whole
    allowance). Leaving it active would cut every runner long before an
    extension level could be reached — so it is suppressed, but ONLY under
    the opt-in flag."""
    src = inspect.getsource(SmartExitEngine.evaluate_exit)
    assert "if not self.use_dynamic_fib_trail:" in src
    assert "Trailing Stop-Loss Hit (Offset)" in src

    # Wide stop so 1:1 partial booking cannot fire, large ATR so the ATR
    # trail cannot fire either — isolating the percentage giveback.
    def _fresh():
        return _pos(entry=200.0, sl=20.0)

    off = SmartExitEngine()
    p = _fresh()
    off.evaluate_exit(p, 260.0, "11:00:00", 500.0)          # peak
    fired = off.evaluate_exit(p, 259.0, "11:05:00", 500.0)  # small giveback
    assert fired[1] == "Trailing Stop-Loss Hit (Offset)"

    # Fib engine: identical path must NOT produce that exit.
    on = SmartExitEngine(use_dynamic_fib_trail=True)
    q = _fresh()
    q.fib_levels, q.fib_direction = _ce_plan(), 1
    on.evaluate_exit(q, 260.0, "11:00:00", 500.0, underlying_price=24_000.0)
    again = on.evaluate_exit(q, 259.0, "11:05:00", 500.0, underlying_price=24_000.0)
    assert again[1] != "Trailing Stop-Loss Hit (Offset)"
