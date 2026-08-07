"""Orchestrates the full Production Strategy Validation Framework:
runs every strategy, day-isolated and aggregated, over the full history
and per-regime, computes metrics, and classifies KEEP/IMPROVE/REMOVE.

Day-isolated by design: this is an intraday-only system (SmartExitEngine
force-closes everything at the EOD cutoff — no position is ever meant to
carry overnight), so each calendar day is backtested independently with a
FRESH RiskManager (matching how a real trading day actually starts: no
carried drawdown state, no stale risk-off flag from a prior session).
Trades are then aggregated across days for the reported metrics.

This also sidesteps a real methodological trap: a single continuous
multi-month run can hit RiskManager's max-drawdown halt early (which,
correctly matching production, never auto-clears without manual
intervention) and then silently produce almost no further trades for the
rest of the period -- which would answer "did the risk manager work" (yes)
rather than "does this strategy have an edge" (the actual question here).
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import pandas as pd

from .harness import BacktestResult, SimTrade, run_strategy_backtest
from .metrics import compute_metrics
from .regimes import REGIME_NAMES, classify_daily_regimes

__all__ = ["run_strategy_day_isolated", "run_full_validation"]


#: Calendar days of prior history included as indicator-warmup context for
#: each day's isolated backtest — generous enough for any strategy's
#: longest lookback (e.g. "premium"'s EMA200 needs ~3 trading days of 5-min
#: bars; some strategies resample to 1hr/5min internally and want more raw
#: history than that) without re-running months of data per day.
_WARMUP_CALENDAR_DAYS = 30


def run_strategy_day_isolated(
    strategy_name: str,
    df: pd.DataFrame,
    instrument: str = "NIFTY",
    initial_capital: float = 100_000.0,
    settings: Optional[dict] = None,
    dates: Optional[set] = None,
) -> tuple[list[SimTrade], dict]:
    """Run `strategy_name` one calendar day at a time (fresh RiskManager
    each day — matching how a real trading day starts with no carried
    drawdown/risk-off state), aggregating trades. Each day's backtest is
    given `_WARMUP_CALENDAR_DAYS` of prior bars as indicator context (so
    long-lookback strategies like "premium"'s EMA200 actually have enough
    history to evaluate), but entries are only permitted within the target
    day itself (`harness.run_strategy_backtest`'s `tradeable_dates`).
    `dates`, if given, restricts to only those calendar dates (for
    per-regime slicing) — otherwise every date present in `df`."""
    all_trades: list[SimTrade] = []
    diagnostics = {"days_run": 0, "candidate_signals": 0, "rejected_untradeable_sl": 0,
                    "rejected_risk_gate": 0, "rejected_market_hours": 0}

    all_dates = sorted(set(df.index.date))
    for day in all_dates:
        if dates is not None and day not in dates:
            continue
        _set_simulated_session_date(day)
        window_start = pd.Timestamp(day) - pd.Timedelta(days=_WARMUP_CALENDAR_DAYS)
        window_df = df.loc[str(window_start.date()):str(day)]
        day_bar_count = (window_df.index.date == day).sum()
        if day_bar_count < 5:  # not enough bars in the target day to matter
            continue
        result = run_strategy_backtest(
            strategy_name, window_df, instrument=instrument,
            initial_capital=initial_capital, settings=settings,
            tradeable_dates={day},
        )
        all_trades.extend(result.trades)
        diagnostics["days_run"] += 1
        diagnostics["candidate_signals"] += result.candidate_signals
        diagnostics["rejected_untradeable_sl"] += result.rejected_untradeable_sl
        diagnostics["rejected_risk_gate"] += result.rejected_risk_gate
        diagnostics["rejected_market_hours"] += result.rejected_market_hours

    return all_trades, diagnostics


def _set_simulated_session_date(day) -> None:
    """Run session-scoped strategy state on the BACKTEST's clock rather
    than the wall clock.

    `RiskAgent`'s Capital Protection Mode expires per IST trading day via
    `_today_ist()`. A backtest compresses 123 simulated trading days into
    ~90 seconds of real time, so against the wall clock that rollover
    would never fire and the backtest would keep reproducing the very
    deadlock the daily reset exists to prevent — measuring a bug that no
    longer exists in production rather than the strategy.

    Pointing the agent's clock at the simulated date is the faithful
    model, not a workaround: in production, real days genuinely do pass
    between these sessions. The agent's own logic is untouched — it still
    decides when to reset; it is simply told what "today" is.
    """
    try:
        from drl.marl import risk_agent as _ra
        _ra._today_ist = lambda _d=day: _d
    except Exception:
        pass  # best-effort: never let harness hygiene break a run


def _reset_cross_strategy_singletons() -> None:
    """Clear process-global strategy state between strategies so one
    strategy's simulated results can't contaminate the next one's.

    Root cause (found 2026-08-07, first corrected-regime full run):
    `marl_strategy` reported 0 trades where an earlier run reported 976.
    Both "MARL_Ultra" and "marl_strategy" resolve to the same
    module-level `_marl_instance` singleton, and this harness (correctly,
    for live fidelity) feeds MARL_Ultra's closed-trade P&L back into that
    singleton's RiskAgent via `record_trade_outcome()`. "MARL_Ultra"
    sorts before "marl_strategy", so it ran first, drove the shared
    RiskAgent to 3+ consecutive losses (its documented "Capital
    Protection Mode"), and `marl_strategy` inherited a permanently
    entry-blocked agent — measuring the leaked state, not the strategy.

    Note this leakage is a harness artifact, but the underlying
    never-resets behavior is a real production concern in its own right —
    see docs/STRATEGY_IMPROVEMENT_BACKLOG.md's MARL capital-protection
    deadlock item.
    """
    try:
        from trading_bot.strategies import marl_strategy as _marl
        if getattr(_marl, "_marl_instance", None) is not None:
            agent = _marl._marl_instance.master_agent.risk_agent
            agent._consecutive_losses = 0
    except Exception:
        pass  # best-effort: never let harness hygiene break a run


def run_full_validation(
    strategy_names: list[str],
    df: pd.DataFrame,
    instrument: str = "NIFTY",
    initial_capital: float = 100_000.0,
    settings: Optional[dict] = None,
    verbose: bool = True,
) -> dict:
    """Run every strategy in `strategy_names` day-isolated over the full
    `df` exactly ONCE (not once per regime — each day's trades are tagged
    with that day's regime from the single sweep and bucketed afterward,
    avoiding redundant re-backtesting of the same days up to 6x). Returns
    a plain-dict report structure, JSON-serializable."""
    regime_labels = classify_daily_regimes(df)
    report: dict = {"instrument": instrument, "initial_capital": initial_capital,
                     "date_range": [str(df.index.min()), str(df.index.max())],
                     "total_days": len(regime_labels), "regime_day_counts": regime_labels.value_counts().to_dict(),
                     "strategies": {}}

    for name in strategy_names:
        _reset_cross_strategy_singletons()
        t0 = time.perf_counter()
        trades, diag = run_strategy_day_isolated(name, df, instrument, initial_capital, settings)
        elapsed = time.perf_counter() - t0

        strat_report: dict = {
            "overall": {**compute_metrics(trades, initial_capital), **diag},
            "by_regime": {},
            "elapsed_seconds": round(elapsed, 1),
        }

        for regime in REGIME_NAMES:
            regime_dates = set(regime_labels[regime_labels == regime].index)
            if not regime_dates:
                strat_report["by_regime"][regime] = {"trade_count": 0, "note": "no days classified in this regime"}
                continue
            regime_trades = [
                t for t in trades
                if pd.Timestamp(t.entry_time).date() in regime_dates
            ]
            strat_report["by_regime"][regime] = compute_metrics(regime_trades, initial_capital)

        report["strategies"][name] = strat_report

        if verbose:
            m = strat_report["overall"]
            print(
                f"[{elapsed:6.1f}s] {name:20s} trades={m['trade_count']:4d} "
                f"net={m['net_profit']:>10} pf={m['profit_factor']} wr={m['win_rate_pct']}%",
                file=sys.stderr,
            )

    return report


def _trades_to_jsonable(trades: list[SimTrade]) -> list[dict]:
    out = []
    for t in trades:
        d = asdict(t)
        d["entry_time"] = str(d["entry_time"])
        d["exit_time"] = str(d["exit_time"])
        out.append(d)
    return out


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Production Strategy Validation Framework")
    parser.add_argument("--data-path", default="data/NSE_NIFTY50-INDEX_5Min.csv")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--strategies", nargs="+", default=None)
    parser.add_argument("--instrument", default="NIFTY")
    parser.add_argument("--initial-capital", type=float, default=100_000.0)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    df = pd.read_csv(args.data_path)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime")
    if args.start:
        df = df.loc[args.start:]
    if args.end:
        df = df.loc[:args.end]

    from trading_bot.strategies.registry import registry
    default_strategies = sorted(set(registry.registered_strategies))
    strategies = args.strategies or default_strategies

    report = run_full_validation(strategies, df, instrument=args.instrument, initial_capital=args.initial_capital)

    out_path = args.out or "validation_harness/results/latest_report.json"
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"Report written to {out_path}", file=sys.stderr)
