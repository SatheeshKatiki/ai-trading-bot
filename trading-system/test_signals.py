import pandas as pd

from shared.indicators import ema, rsi, supertrend

def _volume_filter(df, lookback=20):
    if df["volume"].nunique() <= 1:
        return pd.Series(True, index=df.index)
    vol_avg = df["volume"].rolling(window=lookback, min_periods=1).mean()
    return df["volume"] >= vol_avg

df = pd.read_csv("data/NSE_NIFTY50-INDEX_5Min.csv")
df.rename(columns={"datetime": "datetime", "open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"}, inplace=True)
df["ema_fast"] = ema(df["close"], window=9)
df["ema_slow"] = ema(df["close"], window=21)
df["rsi"] = rsi(df["close"], window=14)
st_df = supertrend(df, period=10, multiplier=3.0)
df["st_direction"] = st_df["direction"]

bullish = (df["ema_fast"] > df["ema_slow"]) & (df["rsi"] > 55) & (df["st_direction"] == 1) & _volume_filter(df)
bearish = (df["ema_fast"] < df["ema_slow"]) & (df["rsi"] < 45) & (df["st_direction"] == -1) & _volume_filter(df)

df["bullish"] = bullish
df["bearish"] = bearish
df["vol_filter"] = _volume_filter(df)

today = df[df["datetime"].str.startswith("2026-07-17")]
print(f"Total bars today: {len(today)}")
print(f"Bullish signals today: {today['bullish'].sum()}")
print(f"Bearish signals today: {today['bearish'].sum()}")
print(f"Volume filter passed today: {today['vol_filter'].sum()}")

# Let's see without volume filter
bullish_no_vol = (df["ema_fast"] > df["ema_slow"]) & (df["rsi"] > 55) & (df["st_direction"] == 1)
today["bullish_no_vol"] = bullish_no_vol[df["datetime"].str.startswith("2026-07-17")]
print(f"Bullish signals without vol filter today: {today['bullish_no_vol'].sum()}")
