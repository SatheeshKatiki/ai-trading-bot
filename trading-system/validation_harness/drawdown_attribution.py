"""Attribute a strategy's max drawdown to the CONTRACT it was taken on.

Backlog #3 asks a specific, falsifiable question: how much of each
strategy's max drawdown comes from cheap, near-expiry option contracts?

The mechanism under test (found while building the harness): a Rs 49.99
premium in the Rs 20-50 band carries a ~Rs 8 intended stop, and such a
contract can crash from 49.99 to 8.97 inside a single simulated 5-minute
bar near expiry — blowing through the stop rather than being filled at
it. The premium-banded SL assumes a stop can be filled near its trigger,
which is least true for exactly these contracts.

Read-only. Nothing here changes a strategy, a filter, or a parameter —
it measures whether the hypothesised concentration is real, so that a
minimum-premium / minimum-DTE entry filter can be argued from evidence
(or dropped) rather than guessed at.

Three separate numbers are reported, because they answer different
questions and it is easy to conflate them:

  share_*          the cohort's share of trade count / gross loss over the
                   WHOLE period. Says "is this cohort disproportionately
                   lossy at all?"
  in_window_*      P&L split inside the actual peak-to-trough segment that
                   PRODUCED the max drawdown. Says "did this cohort cause
                   THE drawdown, not just losses generally?"
  dd_pct_excl      max drawdown recomputed with the cohort's trades
                   dropped from the sequence.

`dd_pct_excl` is an ATTRIBUTION, not a forecast of what a filter would
deliver. Dropping trades from a realised sequence does not reproduce the
run a filter would have produced: position sizing is equity-dependent, so
every later trade in a real filtered run would size differently, and
capital freed by a skipped trade could have been deployed elsewhere. It
brackets the opportunity; the harness must be re-run with a real entry
filter to claim an actual delta.
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence

import pandas as pd

from .exit_quality import parse_option_symbol

__all__ = ["annotate_contracts", "attribute_drawdown", "cohort_grid"]

#: The hypothesised danger cohort: cheap enough that the banded stop is a
#: few rupees wide, near enough to expiry that gamma/theta can cross that
#: width within one bar. Both halves are reported separately as well, so
#: the data can reject one and keep the other.
CHEAP_PREMIUM_MAX = 50.0
NEAR_EXPIRY_MAX_DTE = 1


def annotate_contracts(trades: Sequence) -> pd.DataFrame:
    """One row per trade with the contract attributes the cohort is cut on.

    `dte` is days-to-expiry AT ENTRY, recovered from the Fyers symbol.
    Trades whose symbol will not parse (non-option rows, if any) get
    `dte = None` and are excluded from cohort membership rather than
    silently defaulting into it.
    """
    rows = []
    for t in trades:
        contract = parse_option_symbol(t.symbol)
        entry_ts = pd.Timestamp(t.entry_time)
        dte = (contract.expiry - entry_ts.date()).days if contract is not None else None
        rows.append({
            "entry_time": entry_ts,
            "symbol": t.symbol,
            "entry_premium": t.entry_premium,
            "dte": dte,
            "pnl": t.pnl,
            "exit_reason": t.exit_reason.split("(")[0].strip(),
            "sl_band_label": t.sl_band_label,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Chronological order is what makes the equity curve meaningful. The
    # harness already emits trades in bar order, but day-isolated runs
    # concatenate per-day results, so sort defensively rather than assume.
    df = df.sort_values("entry_time", kind="stable").reset_index(drop=True)

    df["is_cheap"] = df["entry_premium"] < CHEAP_PREMIUM_MAX
    df["is_near_expiry"] = df["dte"].notna() & (df["dte"] <= NEAR_EXPIRY_MAX_DTE)
    df["in_cohort"] = df["is_cheap"] & df["is_near_expiry"]
    return df


def _equity_curve(pnls: Iterable[float], initial_capital: float) -> list[float]:
    equity = initial_capital
    curve = [equity]
    for p in pnls:
        equity += p
        curve.append(equity)
    return curve


def _max_drawdown(pnls: Sequence[float], initial_capital: float) -> tuple[float, int, int]:
    """Return (max_dd_pct, peak_idx, trough_idx) over the trade sequence.

    Indices are into the EQUITY CURVE (length len(pnls)+1, element 0 being
    the starting capital before any trade), so the trades that produced the
    drawdown are `pnls[peak_idx:trough_idx]`. Matches `metrics.compute_metrics`'s
    definition exactly — same peak-relative percentage, same trade
    sequencing — so the number reported here reconciles with the validation
    report rather than being a second, subtly different drawdown.
    """
    curve = _equity_curve(pnls, initial_capital)
    max_dd_pct = 0.0
    peak_idx = 0
    trough_idx = 0
    running_peak = curve[0]
    running_peak_idx = 0
    for i, equity in enumerate(curve):
        if equity > running_peak:
            running_peak = equity
            running_peak_idx = i
        if running_peak > 0:
            dd_pct = (running_peak - equity) / running_peak * 100.0
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct
                peak_idx = running_peak_idx
                trough_idx = i
    return max_dd_pct, peak_idx, trough_idx


def attribute_drawdown(df: pd.DataFrame, initial_capital: float,
                        cohort_col: str = "in_cohort") -> dict:
    """Attribute the max drawdown in `df` to the `cohort_col` cohort.

    See the module docstring on how to read (and how NOT to read)
    `dd_pct_excl`.
    """
    if df.empty:
        return {"trade_count": 0}

    pnls = df["pnl"].tolist()
    cohort = df[cohort_col].fillna(False).astype(bool)

    dd_pct, peak_idx, trough_idx = _max_drawdown(pnls, initial_capital)

    # Trades inside the peak-to-trough segment that produced the max DD.
    window = df.iloc[peak_idx:trough_idx]
    window_cohort = window[window[cohort_col].fillna(False).astype(bool)]
    window_rest = window[~window[cohort_col].fillna(False).astype(bool)]

    losses = df[df["pnl"] <= 0]
    cohort_losses = losses[losses[cohort_col].fillna(False).astype(bool)]
    gross_loss = abs(losses["pnl"].sum())

    kept = df[~cohort]
    dd_excl, _, _ = _max_drawdown(kept["pnl"].tolist(), initial_capital)

    return {
        "trade_count": len(df),
        "cohort_trades": int(cohort.sum()),
        "share_trades_pct": round(cohort.sum() / len(df) * 100.0, 1),
        "share_gross_loss_pct": (
            round(abs(cohort_losses["pnl"].sum()) / gross_loss * 100.0, 1) if gross_loss > 0 else None
        ),
        "cohort_net_pnl": round(df.loc[cohort, "pnl"].sum(), 2),

        "dd_pct": round(dd_pct, 2),
        "dd_window_trades": len(window),
        "in_window_cohort_trades": len(window_cohort),
        "in_window_cohort_pnl": round(window_cohort["pnl"].sum(), 2),
        "in_window_rest_pnl": round(window_rest["pnl"].sum(), 2),
        "in_window_cohort_share_pct": (
            round(window_cohort["pnl"].sum() / window["pnl"].sum() * 100.0, 1)
            if window["pnl"].sum() < 0 else None
        ),

        "dd_pct_excl": round(dd_excl, 2),
        "dd_pct_delta": round(dd_excl - dd_pct, 2),
        "net_pnl": round(df["pnl"].sum(), 2),
        "net_pnl_excl": round(kept["pnl"].sum(), 2),
    }


def cohort_grid(df: pd.DataFrame) -> pd.DataFrame:
    """P&L broken out by (premium band x DTE bucket).

    The cohort definition above is a hypothesis with two hardcoded
    thresholds in it. This grid exists so the thresholds can be checked
    against the data instead of trusted — if the damage actually
    concentrates at <Rs 20 rather than <Rs 50, or at 0 DTE rather than
    <=1, that shows up here and the cohort should be recut.
    """
    if df.empty:
        return df

    prem_bins = [0, 20, 50, 100, 200, float("inf")]
    prem_labels = ["<20", "20-50", "50-100", "100-200", "200+"]
    dte_bins = [-1, 0, 1, 3, 7, float("inf")]
    dte_labels = ["0", "1", "2-3", "4-7", "8+"]

    g = df.copy()
    g["prem_band"] = pd.cut(g["entry_premium"], bins=prem_bins, labels=prem_labels, right=False)
    g["dte_bucket"] = pd.cut(g["dte"], bins=dte_bins, labels=dte_labels)

    out = g.groupby(["prem_band", "dte_bucket"], observed=True).agg(
        n=("pnl", "size"),
        net=("pnl", "sum"),
        gross_loss=("pnl", lambda s: abs(s[s <= 0].sum())),
        win_rate=("pnl", lambda s: (s > 0).mean() * 100.0),
    ).reset_index()
    out["net"] = out["net"].round(0)
    out["gross_loss"] = out["gross_loss"].round(0)
    out["win_rate"] = out["win_rate"].round(1)
    return out.sort_values("net")
