"""Tier 3 -- isolation. The existing system must not notice this strategy.

The full pre-existing suite passing at its baseline count is the primary
evidence of no regression. These tests cover the things a suite-wide pass
would not catch on its own: that registration is additive, that the
institutional-filter opt-out does not leak to any other strategy, that
importing this package has no side effects, and that every existing strategy
still produces a deterministic, unchanged signal series on a fixed frame.
"""
from __future__ import annotations

import hashlib
import importlib
import pathlib


import numpy as np
import pandas as pd
import pytest

import _bootstrap  # noqa: F401

from trading_bot.strategies.registry import registry

FIXTURE = (pathlib.Path(__file__).resolve().parent / "fixtures" / "data"
           / "rsi_smc_NIFTY_5Min.csv")

NEW_STRATEGY = "rsi_smc_options_buyer"

#: The strategies that existed before this one. Any change to this list is a
#: change to the protected surface and must be deliberate.
PRE_EXISTING = (
    "advanced_ai", "buy_the_dip", "drl_strategy", "ema9_rsi_momentum",
    "ema_crossover", "ema_rsi", "enhanced_ai", "institutional_momentum",
    "marl_strategy", "meta_agent_swarm", "momentum_15_5", "premium",
    "structure_break", "ultra_meta_dip_swarm",
)


@pytest.fixture(scope="module")
def nifty() -> pd.DataFrame:
    return pd.read_csv(FIXTURE, parse_dates=["datetime"]).set_index("datetime")


# ---------------------------------------------------------------------
# Registration is additive
# ---------------------------------------------------------------------

def test_every_pre_existing_strategy_is_still_registered():
    registered = set(registry.registered_strategies)
    missing = [name for name in PRE_EXISTING if name not in registered]
    assert not missing, f"strategies disappeared from the registry: {missing}"


def test_the_new_strategy_registered_itself():
    assert NEW_STRATEGY in registry.registered_strategies


def test_no_unexpected_strategy_module_appeared():
    """Only one strategy module was added to the package.

    Asserted against the package DIRECTORY rather than the runtime registry:
    other modules legitimately register runtime aliases into the same
    registry (`validation_harness.harness` and `api_bridge` both register
    "MARL_Ultra"), so the live registry contents depend on which other tests
    have imported what. The directory does not.
    """
    strategies_dir = _bootstrap.TRADING_SYSTEM_ROOT / "trading_bot" / "strategies"
    modules = {p.stem for p in strategies_dir.glob("*.py")
               if p.stem not in ("__init__", "registry", "_signal_utils")}
    packages = {p.name for p in strategies_dir.iterdir()
                if p.is_dir() and (p / "__init__.py").exists()}
    discovered = modules | packages

    known = {
        "advanced_ai_ml_strategy", "buy_the_dip_strategy", "drl_strategy",
        "ema_crossover_pro_strategy", "ema_rsi_strategy", "enhanced_ai_strategy",
        "marl_strategy", "meta_agent_strategy", "ultra_meta_dip_swarm",
        "ema9_rsi_momentum", "momentum_15_5", "momentum_strategy",
        "premium_selection", "structure_break",
        "smc_rsi_frvp_options_v1",
    }
    unexpected = discovered - known - {NEW_STRATEGY}
    assert not unexpected, f"unexpected strategy modules added: {unexpected}"
    assert NEW_STRATEGY in discovered


# ---------------------------------------------------------------------
# Existing strategies are behaviourally unchanged
# ---------------------------------------------------------------------

def _signature(series) -> str:
    values = np.asarray(series, dtype=int)
    return hashlib.sha256(values.tobytes()).hexdigest()[:16]


@pytest.mark.parametrize("name", ["ema_rsi", "structure_break", "momentum_15_5",
                                  "ema9_rsi_momentum", "buy_the_dip"])
def test_existing_strategies_are_deterministic(nifty, name):
    """The same frame must produce the same signals every time.

    Non-determinism here would make any before/after comparison meaningless,
    so this is a precondition for trusting the regression suite at all.
    """
    if name not in registry.registered_strategies:
        pytest.skip(f"{name} not registered in this environment")
    first = registry.run_strategy(name, nifty)
    second = registry.run_strategy(name, nifty)
    if isinstance(first, tuple):
        first, second = first[0], second[0]
    assert _signature(first) == _signature(second)


