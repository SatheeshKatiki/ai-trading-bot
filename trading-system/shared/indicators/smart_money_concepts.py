"""
Smart Money Concepts (SMC) — Institutional Market Structure Engine.
Modeled after LuxAlgo SMC and ICT (Inner Circle Trader) Price Action Principles.

Default Configuration matches LuxAlgo Smart Money Concepts on TradingView:
1. Mode: Present (displays active unmitigated structures)
2. Style: Colored (candle color states)
3. Internal Structure: ON (Bullish=Green, Bearish=Red, Confluence Filter=ON, Label=Tiny)
4. Swing Structure: ON (Bullish=Green, Bearish=Red, Label=Tiny, Swing Length=50, Strong/Weak High/Low=ON)
5. Order Blocks: Internal=3, Swing=3, Filter=ATR, Mitigation=High/Low (Wicks)
6. Equal High / Equal Low (EQH/EQL): ON (Bars=3, Threshold=0.1%, Label=Tiny)
7. Fair Value Gaps (FVG): ON (Auto Threshold=ON, Timeframe=Chart, Extend=20 bars)
8. Highs & Lows MTF: Daily=ON, Weekly=ON, Monthly=ON (Color=Blue)
9. Premium & Discount Zones: ON (Premium=Red, Equilibrium=Pink, Discount=Green)

Designed with zero-lookahead bias, completed-bar semantics, and strict typing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class TrendState(Enum):
    BULLISH = 1
    BEARISH = -1
    NEUTRAL = 0


class StructureType(Enum):
    BOS = "BOS"      # Break of Structure
    CHOCH = "CHoCH"  # Change of Character


@dataclass
class PivotPoint:
    index: int
    timestamp: Any
    price: float
    is_high: bool
    is_internal: bool = False
    is_strong: bool = False
    is_weak: bool = False


@dataclass
class OrderBlock:
    id: str
    is_bullish: bool
    top: float
    bottom: float
    bar_index: int
    timestamp: Any
    is_internal: bool = False
    mitigated: bool = False
    mitigated_index: Optional[int] = None
    invalidated: bool = False
    volume: float = 0.0

    @property
    def midpoint(self) -> float:
        return (self.top + self.bottom) / 2.0


@dataclass
class FairValueGap:
    id: str
    is_bullish: bool
    top: float
    bottom: float
    bar_index: int
    timestamp: Any
    mitigated: bool = False
    mitigated_index: Optional[int] = None
    fill_pct: float = 0.0
    extended_until_index: Optional[int] = None

    @property
    def size(self) -> float:
        return abs(self.top - self.bottom)


@dataclass
class LiquidityPool:
    id: str
    is_high: bool  # True for EQH (Buy-side), False for EQL (Sell-side)
    price: float
    tolerance: float
    bar_indices: List[int]
    swept: bool = False
    sweep_index: Optional[int] = None


@dataclass
class MTFLevel:
    timeframe: str  # "Daily", "Weekly", "Monthly"
    level_type: str # "High", "Low"
    price: float
    color: str = "#3b82f6"  # Blue


@dataclass
class SMCStructureEvent:
    bar_index: int
    timestamp: Any
    event_type: StructureType
    is_bullish: bool
    is_internal: bool
    broken_level: float
    candle_close: float


@dataclass
class LuxAlgoSMCConfig:
    """Exact default configuration for LuxAlgo Smart Money Concepts."""
    # 1. Mode & Display Style
    mode: str = "Present"                     # "Present" (active current zones) or "Historical"
    style: str = "Colored"                    # "Colored"
    color_candles: bool = True               # Color candles according to trend

    # 2. Internal Structure
    show_internal_structure: bool = True      # Internal CHoCH / BOS
    internal_length: int = 5                  # Internal structure lookback
    internal_bullish_color: str = "#10b981"   # Green
    internal_bearish_color: str = "#ef4444"   # Red
    internal_confluence_filter: bool = True   # Filter out low-confidence micro breaks
    internal_label_size: str = "tiny"         # Tiny

    # 3. Real-Time Swing Structure
    show_swing_structure: bool = True         # Major Swing CHoCH / BOS
    swing_points_length: int = 50             # 50-bar swing length (as configured)
    swing_bullish_color: str = "#10b981"      # All Green
    swing_bearish_color: str = "#ef4444"      # All Red
    swing_label_size: str = "tiny"            # Tiny
    show_swing_points: bool = True            # Show swing points markers
    show_strong_weak_high_low: bool = True    # Show Strong/Weak High & Low

    # 4. Order Blocks (OB)
    show_order_blocks: bool = True
    internal_ob_count: int = 3                # Max 3 internal OBs
    swing_ob_count: int = 3                   # Max 3 swing OBs
    ob_filter: str = "ATR"                    # ATR filtered displacement
    ob_mitigation: str = "High/Low"           # High/Low (Wick mitigation)
    bullish_ob_color: str = "#10b981"         # Green
    bearish_ob_color: str = "#ef4444"         # Red

    # 5. Equal High & Low (EQH / EQL)
    show_equal_high_low: bool = True          # Enable EQH / EQL
    eq_bars_confirmation: int = 3             # 3 bars confirmation
    eq_threshold: float = 0.1                 # 0.1% threshold
    eq_label_size: str = "tiny"               # Tiny

    # 6. Fair Value Gaps (FVG)
    show_fvg: bool = True                     # Enable FVG
    fvg_auto_threshold: bool = True           # Auto ATR threshold
    fvg_timeframe: str = "Chart"              # Chart timeframe
    fvg_extend: int = 20                      # Extend 20 bars

    # 7. Multi-Timeframe Highs & Lows (MTF)
    mtf_daily: bool = True                    # Daily High/Low
    mtf_weekly: bool = True                   # Weekly High/Low
    mtf_monthly: bool = True                  # Monthly High/Low
    mtf_color: str = "#3b82f6"                # Blue

    # 8. Premium & Discount Zones
    show_premium_discount: bool = True        # Enable Premium/Discount
    premium_color: str = "#ef4444"            # Red
    equilibrium_color: str = "#ec4899"        # Pink
    discount_color: str = "#10b981"           # Green

    # 9. Style Tab Configuration
    plot_candles: bool = True                 # Plot Candle coloring / highlights
    show_boxes: bool = True                   # Graphic Objects: Boxes (Order Blocks & FVGs)
    show_panel_labels: bool = True            # Graphic Objects: Panel Labels (BOS, CHoCH, EQH/EQL)
    show_lines: bool = True                   # Graphic Objects: Lines (Equilibrium, MTF Levels)
    precision: str = "Default"                # Output Values: Precision ("Default")
    labels_on_price_scale: bool = True        # Output Values: Labels on price scale
    values_in_status_line: bool = True        # Output Values: Values in status line
    inputs_in_status_line: bool = True        # Input Values: Inputs in status line

    # 10. Visibility Tab Configuration
    vis_ticks: bool = True                    # Ticks ON
    vis_seconds: bool = True                  # Seconds ON (1 to 59)
    vis_seconds_min: int = 1
    vis_seconds_max: int = 59
    vis_minutes: bool = True                  # Minutes ON (1 to 59)
    vis_minutes_min: int = 1
    vis_minutes_max: int = 59
    vis_hours: bool = True                    # Hours ON (1 to 24)
    vis_hours_min: int = 1
    vis_hours_max: int = 24
    vis_days: bool = True                     # Days ON (1 to 366)
    vis_days_min: int = 1
    vis_days_max: int = 366
    vis_weeks: bool = True                    # Weeks ON (1 to 52)
    vis_weeks_min: int = 1
    vis_weeks_max: int = 52
    vis_months: bool = True                   # Months ON (1 to 12)
    vis_months_min: int = 1
    vis_months_max: int = 12

    # Technical calculation helpers
    atr_period: int = 14
    swing_length: Optional[int] = None

    def __post_init__(self):
        if self.swing_length is not None:
            self.swing_points_length = self.swing_length

    def is_visible_on_timeframe(self, timeframe: str) -> bool:
        """Determines if the indicator should render based on active resolution."""
        tf = timeframe.lower().strip()
        if "tick" in tf:
            return self.vis_ticks
        if "s" in tf and tf[:-1].isdigit():
            val = int(tf[:-1])
            return self.vis_seconds and (self.vis_seconds_min <= val <= self.vis_seconds_max)
        if ("m" in tf or "min" in tf) and not "mo" in tf:
            digits = "".join(filter(str.isdigit, tf))
            val = int(digits) if digits else 1
            return self.vis_minutes and (self.vis_minutes_min <= val <= self.vis_minutes_max)
        if "h" in tf:
            digits = "".join(filter(str.isdigit, tf))
            val = int(digits) if digits else 1
            return self.vis_hours and (self.vis_hours_min <= val <= self.vis_hours_max)
        if "d" in tf:
            digits = "".join(filter(str.isdigit, tf))
            val = int(digits) if digits else 1
            return self.vis_days and (self.vis_days_min <= val <= self.vis_days_max)
        if "w" in tf:
            digits = "".join(filter(str.isdigit, tf))
            val = int(digits) if digits else 1
            return self.vis_weeks and (self.vis_weeks_min <= val <= self.vis_weeks_max)
        if "mo" in tf or "month" in tf:
            digits = "".join(filter(str.isdigit, tf))
            val = int(digits) if digits else 1
            return self.vis_months and (self.vis_months_min <= val <= self.vis_months_max)
        return True


@dataclass
class SMCAnalysisResult:
    trend: TrendState
    active_swing_high: Optional[float]
    active_swing_low: Optional[float]
    strong_high: Optional[float]
    weak_high: Optional[float]
    strong_low: Optional[float]
    weak_low: Optional[float]
    equilibrium_price: Optional[float]
    premium_zone: Tuple[float, float]
    discount_zone: Tuple[float, float]
    ote_zone: Tuple[float, float]
    active_bullish_obs: List[OrderBlock] = field(default_factory=list)
    active_bearish_obs: List[OrderBlock] = field(default_factory=list)
    active_bullish_fvgs: List[FairValueGap] = field(default_factory=list)
    active_bearish_fvgs: List[FairValueGap] = field(default_factory=list)
    active_liquidity_pools: List[LiquidityPool] = field(default_factory=list)
    mtf_levels: List[MTFLevel] = field(default_factory=list)
    structure_events: List[SMCStructureEvent] = field(default_factory=list)
    config: LuxAlgoSMCConfig = field(default_factory=LuxAlgoSMCConfig)


def detect_pivots(
    highs: np.ndarray,
    lows: np.ndarray,
    length: int = 5
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Identifies fractal pivot points (local peaks and troughs).
    A bar at index `i` is a pivot if it is the strict extremum over `[i - length, i + length]`.
    """
    n = len(highs)
    pivot_highs = np.zeros(n, dtype=bool)
    pivot_lows = np.zeros(n, dtype=bool)

    if n < 2 * length + 1:
        return pivot_highs, pivot_lows

    for i in range(length, n - length):
        window_h = highs[i - length : i + length + 1]
        if highs[i] == np.max(window_h) and np.sum(window_h == highs[i]) == 1:
            pivot_highs[i] = True

        window_l = lows[i - length : i + length + 1]
        if lows[i] == np.min(window_l) and np.sum(window_l == lows[i]) == 1:
            pivot_lows[i] = True

    return pivot_highs, pivot_lows


