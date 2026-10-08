"""CM_Ultimate_MA_MTF_V2 (ChrisMoody Ultimate Moving Average Multi-Timeframe V2).

Faithful pure-Python implementation of ChrisMoody's TradingView indicator.
Supports all 8 moving average calculation models:
1 = SMA
2 = EMA
3 = WMA
4 = HullMA
5 = VWMA
6 = RMA
7 = TEMA
8 = Tilson T3

Configured with the exact parameters provided:
- 1st MA: Length 20, Type 2 (EMA), Change color on direction = True, Color smoothing = 2
- 2nd MA: Length 9, Type 2 (EMA), Change color on direction = True
- Show price crossing 2nd MA = True (Highlights crossing bars)
- Show price crossing 1st MA = False
- Tilson T3 Factors = 7 (0.7)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CMUltimateMASettings:
    """Exact settings matching the user's CM_Ultimate_MA_MTF_V2 configuration."""

    use_current_res: bool = True
    custom_res: str = "1 day"

    # 1st Moving Average (Base Trend)
    ma1_len: int = 20
    ma1_factor_t3: float = 7.0  # 7 * 0.10 = 0.70
    ma1_type: int = 2  # 1=SMA, 2=EMA, 3=WMA, 4=HullMA, 5=VWMA, 6=RMA, 7=TEMA, 8=Tilson T3
    show_price_crossing_ma1: bool = False
    change_color_ma1: bool = True
    color_smoothing: int = 2

    # 2nd Moving Average (Fast Signal)
    optional_2nd_ma: bool = True
    show_price_crossing_ma2: bool = True
    ma2_len: int = 9
    ma2_factor_t3: float = 7.0
    ma2_type: int = 2  # 2 = EMA
    change_color_ma2: bool = True

    # Cross alerts / dots
    warn_dots_without_plot: bool = False
    warn_cross_without_plot: bool = False
    show_dots_on_cross: bool = False


DEFAULT_CM_ULTIMATE_MA_SETTINGS = CMUltimateMASettings()


def _wma(series: pd.Series, length: int) -> pd.Series:
    """Weighted Moving Average (WMA)."""
    if length <= 1:
        return series.copy()
    weights = np.arange(1, length + 1, dtype=float)
    w_sum = weights.sum()

    # Fast convolution using rolling window
    def _apply_wma(window: np.ndarray) -> float:
        return float(np.dot(window, weights) / w_sum)

    return series.rolling(window=length).apply(_apply_wma, raw=True)


def _hull_ma(series: pd.Series, length: int) -> pd.Series:
    """Hull Moving Average (HMA): wma(2*wma(src, len/2) - wma(src, len), round(sqrt(len)))."""
    half_len = max(1, int(length / 2))
    sqrt_len = max(1, int(round(np.sqrt(length))))
    diff = 2.0 * _wma(series, half_len) - _wma(series, length)
    return _wma(diff, sqrt_len)


def _vwma(price: pd.Series, volume: Optional[pd.Series], length: int) -> pd.Series:
    """Volume Weighted Moving Average (VWMA). Fallbacks to SMA if volume is unavailable."""
    if volume is None or (volume == 0).all():
        return price.rolling(window=length).mean()
    pv = price * volume
    vol_sum = volume.rolling(window=length).sum()
    pv_sum = pv.rolling(window=length).sum()
    return pv_sum / (vol_sum + 1e-9)


def _rma(series: pd.Series, length: int) -> pd.Series:
    """Running Moving Average (RMA / Wilder's MA): ewm(alpha=1/length, adjust=False)."""
    return series.ewm(alpha=1.0 / length, adjust=False).mean()


def _tema(series: pd.Series, length: int) -> pd.Series:
    """Triple Exponential Moving Average (TEMA)."""
    e1 = series.ewm(span=length, adjust=False).mean()
    e2 = e1.ewm(span=length, adjust=False).mean()
    e3 = e2.ewm(span=length, adjust=False).mean()
    return 3.0 * (e1 - e2) + e3


def _tilson_t3(series: pd.Series, length: int, factor_t3: float) -> pd.Series:
    """Tilson T3 Moving Average."""
    factor = factor_t3 * 0.10

    def _gd(s: pd.Series) -> pd.Series:
        e1 = s.ewm(span=length, adjust=False).mean()
        e2 = e1.ewm(span=length, adjust=False).mean()
        return e1 * (1.0 + factor) - e2 * factor

    gd1 = _gd(series)
    gd2 = _gd(gd1)
    return _gd(gd2)


