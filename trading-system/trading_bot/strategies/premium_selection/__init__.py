"""Premium Trade Selection Package.

A production-grade, institutional-quality options trade filtering system
for Indian markets (NIFTY / BANKNIFTY / SENSEX / FINNIFTY).

Layers:
  1. Trend Filter        (EMA20/50/200 alignment + slope)
  2. Momentum Filter     (RSI + MACD + candle body strength)
  3. Volume Filter       (volume spike + consecutive participation)
  4. Volatility Filter   (ATR regime — not too quiet, not a spike)
  5. Market Structure    (Higher Highs/Lows, pullback-retest entries)
  6. No-Trade Guard      (time windows, choppy market, sideways)
  7. AI Confidence Gate  (minimum 75% AI score required)
  8. Options Selector    (ATM/ITM strike, expiry, lot size, symbol)
"""
from .signal_engine   import PremiumSignalEngine, PremiumSignal, generate_signals
from .options_selector import select_option, calculate_lots, OptionContract, INSTRUMENT_CONFIG

__all__ = [
    "PremiumSignalEngine",
    "PremiumSignal",
    "generate_signals",
    "select_option",
    "calculate_lots",
    "OptionContract",
    "INSTRUMENT_CONFIG",
]
