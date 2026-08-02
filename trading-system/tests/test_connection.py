import sys
import os
from fyers_apiv3 import fyersModel

# Add project root to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brokers.credentials import load_credentials
from brokers.token_cache import load_token

def main():
    print("=== Testing Fyers Connection ===")

    # Load token
    token = load_token("fyers")
    if not token:
        print("Error: No cached token found! Please run generate_token.py first.")
        sys.exit(1)


    # Load app credentials
    creds = load_credentials("fyers")
    if not creds:
        print("Error: No Fyers credentials found!")
        sys.exit(1)
        
    client_id = creds.get("client_id")
    
    # Initialize fyers model
    # Note: log_path can be empty or a valid directory
    fyers = fyersModel.FyersModel(client_id=client_id, is_async=False, token=token, log_path="")
    
    # Fetch profile to test connection
    try:
        print("Fetching profile info...")
        profile = fyers.get_profile()
        print(f"Response: {profile}")
        
        if profile and profile.get("s") == "ok":
            print("🎉 Connection Successful! Your bot can now access Fyers API.")
            print(f"Welcome, {profile.get('data', {}).get('name')}!")
        else:
            print("❌ Connection Failed! Token might be invalid or expired.")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
