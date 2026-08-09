"""Regression tests for the `institutional_momentum` production exit path.

Found 2026-08-09 by the strategy's deep audit. Three defects, one root
cause: main.py routes this strategy — and only this strategy — to
`TieredExitManager` instead of `SmartExitEngine`, and that branch was
never actually executed or validated.

1. **UnboundLocalError on every exit evaluation.** `df` was assigned only
   inside the non-option branch (`else: df = aggregator...`), while the
   momentum branch reads it unconditionally to resample 5-min candles and
   build AI features. Python makes `df` local to the whole of `on_tick`
   the moment it is assigned anywhere in it, so on an option position —
   which is every position this strategy takes — the read hit an unbound
   local. The broad `except Exception` at the end of `on_tick` logged it
   and continued, so the engine looked healthy while TieredExitManager
   was never once consulted. Same scoping class as the 2026-08-02
   `datetime` shadowing bug in this same function.

2. **No EOD square-off.** The 15:15 IST intraday square-off lives inside
   `SmartExitEngine.evaluate_exit`, which this branch never calls.
   `TieredExitManager` has no time rule of its own (its Phase 2 runner is
   deliberately uncapped), so nothing closed the position at session end
   — overnight gap risk and a night of theta on a near-expiry contract.

3. **The engine was fed a candle that had not closed.** `df.resample(...)`
   with `label='right'`/`closed='right'` leaves the still-forming bar
   last. TieredExitManager's Phase 3 rule is "exit when a candle CLOSES on
   the wrong side of the runner EMA" and its own comment says it reads the
   last COMPLETED candle. With ~1 tick/second that silently became "exit
   the moment price TOUCHES the wrong side".

The first and third are asserted structurally against main.py's source:
they are wiring properties of a 1000-line async tick handler that cannot
be driven without a live broker, feed and event loop. The exit SEMANTICS
are covered behaviourally against `validation_harness.harness`'s mirror
of this branch, which is what the 123-day validation actually runs.

See docs/STRATEGY_IMPROVEMENT_BACKLOG.md #13.
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import ast
import pathlib

import pandas as pd
import pytest

from shared.exits.exit_engine import Position
from trading_bot.strategies.momentum_strategy.exit_manager import TieredExitManager
from validation_harness.harness import _evaluate_tiered_exit

MAIN_PY = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT) / "trading_bot" / "main.py"

EOD = "15:15:00"


def _on_tick_ast():
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == "on_tick":
            return node
    raise AssertionError("on_tick not found in main.py")


# ─────────────────────────────────────────────────────────────────────
# Defect 1 — `df` must be bound unconditionally before it is read
# ─────────────────────────────────────────────────────────────────────

def test_df_is_bound_outside_any_conditional_before_first_use():
    """The pre-fix code bound `df` only inside `else:` of `if is_opt_pos:`,
    so the option path reached the momentum branch with it unbound. The
    binding that dominates the first read must not sit inside a branch."""
    on_tick = _on_tick_ast()

    # For each node, the chain of enclosing `if` branches it sits in,
    # outermost first, as (if-node, "body" | "orelse"). A binding dominates
    # a read when its chain is a PREFIX of the read's chain (every branch
    # taken to reach the read also passed through the binding's scope) and
    # it comes lexically first. That is what the pre-fix code violated: the
    # binding lived in the `orelse` of `if is_opt_pos:` while the momentum
    # read lived outside it, so no path through the option side bound `df`.
    chains: dict[int, list] = {}

    def walk(node, chain):
        chains[id(node)] = chain
        if isinstance(node, ast.If):
            for child in node.body:
                walk(child, chain + [(id(node), "body")])
            for child in node.orelse:
                walk(child, chain + [(id(node), "orelse")])
            for child in [node.test]:
                walk(child, chain)
            return
        for child in ast.iter_child_nodes(node):
            walk(child, chain)

    walk(on_tick, [])

    def chain_of(node):
        cur = node
        while id(cur) not in chains:
            cur = getattr(cur, "_parent", None)
            if cur is None:
                return []
        return chains[id(cur)]

    # Attach parents so a Name can find the statement chain it belongs to.
    for parent in ast.walk(on_tick):
        for child in ast.iter_child_nodes(parent):
            child._parent = parent

    stores, loads = [], []
    for node in ast.walk(on_tick):
        if isinstance(node, ast.Name) and node.id == "df":
            (stores if isinstance(node.ctx, ast.Store) else loads).append(node)

    assert stores, "expected at least one `df` assignment in on_tick"
    assert loads, "expected `df` to be read in on_tick"

    # EVERY read must be dominated, not just the first. The defect was
    # precisely a later read (the momentum branch) sitting in a different
    # branch from the only binding.
    undominated = []
    for load in loads:
        load_chain = chain_of(load)
        if not any(
            s.lineno < load.lineno and chain_of(s) == load_chain[: len(chain_of(s))]
            for s in stores
        ):
            undominated.append(load.lineno)

    assert not undominated, (
        f"`df` is read at line(s) {undominated} with no binding that dominates "
        "them — those paths raise UnboundLocalError (the option path did)"
    )


def test_momentum_branch_does_not_receive_the_forming_candle():
    """main.py must drop the still-forming resampled bar before handing
    df_5min to TieredExitManager, so `iloc[-1]` inside the engine means the
    last COMPLETED candle, as that engine's own comment states."""
    src = MAIN_PY.read_text(encoding="utf-8")
    idx = src.index("df_5min = df.resample(")
    window = src[idx:idx + 900]
    assert "df_5min.iloc[:-1]" in window, (
        "the forming 5-min bar is still being passed to TieredExitManager — "
        "Phase 3's close-confirmation rule degrades to an intrabar trigger"
    )
    call = src.index("m_strategy.manage_active_trades")
    assert src.index("df_5min.iloc[:-1]") < call, (
        "the incomplete bar must be dropped BEFORE the engine is called"
    )


