import yfinance as yf
import pandas as pd
import os
import sys

# 1. Remove AAPL_1min.csv if it exists
file_to_remove = r"C:\Users\Windows\Desktop\Claud project\AI trading Bot\trading-system\data\AAPL_1min.csv"
if os.path.exists(file_to_remove):
    try:
        os.remove(file_to_remove)
        print(f"Removed {file_to_remove}")
    except Exception as e:
        print(f"Error removing file: {e}")

# 2. Fetch Indian stock data dynamically
# Default to NIFTY 50 (^NSEI) if no symbol provided
symbol = "^NSEI"
if len(sys.argv) > 1:
    symbol = sys.argv[1]

print(f"Downloading data for {symbol}...")

# 1-minute data is only available for the last 7 days via yfinance
df = yf.download(symbol, period="5d", interval="1m")

if df.empty:
    print(f"No data found for {symbol}. Make sure the symbol is correct.")
    print("For Indian stocks, use suffix .NS (e.g., RELIANCE.NS, TCS.NS)")
    print("For indices, use ^NSEI (NIFTY 50) or ^NSEBANK (Bank NIFTY)")
    sys.exit(1)

# Handle multi-index columns in newer yfinance versions
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

# Rename to lowercase as required by the backtester
df = df.rename(columns={
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume"
})

# Drop timezone info for compatibility
df.index = df.index.tz_localize(None)

# Clean symbol name for filename
file_symbol = symbol.replace("^", "")
output_path = f"C:\\Users\\Windows\\Desktop\\Claud project\\AI trading Bot\\trading-system\\data\\{file_symbol}_1min.csv"

os.makedirs(os.path.dirname(output_path), exist_ok=True)
df.to_csv(output_path)
print(f"Data saved to {output_path}")
print(f"You can now run backtest with: python -m backtesting_engine.run --data-path data/{file_symbol}_1min.csv")
