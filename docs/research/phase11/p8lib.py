"""Phase 8 research harness. Research-only; nothing here is imported by
trading_bot/ or by any production path.

Two things the Phase 7 measurement got wrong, both fixed here:

1. LIVE-EQUIVALENT CONTEXT. main.py's CandleAggregator keeps tail(2000).
   measure_signal_edge ran the strategy on 43,870 bars at once. The strategy's
   liquidity-pool set grows with history, so the same date range produced
   different signals (24 entries at <=2000 bars of context, 26 at >=6000, with
   different timestamps). Replaying in blocks with a bounded look-back
   reproduces what the live engine would actually have seen.

2. STAGE-WISE FUNNEL. Phase 7 only measured the final conjunction. To find
   where information is lost, every intermediate condition has to be measured
   against the same forward labels.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

ROOT = Path(r"D:\Projects\AI trading Bot\trading-system")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import logging
logging.disable(logging.CRITICAL)

#: What main.py's CandleAggregator retains.
LIVE_CONTEXT_BARS = 2000


def load_nifty() -> pd.DataFrame:
    from measure_signal_edge import load_bars
    return load_bars()


def load_csv(name: str) -> pd.DataFrame:
    df = pd.read_csv(ROOT / "data" / name)
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df.set_index("datetime").sort_index()


# ---------------------------------------------------------------------
# Live-equivalent replay
# ---------------------------------------------------------------------

def replay_conditions(bars: pd.DataFrame, cfg, *, chunk: int = 200,
                      context: int = LIVE_CONTEXT_BARS, symbol: str = "NIFTY"):
    """Recompute the strategy in blocks, each seeing only `context` prior bars.

    Returns (signals, conditions_dict, diagnostics_dict) aligned to `bars`,
    where each value at bar i was computed from a window ending at i whose
    length never exceeded `context + chunk`.
    """
    from trading_bot.strategies.rsi_smc_options_buyer import signal_engine as se
    from trading_bot.strategies.rsi_smc_options_buyer import structure as st

    n = len(bars)
    cond_names = [f.name for f in __import__("dataclasses").fields(se.Conditions)]
    diag_names = [f.name for f in __import__("dataclasses").fields(se.Diagnostics)]

    signals = np.zeros(n, dtype=int)
    conds = {name: np.zeros(n, dtype=bool) for name in cond_names}
    diags = {name: np.full(n, np.nan, dtype=float) for name in diag_names}

    start = 0
    while start < n:
        stop = min(start + chunk, n)
        lo = max(0, start - context)
        window = bars.iloc[lo:stop]
        if len(window) >= cfg.min_bars:
            st.clear_cache()
            raw, c, d, _ = se.build(window, cfg, symbol=symbol)
            offset = start - lo
            signals[start:stop] = raw[offset:]
            for name in cond_names:
                conds[name][start:stop] = np.asarray(getattr(c, name), dtype=bool)[offset:]
            for name in diag_names:
                diags[name][start:stop] = np.asarray(getattr(d, name), dtype=float)[offset:]
        start = stop

    return signals, conds, diags


def edge_trigger_np(signals: np.ndarray) -> np.ndarray:
    """Same rule as trading_bot.strategies._signal_utils.edge_trigger."""
    values = np.asarray(signals, dtype=int).copy()
    if values.shape[0] > 1:
        dup = np.zeros(values.shape[0], dtype=bool)
        dup[1:] = (values[1:] == values[:-1]) & (values[1:] != 0)
        values = np.where(dup, 0, values)
    return values


# ---------------------------------------------------------------------
# Forward labels
# ---------------------------------------------------------------------

def forward_excursions(bars: pd.DataFrame, horizons: Sequence[int]
                       ) -> Dict[int, Tuple[np.ndarray, np.ndarray]]:
    """(up_excursion, down_excursion) from each bar's CLOSE over the next h
    bars, never crossing a day boundary.

    Identical construction to scripts/measure_signal_edge.py: entry price is
    bar i's close, the forward window is bars [i+1, i+h]. Direction is applied
    by the caller, so one computation serves both CE and PE.
    """
    highs = bars["high"].to_numpy(float)
    lows = bars["low"].to_numpy(float)
    closes = bars["close"].to_numpy(float)
    days = bars.index.normalize().to_numpy()
    n = len(bars)

    out: Dict[int, Tuple[np.ndarray, np.ndarray]] = {}
    for h in horizons:
        up = np.full(n, np.nan)
        dn = np.full(n, np.nan)
        for i in range(n - 1):
            end = min(i + 1 + h, n)
            same = days[i + 1:end] == days[i]
            if not same.any():
                continue
            hi = highs[i + 1:end][same]
            lo = lows[i + 1:end][same]
            up[i] = hi.max() - closes[i]
            dn[i] = closes[i] - lo.min()
        out[h] = (up, dn)
    return out


def excursion_stats(up: np.ndarray, dn: np.ndarray, direction: np.ndarray,
                    mask: np.ndarray) -> dict:
    """MFE/MAE statistics for the bars selected by `mask`, with `direction`
    (+1/-1) deciding which side is favourable."""
    sel = mask & np.isfinite(up) & np.isfinite(dn) & (direction != 0)
    if not sel.any():
        return {"n": 0}
    d = direction[sel]
    mfe = np.where(d > 0, up[sel], dn[sel])
    mae = np.where(d > 0, dn[sel], up[sel])
    tot = mae.sum()
    return {
        "n": int(sel.sum()),
        "mfe_gt_mae": float((mfe > mae).mean() * 100),
        "ratio": float(mfe.sum() / tot) if tot > 0 else float("nan"),
        "median_ratio": float(np.median(np.where(mae > 0, mfe / mae, np.nan))),
        "mean_mfe": float(mfe.mean()),
        "mean_mae": float(mae.mean()),
        "median_mfe": float(np.median(mfe)),
        "median_mae": float(np.median(mae)),
    }


# ---------------------------------------------------------------------
# Effective sample size
# ---------------------------------------------------------------------

def clustering(index: pd.DatetimeIndex, positions: np.ndarray,
               horizon: int) -> dict:
    """How independent are these entries really?"""
    if positions.size == 0:
        return {"raw": 0, "days": 0, "overlapping": 0, "effective": 0}
    stamps = index[positions]
    days = pd.Index(stamps).normalize()
    gaps = np.diff(positions)
    overlapping = int((gaps < horizon).sum())
    # Greedy non-overlapping selection: the classic effective-sample proxy
    # for overlapping forward windows.
    effective, last = 0, -10**9
    for p in positions:
        if p - last >= horizon:
            effective += 1
            last = p
    return {
        "raw": int(positions.size),
        "days": int(days.nunique()),
        "per_day": float(positions.size / max(1, days.nunique())),
        "overlapping": overlapping,
        "effective": effective,
    }


def fingerprint(values) -> str:
    return hashlib.sha256(np.asarray(values).tobytes()).hexdigest()[:12]


def replay_extras(bars, cfg, *, chunk: int = 200,
                  context: int = LIVE_CONTEXT_BARS, symbol: str = "NIFTY"):
    """Raw per-bar SMC/regime arrays, same live-equivalent replay.

    The Conditions dataclass only exposes the ALREADY-WINDOWED forms
    (`struct_bull` is "(ranging AND recent CHoCH) OR (trending AND recent
    BOS)"). Testing whether the architecture should be sequential rather than
    a same-bar conjunction needs the underlying events themselves.
    """
    from trading_bot.strategies.rsi_smc_options_buyer import structure as st
    from trading_bot.strategies.rsi_smc_options_buyer import regime as rg

    n = len(bars)
    out = {k: np.zeros(n, dtype=bool) for k in
           ("bos_up", "bos_dn", "choch_up", "choch_dn",
            "trending", "ranging", "in_bull_fvg", "in_bear_fvg",
            "in_bull_ob", "in_bear_ob")}
    start = 0
    while start < n:
        stop = min(start + chunk, n)
        lo = max(0, start - context)
        window = bars.iloc[lo:stop]
        if len(window) >= cfg.min_bars:
            st.clear_cache()
            v = st.build(window, cfg, symbol=symbol)
            r = rg.compute(window, cfg)
            off = start - lo
            out["bos_up"][start:stop] = (v.bos > 0)[off:]
            out["bos_dn"][start:stop] = (v.bos < 0)[off:]
            out["choch_up"][start:stop] = (v.choch > 0)[off:]
            out["choch_dn"][start:stop] = (v.choch < 0)[off:]
            out["trending"][start:stop] = np.asarray(r.trending, bool)[off:]
            out["ranging"][start:stop] = np.asarray(r.ranging, bool)[off:]
            for k in ("in_bull_fvg", "in_bear_fvg", "in_bull_ob", "in_bear_ob"):
                out[k][start:stop] = np.asarray(getattr(v, k), bool)[off:]
        start = stop
    return out


def onset(mask: np.ndarray) -> np.ndarray:
    """First bar of each run of True -- turns a windowed flag into an event."""
    m = np.asarray(mask, dtype=bool)
    out = m.copy()
    out[1:] = m[1:] & ~m[:-1]
    return out


def recent(mask: np.ndarray, window: int) -> np.ndarray:
    m = np.asarray(mask, dtype=bool)
    out = m.copy()
    for k in range(1, max(1, int(window))):
        if k >= m.shape[0]:
            break
        sh = np.zeros(m.shape[0], dtype=bool)
        sh[k:] = m[:-k]
        out |= sh
    return out


def ordered_after(first: np.ndarray, second: np.ndarray, window: int) -> np.ndarray:
    """True at bar i when `second` fires at i and `first` fired within the
    preceding `window` bars -- i.e. genuine SEQUENCE, not co-occurrence."""
    return np.asarray(second, bool) & recent(np.asarray(first, bool), window + 1)
