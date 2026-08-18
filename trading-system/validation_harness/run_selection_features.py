"""Day- and direction-level selection features for `structure_break`.

    python -m validation_harness.run_selection_features

Why only these features
-----------------------
Phase 2 measured, on both the development and the held-out window, that
randomising the entry TIME within the same days and directions performs
as well as or better than the strategy's own break moment (p=0.593 dev,
p=0.888 OOS, null mean above the strategy in both). Refining the trigger
is therefore not the lever. Whatever edge exists lives in *which day* and
*which direction* — so only day- and direction-level features are tested
here.

Each candidate is a mechanism first and a number second. No sweeps, no
generated feature banks, nothing chosen because it scored well:

* `or_width_rel` — opening-range width as a share of price, over the
  trailing 20-session median of the same quantity. **Mechanism:** range
  compression precedes expansion. A break out of a tight balance area
  leaves most of the session's range still available; a break out of an
  already-wide range is late to its own move.
* `gap_aligned` — the overnight gap, signed by whether it agrees with the
  break direction. **Mechanism:** a gap re-prices the balance area before
  the session starts. Breaking with the gap continues that repricing;
  breaking against it is a gap-fill, a different trade.
* `new_territory` — whether the opening range already sits beyond the
  prior session's extreme in the break's direction. **Mechanism:** price
  moving where there is no recent acceptance meets less resting supply or
  demand.
* `or_pos_in_prior_range` — where the opening range sits inside the prior
  session's range, 0 at the prior low and 1 at the prior high.
  **Mechanism:** value-area location. Breaking up from the top of prior
  value is continuation; from the bottom it is mean reversion.

All four are known by 09:45 on the day, before any break can be acted on,
so none can see its own outcome.

The measure is first touch of ±1R — exit-independent, so no exit rule can
flatter or spoil it (see `run_entry_information_test`). Signals are taken
unfiltered (210 on the development window) rather than the 43 that
survive production filtering, because a selection question needs the
statistical power and filtering is a separate experiment.

A feature is only worth acting on if it is monotone across buckets,
consistent in sign across months and across both halves of the window,
adequately sampled, and its top-vs-bottom difference has a bootstrap
confidence interval excluding zero. Anything else is noise wearing a
mechanism's clothes.
"""
from __future__ import annotations

import argparse
import logging

import numpy as np
import pandas as pd

from .research_config import load_window
from .run_entry_information_test import _edge, _first_touch

logging.disable(logging.CRITICAL)

OPENING_RANGE_BARS = 6


def _day_features(df: pd.DataFrame) -> pd.DataFrame:
    """One row per session, using only information available by 09:45."""
    rows = []
    prev_high = prev_low = prev_close = None
    for day, bars in df.groupby(df.index.normalize()):
        if len(bars) < OPENING_RANGE_BARS + 2:
            prev_high, prev_low, prev_close = (
                bars["high"].max(), bars["low"].min(), bars["close"].iloc[-1])
            continue
        rng = bars.iloc[:OPENING_RANGE_BARS]
        or_high, or_low = float(rng["high"].max()), float(rng["low"].min())
        mid = (or_high + or_low) / 2.0
        day_open = float(bars["open"].iloc[0])

        rows.append({
            "date": day,
            "or_high": or_high, "or_low": or_low,
            "or_width_pct": (or_high - or_low) / mid * 100.0,
            "gap_pct": ((day_open - prev_close) / prev_close * 100.0)
                       if prev_close else np.nan,
            "prev_high": prev_high, "prev_low": prev_low,
        })
        prev_high, prev_low, prev_close = (
            bars["high"].max(), bars["low"].min(), bars["close"].iloc[-1])

    feat = pd.DataFrame(rows).set_index("date")
    # Trailing median EXCLUDES the current session (shift(1)): using it
    # would let a day's own width set its own benchmark.
    feat["or_width_rel"] = feat["or_width_pct"] / (
        feat["or_width_pct"].shift(1).rolling(20, min_periods=5).median())
    feat["abs_gap_med"] = feat["gap_pct"].abs().shift(1).rolling(20, min_periods=5).median()
    return feat


