"""Which strike an ema9_rsi_momentum signal buys: ATM, or ITM by real delta.

ATM is the default and is what every entry has used so far. ITM is opt-in via
``Ema9RsiMomentumConfig.strike_selection``.

Why ITM is worth testing (measured 2026-09-11, 578 NIFTY sessions, owner's
exits, costs included): an ITM strike beat ATM at every timeframe tested and
on both NIFTY and SENSEX -- on the 5-minute chart it cut the loss per trade
from -3.20% to -1.47% of premium. The mechanism is structural, not fitted:
theta and the bid/ask spread are a smaller fraction of an ITM premium, and
the higher delta converts more of each spot move into premium. It does not
create an edge by itself; it stops a thin one being eaten by carry.

ITM is chosen by the chain's REAL delta (solved from traded premiums by
``api_bridge``), never by a fixed strike offset: 150 points ITM is delta 0.72
on an expiry-day NIFTY chain and far less a week out. If no in-the-money leg
carries a usable delta, nothing is selected -- the caller skips the trade
rather than guess.
"""

from __future__ import annotations

from typing import Iterable, Optional

ATM = "ATM"
ITM = "ITM"
MODES = (ATM, ITM)


def _f(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


def _tradeable_leg(row: dict, leg_key: str, max_spread_pct: float) -> Optional[dict]:
    """The leg as a normalised dict if it has a real two-sided quote within
    the spread cap, else None."""
    leg = row.get(leg_key) or {}
    ltp, bid, ask = _f(leg.get("ltp")), _f(leg.get("bid")), _f(leg.get("ask"))
    if not ltp or not bid or not ask or ltp <= 0 or bid <= 0 or ask < bid:
        return None
    spread_pct = _f(leg.get("spread_pct"))
    if spread_pct is None:
        spread_pct = (ask - bid) / ask * 100.0
    if spread_pct > max_spread_pct:
        return None
    return {
        "strike": _f(row.get("strike")),
        "ltp": ltp,
        "bid": bid,
        "ask": ask,
        "spread_pct": round(spread_pct, 3),
        "delta": _f(leg.get("delta")),
        "theta": _f(leg.get("theta")),
        "iv": _f(leg.get("iv")),
    }


def select_strike(
    chain_rows: Iterable[dict],
    spot: float,
    side: int,
    mode: str = ATM,
    target_delta: float = 0.70,
    max_spread_pct: float = 1.0,
) -> Optional[dict]:
    """Pick the contract to buy for a CE (``side=1``) or PE (``side=-1``) signal.

    ``chain_rows`` is ``/api/option-chain``'s ``chain``: rows of
    ``{"strike", "ce": {...}, "pe": {...}}``.

    * ``ATM`` -- the strike nearest spot, if that leg is tradeable.
    * ``ITM`` -- among strikes in the money for this side (below spot for a
      CE, above it for a PE), the tradeable leg whose ``|delta|`` is nearest
      ``target_delta``; ties go to the strike nearer spot (more liquid).

    Returns the leg with ``strike``/``opt_type``/``ltp``/``bid``/``ask``/
    ``spread_pct``/``delta``/``theta``/``iv``/``mode``, or None.
    """
    if side not in (1, -1):
        raise ValueError(f"side must be 1 (CE) or -1 (PE), got {side!r}")
    mode = str(mode).upper()
    if mode not in MODES:
        raise ValueError(f"strike selection mode must be one of {MODES}, got {mode!r}")
    spot = _f(spot)
    if not spot or spot <= 0:
        return None

    leg_key, opt_type = ("ce", "CE") if side == 1 else ("pe", "PE")
    rows = [r for r in (chain_rows or ()) if _f(r.get("strike"))]
    if not rows:
        return None

    if mode == ATM:
        nearest = min(rows, key=lambda r: abs(_f(r["strike"]) - spot))
        leg = _tradeable_leg(nearest, leg_key, max_spread_pct)
    else:
        candidates = []
        for row in rows:
            strike = _f(row["strike"])
            in_the_money = strike < spot if side == 1 else strike > spot
            if not in_the_money:
                continue
            leg = _tradeable_leg(row, leg_key, max_spread_pct)
            if leg is None or leg["delta"] is None or not 0.0 < abs(leg["delta"]) < 1.0:
                continue
            candidates.append(leg)
        if not candidates:
            return None
        leg = min(candidates, key=lambda c: (abs(abs(c["delta"]) - target_delta),
                                             abs(c["strike"] - spot)))

    if leg is None:
        return None
    leg["opt_type"] = opt_type
    leg["mode"] = mode
    return leg
