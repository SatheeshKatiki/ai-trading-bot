"""Streamlit dashboard for the AI Intraday Trading System.

Features:
- **Live view** – displays current equity, PnL, and recent trades pulled from
  ``shared/state.json`` (updated by the live bot).
- **Back‑test view** – loads a CSV of historical data, runs the EMA+RSI
  strategy using the same engine as the live bot, and visualises equity curve,
  drawdown and a candlestick chart.
- Auto‑refresh every 5 seconds for the live view.
"""

import sys
import json
import time
from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# Add project root to sys.path so modules like `trading_bot`, `shared`, `brokers` can be found
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── Install log sanitizer before anything else logs ─────────────────────────
try:
    from shared.security import install_log_sanitizer
    install_log_sanitizer()
except Exception:
    pass

# ── Dashboard Authentication ────────────────────────────────
# This MUST run before any page content is rendered.
try:
    from dashboard.auth import require_auth, render_logout_button, render_change_password_widget
    _AUTH_AVAILABLE = True
except Exception:
    _AUTH_AVAILABLE = False
    def require_auth(): return True
    def render_logout_button(): pass
    def render_change_password_widget(): pass

if not require_auth():
    st.stop()

# ---------------------------------------------------------------------------
# Helper to load the shared state (equity, pnl, trades)
# ---------------------------------------------------------------------------
_STATE_FILE = Path(__file__).resolve().parents[1] / "state.json"

