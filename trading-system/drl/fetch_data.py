import yfinance as yf
import pandas as pd
import numpy as np

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

def fetch_and_prepare_data():
    print("Fetching NIFTY 50 Historical Data (Max Available ~20+ Years)...")
    ticker = "^NSEI" 
    # yfinance only allows '1d' interval for data older than 2 years.
    df = yf.download(ticker, period="max", interval="1d")
    
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0].lower() for col in df.columns]
    else:
        df.columns = [col.lower() for col in df.columns]
    
    if 'date' not in df.columns and df.index.name != 'Date':
        df.reset_index(inplace=True)
    elif df.index.name == 'Date' or df.index.name == 'Datetime':
        df.reset_index(inplace=True)
        
    df.rename(columns={'Datetime': 'timestamp', 'Date': 'timestamp'}, inplace=True)
    
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
