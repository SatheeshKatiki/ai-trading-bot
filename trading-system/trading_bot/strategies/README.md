# Trading Strategies

All trading strategies live here. Each strategy exports a `generate_signals(df, **kwargs) → pd.Series` function that returns `1` (buy), `-1` (sell), or `0` (no trade).

## Strategy Registry

Strategies are auto-discovered by `registry.py`. Any `.py` file with a `generate_signals()` function and a `STRATEGY_NAME` variable is automatically registered at import time.

## Available Strategies

| Strategy | Type | Complexity | Best For |
|----------|------|-----------|----------|
| `ema_rsi` | Trend | ⭐⭐ | Beginners, stable trends |
| `enhanced_ai` | AI Hybrid | ⭐⭐⭐ | AI-filtered trades |
| `institutional_ema` | Institutional | ⭐⭐⭐⭐ | Options with SMC concepts |
| `advanced_ai` | ML | ⭐⭐⭐⭐ | XGBoost-driven decisions |
| `buy_the_dip` | Mean Reversion | ⭐⭐ | Oversold bounces |
| `premium_selection/` | 8-Layer Filter | ⭐⭐⭐⭐⭐ | Premium option selection |
| `momentum_strategy/` | Institutional Momentum | ⭐⭐⭐⭐⭐ | Nifty options with MTM trailing |

## Adding a New Strategy

1. Create a new `.py` file (or folder) in this directory
2. Define `STRATEGY_NAME = "your_name"`
3. Implement `generate_signals(df: pd.DataFrame, **kwargs) -> pd.Series`
4. The registry will auto-discover it on next startup
