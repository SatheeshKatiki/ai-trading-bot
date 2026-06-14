import sys
import os
import json
from pathlib import Path

# Add project root to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from brokers.credentials import load_credentials
from fyers_apiv3 import fyersModel

def main():
    print("=== Fyers Login Generator (Using SDK) ===")
    
    creds = load_credentials("fyers")
    if not creds:
        print("Error: No Fyers credentials found! Please enter them in the Dashboard UI first.")
        return
        
    client_id = creds.get("client_id")
    secret_key = creds.get("secret_key")
    
    # Use the exact Redirect URL from your dashboard
    redirect_uri = "http://127.0.0.1:8080"
    
    if not client_id or not secret_key:
        print("Error: Missing Client ID or Secret Key in saved credentials.")
        return
        
    print(f"Using Client ID: {client_id}")
    print(f"Using Redirect URI: {redirect_uri}")
    
    try:
        # Initialize the session model
        session = fyersModel.SessionModel(
            client_id=client_id,
            secret_key=secret_key,
            redirect_uri=redirect_uri,
            response_type="code",
            grant_type="authorization_code"
        )
        
        # In case api.fyers.in fails, the SDK might allow us to see the URL
        # We will try to use the SDK to generate the token if we get the code
        
        print("\nFallback manual GET URL (use this in browser if needed):")
        # We manually construct it with api-t1 just in case the SDK uses the failing one
        import urllib.parse
        url = f"https://api-t1.fyers.in/api/v3/generate-authcode?client_id={client_id}&redirect_uri={urllib.parse.quote(redirect_uri, safe='')}&response_type=code&state=sample_state"
        print("-" * 60)
        print(url)
        print("-" * 60)
        
        auth_code = input("\nEnter the copied auth_code here: ")
        if auth_code:
            print("Exchanging auth code for access token using SDK...")
            
            session.set_token(auth_code)
            response = session.generate_token()
            
            if response and "access_token" in response:
                token = response["access_token"]
                print("\n🎉 Login successful! Your access token has been received.")
                
                # Cache the token
                token_cache_path = Path(__file__).resolve().parents[2] / ".fyers_tokens.json"
                with open(token_cache_path, "w") as f:
                    json.dump({"access_token": token}, f)
                print(f"Token cached to {token_cache_path}")
            else:
                print(f"\n❌ Login failed. Response: {response}")
                
    except Exception as e:
        print(f"\n❌ Error during login: {e}")
        print("If you get a dependency error, we might need to install other missing packages.")

if __name__ == "__main__":
    main()