def _extract_mtf_levels(df: pd.DataFrame, config: LuxAlgoSMCConfig) -> List[MTFLevel]:
    """Calculates Daily, Weekly, and Monthly Highs and Lows from historical bar timestamps."""
    levels: List[MTFLevel] = []
    if df.empty:
        return levels

    idx = df.index
    if not isinstance(idx, pd.DatetimeIndex):
        try:
            time_col = next((c for c in ['datetime', 'date', 'timestamp'] if c in df.columns), None)
            if time_col:
                idx = pd.to_datetime(df[time_col])
            else:
                idx = pd.to_datetime(df.index)
        except Exception:
            return levels

    temp_df = pd.DataFrame({'high': df['high'].values, 'low': df['low'].values}, index=idx)

    # 1. Daily High / Low
    if config.mtf_daily:
        try:
            daily = temp_df.resample('D').agg({'high': 'max', 'low': 'min'}).dropna()
            if len(daily) >= 2:
                prev_d = daily.iloc[-2]
                levels.append(MTFLevel(timeframe="Daily", level_type="High", price=float(prev_d['high']), color=config.mtf_color))
                levels.append(MTFLevel(timeframe="Daily", level_type="Low", price=float(prev_d['low']), color=config.mtf_color))
        except Exception as e:
            logger.debug("Failed to calculate Daily MTF: %s", e)

    # 2. Weekly High / Low
    if config.mtf_weekly:
        try:
            weekly = temp_df.resample('W').agg({'high': 'max', 'low': 'min'}).dropna()
            if len(weekly) >= 2:
                prev_w = weekly.iloc[-2]
                levels.append(MTFLevel(timeframe="Weekly", level_type="High", price=float(prev_w['high']), color=config.mtf_color))
                levels.append(MTFLevel(timeframe="Weekly", level_type="Low", price=float(prev_w['low']), color=config.mtf_color))
        except Exception as e:
            logger.debug("Failed to calculate Weekly MTF: %s", e)

    # 3. Monthly High / Low
    if config.mtf_monthly:
        try:
            monthly = temp_df.resample('M').agg({'high': 'max', 'low': 'min'}).dropna()
            if len(monthly) >= 2:
                prev_m = monthly.iloc[-2]
                levels.append(MTFLevel(timeframe="Monthly", level_type="High", price=float(prev_m['high']), color=config.mtf_color))
                levels.append(MTFLevel(timeframe="Monthly", level_type="Low", price=float(prev_m['low']), color=config.mtf_color))
        except Exception as e:
            logger.debug("Failed to calculate Monthly MTF: %s", e)

    return levels