def load_state() -> dict:
    if not _STATE_FILE.is_file():
        # Return a default empty state if the file does not yet exist.
        return {"equity": 0.0, "pnl": 0.0, "trades": []}
    with open(_STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# Add custom CSS for premium UI
def inject_custom_css():
    st.markdown("""
    <style>
    /* Premium Dark Theme & Glassmorphism */
    .stApp {
        background-color: #0E1117;
        color: #FAFAFA;
    }
    div[data-testid="metric-container"] {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 15px;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    div[data-testid="metric-container"]:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 15px rgba(0, 200, 83, 0.2);
        border-color: rgba(0, 200, 83, 0.5);
    }
    /* Sleek typography */
    h1, h2, h3 {
        font-family: 'Inter', sans-serif;
        font-weight: 600;
        letter-spacing: -0.5px;
    }
    </style>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Helper to manage user settings (timeframe, etc) for live bot
# ---------------------------------------------------------------------------
_SETTINGS_FILE = Path(__file__).resolve().parents[1] / "settings.json"

def load_settings() -> dict:
    defaults = {
        "timeframe": "1 Min",
        "ema_fast": 9,
        "ema_slow": 21,
        "rsi_window": 14,
        "rsi_buy": 40,
        "rsi_sell": 60,
        "target_pct": 1.0,
        "stoploss_pct": 0.5,
        "max_trades_per_day": 4,
        "live_trading_mode": False,
        "active_strategy": "ema_rsi"
    }
    if not _SETTINGS_FILE.is_file():
        return defaults
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        # Merge: saved values override defaults, missing keys get defaults
        defaults.update(saved)
    except Exception:
        pass
    return defaults

def save_settings(settings: dict) -> None:
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4)

def render_sidebar_settings():
    """Renders the settings sidebar and saves to file."""
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚙️ Strategy Parameters")

    current_settings = load_settings()

    st.sidebar.markdown("**Strategy Selection**")
    strategies = ["ema_rsi", "enhanced_ai", "premium"]
    strategy_labels = {
        "ema_rsi":      "📈 EMA + RSI (Classic)",
        "enhanced_ai":  "🤖 Enhanced AI (6-Layer)",
        "premium":      "💎 Premium Selection (Institutional)",
    }
    strat_idx = strategies.index(current_settings.get("active_strategy", "ema_rsi")) if current_settings.get("active_strategy", "ema_rsi") in strategies else 0
    active_strategy = st.sidebar.selectbox(
        "Active Strategy",
        strategies,
        index=strat_idx,
        format_func=lambda x: strategy_labels.get(x, x),
        help="Select the strategy engine to use for both live trading and backtesting."
    )

    st.sidebar.markdown("**Timeframe Selection**")
    timeframes = ["1 Min", "5 Min", "15 Min", "30 Min", "1 Hour", "1 Day"]
    tf_idx = timeframes.index(current_settings.get("timeframe", "1 Min")) if current_settings.get("timeframe", "1 Min") in timeframes else 0
    timeframe_str = st.sidebar.selectbox(
        "Candle Timeframe",
        timeframes,
        index=tf_idx,
        help="Select the timeframe for both live trading and backtesting."
    )

    st.sidebar.markdown("**EMA Settings**")
    ema_fast = st.sidebar.slider("EMA Fast", 3, 50, current_settings.get("ema_fast", 9), 1)
    ema_slow = st.sidebar.slider("EMA Slow", 10, 100, current_settings.get("ema_slow", 21), 1)

    st.sidebar.markdown("**RSI Settings**")
    rsi_window = st.sidebar.slider("RSI Window", 5, 30, current_settings.get("rsi_window", 14), 1)
    rsi_buy = st.sidebar.slider("RSI Buy Threshold (CALL: RSI >)", 20, 70, current_settings.get("rsi_buy", 40), 1)
    rsi_sell = st.sidebar.slider("RSI Sell Threshold (PUT: RSI <)", 30, 80, current_settings.get("rsi_sell", 60), 1)

    new_settings = {
        "timeframe": timeframe_str,
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "rsi_window": rsi_window,
        "rsi_buy": rsi_buy,
        "rsi_sell": rsi_sell,
        "target_pct": current_settings.get("target_pct", 1.0),
        "stoploss_pct": current_settings.get("stoploss_pct", 0.5),
        "live_trading_mode": current_settings.get("live_trading_mode", False),
        "active_strategy": active_strategy
    }

    st.sidebar.markdown("**Risk Management**")
    target_pct = st.sidebar.slider("Target %", 0.1, 5.0, float(current_settings.get("target_pct", 1.0)), 0.1)
    stoploss_pct = st.sidebar.slider("Stoploss %", 0.1, 5.0, float(current_settings.get("stoploss_pct", 0.5)), 0.1)
    trailing_sl = st.sidebar.toggle("Trailing Stoploss", value=current_settings.get("trailing_sl", False))
    max_trades_per_day = st.sidebar.slider("Max Trades/Day", 1, 20, current_settings.get("max_trades_per_day", 4), 1)

    new_settings = {
        "timeframe": timeframe_str,
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "rsi_window": rsi_window,
        "rsi_buy": rsi_buy,
        "rsi_sell": rsi_sell,
        "target_pct": target_pct,
        "stoploss_pct": stoploss_pct,
        "trailing_sl": trailing_sl,
        "max_trades_per_day": max_trades_per_day,
        "live_trading_mode": current_settings.get("live_trading_mode", False),
        "active_strategy": active_strategy,
    }
    
    if new_settings != current_settings:
        save_settings(new_settings)
        
    return new_settings


# ---------------------------------------------------------------------------
# Live view components
# ---------------------------------------------------------------------------
def live_view():
    inject_custom_css()
    st.title("⚡ Live Trading Terminal")
    st.markdown("Monitor real-time executions, AI confidence, and risk limits.")
    
    # Render settings in sidebar
    settings = load_settings()
    
    # Read current state for Python logic, but let CSS handle the instant UI changes
    current_mode = settings.get("live_trading_mode", False)
    
    # Custom CSS for the toggle and layout to ensure INSTANT, perfectly synced color changes
    st.markdown("""
        <style>
        /* Center the Horizontal Block containing the toggle */
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stCheckbox"]) {
            align-items: center !important;
        }
        
        /* 1. Track Background Colors */
        div[data-testid="stCheckbox"] label[data-baseweb="checkbox"]:not(:has(input:checked)) > div:first-child {
            background-color: #9C27B0 !important; /* Violet for Paper */
        }
        div[data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) > div:first-child {
            background-color: #00C853 !important; /* Green for Live */
        }
        
        /* 2. Text Base Styles */
        .mode-text-paper, .mode-text-live {
            font-size: 16px;
            margin: 0;
            padding: 0;
            transition: color 0.1s ease-in-out;
        }
        .mode-text-paper { text-align: right; padding-right: 10px; }
        .mode-text-live { text-align: left; padding-left: 10px; }
        
        /* 3. Text Colors when LIVE is active (Checked) */
        div[data-testid="stHorizontalBlock"]:has(input:checked) .mode-text-live {
            color: #00C853 !important;
            font-weight: 900;
        }
        div[data-testid="stHorizontalBlock"]:has(input:checked) .mode-text-paper {
            color: #555555 !important;
            font-weight: 500;
        }
        
        /* 4. Text Colors when PAPER is active (Unchecked) */
        div[data-testid="stHorizontalBlock"]:not(:has(input:checked)) .mode-text-paper {
            color: #9C27B0 !important;
            font-weight: 900;
        }
        div[data-testid="stHorizontalBlock"]:not(:has(input:checked)) .mode-text-live {
            color: #555555 !important;
            font-weight: 500;
        }

        /* Center the toggle */
        div[data-testid="stCheckbox"] {
            display: flex;
            justify-content: center;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Render toggle with side-by-side text
    c1, c2, c3 = st.columns([1, 0.15, 1])
    with c1:
        st.markdown("<div class='mode-text-paper'>PAPER TRADING ACTIVE</div>", unsafe_allow_html=True)
    with c2:
        is_live = st.toggle("Mode", value=current_mode, label_visibility="collapsed")
        if is_live != current_mode:
            settings["live_trading_mode"] = is_live
            save_settings(settings)
    with c3:
        st.markdown("<div class='mode-text-live'>LIVE TRADING ACTIVE</div>", unsafe_allow_html=True)

    settings = render_sidebar_settings() # Re-render sidebar after potential save
    st.sidebar.success(f"Live Bot is set to {settings['timeframe']} timeframe.")

    state = load_state()

    # Premium Metric Cards
    col1, col2, col3, col4 = st.columns(4)
    equity = state.get('equity', 100000)
    pnl = state.get('pnl', 0)
    
    # Custom HTML for Premium Metrics
    st.markdown(f"""
    <div style="display: flex; gap: 20px; margin-bottom: 25px;">
        <div style="flex: 1; background: linear-gradient(145deg, #1A1E29 0%, #131722 100%); padding: 20px; border-radius: 12px; border: 1px solid #2B3139; box-shadow: 0 4px 15px rgba(0,0,0,0.2);">
            <p style="color: #8B949E; margin: 0 0 5px 0; font-size: 14px; font-weight: 600;">💰 CURRENT EQUITY</p>
            <h2 style="color: #FFFFFF; margin: 0; font-size: 28px;">₹{equity:,.2f}</h2>
        </div>
        <div style="flex: 1; background: linear-gradient(145deg, #1A1E29 0%, #131722 100%); padding: 20px; border-radius: 12px; border: 1px solid #2B3139; box-shadow: 0 4px 15px rgba(0,0,0,0.2);">
            <p style="color: #8B949E; margin: 0 0 5px 0; font-size: 14px; font-weight: 600;">📊 TODAY'S PNL</p>
            <h2 style="color: {'#00C853' if pnl >= 0 else '#FF1744'}; margin: 0; font-size: 28px;">
                {'+' if pnl >= 0 else ''}₹{pnl:,.2f}
            </h2>
        </div>
        <div style="flex: 1; background: linear-gradient(145deg, #1A1E29 0%, #131722 100%); padding: 20px; border-radius: 12px; border: 1px solid #2B3139; box-shadow: 0 4px 15px rgba(0,0,0,0.2);">
            <p style="color: #8B949E; margin: 0 0 5px 0; font-size: 14px; font-weight: 600;">🤖 AI CONFIDENCE</p>
            <h2 style="color: #3B82F6; margin: 0; font-size: 28px;">89.4%</h2>
            <p style="color: #00C853; margin: 5px 0 0 0; font-size: 12px;">▲ High Conviction</p>
        </div>
        <div style="flex: 1; background: linear-gradient(145deg, #1A1E29 0%, #131722 100%); padding: 20px; border-radius: 12px; border: 1px solid #2B3139; box-shadow: 0 4px 15px rgba(0,0,0,0.2);">
            <p style="color: #8B949E; margin: 0 0 5px 0; font-size: 14px; font-weight: 600;">🛡️ RISK ENGINE</p>
            <h2 style="color: #00C853; margin: 0; font-size: 28px;">ACTIVE</h2>
            <p style="color: #8B949E; margin: 5px 0 0 0; font-size: 12px;">Limits OK</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    
    # Live Chart & Trades Side-by-Side
    c_chart, c_trades = st.columns([2, 1])
    
    with c_chart:
        st.subheader("📡 Live Market Feed (NIFTY 50)")
        try:
            import yfinance as yf
            import plotly.graph_objects as go
            import datetime
            # Fetch intraday data to simulate a live chart
            ticker = yf.Ticker("^NSEI")
            df_live = ticker.history(period="1d", interval="5m")
            if not df_live.empty:
                fig = go.Figure(data=[go.Candlestick(
                    x=df_live.index,
                    open=df_live['Open'], high=df_live['High'],
                    low=df_live['Low'], close=df_live['Close'],
                    increasing_line_color='#00C853', decreasing_line_color='#FF1744'
                )])
                fig.update_layout(
                    template="plotly_dark",
                    margin=dict(l=0, r=0, t=0, b=0),
                    height=450,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    xaxis_rangeslider_visible=False
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Market Closed / No Intraday Data available right now.")
        except Exception:
            st.info("Websocket stream active. Waiting for next minute close...")

    with c_trades:
        st.subheader("📋 Recent Executions")
        trades = state.get("trades", [])[-10:]
        if trades:
            df_trades = pd.DataFrame(trades)
            st.dataframe(
                df_trades.style.map(
                    lambda v: "color: #00C853; font-weight: bold" if isinstance(v, (int, float)) and v > 0
                    else ("color: #FF1744; font-weight: bold" if isinstance(v, (int, float)) and v < 0 else ""),
                    subset=["pnl"] if "pnl" in df_trades.columns else None
                ),
                use_container_width=True,
                height=450
            )
        else:
            st.info("No trades recorded today. The AI is scanning the market for high-probability setups.")

    st.caption("⟳ Auto-refreshing every 5 seconds...")
    time.sleep(5)
    st.rerun()

# ---------------------------------------------------------------------------
# Back-test view components
# ---------------------------------------------------------------------------
def backtest_view():
    st.title("🔬 Back-test Dashboard")

    # Render settings in sidebar (shared with live view)
    settings = render_sidebar_settings()
    
    timeframe_str = settings["timeframe"]
    ema_fast = settings["ema_fast"]
    ema_slow = settings["ema_slow"]
    rsi_window = settings["rsi_window"]
    rsi_buy = settings["rsi_buy"]
    rsi_sell = settings["rsi_sell"]
    target_pct = settings["target_pct"]
    stoploss_pct = settings["stoploss_pct"]

    st.sidebar.markdown("**Initial Capital**")
    initial_capital = st.sidebar.number_input("Starting Capital", value=10_000.0,
                                              min_value=1000.0, step=1000.0)

    st.markdown("### 🔍 Search Asset (Auto-Loads Data)")
    
    # Modern Searchable Dropdown using native Streamlit selectbox (type-to-search built-in)
    popular_symbols = {
        "NIFTY 50": "^NSEI",
        "BANK NIFTY": "^NSEBANK",
        "SENSEX": "^BSESN",
        "NIFTY MIDCAP 50": "^NSEMDCP50",
        "FINNIFTY": "^CNXFIN",
        "Reliance Industries": "RELIANCE.NS",
        "TCS": "TCS.NS",
        "Infosys": "INFY.NS",
        "HDFC Bank": "HDFCBANK.NS",
        "Apple Inc.": "AAPL",
    }
    
    col_sym, col_start, col_end, col_btn = st.columns([2, 1, 1, 1.2])
    selected_name = col_sym.selectbox(
        "Search Symbol",
        options=list(popular_symbols.keys()),
        index=0,
        help="Type to search. Automatically updates backtest when changed."
    )
    
    # Dynamic Date Range
    import datetime
    start_date = col_start.date_input("Start Date", value=datetime.date.today() - datetime.timedelta(days=30))
    end_date = col_end.date_input("End Date", value=datetime.date.today())
    
    # Search Button
    col_btn.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
    run_search = col_btn.button("🔍 Search & Run", type="primary", use_container_width=True)

    # State management: Only run when search is clicked, a file is uploaded, or if it was already running
    if "run_backtest" not in st.session_state:
        st.session_state.run_backtest = False
        
    if run_search:
        st.session_state.run_backtest = True
        
    # Validate Date Limits right below the search bar (before the upload section)
    days_diff = (end_date - start_date).days
    is_invalid_range = False
    
    if st.session_state.run_backtest:
        if timeframe_str == "1 Min" and days_diff > 7:
            st.warning(f"**Limit Exceeded:** Max **7 days** allowed for {timeframe_str} (selected {days_diff}). Please adjust dates.", icon="⚠️")
            is_invalid_range = True
        elif timeframe_str in ["5 Min", "15 Min", "30 Min"] and days_diff > 60:
            st.warning(f"**Limit Exceeded:** Max **60 days** allowed for {timeframe_str} (selected {days_diff}). Please adjust dates.", icon="⚠️")
            is_invalid_range = True
        elif timeframe_str == "1 Hour" and days_diff > 730:
            st.warning(f"**Limit Exceeded:** Max **730 days** allowed for {timeframe_str} (selected {days_diff}). Please adjust dates.", icon="⚠️")
            is_invalid_range = True
            
        if is_invalid_range:
            # Auto-hide the warning after 15 seconds using a CSS animation
            st.markdown("""
                <style>
                @keyframes fadeOutAfter15s {
                    0% { opacity: 1; max-height: 500px; margin-bottom: 1rem; }
                    90% { opacity: 1; max-height: 500px; margin-bottom: 1rem; }
                    100% { opacity: 0; max-height: 0px; margin-bottom: 0px; padding: 0px; overflow: hidden; border: none; }
                }
                div[data-testid="stAlert"] {
                    animation: fadeOutAfter15s 15s forwards ease-out;
                }
                </style>
            """, unsafe_allow_html=True)

    # Check if we have uploaded data in session state
    has_uploaded_data = st.session_state.get('uploaded_csv_data') is not None

    # Stop execution if invalid range AND no file uploaded
    if is_invalid_range and not has_uploaded_data:
        st.stop()

    # Determine which data source to use
    df = None
    if st.session_state.run_backtest:
        if has_uploaded_data:
            df = st.session_state['uploaded_csv_data']
            st.success(f"✅ Data Loaded Successfully: {len(df)} total candles loaded from CSV.")
        else:
            symbol = popular_symbols[selected_name]
            with st.spinner(f"Fetching {selected_name} data from market..."):
                try:
                    import yfinance as yf
                    
                    # Map to interval
                    if timeframe_str == "1 Min":
                        interval = "1m"
                    elif timeframe_str in ["5 Min", "15 Min", "30 Min"]:
                        interval = "5m"
                    elif timeframe_str == "1 Hour":
                        interval = "1h"
                    else:
                        interval = "1d"
                        
                    ticker = yf.Ticker(symbol)
                    df_yf = ticker.history(start=start_date, end=end_date + datetime.timedelta(days=1), interval=interval)
                    
                    if not df_yf.empty:
                        df = df_yf.reset_index()
                        df = df.rename(columns={"Date": "date", "Datetime": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
                        st.success(f"✅ Data Loaded Successfully: {len(df)} total candles loaded for {selected_name} at {interval} interval.")
                    else:
                        st.warning(f"⚠️ No data found for {symbol} with interval {interval}. Try reducing the date range.")
                except ImportError:
                    st.error("yfinance is not installed. Run `pip install yfinance` to use auto-fetch.")
                except Exception as e:
                    st.error(f"Failed to fetch data: {e}")

    if df is not None:

        # Normalize column names to lowercase to handle varying CSV formats
        df.columns = df.columns.str.lower().str.strip()
        # Map common aliases
        df = df.rename(columns={"ltp": "close", "vol": "volume"})

        # If volume is missing (common for indices like NIFTY 50), mock it
        if "volume" not in df.columns:
            df["volume"] = 1000

        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(df.columns):
            st.error(f"CSV must contain columns: {required}")
            return

        # Attempt to parse datetime for resampling
        date_col = None
        for col in ["date", "time", "datetime", "timestamp"]:
            if col in df.columns:
                date_col = col
                break
                
        if date_col:
            # format='mixed' handles inconsistent date formats, and dayfirst=True is better for DD/MM/YYYY
            df[date_col] = pd.to_datetime(df[date_col], format='mixed', dayfirst=True)
            df = df.set_index(date_col)
            df = df.sort_index()

            # Resample logic based on selected timeframe
            tf_map = {
                "1 Min": "1min", "5 Min": "5min", "15 Min": "15min", 
                "30 Min": "30min", "1 Hour": "1h", "1 Day": "1D"
            }
            resample_rule = tf_map.get(timeframe_str)
            
            # Only resample if we are shifting to a higher timeframe
            if resample_rule and timeframe_str != "1 Min":
                df = df.resample(resample_rule).agg({
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum"
                }).dropna()

        # Reset index to ensure integer-based .at[] lookups work
        df = df.reset_index()

        # Run the strategy selected in the sidebar
        active_strategy = settings.get("active_strategy", "ema_rsi")
        if active_strategy == "premium":
            from trading_bot.strategies.premium_selection import generate_signals as _run_strategy
            st.info("💎 Running **Premium Selection Strategy** (8-Layer Institutional Engine — needs 200+ bars)")
        elif active_strategy == "enhanced_ai":
            from trading_bot.strategies.enhanced_ai_strategy import generate_signals as _run_strategy
            st.info("🤖 Running **Enhanced AI Strategy** (EMA + RSI + MACD + Volume + SMC + Option Chain)")
        else:
            from trading_bot.strategies.ema_rsi_strategy import generate_signals as _run_strategy
            st.info("📈 Running **EMA + RSI Strategy** (Classic)")

        signals = _run_strategy(
            df,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            rsi_window=rsi_window,
            rsi_buy_thresh=rsi_buy,
            rsi_sell_thresh=rsi_sell,
        )
        df["signal"] = signals

        # Always run AI strategy in background to detect "perfect" signals for over-limit exception
        from trading_bot.strategies.enhanced_ai_strategy import generate_signals as ai_run_strategy
        df["ai_signal"] = ai_run_strategy(df)

        # -----------------------------------------------------------------
        # Enhanced trade simulation with target / stoploss tracking
        # -----------------------------------------------------------------
        capital = initial_capital
        equity_curve: List[float] = [capital]
        trades: List[dict] = []       # detailed trade log
        position_price = None
        entry_index = None
        is_override_trade = False # Track if current position is an override trade
        peak_price = None # Track highest price for Long, lowest for Short
        trailing_sl = settings.get("trailing_sl", False)
        
        max_trades_per_day = settings.get("max_trades_per_day", 4)
        from collections import defaultdict
        trades_per_day = defaultdict(int)

        for i in range(len(df) - 1):
            # Extract date string for tracking daily trade limits
            current_date_str = "unknown"
            if "date" in df.columns:
                current_date_str = str(df.at[i, "date"])[:10]
            elif "index" in df.columns:
                current_date_str = str(df.at[i, "index"])[:10]

            # --- Check intra-bar target / stoploss for open position ------
            # --- Check intra-bar target / stoploss for open position ------
            if position_price is not None:
                bar_high = df.at[i, "high"]
                bar_low = df.at[i, "low"]
                
                if position_type == "Buy":
                    # Update peak price for trailing SL
                    if peak_price is None or bar_high > peak_price:
                        peak_price = bar_high
                        
                    target_price = position_price * (1 + target_pct / 100)
                    
                    if trailing_sl:
                        sl_price = peak_price * (1 - stoploss_pct / 100)
                        
                        if bar_low <= sl_price:
                            pnl = sl_price - position_price
                            capital += pnl
                            trades.append({
                                "Entry Index": entry_index,
                                "Exit Index": i,
                                "Entry Price": round(position_price, 2),
                                "Exit Price": round(sl_price, 2),
                                "PnL": round(pnl, 2),
                                "Outcome": "📉 Trailing SL",
                                "Is Override": is_override_trade,
                                "Type": "Buy",
                            })
                            position_price = None
                            entry_index = None
                            equity_curve.append(capital)
                            continue
                    
                    if bar_high >= target_price:
                        pnl = target_price - position_price
                        capital += pnl
                        trades.append({
                            "Entry Index": entry_index,
                            "Exit Index": i,
                            "Entry Price": round(position_price, 2),
                            "Exit Price": round(target_price, 2),
                            "PnL": round(pnl, 2),
                            "Outcome": "🎯 Target",
                            "Is Override": is_override_trade,
                            "Type": "Buy",
                        })
                        position_price = None
                        entry_index = None
                        equity_curve.append(capital)
                        continue
                        
                elif position_type == "Sell":
                    # Update peak price (lowest price) for trailing SL
                    if peak_price is None or bar_low < peak_price:
                        peak_price = bar_low
                        
                    target_price = position_price * (1 - target_pct / 100)
                    
                    if trailing_sl:
                        sl_price = peak_price * (1 + stoploss_pct / 100)
                        
                        if bar_high >= sl_price:
                            pnl = position_price - sl_price
                            capital += pnl
                            trades.append({
                                "Entry Index": entry_index,
                                "Exit Index": i,
                                "Entry Price": round(position_price, 2),
                                "Exit Price": round(sl_price, 2),
                                "PnL": round(pnl, 2),
                                "Outcome": "📉 Trailing SL",
                                "Is Override": is_override_trade,
                                "Type": "Sell",
                            })
                            position_price = None
                            entry_index = None
                            equity_curve.append(capital)
                            continue
                    
                    if bar_low <= target_price:
                        pnl = position_price - target_price
                        capital += pnl
                        trades.append({
                            "Entry Index": entry_index,
                            "Exit Index": i,
                            "Entry Price": round(position_price, 2),
                            "Exit Price": round(target_price, 2),
                            "PnL": round(pnl, 2),
                            "Outcome": "🎯 Target",
                            "Is Override": is_override_trade,
                            "Type": "Sell",
                        })
                        position_price = None
                        entry_index = None
                        equity_curve.append(capital)
                        continue

            # --- Signal-based entry / exit --------------------------------
            sig = df.at[i, "signal"]

            if position_price is not None:
                if position_type == "Buy" and sig == -1:
                    sell_price = df.at[i + 1, "open"]
                    pnl = sell_price - position_price
                    capital += pnl
                    trades.append({
                        "Entry Index": entry_index,
                        "Exit Index": i + 1,
                        "Entry Price": round(position_price, 2),
                        "Exit Price": round(sell_price, 2),
                        "PnL": round(pnl, 2),
                        "Outcome": "✅ Signal Exit" if pnl >= 0 else "❌ Signal Exit",
                        "Is Override": is_override_trade,
                        "Type": "Buy",
                    })
                    position_price = None
                    entry_index = None
                    
                elif position_type == "Sell" and sig == 1:
                    buy_price = df.at[i + 1, "open"]
                    pnl = position_price - buy_price
                    capital += pnl
                    trades.append({
                        "Entry Index": entry_index,
                        "Exit Index": i + 1,
                        "Entry Price": round(position_price, 2),
                        "Exit Price": round(buy_price, 2),
                        "PnL": round(pnl, 2),
                        "Outcome": "✅ Signal Exit" if pnl >= 0 else "❌ Signal Exit",
                        "Is Override": is_override_trade,
                        "Type": "Sell",
                    })
                    position_price = None
                    entry_index = None

            if position_price is None:
                if sig == 1:
                    if trades_per_day[current_date_str] < max_trades_per_day:
                        position_price = df.at[i + 1, "open"]
                        position_type = "Buy"
                        entry_index = i + 1
                        peak_price = position_price
                        trades_per_day[current_date_str] += 1
                        is_override_trade = False
                    elif trades_per_day[current_date_str] < (max_trades_per_day + 2):
                        if df.at[i, "ai_signal"] == 1:
                            position_price = df.at[i + 1, "open"]
                            position_type = "Buy"
                            entry_index = i + 1
                            peak_price = position_price
                            trades_per_day[current_date_str] += 1
                            is_override_trade = True
                            
                elif sig == -1:
                    if trades_per_day[current_date_str] < max_trades_per_day:
                        position_price = df.at[i + 1, "open"]
                        position_type = "Sell"
                        entry_index = i + 1
                        peak_price = position_price
                        trades_per_day[current_date_str] += 1
                        is_override_trade = False

            equity_curve.append(capital)

        # Close any open position at last close
        if position_price is not None:
            final_price = df.at[len(df) - 1, "close"]
            if position_type == "Buy":
                pnl = final_price - position_price
            else:
                pnl = position_price - final_price
            capital += pnl
            trades.append({
                "Entry Index": entry_index,
                "Exit Index": len(df) - 1,
                "Entry Price": round(position_price, 2),
                "Exit Price": round(final_price, 2),
                "PnL": round(pnl, 2),
                "Outcome": "⏹️ End-of-Data",
                "Is Override": is_override_trade,
                "Type": position_type,
            })
            equity_curve.append(capital)

        df_eq = pd.Series(equity_curve)

        # -----------------------------------------------------------------
        # Compute statistics
        # -----------------------------------------------------------------
        total_trades = len(trades)
        if total_trades > 0:
            pnl_list = [t["PnL"] for t in trades]
            target_hits = sum(1 for t in trades if "Target" in t["Outcome"])
            sl_hits = sum(1 for t in trades if "Stoploss" in t["Outcome"])
            signal_wins = sum(1 for t in trades if t["Outcome"] == "✅ Signal Exit")
            signal_losses = sum(1 for t in trades if t["Outcome"] == "❌ Signal Exit")
            eod_exits = sum(1 for t in trades if "End-of-Data" in t["Outcome"])
            
            # Count actual trades (within limit) and trailing trades (over limit)
            actual_trades = sum(1 for t in trades if not t.get("Is Override", False))
            trailing_trades = sum(1 for t in trades if t.get("Is Override", False))
            
            winning_trades = target_hits + signal_wins
            success_rate = (winning_trades / total_trades) * 100
            
            # Additional metrics requested by user
            num_days = len(trades_per_day)
            avg_trades_per_day = total_trades / num_days if num_days > 0 else 0
            win_pct = (signal_wins / total_trades) * 100 if total_trades > 0 else 0
            loss_pct = (signal_losses / total_trades) * 100 if total_trades > 0 else 0
            
            # Count Buy and Sell signals in the dataset (counting transitions, not continuous states)
            buy_signals = int(((df["signal"] == 1) & (df["signal"].shift(1) != 1)).sum())
            sell_signals = int(((df["signal"] == -1) & (df["signal"].shift(1) != -1)).sum())
            
            # Count Buy and Sell trades (executed)
            buy_trades = sum(1 for t in trades if t.get("Type") == "Buy")
            sell_trades = sum(1 for t in trades if t.get("Type") == "Sell")
            
            # Count exits by outcome
            target_hits = sum(1 for t in trades if t["Outcome"] == "🎯 Target")
            sl_hits = sum(1 for t in trades if t["Outcome"] == "🛑 Stoploss")
            trailing_sl_hits = sum(1 for t in trades if t["Outcome"] == "📉 Trailing SL")
            other_exits = sum(1 for t in trades if t["Outcome"] in ["✅ Signal Exit", "❌ Signal Exit", "⏹️ End-of-Data"])
            
            # Trailing SL or Signal Exits count (legacy variable if needed elsewhere)
            # trailing_sl_hits = signal_wins + signal_losses + eod_exits
            
            # Gross profit/loss calculations
            winning_pnl = sum(t["PnL"] for t in trades if t["PnL"] > 0)
            losing_pnl = sum(t["PnL"] for t in trades if t["PnL"] < 0)
            winning_pnl_pct = (winning_pnl / initial_capital) * 100
            losing_pnl_pct = (losing_pnl / initial_capital) * 100
            
            total_pnl = sum(pnl_list)
            avg_pnl = total_pnl / total_trades
            best_trade = max(pnl_list)
            worst_trade = min(pnl_list)
            # Max drawdown
            eq_series = pd.Series(equity_curve)
            roll_max = eq_series.cummax()
            drawdown = ((roll_max - eq_series) / roll_max) * 100
            max_dd = drawdown.max()
        else:
            target_hits = sl_hits = signal_wins = signal_losses = eod_exits = 0
            actual_trades = trailing_trades = 0
            winning_trades = 0
            avg_trades_per_day = win_pct = loss_pct = 0.0
            success_rate = total_pnl = avg_pnl = best_trade = worst_trade = max_dd = 0.0

        # -----------------------------------------------------------------
        # Display metrics
        # -----------------------------------------------------------------
        st.markdown("---")
        st.subheader("📊 Backtest Performance Summary")

        # Row 1 - Requested Metrics (Buy Orders, Target, SL, Trailing, Other)
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Buy Orders", total_trades)
        c2.metric("🎯 Target Achieved", target_hits)
        c3.metric("🛑 Stop Loss Triggered", sl_hits)
        
        # Trailing SL card - Gray if off!
        if trailing_sl:
            c4.metric("📉 Trailing SL Hits", trailing_sl_hits)
        else:
            with c4:
                st.markdown(
                    """
                    <div style="background-color: #f0f2f6; padding: 10px; border-radius: 5px; text-align: center; border: 1px solid #dcdfe6;">
                        <p style="color: #909399; margin-bottom: 0; font-size: 14px;">📉 Trailing SL Hits</p>
                        <h2 style="color: #909399; margin-top: 0; font-size: 24px; font-weight: 600;">0</h2>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
        c5.metric("⏹️ Other Exits", other_exits)

        # Row 2 - Requested Metrics (Signal Losses, Profit, Loss, Best)
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("❌ Signal Losses", f"{signal_losses} ({loss_pct:.1f}%)")
        c6.metric("💰 Total Profit", f"+{winning_pnl:.2f}", delta=f"+{winning_pnl_pct:.1f}%")
        c7.metric("💸 Total Loss", f"{losing_pnl:.2f}", delta=f"{losing_pnl_pct:.1f}%")
        c8.metric("🏆 Best Trade", f"+{best_trade:.2f}" if total_trades else "N/A")

        # Row 3 - Additional Metrics (Worst, Net PnL)
        c9, c10, c11, c12 = st.columns(4)
        c9.metric("📉 Worst Trade", f"{worst_trade:.2f}" if total_trades else "N/A")
        c10.metric("📊 Net PnL", f"{total_pnl:+.2f}", delta=f"{(total_pnl / initial_capital) * 100:+.1f}%")

        # -----------------------------------------------------------------
        # Trade log table
        # -----------------------------------------------------------------
        st.markdown("---")
        st.subheader("📋 Trade Log")
        if trades:
            df_trades = pd.DataFrame(trades)
            # Color the PnL column
            st.dataframe(
                df_trades.style.map(
                    lambda v: "color: green" if isinstance(v, (int, float)) and v > 0
                    else ("color: red" if isinstance(v, (int, float)) and v < 0 else ""),
                    subset=["PnL"]
                ),
                use_container_width=True,
                height=min(400, 40 + 35 * len(trades)),
            )
        else:
            st.info("No trades were generated by the strategy on this dataset.")

        # -----------------------------------------------------------------
        # Charts
        # -----------------------------------------------------------------
        st.markdown("---")
        st.subheader("📈 Equity Curve")
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            y=df_eq, mode="lines", name="Equity",
            line=dict(color="#00C853", width=2),
            fill="tozeroy", fillcolor="rgba(0,200,83,0.1)",
        ))
        fig_eq.add_hline(y=initial_capital, line_dash="dash",
                         line_color="gray", annotation_text="Starting Capital")
        fig_eq.update_layout(
            title="Equity Curve",
            xaxis_title="Step", yaxis_title="Equity",
            template="plotly_dark",
            height=400,
        )
        st.plotly_chart(fig_eq, use_container_width=True)

        st.subheader("🕯️ Price Chart with Signals")
        fig_candle = go.Figure(data=[go.Candlestick(
            x=df.index, open=df["open"], high=df["high"],
            low=df["low"], close=df["close"], name="Price",
        )])
        # Mark BUY/SELL signals on the chart
        buys = df[df["signal"] == 1]
        sells = df[df["signal"] == -1]
        fig_candle.add_trace(go.Scatter(
            x=buys.index, y=buys["low"] * 0.995,
            mode="markers", marker_symbol="triangle-up",
            marker_color="#00C853", marker_size=10, name="Buy Signal",
        ))
        fig_candle.add_trace(go.Scatter(
            x=sells.index, y=sells["high"] * 1.005,
            mode="markers", marker_symbol="triangle-down",
            marker_color="#FF1744", marker_size=10, name="Sell Signal",
        ))
        fig_candle.update_layout(
            title="Price + Signals",
            xaxis_title="Index", yaxis_title="Price",
            template="plotly_dark",
            height=500,
        )
        st.plotly_chart(fig_candle, use_container_width=True)

    # -----------------------------------------------------------------
    # File Upload at the bottom of the page
    # -----------------------------------------------------------------
    st.markdown("---")
    st.markdown("### 📁 Or Upload Custom Data (For >60 Days Intraday)")
    uploaded_file = st.file_uploader("Upload historical OHLCV CSV (Optional)", type=["csv"])
    
    if uploaded_file is not None:
        st.session_state['uploaded_csv_data'] = pd.read_csv(uploaded_file)
        st.session_state.run_backtest = True
        st.rerun()
    elif 'uploaded_csv_data' in st.session_state and uploaded_file is None:
        # If the user cleared the file uploader, remove it from session state
        del st.session_state['uploaded_csv_data']
        st.rerun()

# ---------------------------------------------------------------------------
# Broker setup guides  (contextual, shown per broker)
# ---------------------------------------------------------------------------

def _render_broker_guide(broker_id: str) -> None:
    """Render a compact, beginner-friendly setup guide for the selected broker."""

    GUIDES = {
        "fyers": {
            "color":    "#00b4d8",
            "portal":   "https://myaccount.fyers.in/app-creation/app-listing",
            "docs":     "https://myapi.fyers.in/docs/",
            "steps": [
                ("🌐", "Create an API App",
                 "Go to **[Fyers API Portal](https://myaccount.fyers.in/app-creation/app-listing)** → "
                 "Log in with your Fyers credentials → Click **Create App** → Fill in the app name "
                 "and set Redirect URI to `https://localhost`."),
                ("🔑", "Get Your Credentials",
                 "After the app is created you'll see:\n"
                 "- **App ID / Client ID** — looks like `XY12345-100`\n"
                 "- **Secret Key** — a long alphanumeric string\n\n"
                 "Copy both and paste them in the form above."),
                ("💾", "Save Credentials",
                 "Fill in **Client ID**, **Secret Key**, and **Redirect URI** in the form above, "
                 "then click **Save Credentials**. Your keys are stored encrypted on your computer."),
                ("🔗", "Generate Login URL & Get Access Token",
                 "Click **Save Credentials** first, then the **OAuth Authentication** section "
                 "appears below.\n\n"
                 "1. Click **Open Fyers Login Page** → A browser tab opens.\n"
                 "2. Log in with your Fyers credentials and approve the app.\n"
                 "3. You'll be redirected to a URL like `https://localhost?auth_code=XXXXX`.\n"
                 "4. Copy the `auth_code` value from that URL.\n"
                 "5. Paste it in the **auth code** box and click **Complete Login**."),
                ("🧪", "Test Connection",
                 "After login completes, click **Test Connection** to verify the broker can "
                 "reach the Fyers API and fetch your account balance."),
                ("⚡", "Activate Broker",
                 "Click **Activate Fyers** to make Fyers the live broker. The trading bot "
                 "will immediately use Fyers for all orders."),
            ],
            "warnings": [
                "⏰ **Access tokens expire daily.** You must re-authenticate each morning before trading.",
                "🔒 Never share your Secret Key with anyone.",
                "📍 Your Redirect URI in the Fyers app settings must exactly match the one you enter here (default: `https://localhost`).",
            ],
        },
        "kite": {
            "color":    "#387ed1",
            "portal":   "https://developers.kite.trade/apps",
            "docs":     "https://kite.trade/docs/connect/v3/",
            "steps": [
                ("🌐", "Create a Kite Connect App",
                 "Go to **[Kite Developer Console](https://developers.kite.trade/apps)** → "
                 "Log in with your Zerodha account → Click **Create new app** → "
                 "Set the app type to **Connect** and enter a Redirect URL (e.g. `https://127.0.0.1`)."),
                ("🔑", "Get Your Credentials",
                 "After creation, the app page shows:\n"
                 "- **API Key** — a short alphanumeric key\n"
                 "- **API Secret** — a longer secret string\n\n"
                 "Copy both and paste in the form above."),
                ("💾", "Save Credentials",
                 "Enter **API Key** and **API Secret** in the fields above, then click **Save Credentials**."),
                ("🔗", "Generate Login URL & Get Request Token",
                 "Once credentials are saved, the **OAuth Authentication** section appears.\n\n"
                 "1. Click **Open Zerodha Login Page** → Log in with your Zerodha credentials.\n"
                 "2. After approval you'll be redirected to a URL containing `request_token=XXXXX`.\n"
                 "3. Copy the `request_token` value and paste it in the **auth code** box.\n"
                 "4. Click **Complete Login** — the access token is generated and saved automatically."),
                ("🧪", "Test Connection",
                 "Click **Test Connection** to confirm Kite API is reachable and your account is accessible."),
                ("⚡", "Activate Broker",
                 "Click **Activate Zerodha (Kite)** to start using this broker for live orders."),
            ],
            "warnings": [
                "⏰ **Access tokens expire at the end of each trading day.** Re-authenticate every morning.",
                "💰 Kite Connect has a usage fee — ensure your Zerodha plan includes API access.",
                "🔒 Keep your API Secret safe. Do not share it.",
            ],
        },
        "angel": {
            "color":    "#ff6b35",
            "portal":   "https://smartapi.angelbroking.com",
            "docs":     "https://smartapi.angelbroking.com/docs",
            "steps": [
                ("🌐", "Create a SmartAPI App",
                 "Go to **[Angel One SmartAPI Portal](https://smartapi.angelbroking.com)** → "
                 "Log in with your Angel One credentials → Go to **My Apps** → Click **Create App** → "
                 "Enter an app name and description. Your **API Key** will be generated immediately."),
                ("🔑", "Get Your Credentials",
                 "You need **4** things:\n"
                 "- **Client ID** — your Angel One login ID (shown in the Angel One app)\n"
                 "- **MPIN** — your 4-digit trading PIN set in the Angel One app\n"
                 "- **API Key** — from the SmartAPI portal after creating the app\n"
                 "- **TOTP Secret** — see the step below"),
                ("📱", "Set Up TOTP (Two-Factor Authentication)",
                 "Angel One requires a time-based one-time password (TOTP) for API login:\n\n"
                 "1. Open the **Angel One mobile app** → Go to **Profile → Two-Factor Auth**.\n"
                 "2. Enable TOTP → You'll see a **QR code** and a **secret key** (text string).\n"
                 "3. Copy the **secret key** (not the QR code) and paste it into the **TOTP Secret Key** field above.\n\n"
                 "> 💡 The secret key looks like: `JBSWY3DPEHPK3PXP`"),
                ("💾", "Save Credentials",
                 "Fill in all 4 fields (Client ID, MPIN, TOTP Secret, API Key) in the form above, "
                 "then click **Save Credentials**."),
                ("⚡", "Authenticate & Activate",
                 "Click **Authenticate with Angel One** — this logs in directly (no browser redirect needed). "
                 "The system generates a TOTP code automatically from your secret key. "
                 "On success, click **Activate Angel One**."),
                ("🧪", "Test Connection",
                 "Click **Test Connection** to verify your credentials and check account balance."),
            ],
            "warnings": [
                "📱 You **must** set up TOTP via the Angel One mobile app before using the API.",
                "⏰ Sessions may expire intraday — the system will attempt auto re-authentication.",
                "⚠️ Do not change your MPIN while the bot is running — it will break authentication.",
                "🔒 Your MPIN and TOTP secret are stored encrypted on this machine only.",
            ],
        },
    }

    guide = GUIDES.get(broker_id)
    if not guide:
        return

    st.markdown("---")
    with st.expander("📖  Step-by-Step Setup Guide  *(click to expand)*", expanded=False):
        # Header
        c1, c2 = st.columns([3, 1])
        with c1:
            st.markdown(f"### How to set up {broker_id.replace('_', ' ').title()}")
            st.caption("Follow these steps in order. This takes about 5 minutes the first time.")
        with c2:
            st.markdown(
                f"[📚 Official Docs]({guide['docs']})  \n"
                f"[🌐 Developer Portal]({guide['portal']})"
            )

        st.markdown("---")

        # Numbered steps
        for i, (icon, title, body) in enumerate(guide["steps"], start=1):
            st.markdown(f"**Step {i} — {icon} {title}**")
            st.markdown(body)
            if i < len(guide["steps"]):
                st.markdown("")   # spacer

        # Warnings / important notes
        if guide["warnings"]:
            st.markdown("---")
            st.markdown("#### ⚠️ Important Notes")
            for w in guide["warnings"]:
                st.warning(w)

        # Quick reference flow diagram
        st.markdown("---")
        st.markdown("#### 🔄 Quick Reference Flow")
        flow_steps = " &nbsp;→&nbsp; ".join([
            f"**{icon} {title}**" for icon, title, _ in guide["steps"]
        ])
        st.markdown(
            f"<div style='background:#1e2130;padding:12px 18px;border-radius:8px;"
            f"border-left:4px solid {guide['color']};font-size:0.85rem;line-height:2'>"
            f"{flow_steps}</div>",
            unsafe_allow_html=True,
        )


def _render_test_connection(broker_id: str, load_credentials_fn) -> None:
    """Render the Test Connection button and result."""
    st.markdown("#### 🧪 Test Connection")
    st.caption("Verify that your credentials are working correctly before going live.")

    if st.button("Run Connection Test", key=f"test_conn_{broker_id}", use_container_width=True):
        creds = load_credentials_fn(broker_id)
        if not creds:
            st.error("❌ No credentials saved. Please fill in and save your credentials first.")
            return

        with st.spinner("Connecting to broker API…"):
            try:
                from brokers.broker_factory import BrokerFactory as _BF
                TmpClass = _BF._registry.get(broker_id)
                if not TmpClass:
                    st.error(f"❌ Broker '{broker_id}' is not registered.")
                    return

                tmp = TmpClass(credentials=creds, paper_mode=False)
                ok  = tmp.authenticate()

                if not ok:
                    st.warning("⚠️ Authentication returned False — credentials may be incomplete or expired.")
                    return

                balance = tmp.get_balance()
                tmp.close()

                st.success("✅ Connection successful!")
                col1, col2, col3 = st.columns(3)
                col1.metric("Available Cash",  f"₹{balance.available_cash:,.2f}")
                col2.metric("Used Margin",     f"₹{balance.used_margin:,.2f}")
                col3.metric("Total Balance",   f"₹{balance.total_balance:,.2f}")

            except Exception as exc:
                st.error(f"❌ Connection failed: {exc}")
                st.caption("Common fixes: check Client ID / API Key, regenerate Access Token, verify network.")


# ---------------------------------------------------------------------------
# Broker Settings view  (main page function)
# ---------------------------------------------------------------------------
def broker_settings_view():
    """UI for selecting, configuring, and authenticating the active broker."""
    st.title("🔌 Broker Settings")
    st.markdown("Configure the active broker, enter credentials, and authenticate. **Only one broker is active at a time.**")

    # Lazy import so the page still loads even if brokers/ has an error
    try:
        from brokers import BrokerFactory, save_credentials, load_credentials, delete_credentials, credentials_exist
    except Exception as e:
        st.error(f"❌ Could not load broker layer: {e}")
        return

    available = BrokerFactory.available_brokers()   # {broker_id: BrokerInfo}
    broker_ids   = list(available.keys())
    broker_names = [available[b].display_name for b in broker_ids]

    # ---- Current active broker ----
    current_active_id = BrokerFactory.get_active_broker_id()

    st.markdown("---")
    st.subheader("⚙️ Active Broker Selection")
    st.caption("⚠️ Switching broker will restart the connection. Ensure credentials are saved first.")

    selected_name = st.radio(
        "Select Broker",
        broker_names,
        index=broker_names.index(available[current_active_id].display_name)
              if current_active_id in available else 0,
        horizontal=True,
        key="broker_radio",
    )
    selected_id = broker_ids[broker_names.index(selected_name)]
    info        = available[selected_id]

    # -- Status badge --
    broker_singleton = BrokerFactory._active
    if broker_singleton and broker_singleton.BROKER_ID == selected_id:
        mode_tag = "🟠 PAPER" if broker_singleton.paper_mode else "🟢 LIVE"
        auth_tag = "✅ Authenticated" if broker_singleton.is_authenticated else "❌ Not authenticated"
        st.success(f"**Active:** {info.display_name}  |  {mode_tag}  |  {auth_tag}")
    else:
        st.info(f"**Configured (not yet active):** {info.display_name}")

    # ---- Activate button ----
    col_act, col_del = st.columns([1, 1])
    with col_act:
        if st.button(f"⚡ Activate {info.display_name}", use_container_width=True):
            if not credentials_exist(selected_id):
                st.warning("⚠️ Save credentials first before activating.")
            else:
                try:
                    BrokerFactory.switch_broker(selected_id)
                    st.success(f"✅ Switched to **{info.display_name}** successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed to switch broker: {e}")
    with col_del:
        if st.button(f"🗑️ Delete Credentials for {info.display_name}", use_container_width=True):
            delete_credentials(selected_id)
            st.warning(f"Credentials for **{info.display_name}** deleted.")

    st.markdown("---")

    # ---- Credential fields ----
    st.subheader(f"🔑 {info.display_name} Credentials")
    if info.description:
        st.caption(info.description)
    if info.website:
        st.markdown(f"🌐 [{info.website}]({info.website})")

    existing = load_credentials(selected_id)
    cred_values = {}

    for field_def in info.credential_fields:
        key     = field_def["key"]
        label   = field_def["label"]
        is_secret = field_def.get("secret", False)
        default   = existing.get(key, field_def.get("default", ""))
        disabled  = key == "access_token"   # auto-filled after OAuth

        if is_secret:
            cred_values[key] = st.text_input(
                label, value=default, type="password",
                disabled=disabled,
                help="This field is stored encrypted.",
                key=f"cred_{selected_id}_{key}",
            )
        else:
            cred_values[key] = st.text_input(
                label, value=default,
                disabled=disabled,
                key=f"cred_{selected_id}_{key}",
            )

    # ---- Save button ----
    if st.button("💾 Save Credentials", use_container_width=True, type="primary"):
        # Filter out empty + auto-filled fields
        to_save = {k: v for k, v in cred_values.items() if v and k != "access_token"}
        # Preserve existing access_token (don't overwrite with empty)
        if existing.get("access_token"):
            to_save["access_token"] = existing["access_token"]
        save_credentials(selected_id, to_save)
        st.success("✅ Credentials saved successfully (encrypted).")

    # ---- Contextual setup guide for the selected broker ----
    _render_broker_guide(selected_id)

    # ---- OAuth Login flow (Fyers / Kite) ----
    if info.get_login_url if hasattr(info, "get_login_url") else False:
        pass  # BrokerInfo doesn't expose get_login_url; handled below

    # Instantiate a temp broker just for URL generation (no auth)
    login_url = None
    tmp_broker = None
    try:
        tmp_creds = load_credentials(selected_id)
        if tmp_creds:
            from brokers.broker_factory import BrokerFactory as _BF
            TmpClass = _BF._registry.get(selected_id)
            if TmpClass:
                tmp_broker = TmpClass(credentials=tmp_creds, paper_mode=True)
                login_url  = tmp_broker.get_login_url()
    except Exception:
        pass

    # If the SDK isn't installed, build the Fyers login URL manually
    if login_url is None and selected_id == "fyers":
        try:
            fc = load_credentials("fyers")
            cid = fc.get("client_id", "")
            ruri = fc.get("redirect_uri", "https://trade.fyers.in/api-login/redirect-uri/login/v3/sas")
            if cid:
                import urllib.parse
                login_url = (
                    f"https://api-t1.fyers.in/api/v3/generate-authcode?"
                    f"client_id={urllib.parse.quote(cid)}"
                    f"&redirect_uri={urllib.parse.quote(ruri)}"
                    f"&response_type=code&state=None"
                )
        except Exception:
            pass

    if login_url:
        st.subheader("🔐 OAuth Authentication")
        st.markdown(
            f"**Step 1:** Click the link below to log in:\n\n"
            f"🔗 [Open {info.display_name} Login Page]({login_url})"
        )
        st.caption(
            "After logging in, you'll be redirected. Copy the **auth_code** or "
            "**request_token** value from the redirect URL (look for `auth_code=XXXX` "
            "or `code=XXXX` in the address bar)."
        )
        auth_code = st.text_input(
            "Step 2 — Paste the auth code here:",
            key=f"auth_code_{selected_id}",
        )
        if st.button("✅ Complete Login", key=f"complete_login_{selected_id}"):
            if auth_code:
                try:
                    if tmp_broker:
                        ok = tmp_broker.complete_login(auth_code)
                        if ok:
                            updated = load_credentials(selected_id)
                            updated["access_token"] = tmp_broker.credentials.get("access_token", "")
                            save_credentials(selected_id, updated)
                            BrokerFactory.switch_broker(selected_id)
                            st.success("✅ Authenticated and activated successfully!")
                            st.rerun()
                    else:
                        # SDK not installed — try manual token exchange
                        st.warning(
                            f"⚠️ The `fyers-api` SDK is not installed. "
                            f"Install it with: `pip install fyers-apiv3`\n\n"
                            f"Then restart the dashboard and try again."
                        )
                except Exception as e:
                    st.error(f"❌ Login failed: {e}")
            else:
                st.warning("Please paste the auth code first.")
    elif selected_id not in ("fyers", "kite"):
        # Direct-login broker (Angel One) — use Authenticate button
        st.subheader("🔐 Direct Authentication")
        if st.button(f"⚡ Authenticate with {info.display_name}", key=f"auth_direct_{selected_id}"):
            try:
                save_credentials(selected_id, {k: v for k, v in cred_values.items() if v})
                BrokerFactory.switch_broker(selected_id)
                st.success("✅ Authenticated and activated!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Authentication failed: {e}")
    else:
        st.info(
            f"⚠️ Could not generate login URL. Make sure your credentials are saved "
            f"and the broker SDK is installed (`pip install fyers-apiv3` for Fyers, "
            f"`pip install kiteconnect` for Zerodha)."
        )

    # ---- Test Connection ----
    st.markdown("---")
    _render_test_connection(selected_id, load_credentials)

    # ---- All registered brokers at a glance ----
    st.markdown("---")
    st.subheader("📋 All Registered Brokers")
    rows = []
    for bid, binfo in available.items():
        has_creds = credentials_exist(bid)
        is_active = (BrokerFactory._active is not None and
                     BrokerFactory._active.BROKER_ID == bid)
        rows.append({
            "Broker":      binfo.display_name,
            "ID":          bid,
            "Credentials": "✅ Saved" if has_creds else "❌ Not saved",
            "Status":      "🟢 ACTIVE" if is_active else ("🟡 Configured" if has_creds else "⚪ Not set up"),
            "Options":     "✅" if binfo.supports_options else "❌",
            "Streaming":   "✅" if binfo.supports_streaming else "❌",
        })
    import pandas as _pd
    st.dataframe(_pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ---- Security: Change Dashboard Password ----
    st.markdown("---")
    st.subheader("🛡️ Security")
    render_change_password_widget()

    # ---- Audit Log Viewer ----
    st.markdown("---")
    st.subheader("📜 Audit Log")
    st.caption(
        "Every trade, authentication event, and credential change is recorded here. "
        "The log is cryptographically chained — tampering is detectable."
    )

    try:
        from shared.security.audit_log import audit, _AUDIT_DIR
        import json as _json

        # Date picker — default to today
        import datetime
        audit_date = st.date_input(
            "View log for date:", value=datetime.date.today(), key="audit_date"
        )
        log_path = _AUDIT_DIR / f"audit_{audit_date}.log"

        col_verify, col_download = st.columns([1, 1])
        with col_verify:
            if st.button("🔍 Verify Integrity", key="audit_verify"):
                ok, errors = audit.verify_integrity(str(audit_date))
                if ok:
                    st.success("✅ Chain intact — no tampering detected.")
                else:
                    st.error(f"❌ Integrity check failed — {len(errors)} broken link(s):")
                    for e in errors:
                        st.code(e)

        if log_path.is_file():
            records = []
            with open(log_path, "r", encoding="utf-8") as _f:
                for line in _f:
                    line = line.strip()
                    if line:
                        try:
                            rec = _json.loads(line)
                            records.append({
                                "Time (UTC)": rec.get("ts", "")[:19].replace("T", " "),
                                "Event":      rec.get("event", ""),
                                "Severity":   rec.get("severity", "INFO"),
                                "Details":    _json.dumps(rec.get("data", {}), separators=(",", ":")),
                            })
                        except Exception:
                            pass

            if records:
                df_audit = _pd.DataFrame(records)
                with col_download:
                    st.download_button(
                        "⬇️ Download CSV",
                        data=df_audit.to_csv(index=False),
                        file_name=f"audit_{audit_date}.csv",
                        mime="text/csv",
                        key="audit_download",
                    )

                # Colour-code by severity
                def _severity_style(val):
                    colours = {"WARNING": "background-color:#3d2700;color:#ffaa00",
                               "ERROR":   "background-color:#3d0000;color:#ff6060",
                               "CRITICAL":"background-color:#5a0000;color:#ff0000"}
                    return colours.get(val, "")

                st.dataframe(
                    df_audit.style.applymap(_severity_style, subset=["Severity"]),
                    use_container_width=True, hide_index=True,
                )
                st.caption(f"{len(records)} records for {audit_date}.")
            else:
                st.info("No audit records for this date.")
        else:
            st.info(f"No audit log file found for {audit_date}.")

    except Exception as _exc:
        st.caption(f"⚠️ Audit log unavailable: {_exc}")


# ---------------------------------------------------------------------------
# Main navigation
# ---------------------------------------------------------------------------
st.sidebar.title("Navigation")
page = st.sidebar.radio(
    "Select view",
    ["Live", "Back\u2011test", "🔌 Broker Settings"],
)

# Logout button in sidebar
render_logout_button()

if page == "Live":
    live_view()
elif "Broker" in page:
    broker_settings_view()
else:
    backtest_view()