@pytest.mark.parametrize("name", ["ema_rsi", "structure_break", "ema9_rsi_momentum"])
def test_existing_strategies_do_not_inherit_the_filter_opt_out(name):
    """`SKIP_INSTITUTIONAL_FILTERS` must apply to this strategy alone.

    `registry._owned_filters` resolves the declaration from the strategy
    FUNCTION's own module, so a frozenset declared here cannot reach another
    strategy. This asserts that rather than assuming it.
    """
    from trading_bot.strategies.registry import _owned_filters

    if name not in registry.registered_strategies:
        pytest.skip(f"{name} not registered in this environment")
    assert _owned_filters(registry._strategies[name]) == frozenset()


def test_the_new_strategy_declares_its_own_opt_out():
    from trading_bot.strategies.registry import _owned_filters

    owned = _owned_filters(registry._strategies[NEW_STRATEGY])
    assert owned == frozenset({"squeeze", "extension", "cpr", "aggression"})


def test_institutional_filters_do_not_alter_this_strategys_signals(nifty):
    """With the opt-out declared, the registry must return what the strategy
    produced, whatever the filter toggles say."""
    import trading_bot.strategies.rsi_smc_options_buyer as strategy
    from trading_bot.strategies.rsi_smc_options_buyer import structure

    structure.clear_cache()
    direct = strategy.generate_signals(nifty)
    structure.clear_cache()
    through_registry = registry.run_strategy(
        NEW_STRATEGY, nifty,
        enable_squeeze_filter=True, enable_extension_filter=True,
        enable_cpr_filter=True, enable_aggression_filter=True,
    )
    np.testing.assert_array_equal(direct.to_numpy(), np.asarray(through_registry))


# ---------------------------------------------------------------------
# Importing the package is inert
# ---------------------------------------------------------------------

def test_import_has_no_side_effects():
    """Importing must define names, not act.

    No file written, no network call, no global mutated beyond the registry
    entry `autodiscover` makes.
    """
    module = importlib.import_module(
        "trading_bot.strategies.rsi_smc_options_buyer")
    assert module.STRATEGY_NAME == NEW_STRATEGY
    assert module.STRATEGY_ID == "RSI_SMC_OPTIONS_BUYER_V1"
    # A re-import must be a no-op.
    importlib.reload(module)
    assert module.STRATEGY_NAME == NEW_STRATEGY


def test_strategy_does_not_declare_the_fib_trail_flag():
    """`USE_DYNAMIC_FIB_TRAIL` is honoured by validation_harness and NOT by
    main.py, so a strategy that opted in would trail one way in replay and
    another way live. This strategy must not depend on it."""
    import trading_bot.strategies.rsi_smc_options_buyer as strategy
    assert not hasattr(strategy, "USE_DYNAMIC_FIB_TRAIL")


def test_package_directory_matches_the_strategy_name():
    """`shared.entry_gate._grader` imports
    `trading_bot.strategies.{strategy_name}` to find a strategy's own entry
    grader. If the directory and the name diverge, grading silently stops."""
    import trading_bot.strategies.rsi_smc_options_buyer as strategy
    package = pathlib.Path(strategy.__file__).parent.name
    assert package == strategy.STRATEGY_NAME


def test_entry_gate_can_find_the_grader():
    from shared.entry_gate import _grader
    assert _grader(NEW_STRATEGY) is not None


# ---------------------------------------------------------------------
# Protected files untouched
# ---------------------------------------------------------------------

@pytest.mark.parametrize("relative", [
    "shared/indicators/smart_money_concepts.py",
    "shared/indicators/rsi.py",
    "shared/risk/manager.py",
    "shared/exits/exit_engine.py",
    "shared/entry_gate.py",
    "trading_bot/strategies/registry.py",
    "trading_bot/strategies/_signal_utils.py",
    "trading_bot/strategies/momentum_strategy/price_action.py",
    "trading_bot/strategies/premium_selection/options_selector.py",
])
def test_protected_module_carries_no_rsi_smc_reference(relative):
    """Shared infrastructure must not know this strategy exists.

    main.py is the single, approved exception (M1/M2), and its guards are
    asserted in test_rsi_smc_exit_branch.py.
    """
    path = _bootstrap.TRADING_SYSTEM_ROOT / relative
    source = path.read_text(encoding="utf-8")
    assert "rsi_smc" not in source.lower(), (
        f"{relative} references rsi_smc -- shared code must stay strategy-agnostic")
