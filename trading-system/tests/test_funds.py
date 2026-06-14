import json
import os
from fyers_apiv3 import fyersModel

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
print("Fetching funds...")

try:
    fyers = fyersModel.FyersModel(client_id=client_id, is_async=False, token=token, log_path="")
    funds = fyers.funds() # Updated to funds()
    print("\n=== Funds Response ===")
    print(json.dumps(funds, indent=2))
except Exception as e:
    print(f"Error: {e}")
