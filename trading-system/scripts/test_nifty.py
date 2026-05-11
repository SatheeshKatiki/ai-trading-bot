import json
import os
from fyers_apiv3 import fyersModel
from datetime import datetime, timedelta

# Load token
token_path = ".fyers_tokens.json"
if not os.path.exists(token_path):
    print(f"Error: {token_path} not found!")
    exit(1)

with open(token_path, "r") as f:
    token_data = json.load(f)
    token = token_data["access_token"]

# App ID
client_id = "0KHBQ6IQA4-100"

print(f"Using App ID: {client_id}")
print("Fetching NIFTY history...")

fyers = fyersModel.FyersModel(client_id=client_id, is_async=False, token=token, log_path="")

# Fetch historical data for Nifty 50
symbol = "NSE:NIFTY50-INDEX"
end = datetime.now()
start = end - timedelta(days=5)

data = {
    "symbol": symbol,
    "resolution": "15",
    "date_format": "1",
    "range_from": start.strftime("%Y-%m-%d"),
    "range_to": end.strftime("%Y-%m-%d"),
    "cont_flag": "1"
}

try:
    response = fyers.history(data=data)
    print("\n=== History Response ===")
    print(json.dumps(response, indent=2))
except Exception as e:
    print(f"Error: {e}")
