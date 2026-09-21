"""
Fixed Range Volume Profile (FRVP) — Institutional Auction Market Theory Engine.
Modeled after TradingView's Fixed Range & Anchored Volume Profile tools.

Core Concepts:
1. Dynamic / Fixed Price Binning over user-defined or structural range
2. Proportional Candle Volume Distribution across High-Low span
3. Point of Control (POC): Price level holding the single largest concentration of volume
4. Value Area (VAH / VAL): Range representing 70% of total traded volume
5. High Volume Nodes (HVN - Institutional Acceptance) & Low Volume Nodes (LVN - Rejection)
6. Volume Delta: Up (Buyer-initiated) vs Down (Seller-initiated) volume per price bucket

Follows strict quantitative standards with no lookahead bias.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class VolumeProfileBin:
    bin_index: int
    price_low: float
    price_high: float
    price_mid: float
    total_volume: float
    up_volume: float
    down_volume: float
    delta: float  # up_volume - down_volume
    is_poc: bool = False
    is_in_value_area: bool = False


@dataclass
class VolumeProfileResult:
    poc_price: float
    vah_price: float  # Value Area High
    val_price: float  # Value Area Low
    total_volume: float
    value_area_volume: float
    value_area_pct: float
    range_high: float
    range_low: float
    bins: List[VolumeProfileBin] = field(default_factory=list)
    hvn_levels: List[float] = field(default_factory=list)  # High Volume Nodes
    lvn_levels: List[float] = field(default_factory=list)  # Low Volume Nodes

    def is_inside_value_area(self, price: float) -> bool:
        """Returns True if price is between VAL and VAH."""
        return self.val_price <= price <= self.vah_price

    def distance_to_poc_pct(self, price: float) -> float:
        """Percentage distance from current price to POC."""
        if self.poc_price == 0:
            return 0.0
        return ((price - self.poc_price) / self.poc_price) * 100.0


def calculate_fixed_range_volume_profile(
    df: pd.DataFrame,
    start_idx: Optional[int] = None,
    end_idx: Optional[int] = None,
    num_bins: int = 50,
    value_area_pct: float = 0.70
) -> VolumeProfileResult:
    """
    Computes Fixed Range Volume Profile over the specified bar range `[start_idx, end_idx]`.

    Parameters:
    -----------
    df : pd.DataFrame
        OHLCV DataFrame with columns ['open', 'high', 'low', 'close', 'volume'].
    start_idx : Optional[int]
        Start bar index (inclusive). If None, defaults to 0.
    end_idx : Optional[int]
        End bar index (inclusive). If None, defaults to len(df) - 1.
    num_bins : int
        Number of horizontal price buckets (default: 50).
    value_area_pct : float
        Fraction of volume defining the Value Area (default: 0.70 for 70%).

    Returns:
    --------
    VolumeProfileResult:
        Structured object containing POC, VAH, VAL, volume bins, and node levels.
    """
    if df.empty:
        return VolumeProfileResult(
            poc_price=0.0,
            vah_price=0.0,
            val_price=0.0,
            total_volume=0.0,
            value_area_volume=0.0,
            value_area_pct=value_area_pct,
            range_high=0.0,
            range_low=0.0
        )

    # Standardize column naming
    sub_df = df.copy()
    sub_df.rename(columns={c: c.lower() for c in sub_df.columns}, inplace=True)

    n = len(sub_df)
    s_idx = max(0, start_idx if start_idx is not None else 0)
    e_idx = min(n - 1, end_idx if end_idx is not None else n - 1)

    if s_idx > e_idx:
        s_idx, e_idx = e_idx, s_idx

    slice_df = sub_df.iloc[s_idx : e_idx + 1]
    if slice_df.empty:
        return VolumeProfileResult(0.0, 0.0, 0.0, 0.0, 0.0, value_area_pct, 0.0, 0.0)

    highs = slice_df['high'].to_numpy(dtype=float)
    lows = slice_df['low'].to_numpy(dtype=float)
    opens = slice_df['open'].to_numpy(dtype=float)
    closes = slice_df['close'].to_numpy(dtype=float)

    # If no volume reported (e.g. index data), fall back to candle range as synthetic volume weight
    if 'volume' in slice_df.columns and slice_df['volume'].sum() > 0:
        volumes = slice_df['volume'].to_numpy(dtype=float)
    else:
        volumes = np.maximum(highs - lows, 1.0)

    range_min = float(np.min(lows))
    range_max = float(np.max(highs))

    if range_max <= range_min:
        return VolumeProfileResult(range_min, range_min, range_min, float(np.sum(volumes)), float(np.sum(volumes)), value_area_pct, range_max, range_min)

    # Create price bin edges
    bin_edges = np.linspace(range_min, range_max, num_bins + 1)
    bin_step = (range_max - range_min) / num_bins

    bin_total_vol = np.zeros(num_bins, dtype=float)
    bin_up_vol = np.zeros(num_bins, dtype=float)
    bin_down_vol = np.zeros(num_bins, dtype=float)

    # Proportional volume distribution per candle across all overlapping price bins
    for b in range(len(slice_df)):
        b_low = lows[b]
        b_high = highs[b]
        b_open = opens[b]
        b_close = closes[b]
        b_vol = volumes[b]

        if b_vol <= 0:
            continue

        candle_span = max(b_high - b_low, 1e-6)

        # Buyer / Seller ratio
        if b_close >= b_open:
            up_ratio = 0.65 if b_close > b_open else 0.50
            down_ratio = 1.0 - up_ratio
        else:
            down_ratio = 0.65
            up_ratio = 1.0 - down_ratio

        # Find first and last bin this candle touches
        first_bin = max(0, min(num_bins - 1, int((b_low - range_min) / bin_step)))
        last_bin = max(0, min(num_bins - 1, int((b_high - range_min) / bin_step)))

        if first_bin == last_bin:
            bin_total_vol[first_bin] += b_vol
            bin_up_vol[first_bin] += b_vol * up_ratio
            bin_down_vol[first_bin] += b_vol * down_ratio
        else:
            for k in range(first_bin, last_bin + 1):
                k_low = bin_edges[k]
                k_high = bin_edges[k + 1]
                overlap = max(0.0, min(b_high, k_high) - max(b_low, k_low))
                k_fraction = overlap / candle_span
                k_vol = b_vol * k_fraction

                bin_total_vol[k] += k_vol
                bin_up_vol[k] += k_vol * up_ratio
                bin_down_vol[k] += k_vol * down_ratio

    total_vol = float(np.sum(bin_total_vol))
    if total_vol <= 0:
        return VolumeProfileResult(range_min, range_max, range_min, 0.0, 0.0, value_area_pct, range_max, range_min)

    # 1. Point of Control (POC)
    poc_idx = int(np.argmax(bin_total_vol))
    poc_price = (bin_edges[poc_idx] + bin_edges[poc_idx + 1]) / 2.0

    # 2. Value Area Calculation (70% Volume Expansion)
    target_va_volume = total_vol * value_area_pct
    current_va_volume = bin_total_vol[poc_idx]
    va_included_bins = {poc_idx}

    idx_up = poc_idx + 1
    idx_down = poc_idx - 1

    while current_va_volume < target_va_volume and (idx_up < num_bins or idx_down >= 0):
        vol_up = bin_total_vol[idx_up] if idx_up < num_bins else -1.0
        vol_down = bin_total_vol[idx_down] if idx_down >= 0 else -1.0

        if vol_up >= vol_down and idx_up < num_bins:
            va_included_bins.add(idx_up)
            current_va_volume += vol_up
            idx_up += 1
        elif idx_down >= 0:
            va_included_bins.add(idx_down)
            current_va_volume += vol_down
            idx_down -= 1
        else:
            break

    min_va_bin = min(va_included_bins)
    max_va_bin = max(va_included_bins)
    val_price = float(bin_edges[min_va_bin])
    vah_price = float(bin_edges[max_va_bin + 1])

    # 3. Construct Profile Bins & Detect HVN / LVN
    bins: List[VolumeProfileBin] = []
    mean_bin_vol = np.mean(bin_total_vol)
    hvn_threshold = mean_bin_vol * 1.40  # 40% above mean volume
    lvn_threshold = mean_bin_vol * 0.60  # 40% below mean volume

    hvn_levels: List[float] = []
    lvn_levels: List[float] = []

    for k in range(num_bins):
        k_mid = (bin_edges[k] + bin_edges[k + 1]) / 2.0
        is_poc = (k == poc_idx)
        is_in_va = (k in va_included_bins)

        bins.append(
            VolumeProfileBin(
                bin_index=k,
                price_low=bin_edges[k],
                price_high=bin_edges[k + 1],
                price_mid=k_mid,
                total_volume=float(bin_total_vol[k]),
                up_volume=float(bin_up_vol[k]),
                down_volume=float(bin_down_vol[k]),
                delta=float(bin_up_vol[k] - bin_down_vol[k]),
                is_poc=is_poc,
                is_in_value_area=is_in_va
            )
        )

        if bin_total_vol[k] >= hvn_threshold:
            hvn_levels.append(k_mid)
        elif bin_total_vol[k] <= lvn_threshold and bin_total_vol[k] > 0:
            lvn_levels.append(k_mid)

    return VolumeProfileResult(
        poc_price=poc_price,
        vah_price=vah_price,
        val_price=val_price,
        total_volume=total_vol,
        value_area_volume=float(current_va_volume),
        value_area_pct=value_area_pct,
        range_high=range_max,
        range_low=range_min,
        bins=bins,
        hvn_levels=hvn_levels,
        lvn_levels=lvn_levels
    )
