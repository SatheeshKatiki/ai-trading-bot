"""RSI_SMC_OPTIONS_BUYER_V1 -- RSI + SMC + price action + liquidity, buying
index options.

One sentence: buy a CE (or PE) when the higher timeframe agrees, the regime
permits, price has just SWEPT a level where stops rest and closed back inside
it, market structure has confirmed the turn or the resumption, RSI agrees, a
decisive candle triggers, and the structural risk/reward clears the floor.

What is NEW here, and what is reused
------------------------------------
Almost nothing is new. The entry composition is, and so is a vectorised
liquidity-sweep detector, because the repository had a definition
(``LiquiditySweepDetector``, dead code) but no working implementation, and
``LiquidityPool.swept`` is declared and never assigned. Everything else is an
import:

* structure -- ``shared/indicators/smart_money_concepts.py::calculate_smc``,
  called once per closed bar through the causal adapter in :mod:`structure`
* RSI, EMA, ATR -- ``shared/indicators``
* regime -- ``momentum_strategy``'s ``MarketRegimeDetector``, read-only
* choppiness -- ``premium_selection``'s ``_choppiness_index``, read-only
* the exit ladder -- ``ema9_rsi_momentum/exit_ladder.py``, pure functions
* strike/expiry/lot size -- ``premium_selection``'s ``select_option``
* stops, sizing, every risk veto -- ``shared/risk``
* trailing, partial booking, EOD -- ``shared/exits/exit_engine.py``

Deliberately NOT declared
-------------------------
``USE_DYNAMIC_FIB_TRAIL`` is read by ``validation_harness/harness.py`` and NOT
by ``trading_bot/main.py``. A strategy that opted in would trail one way in
replay and another way live -- the exact live/backtest divergence this
repository has been bitten by before. Fixing that asymmetry would change
``momentum_15_5``'s behaviour, which is out of scope, so this strategy simply
does not depend on the flag.

Order Blocks are not used either; :mod:`structure` explains why (their
availability lag is variable and unrecoverable from the engine's output).

Open Interest, OI change, Implied Volatility and Delta are NOT available on
the live execution path and are excluded from V1 rather than approximated.
See :func:`approve_contract`.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from trading_bot.strategies._signal_utils import edge_trigger

from . import exits as _exits
from . import signal_engine as _signal_engine
from . import structure as _structure
from .config import STRATEGY_ID, STRATEGY_NAME, RsiSmcConfig
from .no_trade import instrument_reason

logger = logging.getLogger(__name__)

#: Institutional filters the registry must NOT apply to this strategy.
#:
#: A declaration of inapplicability, not of ownership -- nothing in this
#: package reads or implements them. Each is adversarial to a
#: sweep-and-structure-break entry by construction: ``squeeze`` vetoes exactly
#: the volatility expansion a break IS, ``extension`` rejects price that has
#: travelled from its EMA (which a decisive trigger candle has, by
#: definition), and ``cpr``/``aggression`` penalise decisive candles near
#: pivots -- but pivots are precisely where this strategy's liquidity levels
#: sit, so that veto would fire on the setup rather than on a mistake.
#:
#: ``config/settings.json`` currently ships ``enable_squeeze_filter: true``,
#: so without this declaration the live book would silently lose most
#: signals -- the same interaction that reduced ``institutional_momentum`` to
#: zero trades and cost ``momentum_15_5`` 19 of 23 signals on its development
#: window.
#:
#: Declared in code rather than configuration on purpose, so the live engine
#: and the validation harness resolve it identically whatever settings.json
#: happens to say.
SKIP_INSTITUTIONAL_FILTERS = frozenset({"squeeze", "extension", "cpr", "aggression"})

__all__ = [
    "STRATEGY_NAME",
    "STRATEGY_ID",
    "SKIP_INSTITUTIONAL_FILTERS",
    "generate_signals",
    "assess_entry_quality",
    "approve_contract",
    "EntryGrade",
    "ContractVerdict",
    "RsiSmcConfig",
]

# Bounded log de-duplication: the live engine re-evaluates every ~200 ms, so
# without this a signal bar that keeps failing a downstream gate would log the
# same line dozens of times before the next bar closes. Gates logging only --
# never the returned signal series.
_MAX_LOGGED = 128
_logged: deque = deque(maxlen=_MAX_LOGGED)
_logged_set: set = set()


def _log_once(key) -> bool:
    if key in _logged_set:
        return False
    if len(_logged) == _MAX_LOGGED:
        _logged_set.discard(_logged[0])
    _logged.append(key)
    _logged_set.add(key)
    return True


def _configured_symbols(settings: Mapping[str, Any]) -> list:
    """The symbol set this engine is configured to trade, if it says."""
    symbols = settings.get("symbols")
    if isinstance(symbols, (list, tuple)) and symbols:
        return [str(s) for s in symbols]
    single = settings.get("symbol")
    return [str(single)] if single else []


def _instrument_block(settings: Mapping[str, Any], cfg: RsiSmcConfig,
                      symbol: Optional[str]) -> str:
    """Why this evaluation must emit nothing, on instrument grounds.

    ``registry.run_strategy(name, df, **settings)`` does not pass the symbol
    currently being evaluated -- ``main.py`` loops over
    ``aggregator.symbols`` and calls the registry with the settings dict
    alone. So when no explicit ``symbol`` is supplied this checks the
    CONFIGURED SET instead, and refuses if ANY member of it is outside the
    allowed instruments: if the set is mixed, this evaluation cannot know
    which member it is on, and guessing would be the one mistake that lets an
    equity trade through.

    An unverifiable set (no symbols configured at all, as in a bare unit test
    or a harness call) is allowed through -- the caller is then responsible
    for the instrument, and ``main.py``'s own option-mapping abort still
    stands behind this.
    """
    if symbol:
        return instrument_reason(symbol, cfg)
    for candidate in _configured_symbols(settings):
        reason = instrument_reason(candidate, cfg)
        if reason:
            return (f"{reason} (configured symbol set includes it, and the "
                    f"registry does not say which symbol this evaluation is for)")
    return ""


def generate_signals(df: pd.DataFrame, symbol: Optional[str] = None, **kwargs) -> pd.Series:
    """Registry entry point.

    Returns a ``pandas.Series`` of ``1`` (buy CE), ``-1`` (buy PE) or ``0``,
    aligned to ``df``'s index. Every mandatory condition is ANDed in
    :func:`signal_engine.compose`; repeated bars of the same signal are
    collapsed to the opening bar by the shared :func:`edge_trigger`.
    """
    if df is None or len(df) == 0 or "close" not in getattr(df, "columns", []):
        return pd.Series(dtype=int)

    cfg = RsiSmcConfig.from_settings(kwargs, symbol=symbol)

    blocked = _instrument_block(kwargs, cfg, symbol)
    if blocked:
        if _log_once(("instrument", blocked)):
            logger.info("%s: no signals -- %s", STRATEGY_ID, blocked)
        return pd.Series(np.zeros(len(df), dtype=int), index=df.index, dtype=int)

    if len(df) < cfg.min_bars:
        if _log_once(("short", len(df))):
            logger.info(
                "%s: no signals -- %d bars is below the %d needed for a "
                "%d-bar swing lookback (the structure engine would silently "
                "substitute a shorter one).",
                STRATEGY_ID, len(df), cfg.min_bars, cfg.swing_points_length,
            )
        return pd.Series(np.zeros(len(df), dtype=int), index=df.index, dtype=int)

    try:
        raw, conditions, diagnostics, blocks = _signal_engine.build(df, cfg, symbol=symbol)
    except Exception as exc:
        # Failure isolation: a broken strategy must not take the engine down.
        # main.py's entry path catches this, but returning zeros keeps the
        # contract (a Series aligned to df) intact for every other caller.
        logger.exception("%s: signal generation failed (%s) -- emitting no signals.",
                         STRATEGY_ID, exc)
        return pd.Series(np.zeros(len(df), dtype=int), index=df.index, dtype=int)

    signals = edge_trigger(pd.Series(raw, index=df.index, dtype=int))

    latest = int(signals.iloc[-1]) if len(signals) else 0
    last = len(df) - 1
    if latest != 0 and _log_once((df.index[-1], latest)):
        side = "CE" if latest > 0 else "PE"
        rr = (diagnostics.reward_risk_bull[last] if latest > 0
              else diagnostics.reward_risk_bear[last])
        level = (diagnostics.swept_level_bull[last] if latest > 0
                 else diagnostics.swept_level_bear[last])
        extreme = (diagnostics.swept_extreme_bull[last] if latest > 0
                   else diagnostics.swept_extreme_bear[last])
        logger.info(
            "ENTRY %s %s | swept %.2f (wick %.2f) | RSI %.1f vs MA %.1f | "
            "R:R %.2f | reason: liquidity sweep confirmed by %s, RSI agreeing, "
            "decisive trigger.",
            STRATEGY_ID, side, level, extreme,
            diagnostics.rsi[last], diagnostics.rsi_ma[last], rr,
            "CHoCH" if conditions.struct_bull[last] or conditions.struct_bear[last] else "structure",
        )
    elif latest == 0 and blocks.blocked[last] and _log_once(("block", df.index[-1])):
        logger.debug("%s: bar %s blocked -- %s", STRATEGY_ID, df.index[-1],
                     blocks.reason_at(last))

    return signals


@dataclass(frozen=True)
class EntryGrade:
    """What ``shared.entry_gate`` reads back from this strategy."""

    priority: str
    take: bool
    reward_risk: float
    decisive_trigger: bool


def assess_entry_quality(df: pd.DataFrame, direction: int,
                         settings: Optional[dict] = None) -> Optional[EntryGrade]:
    """This strategy's grade for the LATEST bar, for the shared entry gate.

    ``shared.entry_gate`` drops a setup graded LOW. Nothing here is ever
    graded LOW, and that is deliberate rather than an oversight: by the time a
    signal exists it has already satisfied all nine mandatory conditions, so
    there is no weak survivor left to discard. The grade distinguishes a
    strong setup from an ordinary one for logging and for the shadow book's
    diagnostics.

    HIGH   a decisive trigger candle (not merely an FVG reaction) AND at
           least twice the minimum reward-to-risk.
    MEDIUM everything else that produced a signal.
    """
    if df is None or direction == 0:
        return None
    cfg = RsiSmcConfig.from_settings(settings or {})
    if len(df) < cfg.min_bars:
        return None
    try:
        _, conditions, diagnostics, _ = _signal_engine.build(df, cfg)
    except Exception:
        return None

    last = len(df) - 1
    if direction > 0:
        rr = float(diagnostics.reward_risk_bull[last])
        decisive = bool(conditions.trigger_bull[last])
    else:
        rr = float(diagnostics.reward_risk_bear[last])
        decisive = bool(conditions.trigger_bear[last])

    strong = decisive and np.isfinite(rr) and rr >= 2.0 * float(cfg.min_rr)
    return EntryGrade(
        priority="HIGH" if strong else "MEDIUM",
        take=True,
        reward_risk=rr if np.isfinite(rr) else 0.0,
        decisive_trigger=decisive,
    )


@dataclass(frozen=True)
class ContractVerdict:
    """Whether a selected option contract may actually be bought."""

    approved: bool
    reason: str
    spread_pct: float = float("nan")


def approve_contract(symbol: str, quote: Any, settings: Optional[dict] = None,
                     age_s: Optional[float] = None) -> ContractVerdict:
    """M2: the contract-quality screen, consulted by ``main.py`` after the
    live premium is fetched and before the order is sized.

    WHAT THIS CHECKS -- spread, quote validity, staleness, traded volume.
    Everything available from ``broker.get_market_data()``'s ``MarketQuote``.

    WHAT IT CANNOT CHECK -- Open Interest, OI change, Implied Volatility and
    Delta. Their only source in this repository is
    ``api_bridge.py::_fetch_real_option_chain``, an async function inside the
    FastAPI application module that the live engine cannot import, and
    ``select_option`` returns an ``OptionContract`` with no Greek fields (the
    Greeks are computed there and only logged). They are BLOCKED for V1 and
    are deliberately NOT approximated from anything else: a fabricated
    liquidity read is worse than an absent one, because it looks like a
    safeguard.

    A missing two-sided quote is a REJECTION, not a pass. If the broker does
    not populate depth for option contracts this will refuse every entry --
    that is the intended direction of failure under "if market data integrity
    is uncertain, no trade", and the shadow book will surface it on day one
    rather than after a bad fill.
    """
    cfg = RsiSmcConfig.from_settings(settings or {})

    if quote is None:
        return ContractVerdict(False, f"no quote for {symbol}")

    ltp = float(getattr(quote, "ltp", 0.0) or 0.0)
    bid = float(getattr(quote, "bid", 0.0) or 0.0)
    ask = float(getattr(quote, "ask", 0.0) or 0.0)
    volume = int(getattr(quote, "volume", 0) or 0)

    if not np.isfinite(ltp) or ltp <= 0:
        return ContractVerdict(False, f"{symbol}: invalid last price ({ltp})")

    if age_s is not None and np.isfinite(age_s) and age_s > float(cfg.quote_max_age_s):
        return ContractVerdict(
            False, f"{symbol}: quote is {age_s:.1f}s old (limit {cfg.quote_max_age_s:.1f}s)")

    if bid <= 0 or ask <= 0:
        return ContractVerdict(
            False,
            f"{symbol}: no two-sided quote (bid {bid}, ask {ask}) -- cannot "
            f"verify the spread this entry would pay")

    if ask < bid:
        return ContractVerdict(False, f"{symbol}: crossed quote (bid {bid} > ask {ask})")

    spread_pct = (ask - bid) / ltp * 100.0
    if spread_pct > float(cfg.max_spread_pct):
        return ContractVerdict(
            False,
            f"{symbol}: spread {spread_pct:.2f}% of premium exceeds "
            f"{cfg.max_spread_pct:.2f}%", spread_pct)

    if cfg.min_contract_volume > 0 and volume < int(cfg.min_contract_volume):
        return ContractVerdict(
            False,
            f"{symbol}: traded volume {volume} below {cfg.min_contract_volume}",
            spread_pct)

    return ContractVerdict(True, "", spread_pct)


# Re-exported so main.py's M1 branch has one import site.
exits = _exits
structure = _structure
signal_engine = _signal_engine
