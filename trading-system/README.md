# 🚀 AI Intraday Trading System

A production-grade, highly scalable quantitative trading system built for the Indian Stock Market (NIFTY/BankNIFTY/Stocks). It features a robust live trading bot connected to the Fyers API, an advanced AI trade filter, institutional risk management, and a premium Streamlit dashboard.

---

## 🎯 Features

- **Live Trading Bot:** Async, event-driven architecture streaming ticks via Fyers API.
- **Advanced Strategies:** Includes EMA+RSI trend following, Options Directional Scalping, Bull Call Spreads, Bear Put Spreads, and Iron Condors.
- **AI Trade Filter:** Uses Scikit-learn (Random Forest / XGBoost) to score trade setups on 20+ custom price/volume/volatility features and auto-rejects low confidence signals.
- **Institutional Risk Engine:** Dynamic position sizing (Kelly Criterion), max drawdown kill-switches, consecutive loss halts, and volatility gating.
- **Smart Exit Engine:** ATR-based trailing stop-losses, partial profit booking, and automated End-of-Day (EOD) square-offs.
- **Backtesting & Validation Suite:** High-fidelity simulation with slippage/commissions, Walk-Forward Testing to prevent curve-fitting, and Monte Carlo simulation for Risk of Ruin analysis.
- **Telegram Alerts:** Real-time push notifications for executions, exits, and critical Risk-Off events.
- **Premium Dashboard:** Modern, glassmorphism UI with live metrics and historical charting.

---

## 🏗️ Folder Explanation

```bash
trading-system/
├── trading_bot/           # Live execution engine (main.py, api clients, strategy registry)
├── backtesting_engine/    # Simulation (run.py), Walk-Forward validation, Monte Carlo
├── shared/                # Core logic (AI filter, Risk Manager, Exits, Alerts, Indicators)
├── dashboard/             # Premium Streamlit UI (Live view & Backtest view)
├── deployment/            # Dockerfile, docker-compose.yml, and systemd services
├── data/                  # Historical OHLCV CSVs for backtesting
└── tests/                 # Unit testing suite
```

---

## 🛠️ Installation & Setup

1. **Clone the repository** and install requirements:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables:**
   Create a `.env` file in the root directory (use `.env.example` as a template):
   ```env
   FYERS_CLIENT_ID=your_client_id
   FYERS_SECRET_KEY=your_secret_key
   FYERS_REDIRECT_URI=http://localhost:8080/login
   LOG_LEVEL=INFO
   TELEGRAM_BOT_TOKEN=your_bot_token
   TELEGRAM_CHAT_ID=your_chat_id
   ```
   *Note: If Fyers API keys are left blank, the bot will run in Paper Trading (Synthetic) Mode!*

---

## 💻 Running the System

### 1. The Dashboard (UI)
To view live metrics, backtest strategies, and see AI confidence scores:
```bash
streamlit run dashboard/app.py
```
Open your browser to `http://localhost:8501`.

### 2. Live Trading Bot
To run the automated execution engine:
```bash
python -m trading_bot.main
```

### 3. Backtesting CLI
Run simulations natively via terminal:
```bash
python -m backtesting_engine.run --data-path data/NIFTY50.csv --initial-capital 100000
```

---

## ☁️ Deployment (Docker & AWS)

The system is ready for Linux VPS / AWS EC2 deployment via Docker.

**Using Docker Compose:**
```bash
cd deployment
docker-compose up -d --build
```
This will launch both the `ai_trading_bot` background worker and the `ai_trading_dashboard` UI.

**Using Systemd (Native Linux):**
Copy `deployment/bot.service` to `/etc/systemd/system/`, then run:
```bash
sudo systemctl enable bot
sudo systemctl start bot
```

---

## 🧠 AI System Details
The AI filter (`shared/ai/model.py`) is trained on forward-returns. It classifies 1-minute bars into 1 (Profitable Long), -1 (Profitable Short), or 0 (No Trade). Features include candle body ratios, ADX, Momentum, Volume SMA gaps, and RSI.

## 🛡️ Risk Management Details
The Risk Manager (`shared/risk/manager.py`) guarantees account survival by:
- Rejecting trades if current Volatility > `high_volatility_threshold` (e.g. 3.0 ATR).
- Activating a hard **Risk-Off** freeze if daily drawdown exceeds 5% or total drawdown exceeds 20%.

---
*Built for production algorithmic trading. Use with caution in live markets.*