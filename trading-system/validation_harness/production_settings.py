"""The settings the live bot actually runs with, for the validation harness.

Why this exists (measured 2026-08-08, `ema_rsi`, 123-day window)
---------------------------------------------------------------
`registry.run_strategy()` applies the four institutional filters to every
strategy's signals, gated on `enable_*_filter` keys. `config/settings.json`
has **all four enabled**. The harness called it with `settings={}`, so all
four were **off** in every number the validation report has ever produced.
Separately, `main.py` copies `max_trades_per_day` from the same file into
`risk_manager.config.max_trades_per_day` on the live entry path; the
harness built `RiskManager` without a config, leaving the cap at its
default of 0 (unlimited).

The gap is not cosmetic. Measured on `ema_rsi` over the same window, same
code, changing only these settings:

    filters OFF, no cap (what was validated)  522 legs  Rs 211,316  DD 19.01%
    production filters + cap (what runs)      194 legs  Rs  81,922  DD 15.24%

Same strategy, 61% less profit, 20% less drawdown, and a different verdict
input. A validation harness that measures a different entry path than
production is not measuring production.

What this does and does not model
---------------------------------
Passing the whole settings file could change more than the entry path, so
the overlap was checked rather than assumed. Of the 39 keys in
`config/settings.json`, the harness's code path reads only these:

* `enable_squeeze_filter`, `enable_extension_filter`, `enable_cpr_filter`,
  `enable_aggression_filter` — the entry filters. **These differ** from
  the harness's previous behaviour; they are the point of this module.
* `option_sl_bands`, `option_sl_band_mode`, `option_sl_dynamic`,
  `option_sl_max_pct_of_premium`, `option_sl_tick_size`,
  `option_risk_based_sizing`, `option_strike_itm_offset` — verified to
  produce **bit-identical** stops and sizing to the harness's own module
  defaults across the whole premium range (5 to 600). Passing them
  changes nothing; they are included so that a future edit to
  `settings.json` is picked up instead of silently diverging again.
* `max_trades_per_day` — honoured by `harness.run_strategy_backtest`,
  mirroring `main.py`'s own key precedence.

Everything else in the file (broker selection, emergency stop, pyramiding,
symbols, timeframe, the retired `stoploss_pct`/`target_pct` pair) is
either irrelevant to a backtest or belongs to a subsystem the harness
documents as out of scope. Notably still NOT modelled, unchanged by this
module: pyramid scale-in, and the AI-confidence filter (see
`harness.py`'s docstring).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

__all__ = ["SETTINGS_PATH", "load_production_settings", "resolve_max_trades_per_day"]

#: Same file `trading_bot/main.py` loads (`main.py`'s `_SETTINGS_PATH`).
SETTINGS_PATH = Path(__file__).resolve().parents[1] / "config" / "settings.json"


def load_production_settings(path: Optional[Path] = None) -> dict[str, Any]:
    """Return the live settings dict, or `{}` if the file is unreadable.

    Never raises: a missing or malformed settings file must degrade to the
    harness's own defaults rather than abort a validation run — but the
    caller is expected to report which path was used, so an empty return
    is visible rather than silent.
    """
    p = Path(path) if path else SETTINGS_PATH
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def resolve_max_trades_per_day(settings: dict) -> int:
    """Resolve the daily trade cap using `main.py`'s exact key precedence
    (`max_trades_per_day`, then `maxDailyTrades`, then `max_daily_trades`).

    Duplicating the precedence rather than reading one key is deliberate:
    `config/settings.json` currently carries BOTH `max_trades_per_day` and
    `max_daily_trades`, so picking the wrong one silently models a
    different cap than production enforces. 0 means unlimited, matching
    `RiskConfig`'s own default.
    """
    for key in ("max_trades_per_day", "maxDailyTrades", "max_daily_trades"):
        if settings.get(key) is not None:
            try:
                return int(settings[key])
            except (TypeError, ValueError):
                return 0
    return 0
