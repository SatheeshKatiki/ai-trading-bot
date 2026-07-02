# Trading System — Backend Engine

The core backend of the AI Trading Bot. This directory contains the complete trading infrastructure: strategies, brokers, risk management, AI models, and the API bridge that connects to the Next.js frontend.

## Directory Structure

```
trading-system/
│
├── api_bridge.py              # FastAPI server — connects frontend ↔ backend
│
├── trading_bot/               # Live trading engine
│   ├── main.py                # Bot entry point (async tick processor)
│   └── strategies/            # All trading strategies (see below)
│
├── brokers/                   # Broker abstraction layer (Fyers, Kite, Angel)
├── shared/                    # Shared modules (AI, Risk, Exits, Alerts, Security, Indicators)
├── backtesting_engine/        # Historical backtesting framework
├── dashboard/                 # Legacy Streamlit dashboard
│
├── scripts/                   # Utility scripts
│   ├── auth/                  # Authentication & credential management
│   ├── run_backtest.py        # CLI backtest runner
│   ├── train_ai_model.py      # XGBoost model trainer
│   └── fetch_data.py          # Historical data downloader
│
├── tests/                     # All test files
├── config/                    # Runtime configuration
├── models/                    # Trained ML model files (.pkl, .json)
├── data/                      # Historical OHLCV data (.csv)
├── logs/                      # Runtime log files
├── audit/                     # Security audit trail
└── deployment/                # Docker & systemd configs
```

## Trading Strategies

| Strategy | File | Description |
|----------|------|-------------|
| EMA + RSI | `ema_rsi_strategy.py` | Classic EMA crossover + RSI + SuperTrend |
| Enhanced AI | `enhanced_ai_strategy.py` | Multi-layer confirmation + AI filter |
| Advanced AI/ML | `advanced_ai_ml_strategy.py` | XGBoost ML predictions |
| Buy the Dip | `buy_the_dip_strategy.py` | Mean reversion on dips |
| Premium 8-Layer | `premium_selection/` | 8-layer institutional filter |
| **Institutional Momentum** | `momentum_strategy/` | **Multi-TF breakout + ITM options + MTM trailing** |

## Quick Start

```bash
# 1. Activate virtual environment
.\venv\Scripts\activate

# 2. Start the API bridge
uvicorn api_bridge:app --host 0.0.0.0 --port 8000

# 3. Run a backtest
python scripts/run_backtest.py

# 4. Auto-login to Fyers
python scripts/auth/auto_login_fyers.py
```