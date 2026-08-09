"""Opt-in execution realism for the validation harness.

Everything here is **off by default**. `run_strategy_backtest(realism=None)`
— the default — takes exactly the code path it always took, so every
result this project has published reproduces byte-for-byte. Nothing in
`trading_bot/` imports this module.

Three independent corrections, each measured in the 2026-08-10 audit:

1. **Friction** (`FrictionModel`). `_close_position` computed
   `pnl = (exit - entry) * qty` and nothing else: no spread, no
   brokerage, no statutory charges, no slippage. Meanwhile the live path
   deliberately crosses the spread with marketable limit orders
   (`premium * 1.05` in, `* 0.95` out). Estimated round trip for one
   NIFTY lot at ~Rs 160 premium is **Rs 125-260**, against a measured
   gross expectancy of **Rs 305/position** for the new strategy — i.e.
   friction is the same order of magnitude as the edge being measured.

2. **Intraday theta** (`fractional_dte`). The harness computed
   `days_to_expiry` as an INTEGER per bar date, so it was constant for a
   whole session and stepped down only overnight. Every position here is
   intraday, so **time decay was never charged during the holding
   period**. Measured cost of that omission on a 45-minute hold, spot
   unchanged: 18.8% of the entire banded stop at 0 DTE, 6.8% at 1 DTE,
   ~2% at 4-6 DTE.

3. **Simulated clock** (`simulated_clock`). `select_option`'s Greeks
   Guard read `datetime.now()` — the machine clock — so in a backtest of
   2025-06-10 it computed a days-to-expiry of **-426** instead of 0 and
   never fired. Enabling this passes the simulated bar timestamp instead.

Why 3 is opt-in rather than simply fixed
----------------------------------------
Correcting the clock unconditionally would change every historical
backtest that ever selected a contract on an expiry day after 14:00 —
the guard would start firing and shifting those trades two strikes
deeper ITM. That silently rewrites published results, which the
infrastructure brief explicitly forbids. So the correctness fix lives
behind the same flag as the rest of the realism modelling: default off
and bit-identical, on when you have asked for a realistic run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Optional

import pandas as pd

__all__ = [
    "FrictionModel",
    "NIFTY_RETAIL",
    "RealismConfig",
    "REALISTIC",
    "fractional_dte",
    "SESSION_CLOSE",
]

#: Indian index options settle at the close; time value is measured to
#: this moment, not to midnight.
SESSION_CLOSE = time(15, 30)


@dataclass(frozen=True)
class FrictionModel:
    """Execution friction and statutory charges for Indian index options.

    All rates are configurable because they are broker- and
    regime-dependent; the defaults are zero so an unconfigured instance
    is a no-op. `NIFTY_RETAIL` below carries the researched values and
    states its assumptions.

    Sign convention: this system only ever BUYS premium. The buy fills
    above the observed mid and the sell fills below it.
    """

    #: Half-spread as a fraction of premium, applied on each side.
    half_spread_pct: float = 0.0
    #: Absolute floor on the half-spread, in rupees (the tick).
    min_half_spread: float = 0.0
    #: Extra adverse fill beyond the spread, as a fraction of premium.
    slippage_pct: float = 0.0
    #: Flat brokerage per order; charged on both entry and exit.
    brokerage_per_order: float = 0.0
    #: Securities Transaction Tax, on SELL-side premium turnover.
    stt_sell_pct: float = 0.0
    #: Exchange transaction charge, on premium turnover, both sides.
    exchange_txn_pct: float = 0.0
    #: SEBI turnover fee, on premium turnover, both sides.
    sebi_pct: float = 0.0
    #: Stamp duty, on BUY-side premium turnover.
    stamp_duty_buy_pct: float = 0.0
    #: GST on (brokerage + exchange + SEBI).
    gst_pct: float = 0.0

    @property
    def is_active(self) -> bool:
        return any((
            self.half_spread_pct, self.min_half_spread, self.slippage_pct,
            self.brokerage_per_order, self.stt_sell_pct, self.exchange_txn_pct,
            self.sebi_pct, self.stamp_duty_buy_pct,
        ))

    def _half_spread(self, premium: float) -> float:
        return max(premium * self.half_spread_pct, self.min_half_spread)

    def buy_fill(self, mid: float) -> float:
        """Price actually paid when buying at an observed mid."""
        return mid + self._half_spread(mid) + mid * self.slippage_pct

    def sell_fill(self, mid: float) -> float:
        """Price actually received when selling at an observed mid.

        Floored at zero: a premium cannot be negative, and a wide
        proportional spread on a near-worthless option must not turn into
        a phantom credit.
        """
        return max(0.0, mid - self._half_spread(mid) - mid * self.slippage_pct)

    def charges(self, buy_price: float, sell_price: float, quantity: int) -> float:
        """Statutory + brokerage charges for one round trip, in rupees.

        Spread and slippage are NOT included here — they are already
        expressed in the fill prices, and double-counting them would
        overstate friction.
        """
        buy_turnover = buy_price * quantity
        sell_turnover = sell_price * quantity
        turnover = buy_turnover + sell_turnover

        brokerage = self.brokerage_per_order * 2
        exchange = turnover * self.exchange_txn_pct
        sebi = turnover * self.sebi_pct
        stt = sell_turnover * self.stt_sell_pct
        stamp = buy_turnover * self.stamp_duty_buy_pct
        gst = (brokerage + exchange + sebi) * self.gst_pct
        return brokerage + exchange + sebi + stt + stamp + gst


#: Researched retail preset for NIFTY weekly options, 2026 rate card.
#:
#: ASSUMPTIONS — stated so they can be argued with:
#:   * half-spread 0.25% of premium, floored at one Rs 0.05 tick. On a
#:     Rs 160 ATM weekly that is Rs 0.40 a side, Rs 0.80 round trip per
#:     unit. Liquid ATM/ITM strikes only; far OTM and the last hour of
#:     expiry day are materially worse and are NOT modelled.
#:   * brokerage Rs 20 per order (discount-broker flat rate).
#:   * STT 0.0625% on sell-side premium turnover.
#:   * exchange transaction charge 0.0495% of premium turnover.
#:   * SEBI turnover fee 0.0001%.
#:   * stamp duty 0.003% on the buy side.
#:   * GST 18% on brokerage + exchange + SEBI.
#: `slippage_pct` is left at zero: the marketable-limit crossing this
#: system uses is already represented by the half-spread, and stacking a
#: second adverse term on top would double-count it. Raise it explicitly
#: to stress-test fills.
NIFTY_RETAIL = FrictionModel(
    half_spread_pct=0.0025,
    min_half_spread=0.05,
    slippage_pct=0.0,
    brokerage_per_order=20.0,
    stt_sell_pct=0.000625,
    exchange_txn_pct=0.000495,
    sebi_pct=0.000001,
    stamp_duty_buy_pct=0.00003,
    gst_pct=0.18,
)


def fractional_dte(expiry: date, ts, session_close: time = SESSION_CLOSE) -> float:
    """Days to expiry as a CONTINUOUS quantity, measured to the expiry
    session's close.

    The integer form the harness uses by default is constant across a
    session, so an intraday position is priced as if no time passed. This
    measures the real remaining life, so a 0 DTE contract held from 09:45
    to 10:30 genuinely loses time value.

    Calendar time, not trading time: Black-Scholes theta is quoted in
    calendar days, and `calculate_option_price` is a calendar-time model.
    A trading-time convention would decay faster over weekends and is a
    defensible alternative, but mixing conventions inside one pricing
    call is not.

    Never negative — an expired contract is handled by the caller's own
    expiry branch, not by feeding a negative life into the pricer.
    """
    ts = pd.Timestamp(ts)
    expiry_moment = datetime.combine(expiry, session_close)
    remaining = (expiry_moment - ts.to_pydatetime()).total_seconds() / 86_400.0
    return max(remaining, 0.0)


@dataclass(frozen=True)
class RealismConfig:
    """What the harness should model beyond the default. All off by
    default, so `RealismConfig()` is itself a no-op and `None` means the
    legacy path is taken without even consulting this object."""

    #: Spread, slippage, brokerage and statutory charges.
    friction: Optional[FrictionModel] = None
    #: Price options on continuous time-to-expiry within the session.
    intraday_theta: bool = False
    #: Give `select_option` the simulated bar timestamp so its Greeks
    #: Guard evaluates the simulated session rather than the wall clock.
    simulated_clock: bool = False

    @property
    def is_active(self) -> bool:
        return bool(
            (self.friction is not None and self.friction.is_active)
            or self.intraday_theta
            or self.simulated_clock
        )


#: The full realistic configuration, for convenience in research runners.
REALISTIC = RealismConfig(
    friction=NIFTY_RETAIL,
    intraday_theta=True,
    simulated_clock=True,
)
