import sys
import os
from pathlib import Path

# Add project root to path so we can import brokers module
sys.path.append(str(Path(__file__).resolve().parents[1]))

from brokers.credentials import save_credentials

def main():
    print("=== Secure Broker Credential Manager ===")
    print("This script will encrypt and save your broker API keys.")
    print("------------------------------------------------")
    
    broker = input("Enter Broker ID (e.g., fyers, kite, angel): ").strip().lower()
    
    if not broker:
        print("Broker ID cannot be empty.")
        return
        
    creds = {}
    
    if broker == "fyers":
        creds["client_id"] = input("Enter Fyers Client ID: ").strip()
        creds["secret_key"] = input("Enter Fyers Secret Key: ").strip()
        creds["redirect_uri"] = input("Enter Fyers Redirect URI (usually http://localhost:3000/): ").strip()
    elif broker == "kite":
        creds["api_key"] = input("Enter Kite API Key: ").strip()
        creds["api_secret"] = input("Enter Kite API Secret: ").strip()
    elif broker == "angel":
        creds["api_key"] = input("Enter Angel One API Key: ").strip()
        creds["client_code"] = input("Enter Client Code: ").strip()
        creds["password"] = input("Enter Password/PIN: ").strip()
    else:
        print(f"ℹ Custom broker detected. Please enter key-value pairs.")
        while True:
            key = input("Enter key name (or leave empty to finish): ").strip()
            if not key:
                break
            val = input(f"Enter value for {key}: ").strip()
            creds[key] = val
            
    if creds and any(creds.values()):
        # Filter out empty values
        creds = {k: v for k, v in creds.items() if v}
        
        print("\nSaving and encrypting credentials...")
        save_credentials(broker, creds)
        print(f"✓ Success! Credentials saved for '{broker}'.")
        print("You can now select this broker in your Strategy Settings or settings.json.")
    else:
        print("✖ No credentials entered. Aborting.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
    except Exception as e:
        print(f"\nError: {e}")
