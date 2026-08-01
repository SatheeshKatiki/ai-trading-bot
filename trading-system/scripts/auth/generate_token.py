import sys
import os
from fyers_apiv3 import fyersModel

# Add project root to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from brokers.credentials import load_credentials

def main():
    print("=== Generating Fyers Access Token ===")
    
    # Load credentials
    creds = load_credentials("fyers")
    if not creds:
        print("Error: No Fyers credentials found!")
        sys.exit(1)
        
    client_id = creds.get("client_id")
    secret_key = creds.get("secret_key")
    redirect_uri = "http://127.0.0.1:8080" # Forced to match the one used!
    
    auth_code = input("Please paste the 'auth_code' from the URL bar: ").strip()
    
    session = fyersModel.SessionModel(
        client_id=client_id,
        secret_key=secret_key,
        redirect_uri=redirect_uri,
        response_type="code",
        grant_type="authorization_code"
    )
    
    try:
        print("Exchanging auth code for access token...")
        session.set_token(auth_code)
        response = session.generate_token()
        
        if response and "access_token" in response:
            token = response["access_token"]
            print("🎉 Login successful!")

            # Save token (encrypted — see brokers/token_cache.py)
            from brokers.token_cache import save_token
            save_token(token, "fyers")
            print("Token saved (encrypted).")
            sys.exit(0)
        else:
            print(f"❌ Login failed! Response: {response}")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Token Generation Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
