"""Synthesizes a plausible option-premium series from historical
underlying (index) OHLCV bars.

Root cause this exists for: this repository has no historical option
*premium* data — only index OHLCV (`data/*.csv`). The shared backtest
engine (`backtesting_engine/run.py`) works around this with a flat
`options_delta=0.5` constant applied to underlying point-moves — a crude
approximation that ignores strike, moneyness, and time decay entirely
(its own docstring admits this). This module instead reprices the actual
selected contract via Black-Scholes on every historical bar
(`options_selector.py::calculate_option_price`, added alongside the
already-live `calculate_greeks` rather than duplicating its math),
correctly capturing delta changing with moneyness and theta decay as
expiry approaches — a materially more realistic premium series for the
SAME contract `select_option()` actually picked.

Still an approximation, not real market data: real premiums also move on
implied-volatility changes (vol smile/skew, IV crush after events) that
this flat-vol model doesn't capture. Documented as a known limitation
everywhere this module's output is used, not hidden.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

import pandas as pd

from trading_bot.strategies.premium_selection.options_selector import (
    OptionContract,
    calculate_option_price,
)

__all__ = ["DEFAULT_IV", "simulate_premium_series"]

#: Flat implied-volatility assumption, matching calculate_greeks()'s own
#: default (0.15) so the simulated premium is consistent with the Greeks
#: already computed live at selection time for the same contract.
DEFAULT_IV = 0.15


@dataclass(frozen=True)
class PremiumBar:
    """One bar of the synthesized premium series, aligned to the
    underlying bar that produced it."""
    timestamp: pd.Timestamp
    spot: float
    premium: float
    days_to_expiry: float


def simulate_premium_series(
    contract: OptionContract,
    underlying_bars: pd.DataFrame,
    vol: float = DEFAULT_IV,
) -> list[PremiumBar]:
    """Reprice `contract` via Black-Scholes across every bar in
    `underlying_bars` from entry to expiry (or the end of the provided
    data, whichever comes first).

    Parameters
    ----------
    contract
        The option contract selected by the real `select_option()`.
    underlying_bars
        The underlying's own OHLC candles from entry onward (must have a
        DatetimeIndex and a `close` column — only close is used, matching
        how main.py's own exit-check loop treats a single LTP per
        evaluation rather than a full OHLC range for the option itself).
    vol
        Flat implied-volatility assumption for every bar (see module
        docstring for why this is a known simplification).
    """
    out: list[PremiumBar] = []
    expiry: date = contract.expiry

    for ts, row in underlying_bars.iterrows():
        bar_date = ts.date() if hasattr(ts, "date") else ts
        days_to_expiry = (expiry - bar_date).days
        if days_to_expiry < 0:
            break  # contract has expired; caller should have exited by now

        spot = float(row["close"])
        premium = calculate_option_price(
            spot=spot,
            strike=float(contract.strike),
            days_to_expiry=max(days_to_expiry, 0),
            vol=vol,
            option_type=contract.option_type,
        )
        out.append(PremiumBar(timestamp=ts, spot=spot, premium=premium, days_to_expiry=days_to_expiry))

    return out


def premium_bars_to_candles(bars: Sequence[PremiumBar]) -> pd.DataFrame:
    """Convert a PremiumBar sequence into the same OHLCV shape
    `CandleAggregator`/`shared.indicators.atr` expect, one "candle" per
    bar (the underlying data is already bar-level, so there is no
    intra-bar high/low to aggregate — open=high=low=close=premium is the
    correct degenerate case, not an approximation of a real intra-bar
    range we don't have)."""
    if not bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    idx = [b.timestamp for b in bars]
    prices = [b.premium for b in bars]
    return pd.DataFrame(
        {"open": prices, "high": prices, "low": prices, "close": prices, "volume": [0] * len(prices)},
        index=idx,
    )
