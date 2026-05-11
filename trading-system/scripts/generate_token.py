import sys
import os
import json
from pathlib import Path
from fyers_apiv3 import fyersModel

# Add project root to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    
    auth_code = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcHBfaWQiOiIwS0hCUTZJUUE0IiwidXVpZCI6ImI2ZmZlZTVkNDQ5NjQ4YzNhZTc0MGNkMGU0YThlZDMxIiwiaXBBZGRyIjoiIiwibm9uY2UiOiIiLCJzY29wZSI6IiIsImRpc3BsYXlfbmFtZSI6IllLMTcxOTAiLCJvbXMiOiJLMSIsImhzbV9rZXkiOiI4ODQ1YjBmZmNlNGZmOTY2NzE0ZmU5ZGZmMzVhNGFlZTJmZGU2MTM3YjVkN2FkOWE1MzNmYzY3OCIsImlzRGRwaUVuYWJsZWQiOiJOIiwiaXNNdGZFbmFibGVkIjoiTiIsImF1ZCI6IltcImQ6MVwiLFwiZDoyXCIsXCJ4OjBcIixcIng6MVwiLFwieDoyXCJdIiwiZXhwIjoxNzc4NTAzODU5LCJpYXQiOjE3Nzg0NzM4NTksImlzcyI6ImFwaS5sb2dpbi5meWVycy5pbiIsIm5iZiI6MTc3ODQ3Mzg1OSwic3ViIjoiYXV0aF9jb2RlIn0.CQYCyb-G2ZQGFjkhvsOOT-RjXX8Z_fDug6VO_w8xr0U"
    
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
            
            # Save token
            token_path = Path(__file__).resolve().parents[1] / ".fyers_tokens.json"
            with open(token_path, "w") as f:
                json.dump({"access_token": token}, f)
            print(f"Token saved to {token_path}")
            sys.exit(0)
        else:
            print(f"❌ Login failed! Response: {response}")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Token Generation Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