def _attach(signals, feat: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for ts, direction in signals:
        day = ts.normalize()
        if day not in feat.index:
            continue
        f = feat.loc[day]
        if not np.isfinite(f.get("or_width_rel", np.nan)):
            continue
        sign = 1.0 if direction == "CE" else -1.0

        # Signed so that a larger value always means "more of the thing the
        # mechanism says should help", for CE and PE alike.
        gap_aligned = (f["gap_pct"] * sign) / f["abs_gap_med"] if f["abs_gap_med"] else np.nan

        if direction == "CE":
            new_territory = float(f["or_high"] > f["prev_high"]) if f["prev_high"] else np.nan
        else:
            new_territory = float(f["or_low"] < f["prev_low"]) if f["prev_low"] else np.nan

        span = (f["prev_high"] - f["prev_low"]) if f["prev_high"] and f["prev_low"] else np.nan
        mid = (f["or_high"] + f["or_low"]) / 2.0
        pos = (mid - f["prev_low"]) / span if span and np.isfinite(span) and span > 0 else np.nan
        # Signed the same way: for a CE break, high in prior value is the
        # continuation case; for PE it is low in prior value.
        or_pos_signed = pos if direction == "CE" else (1.0 - pos if np.isfinite(pos) else np.nan)

        rows.append({
            "ts": ts, "date": day, "direction": direction,
            "or_width_rel": f["or_width_rel"],
            "gap_aligned": gap_aligned,
            "new_territory": new_territory,
            "or_pos_in_prior_range": or_pos_signed,
        })
    return pd.DataFrame(rows)


def _bucket_report(d: pd.DataFrame, col: str, n_buckets: int = 4) -> None:
    vals = d[col].replace([np.inf, -np.inf], np.nan)
    ok = d[vals.notna()].copy()
    ok[col] = vals[vals.notna()]
    if len(ok) < 40:
        print(f"\n### `{col}` — only {len(ok)} usable signals, not evaluated\n")
        return

    binary = ok[col].nunique() <= 2
    if binary:
        ok["bucket"] = ok[col].map({0.0: "no", 1.0: "yes"})
        order = ["no", "yes"]
    else:
        try:
            ok["bucket"] = pd.qcut(ok[col], n_buckets, labels=[f"Q{i+1}" for i in range(n_buckets)])
        except ValueError:
            print(f"\n### `{col}` — not enough distinct values to bucket\n")
            return
        order = [f"Q{i+1}" for i in range(n_buckets)]

    print(f"\n### `{col}`\n")
    print("| bucket | n | range | win-first | loss-first | edge (pp) |")
    print("|---|---|---|---|---|---|")
    edges = []
    for b in order:
        g = ok[ok.bucket == b]
        if g.empty:
            continue
        e = _edge(g.outcome.values)
        edges.append(e)
        rng = f"{g[col].min():.2f}..{g[col].max():.2f}"
        a = g.outcome.values
        print(f"| {b} | {len(g)} | {rng} | {np.mean(a=='win_first')*100:.1f}% | "
              f"{np.mean(a=='loss_first')*100:.1f}% | **{e:+.1f}** |")

    if len(edges) < 2:
        return
    # Monotonicity: Spearman of bucket order against edge.
    rho = float(pd.Series(edges).corr(pd.Series(range(len(edges))), method="spearman"))
    top, bot = ok[ok.bucket == order[-1]], ok[ok.bucket == order[0]]
    diff = _edge(top.outcome.values) - _edge(bot.outcome.values)

    rng = np.random.default_rng(20260809)
    draws = []
    for _ in range(5000):
        a = top.outcome.values[rng.integers(0, len(top), len(top))]
        b = bot.outcome.values[rng.integers(0, len(bot), len(bot))]
        draws.append(_edge(a) - _edge(b))
    lo, hi = np.percentile(draws, [2.5, 97.5])

    print(f"\nmonotonicity (Spearman bucket vs edge): **{rho:+.2f}**  ")
    print(f"top − bottom: **{diff:+.1f}pp**, bootstrap 95% CI "
          f"**[{lo:+.1f}, {hi:+.1f}]**, P(diff<=0) = **{np.mean(np.array(draws)<=0):.3f}**  ")

    # Stability: sign consistency by month and across halves.
    ok = ok.copy()
    ok["month"] = ok.date.dt.to_period("M").astype(str)
    months = sorted(ok.month.unique())
    signs = []
    for m in months:
        g = ok[ok.month == m]
        t, b2 = g[g.bucket == order[-1]], g[g.bucket == order[0]]
        if len(t) >= 3 and len(b2) >= 3:
            signs.append(np.sign(_edge(t.outcome.values) - _edge(b2.outcome.values)))
    pos = int(sum(1 for s in signs if s > 0))
    print(f"months with enough data: **{len(signs)}**, sign positive in "
          f"**{pos}/{len(signs)}**  ")

    half = ok.date.median()
    for name, g in (("first half", ok[ok.date <= half]), ("second half", ok[ok.date > half])):
        t, b2 = g[g.bucket == order[-1]], g[g.bucket == order[0]]
        if len(t) >= 5 and len(b2) >= 5:
            print(f"{name}: top−bottom **{_edge(t.outcome.values)-_edge(b2.outcome.values):+.1f}pp** "
                  f"(n={len(t)}/{len(b2)})  ")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--window", choices=["dev"], default="dev",
                    help="development only — the held-out window is not a tuning set")
    args = ap.parse_args()

    df = load_window(args.window)
    from trading_bot.strategies.registry import registry
    raw = registry._strategies["structure_break"](df)
    raw = raw[0] if isinstance(raw, tuple) else raw
    signals = [(ts, "CE" if v == 1 else "PE") for ts, v in raw.items() if v != 0]

    feat = _day_features(df)
    d = _attach(signals, feat)

    outcomes = []
    by_day = {day: bars for day, bars in df.groupby(df.index.normalize())}
    for r in d.itertuples():
        o = _first_touch(by_day[r.date], r.ts, r.direction)
        outcomes.append(o.first_touch if o else None)
    d["outcome"] = outcomes
    d = d[d.outcome.notna()]

    print(f"# Selection features — `structure_break` ({args.window.upper()})\n")
    print(f"Signals measured: **{len(d)}** (unfiltered), "
          f"baseline edge **{_edge(d.outcome.values):+.1f}pp**\n")
    print("Direction split: " + ", ".join(
        f"{k}={v}" for k, v in d.direction.value_counts().items()))

    for col in ("or_width_rel", "gap_aligned", "new_territory", "or_pos_in_prior_range"):
        _bucket_report(d, col)


if __name__ == "__main__":
    main()
