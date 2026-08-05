import sys
from pathlib import Path
import json
import os
from fyers_apiv3 import fyersModel

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
    print("Fetching funds...")

    try:
        fyers = fyersModel.FyersModel(client_id=client_id, is_async=False, token=token, log_path="")
        funds = fyers.funds() # Updated to funds()
        print("\n=== Funds Response ===")
        print(json.dumps(funds, indent=2))
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
