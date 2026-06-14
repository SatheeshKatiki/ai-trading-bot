import sys
import os
import json
import base64
import requests
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# Add project root to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from brokers.credentials import load_credentials
from fyers_apiv3 import fyersModel

def get_auth_code_automated(client_id, secret_key, redirect_uri, user_id, pin, totp_secret):
    import pyotp
    
    # 1. Send OTP
    print("Sending login OTP...")
    send_otp_url = "https://api-t2.fyers.in/vagator/v2/send_login_otp_v2"
    payload = {"fy_id": base64.b64encode(user_id.encode()).decode(), "app_id": "2"}
    res = requests.post(send_otp_url, json=payload).json()
    if res.get("s") != "ok":
        raise Exception(f"Failed to send OTP: {res}")
    request_key = res["request_key"]
    
    # 2. Verify TOTP
    print("Verifying TOTP...")
    totp = pyotp.TOTP(totp_secret).now()
    verify_otp_url = "https://api-t2.fyers.in/vagator/v2/verify_otp"
    payload = {"request_key": request_key, "otp": totp}
    res = requests.post(verify_otp_url, json=payload).json()
    if res.get("s") != "ok":
        raise Exception(f"Failed to verify TOTP: {res}")
    request_key = res["request_key"]
    
    # 3. Verify PIN
    print("Verifying PIN...")
    verify_pin_url = "https://api-t2.fyers.in/vagator/v2/verify_pin_v2"
    payload = {"request_key": request_key, "identity_type": "pin", "identifier": base64.b64encode(pin.encode()).decode()}
    res = requests.post(verify_pin_url, json=payload).json()
    if res.get("s") != "ok":
        raise Exception(f"Failed to verify PIN: {res}")
    access_token = res["data"]["access_token"]
    
    # 4. Get Auth Code
    print("Generating Auth Code...")
    token_url = "https://api-t1.fyers.in/api/v3/token"
    payload = {
        "fyers_id": user_id,
        "app_id": client_id,
        "redirect_uri": redirect_uri,
        "appType": "100",
        "code_challenge": "",
        "state": "None",
        "scope": "",
        "nonce": "",
        "response_type": "code",
        "create_cookie": True
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    res = requests.post(token_url, json=payload, headers=headers).json()
    if res.get("s") != "ok":
        # Let's try client_id without -100
        payload["app_id"] = client_id[:-4]
        res = requests.post(token_url, json=payload, headers=headers).json()
        if res.get("s") != "ok":
            raise Exception(f"Failed to get auth code: {res}")
    
    auth_code = res["Url"].split("auth_code=")[1].split("&")[0]
    return auth_code

def main():
    print("=== Fyers Auto-Login Generator ===")
    creds = load_credentials("fyers")
    if not creds:
        print("Error: No Fyers credentials found!")
        return
        
    client_id = creds.get("client_id")
    secret_key = creds.get("secret_key")
    redirect_uri = creds.get("redirect_uri") or "http://localhost:3000/auth/fyers/callback"
    user_id = creds.get("fyers_user_id")
    pin = creds.get("fyers_pin") or creds.get("pin")
    totp_secret = creds.get("fyers_totp_key") or creds.get("totp_secret")
    
    if not all([client_id, secret_key, redirect_uri, user_id, pin, totp_secret]):
        print("Error: Missing one of the required credentials for auto-login.")
        print(f"client_id={bool(client_id)}, secret_key={bool(secret_key)}, user_id={bool(user_id)}, pin={bool(pin)}, totp={bool(totp_secret)}")
        return
        
    try:
        auth_code = get_auth_code_automated(client_id, secret_key, redirect_uri, user_id, pin, totp_secret)
        print("Auth code received automatically! Exchanging for access token...")
        
        session = fyersModel.SessionModel(
            client_id=client_id,
            secret_key=secret_key,
            redirect_uri=redirect_uri,
            response_type="code",
            grant_type="authorization_code"
        )
        session.set_token(auth_code)
        response = session.generate_token()
        
        if response and "access_token" in response:
            token = response["access_token"]
            print("\nLogin successful! Your access token has been received.")
            
            # Cache the token
            token_cache_path = Path(__file__).resolve().parents[2] / ".fyers_tokens.json"
            with open(token_cache_path, "w") as f:
                json.dump({"access_token": token}, f)
            print(f"Token cached to {token_cache_path}")
        else:
            print(f"\nLogin failed. Response: {response}")
            
    except Exception as e:
        print(f"\nError during auto-login: {e}")

if __name__ == "__main__":
    main()
