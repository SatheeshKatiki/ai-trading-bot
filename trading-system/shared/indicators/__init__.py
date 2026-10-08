"""Technical indicator package.

Exports common indicators that can be used by both the live bot and the back-testing engine.
"""

from .ema import ema
from .rsi import (
    rsi,
    calculate_rsi_indicator,
    rsi_indicator,
    RSISettings,
    DEFAULT_RSI_SETTINGS,
)
from .cm_ultimate_ma import (
    cm_ultimate_moving_average,
    cm_ultimate_ma,
    CM_Ultimate_MA_MTF_V2,
    CMUltimateMASettings,
    DEFAULT_CM_ULTIMATE_MA_SETTINGS,
)
from .macd import macd
from .atr import atr
from .adx import adx, dmi
from .smc import smc_features
from .option_chain import simulate_option_chain_sentiment
from .supertrend import supertrend

__all__ = [
    "ema", "rsi", "calculate_rsi_indicator", "rsi_indicator",
    "RSISettings", "DEFAULT_RSI_SETTINGS",
    "cm_ultimate_moving_average", "cm_ultimate_ma", "CM_Ultimate_MA_MTF_V2",
    "CMUltimateMASettings", "DEFAULT_CM_ULTIMATE_MA_SETTINGS",
    "macd", "atr",
    "adx", "dmi",
    "smc_features", "simulate_option_chain_sentiment", "supertrend",
]