def compute_ma_by_type(
    series: pd.Series,
    ma_type: int,
    length: int,
    factor_t3: float = 7.0,
    volume: Optional[pd.Series] = None,
) -> pd.Series:
    """Calculate moving average according to ChrisMoody type selection (1 to 8)."""
    if length <= 0:
        raise ValueError(f"MA length must be positive, got {length}")

    if ma_type == 1:  # SMA
        return series.rolling(window=length).mean()
    elif ma_type == 2:  # EMA
        return series.ewm(span=length, adjust=False).mean()
    elif ma_type == 3:  # WMA
        return _wma(series, length)
    elif ma_type == 4:  # HullMA
        return _hull_ma(series, length)
    elif ma_type == 5:  # VWMA
        return _vwma(series, volume, length)
    elif ma_type == 6:  # RMA
        return _rma(series, length)
    elif ma_type == 7:  # TEMA
        return _tema(series, length)
    elif ma_type == 8:  # Tilson T3
        return _tilson_t3(series, length, factor_t3)
    else:
        raise ValueError(f"Unknown MA type {ma_type}. Must be 1-8.")


def cm_ultimate_moving_average(
    df: pd.DataFrame,
    ma1_len: int = DEFAULT_CM_ULTIMATE_MA_SETTINGS.ma1_len,
    ma1_type: int = DEFAULT_CM_ULTIMATE_MA_SETTINGS.ma1_type,
    ma1_factor_t3: float = DEFAULT_CM_ULTIMATE_MA_SETTINGS.ma1_factor_t3,
    change_color_ma1: bool = DEFAULT_CM_ULTIMATE_MA_SETTINGS.change_color_ma1,
    color_smoothing: int = DEFAULT_CM_ULTIMATE_MA_SETTINGS.color_smoothing,
    show_price_crossing_ma1: bool = DEFAULT_CM_ULTIMATE_MA_SETTINGS.show_price_crossing_ma1,
    optional_2nd_ma: bool = DEFAULT_CM_ULTIMATE_MA_SETTINGS.optional_2nd_ma,
    ma2_len: int = DEFAULT_CM_ULTIMATE_MA_SETTINGS.ma2_len,
    ma2_type: int = DEFAULT_CM_ULTIMATE_MA_SETTINGS.ma2_type,
    ma2_factor_t3: float = DEFAULT_CM_ULTIMATE_MA_SETTINGS.ma2_factor_t3,
    change_color_ma2: bool = DEFAULT_CM_ULTIMATE_MA_SETTINGS.change_color_ma2,
    show_price_crossing_ma2: bool = DEFAULT_CM_ULTIMATE_MA_SETTINGS.show_price_crossing_ma2,
    show_dots_on_cross: bool = DEFAULT_CM_ULTIMATE_MA_SETTINGS.show_dots_on_cross,
) -> pd.DataFrame:
    """Calculate the complete CM_Ultimate_MA_MTF_V2 indicator.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV DataFrame containing at least 'open' and 'close'. 'volume' is optional.
    ma1_len : int, default 20
        Lookback length of 1st moving average.
    ma1_type : int, default 2
        1=SMA, 2=EMA, 3=WMA, 4=HullMA, 5=VWMA, 6=RMA, 7=TEMA, 8=Tilson T3.
    ma1_factor_t3 : float, default 7.0
        Tilson T3 factor (* 0.10) for 1st MA.
    change_color_ma1 : bool, default True
        Change direction color for 1st MA.
    color_smoothing : int, default 2
        Smoothing lookback shift for slope comparison.
    show_price_crossing_ma1 : bool, default False
        Highlight bar on price crossing 1st MA.
    optional_2nd_ma : bool, default True
        Enable 2nd moving average.
    ma2_len : int, default 9
        Lookback length of 2nd moving average.
    ma2_type : int, default 2
        MA type for 2nd MA (2=EMA).
    ma2_factor_t3 : float, default 7.0
        Tilson T3 factor (* 0.10) for 2nd MA.
    change_color_ma2 : bool, default True
        Change direction color for 2nd MA.
    show_price_crossing_ma2 : bool, default True
        Highlight bar on price crossing 2nd MA.
    show_dots_on_cross : bool, default False
        Flag cross points when MA1 and MA2 cross.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns:
        - `ma1`: 1st MA (20 EMA)
        - `ma1_dir`: Direction of MA1 (1 = Up, -1 = Down)
        - `ma1_color`: Direction color ("lime", "red", "aqua")
        - `ma2`: 2nd MA (9 EMA)
        - `ma2_dir`: Direction of MA2 (1 = Up, -1 = Down)
        - `ma2_color`: Direction color ("blue", "cyan")
        - `price_cross_ma1_up`: Open < MA1 and Close > MA1
        - `price_cross_ma1_down`: Open > MA1 and Close < MA1
        - `price_cross_ma2_up`: Open < MA2 and Close > MA2
        - `price_cross_ma2_down`: Open > MA2 and Close < MA2
        - `bar_highlight`: True if bar is highlighted (Yellow in style)
        - `ma_cross_up`: MA2 crossed above MA1
        - `ma_cross_down`: MA2 crossed below MA1
        - `ma_cross`: Either MA crossover occurred
    """
    close = df["close"]
    open_price = df["open"] if "open" in df.columns else close
    volume = df["volume"] if "volume" in df.columns else None

    # 1. First MA Calculation (Default: 20 EMA)
    out1 = compute_ma_by_type(close, ma1_type, ma1_len, ma1_factor_t3, volume)

    # Direction & Color for MA1
    smoothe = max(1, int(color_smoothing))
    shift_out1 = out1.shift(smoothe)
    ma1_up = out1 >= shift_out1
    ma1_down = out1 < shift_out1

    if change_color_ma1:
        ma1_dir = np.where(ma1_up, 1, np.where(ma1_down, -1, 0))
        ma1_color = np.where(ma1_up, "lime", np.where(ma1_down, "red", "aqua"))
    else:
        ma1_dir = np.ones(len(df), dtype=int)
        ma1_color = np.full(len(df), "aqua", dtype=object)

    # Price crossing MA1
    cr_up1 = (open_price < out1) & (close > out1)
    cr_down1 = (open_price > out1) & (close < out1)

    result_dict: dict[str, Union[pd.Series, np.ndarray]] = {
        "ma1": out1,
        "ma1_dir": ma1_dir,
        "ma1_color": ma1_color,
        "price_cross_ma1_up": cr_up1,
        "price_cross_ma1_down": cr_down1,
    }

    # 2. Second MA Calculation (Default: 9 EMA)
    if optional_2nd_ma:
        out2 = compute_ma_by_type(close, ma2_type, ma2_len, ma2_factor_t3, volume)

        shift_out2 = out2.shift(smoothe)
        ma2_up = out2 >= shift_out2
        ma2_down = out2 < shift_out2

        if change_color_ma2:
            ma2_dir = np.where(ma2_up, 1, np.where(ma2_down, -1, 0))
            ma2_color = np.where(ma2_up, "blue", np.where(ma2_down, "blue", "cyan"))
        else:
            ma2_dir = np.ones(len(df), dtype=int)
            ma2_color = np.full(len(df), "white", dtype=object)

        # Price crossing MA2
        cr_up2 = (open_price < out2) & (close > out2)
        cr_down2 = (open_price > out2) & (close < out2)

        # Cross of both MAs
        out1_arr = out1.to_numpy()
        out2_arr = out2.to_numpy()
        ma_cross_up = (out2_arr > out1_arr) & np.r_[False, out2_arr[:-1] <= out1_arr[:-1]]
        ma_cross_down = (out2_arr < out1_arr) & np.r_[False, out2_arr[:-1] >= out1_arr[:-1]]
        ma_cross = ma_cross_up | ma_cross_down

        result_dict["ma2"] = out2
        result_dict["ma2_dir"] = ma2_dir
        result_dict["ma2_color"] = ma2_color
        result_dict["price_cross_ma2_up"] = cr_up2
        result_dict["price_cross_ma2_down"] = cr_down2
        result_dict["ma_cross_up"] = ma_cross_up
        result_dict["ma_cross_down"] = ma_cross_down
        result_dict["ma_cross"] = ma_cross
    else:
        cr_up2 = pd.Series(False, index=df.index)
        cr_down2 = pd.Series(False, index=df.index)

    # 3. Bar color highlight logic:
    # Yellow highlight if spc (MA1 cross) or spc2 (MA2 cross) is active
    highlight = pd.Series(False, index=df.index)
    if show_price_crossing_ma1:
        highlight = highlight | cr_up1 | cr_down1
    if optional_2nd_ma and show_price_crossing_ma2:
        highlight = highlight | cr_up2 | cr_down2

    result_dict["bar_highlight"] = highlight

    return pd.DataFrame(result_dict, index=df.index)


# Convenient alias
CM_Ultimate_MA_MTF_V2 = cm_ultimate_moving_average
cm_ultimate_ma = cm_ultimate_moving_average
