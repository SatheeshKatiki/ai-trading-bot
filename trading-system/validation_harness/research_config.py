"""Experimental configuration for the clean-sheet strategy programme.

Kept deliberately separate from `production_settings.py`. That module
loads `config/settings.json` — what the live engine actually runs. This
one holds research-only choices that must NEVER leak into production
configuration, and it is imported only by research runners, never by
`trading_bot/`.

Two things live here:

* the **development / out-of-sample split**, and
* the **1% base risk tier** used to evaluate a new strategy.

The split
---------
`data/NSE_NIFTY50-INDEX_5Min.csv` begins on 2025-05-16, not 2026-02-01.
Every result this project has ever published used only the tail of it —
the 123 trading days from 2026-02-01. That leaves **178 trading days**
(2025-05-16 to 2026-01-31) that no strategy, parameter or filter in this
repository has ever been measured against.

That is a genuine out-of-sample set, and the two halves are not alike:
the development period drifts **+1.25%** while the held-out window drifts
**-3.62%** (with a -9.94% March). A strategy fitted to one has no reason
to survive the other, which is exactly the property that makes the split
worth enforcing.

Rule: develop, measure and decide on `DEV_*`. Touch `OOS_*` **once**, at
the end, to find out whether the thing works. Any parameter chosen after
looking at OOS results has burned the split, and there is no way to
un-burn it.

The risk tier
-------------
Live sizing currently lands on the 3.5% high-confidence tier, because
`enable_ai_filter` is unset -> `confidence` is pinned to 1.0 ->
`high_confidence_threshold` (0.85) is cleared on every trade. That is a
leverage setting: it scales returns and drawdown together without
improving risk-adjusted performance, and changing it in
`config/settings.json` would alter the live system.

`BASE_RISK_TIER` instead evaluates a new strategy at the 1% base tier by
pinning both tiers to 1%, so the confidence override cannot fire. Nothing
in production is touched; the harness takes this as an explicit argument.
"""
from __future__ import annotations

from dataclasses import replace

from shared.risk import RiskConfig

__all__ = [
    "DEV_START", "DEV_END", "OOS_START", "OOS_END",
    "BASE_RISK_TIER", "load_window",
]

#: Development set — 178 trading days never used by any prior result.
DEV_START = "2025-05-16"
DEV_END = "2026-01-31"

#: Held-out set — the established 123-day validation window. Do not tune
#: against this. Do not look at it until the development cycle is closed.
OOS_START = "2026-02-01"
OOS_END = "2026-07-31"

#: 1% base risk tier. Both tiers are pinned to the same value so the
#: `ai_confidence >= high_confidence_threshold` override in
#: `RiskManager.calculate_position_size` / `can_trade` cannot silently
#: promote a trade to 3.5% — the harness passes confidence 1.0, which
#: clears that threshold on every single call.
BASE_RISK_TIER = replace(
    RiskConfig(),
    risk_per_trade=0.01,
    high_confidence_risk_per_trade=0.01,
)


def load_window(which: str, data_path: str = "data/NSE_NIFTY50-INDEX_5Min.csv"):
    """Load `"dev"` or `"oos"` as a DatetimeIndex-ed OHLCV frame.

    Named rather than parameterised by dates on purpose: a runner that
    has to spell out a date range is a runner that can quietly be pointed
    at the wrong one.
    """
    import pandas as pd

    if which not in ("dev", "oos"):
        raise ValueError(f"window must be 'dev' or 'oos', got {which!r}")
    start, end = (DEV_START, DEV_END) if which == "dev" else (OOS_START, OOS_END)

    df = pd.read_csv(data_path)
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df.set_index("datetime").sort_index().loc[start:end]
