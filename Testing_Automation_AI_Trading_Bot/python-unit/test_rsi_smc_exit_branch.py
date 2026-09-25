"""M1 -- the strategy-specific stop/exit branch.

Two layers of coverage, because the branch itself lives inside a 2,000-line
async tick handler that cannot be driven directly from a unit test:

* **behavioural** -- `exits.evaluate()` is pure and is tested for real: EOD
  ordering, the ratchet, structural invalidation, structure reversal, and the
  guarantee that it never raises.
* **structural** -- `main.py`'s branch is asserted by reading its source, the
  pattern this suite already uses for `test_ema9_exit_ladder.py`,
  `test_entry_gate.py` and `test_eod_policy.py`.

The structural assertions are not decoration. An exception escaping the exit
path does NOT reach `on_tick`'s own handler -- that only wraps the entry
section -- it escapes into `FyersBroker.stream_quotes`, whose `except` treats
anything at all as a dropped socket and reconnects. A strategy bug would
present as a feed outage, on every tick.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
import pytest

import _bootstrap  # noqa: F401

from trading_bot.strategies.rsi_smc_options_buyer import exits
from trading_bot.strategies.rsi_smc_options_buyer.config import RsiSmcConfig

FIXTURE = (pathlib.Path(__file__).resolve().parent / "fixtures" / "data"
           / "rsi_smc_NIFTY_5Min.csv")


@pytest.fixture(scope="module")
def nifty() -> pd.DataFrame:
    return pd.read_csv(FIXTURE, parse_dates=["datetime"]).set_index("datetime")


@pytest.fixture(autouse=True)
def _reset():
    exits.reset_state()
    yield
    exits.reset_state()


def _main_source() -> str:
    return (_bootstrap.TRADING_SYSTEM_ROOT / "trading_bot" / "main.py").read_text(
        encoding="utf-8")


def _base_kwargs(**overrides):
    kwargs = dict(
        df_underlying=None,
        direction=1,
        entry_premium=100.0,
        current_premium=100.0,
        best_premium=100.0,
        current_stop=85.0,
        now_hms="11:00:00",
        eod_time="15:15:00",
        cfg=RsiSmcConfig(),
    )
    kwargs.update(overrides)
    return kwargs


# ---------------------------------------------------------------------
# EOD is first
# ---------------------------------------------------------------------

def test_position_open_at_exactly_1515_is_closed_by_the_branch():
    """The mandated safeguard.

    A branch that bypasses SmartExitEngine bypasses the 15:15 cutoff that
    lives inside it. `institutional_momentum` shipped exactly that defect and
    had nothing at all to close its positions at the end of a session.
    """
    decision = exits.evaluate(**_base_kwargs(now_hms="15:15:00"))
    assert decision.should_exit
    assert decision.reason == "Time-based EOD Exit"


def test_eod_wins_over_a_profitable_ladder():
    """EOD is checked FIRST, not merely checked."""
    decision = exits.evaluate(**_base_kwargs(
        now_hms="15:20:00", current_premium=300.0, best_premium=300.0))
    assert decision.should_exit
    assert decision.reason == "Time-based EOD Exit"


def test_eod_accepts_a_datetime_prefixed_time():
    decision = exits.evaluate(**_base_kwargs(now_hms="2026-09-25 15:16:00"))
    assert decision.should_exit and "EOD" in decision.reason


def test_before_eod_does_not_exit_on_time():
    decision = exits.evaluate(**_base_kwargs(now_hms="15:14:59"))
    assert not decision.should_exit


# ---------------------------------------------------------------------
# The premium ladder -- percentages only, never an ATR
# ---------------------------------------------------------------------

def test_opening_stop_is_the_configured_percentage_under_entry():
    cfg = RsiSmcConfig()
    assert exits.opening_stop(100.0, cfg) == pytest.approx(85.0, abs=0.05)


def test_stop_ratchets_up_and_never_down():
    cfg = RsiSmcConfig()
    decision = exits.evaluate(**_base_kwargs(
        cfg=cfg, current_premium=120.0, best_premium=120.0, current_stop=85.0))
    assert decision.new_stop >= 85.0
    # Once +15% has been reached the stop is at breakeven or better.
    assert decision.new_stop >= 99.0

    # A later, worse price must not widen it.
    later = exits.evaluate(**_base_kwargs(
        cfg=cfg, current_premium=101.0, best_premium=120.0,
        current_stop=decision.new_stop))
    assert later.new_stop >= decision.new_stop


def test_premium_at_or_below_the_stop_exits():
    decision = exits.evaluate(**_base_kwargs(current_premium=85.0, current_stop=85.0))
    assert decision.should_exit
    assert "STOP" in decision.reason.upper() or "BREAKEVEN" in decision.reason.upper()


def test_ladder_uses_no_atr_at_all():
    """The two price scales must never meet.

    `evaluate` does not accept a premium ATR, so an index-scale value cannot
    be passed into premium maths by mistake -- the 2026-08-07 audit §2.1
    defect class.
    """
    import inspect
    parameters = set(inspect.signature(exits.evaluate).parameters)
    assert "current_atr" not in parameters
    assert "atr" not in parameters


# ---------------------------------------------------------------------
# Structural invalidation (UNDERLYING scale)
# ---------------------------------------------------------------------

def test_structural_invalidation_is_below_the_swept_low_for_a_call():
    cfg = RsiSmcConfig()
    level = exits.structural_invalidation(1, swept_extreme=100.0,
                                          underlying_atr=10.0, cfg=cfg)
    assert level == pytest.approx(100.0 - cfg.sl_atr_buffer * 10.0)


def test_structural_invalidation_is_above_the_swept_high_for_a_put():
    cfg = RsiSmcConfig()
    level = exits.structural_invalidation(-1, swept_extreme=100.0,
                                          underlying_atr=10.0, cfg=cfg)
    assert level == pytest.approx(100.0 + cfg.sl_atr_buffer * 10.0)


def test_structural_invalidation_handles_missing_inputs():
    cfg = RsiSmcConfig()
    assert np.isnan(exits.structural_invalidation(1, float("nan"), 10.0, cfg))
    assert np.isnan(exits.structural_invalidation(1, 100.0, float("nan"), cfg))


def test_underlying_through_the_invalidation_exits():
    decision = exits.evaluate(**_base_kwargs(
        underlying_price=24000.0, invalidation_price=24050.0))
    assert decision.should_exit
    assert "Structural invalidation" in decision.reason


def test_underlying_above_the_invalidation_holds():
    decision = exits.evaluate(**_base_kwargs(
        underlying_price=24100.0, invalidation_price=24050.0))
    assert not decision.should_exit


def test_absent_invalidation_is_simply_not_checked():
    """After a restart the in-process record is empty. That must degrade to
    "no structural check", not to an error or a spurious exit."""
    decision = exits.evaluate(**_base_kwargs(
        underlying_price=24000.0, invalidation_price=None))
    assert not decision.should_exit


# ---------------------------------------------------------------------
# Structure reversal
# ---------------------------------------------------------------------

def test_structure_reversal_runs_once_per_closed_bar(nifty, monkeypatch):
    cfg = RsiSmcConfig()
    calls = {"n": 0}
    real_build = exits._structure.build

    def counting_build(*args, **kwargs):
        calls["n"] += 1
        return real_build(*args, **kwargs)

    monkeypatch.setattr(exits._structure, "build", counting_build)
    for _ in range(5):
        exits.structure_reversed(nifty, 1, cfg, symbol="NIFTY")
    assert calls["n"] == 1, "the reversal check must not run on every tick"


def test_reversal_failure_does_not_raise(nifty, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("deliberate")

    monkeypatch.setattr(exits, "structure_reversed", boom)
    decision = exits.evaluate(**_base_kwargs(df_underlying=nifty))
    assert not decision.should_exit  # held, not crashed


def test_evaluate_never_raises_on_bad_input():
    for bad in (0.0, -1.0, float("nan")):
        decision = exits.evaluate(**_base_kwargs(entry_premium=bad))
        assert isinstance(decision, exits.ExitDecision)


# ---------------------------------------------------------------------
# main.py structural assertions
# ---------------------------------------------------------------------

def test_branch_is_guarded_on_the_strategy_name():
    source = _main_source()
    assert 'elif strategy_name == RSI_SMC_STRATEGY_NAME and is_opt_pos:' in source, (
        "the M1 exit branch must be reachable only for this strategy")


def test_branch_body_is_wrapped_in_try_except():
    """An exception here is misread as a WebSocket disconnect. It must not
    escape."""
    source = _main_source()
    start = source.index("elif strategy_name == RSI_SMC_STRATEGY_NAME and is_opt_pos:")
    end = source.index("else:\n                    # Dynamically apply Trailing SL settings", start)
    branch = source[start:end]
    assert "try:" in branch
    assert "except Exception as _rsi_smc_exc:" in branch
    assert "logger.error(" in branch
    assert "exit_engine.evaluate_exit(" in branch, (
        "the branch must fall through to SmartExitEngine when it fails")


def test_branch_passes_the_two_price_scales_separately():
    source = _main_source()
    start = source.index("elif strategy_name == RSI_SMC_STRATEGY_NAME and is_opt_pos:")
    branch = source[start:start + 4000]
    assert "current_premium=exit_check_price" in branch
    assert "underlying_price=ltp" in branch
    assert "current_atr" not in branch.split("except Exception")[0], (
        "no ATR may be passed into the premium-scale exit evaluation")


def test_entry_branch_records_the_invalidation_level():
    source = _main_source()
    assert "_RSI_SMC_INVALIDATION[s] = " in source
    assert "invalidation_price=_RSI_SMC_INVALIDATION.get(sym)" in source


def test_main_executes_no_rsi_smc_code_outside_a_name_guard():
    """The isolation guarantee, checked on identifiers rather than text.

    Every executable reference to this strategy in `main.py` must sit either
    at module level (the name-only import and the two bookkeeping dicts) or
    inside an `if`/`elif` whose test names `RSI_SMC_STRATEGY_NAME`. With any
    other strategy selected, none of the guarded lines can run.

    Tokenising rather than scanning lines matters: a log message containing
    the string "RSI_SMC" is not executable code, and an earlier version of
    this test failed on exactly that.
    """
    import ast
    import io
    import tokenize

    source = _main_source()
    tree = ast.parse(source)

    # Line ranges of every branch guarded on this strategy's name.
    guarded: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test_names = {n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)}
        if "RSI_SMC_STRATEGY_NAME" not in test_names:
            continue
        for body in (node.body, node.orelse):
            if body:
                guarded.append((body[0].lineno, max(
                    getattr(stmt, "end_lineno", stmt.lineno) for stmt in body)))
        guarded.append((node.lineno, node.lineno))

    # Module-level declarations are allowed: they define names, they do not
    # act. Anything else must be inside a guard.
    module_level_spans = [
        (node.lineno, getattr(node, "end_lineno", node.lineno))
        for node in tree.body
        if isinstance(node, (ast.ImportFrom, ast.Assign, ast.AnnAssign))
    ]

    markers = ("rsi_smc", "RSI_SMC")
    offenders = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.NAME:
            continue
        if not any(marker in token.string for marker in markers):
            continue
        line = token.start[0]
        if any(start <= line <= end for start, end in guarded):
            continue
        if any(start <= line <= end for start, end in module_level_spans):
            continue
        offenders.append((line, token.string))

    assert not offenders, (
        "main.py executes rsi_smc code outside a strategy-name guard at "
        f"{offenders}"
    )


def test_main_actually_contains_the_guarded_branches():
    """Guards against the previous test passing vacuously."""
    source = _main_source()
    assert source.count("RSI_SMC_STRATEGY_NAME") >= 3, (
        "expected the import plus both the entry-side and exit-side guards")
