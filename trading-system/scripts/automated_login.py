import sys
import os
import json
from pathlib import Path

# Add project root to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brokers.credentials import load_credentials

def main():
    print("=== Credential Verification ===")
    
    creds = load_credentials("fyers")
    if not creds:
        print("Error: No Fyers credentials found!")
        sys.exit(1)
        
    client_id = creds.get("fyers_user_id")
    pin = creds.get("fyers_pin")
    totp_key = creds.get("fyers_totp_key")
    
    if not client_id or not pin or not totp_key:
        print("Error: Missing Client ID, PIN, or TOTP Key in saved credentials.")
        sys.exit(1)
        
    # Fail if dummy values are detected
    if client_id == "dsfaf" or totp_key == "dasfdasdsagfsagfgasdfsda":
        print("Error: Detected dummy values! Please enter real credentials.")
        sys.exit(1)
        
    print("Verification successful!")
    sys.exit(0)

if __name__ == "__main__":
    main()
