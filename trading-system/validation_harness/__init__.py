"""Production Strategy Validation Harness.

Isolated from `backtesting_engine/` (the shared engine used by
grid_search.py, WalkForwardValidator, and /api/backtest, which was
explicitly left untouched — see docs/STRATEGY_AUDIT_2026-08-07.md §2.2).

This harness exists because that shared engine still simulates a
fixed-percentage stop-loss and a fixed profit target — the architecture
that was replaced live on 2026-08-06. Validating any strategy against it
would be validating a stop-loss/exit model that no longer exists in
production.

Design principle: reuse real production components end-to-end rather than
reimplementing risk/exit logic a second time —
`shared/risk/manager.py::RiskManager`, `shared/risk/option_stop_loss.py`,
`shared/exits/exit_engine.py::SmartExitEngine`,
`shared/risk/option_atr.py::resolve_option_atr`,
`trading_bot/strategies/premium_selection/options_selector.py::select_option`,
and `trading_bot/strategies/registry.py::registry` are all imported and
called directly, unmodified. The only genuinely new logic here is what
CAN'T be reused from production because it doesn't exist yet: a synthetic
option-premium series (this repository has no historical option-premium
data — see `premium_simulator.py`) and the backtest event loop that walks
historical bars and calls all of the above in the same order main.py's
live tick loop does.
"""
