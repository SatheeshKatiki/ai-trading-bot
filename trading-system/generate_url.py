import sys
import os
from dotenv import load_dotenv

load_dotenv("d:\\Projects\\AI trading Bot\\trading-system\\.env")

try:
    from fyers_apiv3 import fyersModel
except ImportError:
    print("fyers_apiv3 is not installed.")
    sys.exit(1)

client_id = os.getenv("FYERS_CLIENT_ID", "")
secret_key = os.getenv("FYERS_SECRET_KEY", "")
redirect_uri = os.getenv("FYERS_REDIRECT_URI", "")

if not client_id or not secret_key:
    print("Please ensure FYERS_CLIENT_ID and FYERS_SECRET_KEY are correctly set in the .env file.")
    sys.exit(1)

session = fyersModel.SessionModel(
    client_id=client_id,
    secret_key=secret_key,
    redirect_uri=redirect_uri,
    response_type="code",
    grant_type="authorization_code",
)

url = session.generate_authcode()
print("\n" + "="*80)
print("Please visit the following URL to log in and authorize the app:")
print(url)
print("="*80 + "\n")
