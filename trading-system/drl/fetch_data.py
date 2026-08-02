import sys
import os
from datetime import datetime, timedelta

import yfinance as yf
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def calculate_rsi(series, period=14):
    delta = series.diff()
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0
    down[down > 0] = 0
    roll_up1 = up.ewm(span=period, min_periods=period).mean()
    roll_down1 = down.abs().ewm(span=period, min_periods=period).mean()
    RS = roll_up1 / roll_down1
    return 100.0 - (100.0 / (1.0 + RS))

def calculate_macd(series, fast=12, slow=26, signal=9):
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    sig = macd.ewm(span=signal, adjust=False).mean()
    return macd, sig

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(period).mean()

def _fetch_intraday_via_broker(timeframe: str, years_of_history: int) -> "pd.DataFrame | None":
    """Fetch real intraday history at `timeframe` granularity via the
    authenticated broker (the same brokers.get_historical_data() pagination
    path already used by scripts/daily_ai_retrain.py). Returns None if the
    broker isn't authenticated, so the caller can fall back to yfinance.
    """
    try:
        from brokers import BrokerFactory
    except Exception as exc:
        print(f"Broker module unavailable ({exc}); falling back to yfinance.")
        return None

    broker = BrokerFactory.get_active_broker()
    if not broker.authenticate():
        print("Broker not authenticated — cannot fetch real intraday history. Falling back to yfinance.")
        return None

    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * years_of_history)
    print(
        f"Fetching NIFTY 50 intraday history via broker: {timeframe} bars, "
        f"{start_date.date()} to {end_date.date()} ({years_of_history} years)..."
    )
    raw = broker.get_historical_data(
        symbol="NSE:NIFTY50-INDEX",
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        timeframe=timeframe,
    )
    if not raw:
        print("Broker returned no data — falling back to yfinance.")
        return None

    df = pd.DataFrame(raw)
    df.rename(columns={"time": "timestamp", "datetime": "timestamp"}, inplace=True)
    return df


def _fetch_intraday_via_yfinance(yf_interval: str) -> pd.DataFrame:
    """Fallback path when no broker session is available. yfinance only
    serves intraday granularity (anything finer than daily) for roughly the
    trailing 60 days — a real limitation of the free API, not a bug — so
    this trades off history length for correct granularity rather than the
    other way around.
    """
    print(
        f"Fetching NIFTY 50 via yfinance at {yf_interval} granularity "
        f"(yfinance intraday history is limited to ~60 days — this will be "
        f"far less history than the old daily-bar fetch, but at the "
        f"granularity the live/backtest system actually trades at)."
    )
    df = yf.download("^NSEI", period="60d", interval=yf_interval)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0].lower() for col in df.columns]
    else:
        df.columns = [col.lower() for col in df.columns]

    if 'date' not in df.columns and df.index.name != 'Date':
        df.reset_index(inplace=True)
    elif df.index.name == 'Date' or df.index.name == 'Datetime':
        df.reset_index(inplace=True)

    df.rename(columns={'Datetime': 'timestamp', 'Date': 'timestamp'}, inplace=True)
    return df


def fetch_and_prepare_data(timeframe: str = "5 Min", years_of_history: int = 3):
    """Fetch NIFTY history at ``timeframe`` granularity — matching the
    granularity the live engine and backtester actually trade at — instead
    of the daily bars this used to fetch regardless of how the resulting
    model would be deployed.

    Root-cause fix: the old version always called
    ``yf.download(ticker, period="max", interval="1d")``, i.e. DAILY bars,
    because yfinance only allows the '1d' interval for data older than
    ~2 years and this script wanted 20 years of span. But the model trained
    on that data is deployed live against 5-minute/tick data — a model that
    has only ever seen one end-of-day close per day has never seen the
    intraday volatility/noise profile it now trades with real money. This
    now fetches at matching intraday granularity by default: via the
    broker's paginated historical-data API when authenticated (real
    multi-year intraday history, same mechanism scripts/daily_ai_retrain.py
    already uses), or via yfinance at the same granularity — accepting a
    much shorter window — when no broker session is available, rather than
    silently reverting to daily bars either way.
    """
    yf_interval_map = {
        "1 Min": "1m", "5 Min": "5m", "15 Min": "15m", "30 Min": "30m", "1 Hour": "60m",
    }
    yf_interval = yf_interval_map.get(timeframe, "5m")

    df = _fetch_intraday_via_broker(timeframe, years_of_history)
    if df is None or df.empty:
        df = _fetch_intraday_via_yfinance(yf_interval)

    print("Calculating Professional Technical Indicators (Features)...")
    df['rsi'] = calculate_rsi(df['close'])
    
    macd, _ = calculate_macd(df['close'])
    df['macd'] = macd
    
    df['atr'] = calculate_atr(df)
    
    if 'volume' not in df.columns or df['volume'].sum() == 0:
        df['volume'] = df['high'] - df['low']
        
    df['vol_delta'] = df['volume'].diff().fillna(0)
    
    df.dropna(inplace=True)
    
    cols_to_keep = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'rsi', 'macd', 'atr', 'vol_delta']
    available_cols = [c for c in cols_to_keep if c in df.columns]
    df = df[available_cols]
    
    filename = "nifty_historical_data.csv"
    df.to_csv(filename, index=False)
    print(f"Data successfully saved to {filename}. Total rows: {len(df)}")
    
if __name__ == "__main__":
    fetch_and_prepare_data()
