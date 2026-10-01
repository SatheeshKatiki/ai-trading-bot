"""SMC_RSI_FRVP_OPTIONS_V1 (``smc1``) -- SMC + RSI + FRVP intraday options buying.

Design of record: ``docs/strategies/smc_rsi_frvp_options_v1/DESIGN.md``.

Phase B status: only the detectors exist (``detectors/``). There is
deliberately NO ``generate_signals`` here yet, so the registry's
auto-discovery imports this package but registers nothing, and no engine can
select it. Phase B2 decides whether a strategy is built on these detectors at
all (DESIGN.md §16).

Everything in this package is additive: no existing module is modified, and
every numeric parameter lives in
``config/strategies/smc_rsi_frvp_options_v1.json`` (see :mod:`.config`).
"""

from __future__ import annotations

STRATEGY_NAME = "smc_rsi_frvp_options_v1"
STRATEGY_ID = "SMC_RSI_FRVP_OPTIONS_V1"

__all__ = ["STRATEGY_NAME", "STRATEGY_ID"]
