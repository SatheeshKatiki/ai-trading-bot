import json
from brokers.fyers_broker import FyersBroker
import pandas as pd

with open(".fyers_tokens.json", "r") as f:
    token = json.load(f)["access_token"]

broker = FyersBroker({"client_id": "0KHBQ6IQA4-100", "access_token": token})
broker.authenticate()
data = broker.get_historical_data("NSE:NIFTY50-INDEX", "2026-07-01", "2026-07-10", "5 Min")

if data:
    df = pd.DataFrame(data)
    print("GOT DATA:", len(df))
    print(df.tail(10))
else:
    print("NO DATA RETURNED")