def test_momentum_branch_squares_off_at_eod():
    """This branch bypasses SmartExitEngine, so it must apply the EOD
    square-off itself — and reuse the same cutoff, not redeclare one."""
    src = MAIN_PY.read_text(encoding="utf-8")
    start = src.index('if strategy_name == "institutional_momentum"')
    branch = src[start:src.index("m_strategy.manage_active_trades", start)]
    assert "exit_engine.eod_exit_time" in branch, (
        "momentum branch has no EOD square-off, or declares its own cutoff"
    )
    assert "Time-based EOD Exit" in branch


# ─────────────────────────────────────────────────────────────────────
# Exit semantics — behavioural, against the harness mirror
# ─────────────────────────────────────────────────────────────────────

def _pos(entry=200.0, sl=170.0, qty=150, lot=75, target=0.0):
    return Position(
        symbol="NSE:NIFTY2680724000CE", side=1, entry_price=entry, quantity=qty,
        entry_time="2026-03-02T09:20:00", highest_price=entry, lowest_price=entry,
        stop_loss=sl, target=target, lot_size=lot,
    )


def _bars(n=60, start=24_000.0, step=5.0):
    idx = pd.date_range("2026-03-02 09:15", periods=n, freq="5min")
    close = [start + step * i for i in range(n)]
    return pd.DataFrame(
        {"open": close, "high": [c + 3 for c in close],
         "low": [c - 3 for c in close], "close": close, "volume": [1e5] * n},
        index=idx,
    )


def _armed_tiered(pos):
    t = TieredExitManager()
    t.open_position(pos.entry_price, pos.stop_loss, pos.quantity, 1)
    return t


def test_eod_square_off_fires_even_when_the_engine_wants_to_hold():
    """The defect: a position with no stop hit and a happy runner simply
    never closed. At the cutoff it must close regardless."""
    pos = _pos()
    tiered = _armed_tiered(pos)
    bars = _bars()

    hold, _, _ = _evaluate_tiered_exit(tiered, pos, 205.0, bars, "14:00:00", 10.0, EOD)
    assert hold is False, "should still be holding before the cutoff"

    should_exit, reason, qty = _evaluate_tiered_exit(
        tiered, pos, 205.0, bars, "15:15:00", 10.0, EOD
    )
    assert should_exit is True
    assert reason == "Time-based EOD Exit"
    assert qty is None, "EOD closes the whole position"


def test_hard_stop_loss_takes_precedence_over_the_engine():
    """main.py runs the hard-SL interceptor before consulting the strategy
    engine; the mirror must keep that order or the modelled exit price is
    wrong."""
    pos = _pos()
    tiered = _armed_tiered(pos)
    should_exit, reason, qty = _evaluate_tiered_exit(
        tiered, pos, 169.0, _bars(), "11:00:00", 10.0, EOD
    )
    assert should_exit is True
    assert reason.startswith("Hard SL Hit")
    assert qty is None


def test_inert_zero_target_never_triggers():
    """Option entries are written `target=0.0` ("no fixed target"). A
    missing `> 0` guard would exit instantly on every position."""
    pos = _pos(target=0.0)
    tiered = _armed_tiered(pos)
    should_exit, _, _ = _evaluate_tiered_exit(
        tiered, pos, 201.0, _bars(), "10:00:00", 500.0, EOD
    )
    assert should_exit is False


def test_partial_book_exits_whole_lots_only():
    """A partial book must round to whole lots and never exceed the
    position — an option lot is indivisible."""
    pos = _pos(qty=150, lot=75)
    tiered = _armed_tiered(pos)
    # Force Phase 1 to trigger on the next evaluation.
    tiered.partial_rr = 0.1
    should_exit, reason, qty = _evaluate_tiered_exit(
        tiered, pos, 235.0, _bars(), "10:00:00", 1e9, EOD
    )
    assert should_exit is True
    assert "Phase 1" in reason
    assert qty is not None
    assert qty % pos.lot_size == 0, "partial book must be whole lots"
    assert 0 < qty <= pos.quantity


def test_engine_state_is_required_before_it_can_exit():
    """`TieredExitManager` returns no decision until `open_position` arms
    it. If the harness (or main.py) ever stops arming it, exits silently
    stop — the failure this whole cycle is about."""
    pos = _pos()
    unarmed = TieredExitManager()
    should_exit, _, _ = _evaluate_tiered_exit(
        unarmed, pos, 400.0, _bars(), "10:00:00", 1.0, EOD
    )
    assert should_exit is False
    assert unarmed.has_position is False


# ─────────────────────────────────────────────────────────────────────
# Harness fidelity — the right engine for the right strategy
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "strategy_name, expects_tiered",
    [("institutional_momentum", True), ("ema_rsi", False), ("buy_the_dip", False)],
)
def test_harness_routes_only_momentum_to_the_tiered_engine(strategy_name, expects_tiered):
    """Production sends exactly one strategy down the TieredExitManager
    branch. The harness must mirror that, or it validates an engine
    production does not run."""
    import inspect

    from validation_harness import harness

    src = inspect.getsource(harness.run_strategy_backtest)
    assert 'strategy_name == "institutional_momentum"' in src
    assert "TieredExitManager() if" in src

    # And main.py gates on the same single name.
    main_src = MAIN_PY.read_text(encoding="utf-8")
    gated = f'strategy_name == "{strategy_name}" and sym in momentum_strategies' in main_src
    assert gated is expects_tiered
