# AI Trading Bot — Project Map

> Institutional-grade AI-powered intraday trading platform for Indian markets.

## Architecture

```
AI Trading Bot/
│
├── frontend/                  # Next.js 16 UI (Port 3000)
│   ├── app/                   # Page routes
│   │   ├── page.tsx           # Dashboard (Mission Control)
│   │   ├── live/              # Live Trading Engine
│   │   ├── backtest/          # Backtesting Interface
│   │   ├── signals/           # AI Signal Monitor
│   │   ├── strategy/          # Strategy Parameter Tuning
│   │   ├── journal/           # Trading Journal (CRUD + localStorage)
│   │   ├── analytics/         # Performance Analytics
│   │   ├── broker/            # Broker Configuration
│   │   ├── risk/              # Risk Management Settings
│   │   └── settings/          # App Preferences
│   └── components/            # Shared UI (Sidebar, Header, ThemeProvider)
│
├── trading-system/            # Python Backend (Port 8000)
│   ├── api_bridge.py          # FastAPI — REST + WebSocket bridge
│   ├── trading_bot/           # Live trading engine
│   │   ├── main.py            # Async tick processor
│   │   └── strategies/        # 7 trading strategies
│   │       ├── ema_rsi_strategy.py
│   │       ├── enhanced_ai_strategy.py
│   │       ├── institutional_ema_strategy.py
│   │       ├── advanced_ai_ml_strategy.py
│   │       ├── buy_the_dip_strategy.py
│   │       ├── premium_selection/     # 8-layer institutional filter
│   │       ├── momentum_strategy/     # Nifty options momentum engine
│   │       └── registry.py           # Auto-discovery registry
│   ├── brokers/               # Broker abstraction (Fyers, Kite, Angel)
│   ├── shared/                # Core modules
│   │   ├── ai/                # XGBoost trade filter
│   │   ├── risk/              # Risk management engine
│   │   ├── exits/             # Smart exit engine
│   │   ├── alerts/            # Telegram notifications
│   │   ├── security/          # Audit, rate limiter, validator
│   │   └── indicators/        # Technical indicators (EMA, RSI, MACD, etc.)
│   ├── backtesting_engine/    # Historical backtester
│   ├── scripts/               # Utilities
│   │   ├── auth/              # Login & credential scripts
│   │   ├── run_backtest.py
│   │   ├── train_ai_model.py
│   │   └── fetch_data.py
│   ├── tests/                 # All test files
│   ├── config/                # Runtime configuration
│   ├── models/                # Trained ML models
│   ├── data/                  # Historical OHLCV data
│   ├── logs/                  # Runtime logs
│   ├── audit/                 # Security audit trail
│   └── deployment/            # Docker configs
│
└── docs/                      # Project documentation
```

## Key Commands

```bash
# Frontend
cd frontend && npm run dev

# Backend API
cd trading-system && uvicorn api_bridge:app --port 8000

# Fyers Login
cd trading-system && python scripts/auth/auto_login_fyers.py

# Run Backtest
cd trading-system && python scripts/run_backtest.py

# Train AI Model
cd trading-system && python scripts/train_ai_model.py
```

## Branch Naming

| Branch | Version |
|--------|---------|
| `main` | Stable release |
| `trading_bot_v1.2.0` | Foundation |
| `trading_bot_v1.3.0` | Strategies + Brokers |
| `trading_bot_v1.4.0` | Institutional Standard |
| `trading_bot_v1.5.0` | Current (Momentum Strategy + Terminal) |
