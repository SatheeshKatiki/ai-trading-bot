"""Shared signal-post-processing helpers for strategy ``generate_signals``.

Currently just :func:`edge_trigger`. Kept in one place so the three strategies
that edge-trigger (``ema_rsi``, ``advanced_ai_ml``, ``ultra_meta_dip_swarm``)
share a single implementation that is provably free of the boolean-mask
``Series.__setitem__`` CPU-livelock (see the module-level notes in
``ema_rsi_strategy.py`` and ``docs/paper_trading_validation/anomaly_log.md``'s
2026-08-06/07/08/28 entries).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def edge_trigger(signals: pd.Series) -> pd.Series:
    """Collapse each run of an identical non-zero signal to its opening bar.

    Equivalent to ``signals[(signals == signals.shift(1)) & (signals != 0)] = 0``
    but computed on the underlying numpy array. The boolean-mask
    ``Series.__setitem__`` form routes through
    ``Series._set_with_engine -> Index.get_loc -> Series.__repr__`` when the
    index carries duplicate or non-monotonic labels (which the live 5-min
    candle cache can accumulate), turning an O(n) step into a per-row label
    lookup + full-Series repr — a CPU livelock that silenced the live engine
    for a whole session on 2026-08-28.

    A direction flip (``+1 -> -1``) is a new setup, not a duplicate, and is
    preserved. Position 0 is always kept (no previous bar). The result keeps
    ``signals``' index and ``int`` dtype.
    """
    values = np.asarray(signals, dtype=int)
    if values.shape[0] > 1:
        duplicate = np.zeros(values.shape[0], dtype=bool)
        duplicate[1:] = (values[1:] == values[:-1]) & (values[1:] != 0)
        values = np.where(duplicate, 0, values)
    return pd.Series(values, index=signals.index, dtype=int)
