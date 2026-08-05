import sys
from pathlib import Path
import os
import json
from fyers_apiv3 import fyersModel
from datetime import datetime, timedelta

# Add the application root (trading-system/) to python path -- this file
# lives in Testing_Automation_AI_Trading_Bot/legacy-manual/, two levels up.
sys.path.append(str(Path(__file__).resolve().parents[2] / 'trading-system'))

from brokers.token_cache import load_token


def main():
    # Load token
    token = load_token("fyers")
    if not token:
        print("Error: no cached Fyers token found!")
        exit(1)

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


if __name__ == "__main__":
    main()
