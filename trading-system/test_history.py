from brokers.fyers_broker import FyersBroker
from brokers.token_cache import load_token
import pandas as pd

token = load_token("fyers")

broker = FyersBroker({"client_id": "0KHBQ6IQA4-100", "access_token": token})
broker.authenticate()
data = broker.get_historical_data("NSE:NIFTY50-INDEX", "2026-07-01", "2026-07-10", "5 Min")

if data:
    df = pd.DataFrame(data)
    print("GOT DATA:", len(df))
    print(df.tail(10))
else:
    print("NO DATA RETURNED")