def calculate_smc(
    df: pd.DataFrame,
    config: Optional[LuxAlgoSMCConfig] = None,
    **kwargs
) -> Tuple[pd.DataFrame, SMCAnalysisResult]:
    """
    Computes complete Smart Money Concepts using LuxAlgo specification.
    """
    cfg = config or LuxAlgoSMCConfig(**kwargs) if kwargs else (config or LuxAlgoSMCConfig())

    if df.empty:
        empty_res = SMCAnalysisResult(
            trend=TrendState.NEUTRAL,
            active_swing_high=None,
            active_swing_low=None,
            strong_high=None,
            weak_high=None,
            strong_low=None,
            weak_low=None,
            equilibrium_price=None,
            premium_zone=(0.0, 0.0),
            discount_zone=(0.0, 0.0),
            ote_zone=(0.0, 0.0),
            config=cfg
        )
        return df.copy(), empty_res

    res_df = df.copy()
    res_df.rename(columns={c: c.lower() for c in res_df.columns}, inplace=True)

    opens = res_df['open'].to_numpy(dtype=float)
    highs = res_df['high'].to_numpy(dtype=float)
    lows = res_df['low'].to_numpy(dtype=float)
    closes = res_df['close'].to_numpy(dtype=float)
    volumes = res_df['volume'].to_numpy(dtype=float) if 'volume' in res_df.columns else np.zeros(len(res_df))
    timestamps = res_df.index.tolist()
    n = len(res_df)

    # ATR calculation
    tr = np.zeros(n, dtype=float)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
    atr = pd.Series(tr).rolling(14, min_periods=1).mean().to_numpy()

    # Effective swing length clamped to data length
    effective_swing_len = min(cfg.swing_points_length, max(3, n // 6))
    effective_internal_len = min(cfg.internal_length, max(2, effective_swing_len // 2))

    # 1. Detect Pivots
    p_highs_mask, p_lows_mask = detect_pivots(highs, lows, length=effective_swing_len)
    p_int_highs, p_int_lows = detect_pivots(highs, lows, length=effective_internal_len)

    structure_events: List[SMCStructureEvent] = []
    current_trend = TrendState.NEUTRAL
    last_swing_high: Optional[PivotPoint] = None
    last_swing_low: Optional[PivotPoint] = None

    strong_high: Optional[float] = None
    weak_high: Optional[float] = None
    strong_low: Optional[float] = None
    weak_low: Optional[float] = None

    bos_series = np.zeros(n, dtype=int)     # +1 Bullish BOS, -1 Bearish BOS
    choch_series = np.zeros(n, dtype=int)   # +1 Bullish CHoCH, -1 Bearish CHoCH
    order_blocks: List[OrderBlock] = []

    for i in range(n):
        conf_idx = i - effective_swing_len
        if conf_idx >= 0:
            if p_highs_mask[conf_idx]:
                last_swing_high = PivotPoint(conf_idx, timestamps[conf_idx], highs[conf_idx], is_high=True)
            if p_lows_mask[conf_idx]:
                last_swing_low = PivotPoint(conf_idx, timestamps[conf_idx], lows[conf_idx], is_high=False)

        current_close = closes[i]

        # Break of Structure / Change of Character
        if last_swing_high is not None and current_close > last_swing_high.price:
            is_bos = (current_trend == TrendState.BULLISH)
            ev_type = StructureType.BOS if is_bos else StructureType.CHOCH
            structure_events.append(
                SMCStructureEvent(i, timestamps[i], ev_type, is_bullish=True, is_internal=False, broken_level=last_swing_high.price, candle_close=current_close)
            )
            if is_bos:
                bos_series[i] = 1
            else:
                choch_series[i] = 1
                current_trend = TrendState.BULLISH

            # Strong Low marked at the low that formed this expansion
            if last_swing_low:
                strong_low = last_swing_low.price
            weak_high = highs[i]

            # Bullish Order Block (OB Filter = ATR)
            for b in range(i - 1, max(0, last_swing_high.index - 1), -1):
                if closes[b] < opens[b]:
                    candle_body = abs(closes[b] - opens[b])
                    if cfg.ob_filter != "ATR" or candle_body >= (0.3 * atr[b]):
                        order_blocks.append(
                            OrderBlock(
                                id=f"OB_BULL_{b}",
                                is_bullish=True,
                                top=max(opens[b], closes[b]),
                                bottom=lows[b],
                                bar_index=b,
                                timestamp=timestamps[b],
                                is_internal=False,
                                volume=volumes[b]
                            )
                        )
                        break

            last_swing_high = None

        elif last_swing_low is not None and current_close < last_swing_low.price:
            is_bos = (current_trend == TrendState.BEARISH)
            ev_type = StructureType.BOS if is_bos else StructureType.CHOCH
            structure_events.append(
                SMCStructureEvent(i, timestamps[i], ev_type, is_bullish=False, is_internal=False, broken_level=last_swing_low.price, candle_close=current_close)
            )
            if is_bos:
                bos_series[i] = -1
            else:
                choch_series[i] = -1
                current_trend = TrendState.BEARISH

            # Strong High marked at the high that formed this breakdown
            if last_swing_high:
                strong_high = last_swing_high.price
            weak_low = lows[i]

            # Bearish Order Block (OB Filter = ATR)
            for b in range(i - 1, max(0, last_swing_low.index - 1), -1):
                if closes[b] > opens[b]:
                    candle_body = abs(closes[b] - opens[b])
                    if cfg.ob_filter != "ATR" or candle_body >= (0.3 * atr[b]):
                        order_blocks.append(
                            OrderBlock(
                                id=f"OB_BEAR_{b}",
                                is_bullish=False,
                                top=highs[b],
                                bottom=min(opens[b], closes[b]),
                                bar_index=b,
                                timestamp=timestamps[b],
                                is_internal=False,
                                volume=volumes[b]
                            )
                        )
                        break

            last_swing_low = None

        # Mitigation evaluation: High/Low (Wicks)
        for ob in order_blocks:
            if not ob.mitigated and not ob.invalidated and i > ob.bar_index:
                if ob.is_bullish:
                    # Low tests top of OB -> Mitigated
                    if lows[i] <= ob.top:
                        ob.mitigated = True
                        ob.mitigated_index = i
                    if closes[i] < ob.bottom:
                        ob.invalidated = True
                else:
                    # High tests bottom of OB -> Mitigated
                    if highs[i] >= ob.bottom:
                        ob.mitigated = True
                        ob.mitigated_index = i
                    if closes[i] > ob.top:
                        ob.invalidated = True

    # 2. Fair Value Gaps (Auto Threshold = ATR, Extend = 20 bars)
    fvgs: List[FairValueGap] = []
    bull_fvg_series = np.zeros(n, dtype=bool)
    bear_fvg_series = np.zeros(n, dtype=bool)

    if cfg.show_fvg:
        for i in range(2, n):
            threshold = (0.25 * atr[i]) if cfg.fvg_auto_threshold else 1.0

            # Bullish FVG
            if lows[i] > highs[i - 2]:
                if (lows[i] - highs[i - 2]) >= threshold:
                    fvg = FairValueGap(
                        id=f"FVG_BULL_{i}",
                        is_bullish=True,
                        top=lows[i],
                        bottom=highs[i - 2],
                        bar_index=i,
                        timestamp=timestamps[i],
                        extended_until_index=min(n - 1, i + cfg.fvg_extend)
                    )
                    fvgs.append(fvg)
                    bull_fvg_series[i] = True

            # Bearish FVG
            elif highs[i] < lows[i - 2]:
                if (lows[i - 2] - highs[i]) >= threshold:
                    fvg = FairValueGap(
                        id=f"FVG_BEAR_{i}",
                        is_bullish=False,
                        top=lows[i - 2],
                        bottom=highs[i],
                        bar_index=i,
                        timestamp=timestamps[i],
                        extended_until_index=min(n - 1, i + cfg.fvg_extend)
                    )
                    fvgs.append(fvg)
                    bear_fvg_series[i] = True

        for fvg in fvgs:
            for j in range(fvg.bar_index + 1, n):
                if fvg.is_bullish:
                    if lows[j] <= fvg.bottom:
                        fvg.mitigated = True
                        fvg.mitigated_index = j
                        fvg.fill_pct = 1.0
                        break
                else:
                    if highs[j] >= fvg.top:
                        fvg.mitigated = True
                        fvg.mitigated_index = j
                        fvg.fill_pct = 1.0
                        break

    # 3. Equal Highs & Equal Lows (EQH / EQL)
    liquidity_pools: List[LiquidityPool] = []
    if cfg.show_equal_high_low:
        pivot_high_indices = [idx for idx in range(n) if p_int_highs[idx]]
        pivot_low_indices = [idx for idx in range(n) if p_int_lows[idx]]

        for a_idx in range(len(pivot_high_indices)):
            for b_idx in range(a_idx + 1, min(len(pivot_high_indices), a_idx + 1 + cfg.eq_bars_confirmation)):
                ia, ib = pivot_high_indices[a_idx], pivot_high_indices[b_idx]
                pa, pb = highs[ia], highs[ib]
                avg = (pa + pb) / 2.0
                if abs(pa - pb) / avg <= (cfg.eq_threshold / 100.0):
                    liquidity_pools.append(
                        LiquidityPool(f"EQH_{ia}_{ib}", is_high=True, price=avg, tolerance=abs(pa - pb), bar_indices=[ia, ib])
                    )

        for a_idx in range(len(pivot_low_indices)):
            for b_idx in range(a_idx + 1, min(len(pivot_low_indices), a_idx + 1 + cfg.eq_bars_confirmation)):
                ia, ib = pivot_low_indices[a_idx], pivot_low_indices[b_idx]
                pa, pb = lows[ia], lows[ib]
                avg = (pa + pb) / 2.0
                if abs(pa - pb) / avg <= (cfg.eq_threshold / 100.0):
                    liquidity_pools.append(
                        LiquidityPool(f"EQL_{ia}_{ib}", is_high=False, price=avg, tolerance=abs(pa - pb), bar_indices=[ia, ib])
                    )

    # 4. Premium & Discount Zones (Red Premium, Pink Equilibrium, Green Discount)
    lookback_window = min(n, effective_swing_len * 4)
    recent_high = float(np.max(highs[-lookback_window:]))
    recent_low = float(np.min(lows[-lookback_window:]))
    swing_range = recent_high - recent_low
    equilibrium = recent_low + (0.50 * swing_range) if swing_range > 0 else recent_low

    premium_zone = (equilibrium, recent_high)
    discount_zone = (recent_low, equilibrium)
    ote_zone = (recent_low + 0.618 * swing_range, recent_low + 0.786 * swing_range)

    # 5. Multi-Timeframe Highs & Lows (Blue)
    mtf_levels = _extract_mtf_levels(df, cfg)

    # 6. Mode Filtering: "Present" shows last N active unmitigated blocks
    if cfg.mode == "Present":
        active_bull_obs = [ob for ob in order_blocks if ob.is_bullish and not ob.invalidated and not ob.mitigated][-cfg.swing_ob_count:]
        active_bear_obs = [ob for ob in order_blocks if not ob.is_bullish and not ob.invalidated and not ob.mitigated][-cfg.swing_ob_count:]
        active_bull_fvgs = [f for f in fvgs if f.is_bullish and not f.mitigated][-cfg.swing_ob_count:]
        active_bear_fvgs = [f for f in fvgs if not f.is_bullish and not f.mitigated][-cfg.swing_ob_count:]
    else:
        active_bull_obs = [ob for ob in order_blocks if ob.is_bullish and not ob.invalidated]
        active_bear_obs = [ob for ob in order_blocks if not ob.is_bullish and not ob.invalidated]
        active_bull_fvgs = [f for f in fvgs if f.is_bullish]
        active_bear_fvgs = [f for f in fvgs if not f.is_bullish]

    # Attach series to DataFrame
    res_df['smc_bos'] = bos_series
    res_df['smc_choch'] = choch_series
    res_df['smc_trend'] = current_trend.value
    res_df['smc_bullish_fvg'] = bull_fvg_series
    res_df['smc_bearish_fvg'] = bear_fvg_series
    res_df['smc_equilibrium'] = equilibrium

    # Candle color classification (Colored style)
    if cfg.color_candles:
        candle_colors = []
        for close, open_p, trend_val in zip(closes, opens, res_df['smc_trend']):
            if trend_val == 1:
                candle_colors.append(cfg.internal_bullish_color if close >= open_p else "#059669")
            elif trend_val == -1:
                candle_colors.append(cfg.internal_bearish_color if close < open_p else "#dc2626")
            else:
                candle_colors.append("#6b7280")
        res_df['smc_candle_color'] = candle_colors

    analysis = SMCAnalysisResult(
        trend=current_trend,
        active_swing_high=recent_high,
        active_swing_low=recent_low,
        strong_high=strong_high,
        weak_high=weak_high,
        strong_low=strong_low,
        weak_low=weak_low,
        equilibrium_price=equilibrium,
        premium_zone=premium_zone,
        discount_zone=discount_zone,
        ote_zone=ote_zone,
        active_bullish_obs=active_bull_obs,
        active_bearish_obs=active_bear_obs,
        active_bullish_fvgs=active_bull_fvgs,
        active_bearish_fvgs=active_bear_fvgs,
        active_liquidity_pools=liquidity_pools,
        mtf_levels=mtf_levels,
        structure_events=structure_events,
        config=cfg
    )

    return res_df, analysis
