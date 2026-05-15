import sys
import os
import json
import time
from pathlib import Path

# Add project root to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brokers.credentials import load_credentials, save_credentials
from fyers_apiv3 import fyersModel
import pyotp
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

def main():
    print("=== Fyers Automated Login (Using Selenium & TOTP) ===")
    
    # 1. Load credentials
    creds = load_credentials("fyers")
    if not creds:
        print("Error: No Fyers credentials found! Please enter them in the Dashboard UI first.")
        return
        
    client_id = creds.get("client_id")
    secret_key = creds.get("secret_key")
    redirect_uri = "http://127.0.0.1:8080" # Default redirect URI
    
    # Check for TOTP Secret and PIN
    totp_secret = creds.get("totp_secret")
    pin = creds.get("pin")
    
    if not totp_secret or not pin:
        print("\n[!] Missing TOTP Secret or PIN in saved credentials.")
        if not totp_secret:
            totp_secret = input("Enter your Fyers TOTP Secret Key (16 digits): ").strip()
            creds["totp_secret"] = totp_secret
        if not pin:
            pin = input("Enter your Fyers 4-Digit PIN: ").strip()
            creds["pin"] = pin
            
        # Save updated credentials securely
        save_credentials("fyers", creds)
        print("[OK] Credentials updated and saved securely.")

    if not client_id or not secret_key:
        print("Error: Missing Client ID or Secret Key in saved credentials.")
        return
        
    print(f"Using Client ID: {client_id}")
    
    # 2. Generate Auth URL
    session = fyersModel.SessionModel(
        client_id=client_id,
        secret_key=secret_key,
        redirect_uri=redirect_uri,
        response_type="code",
        grant_type="authorization_code"
    )
    
    auth_url = session.generate_authcode()
    print(f"Generated Auth URL: {auth_url}")
    
    # 3. Automate Login with Selenium
    print("\nStarting Chrome for automated login...")
    options = webdriver.ChromeOptions()
    # Uncomment line below to run without showing browser window (Headless)
    # options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        driver.get(auth_url)
        print("\n[!] IMPORTANT: If you see a 'Verify you are human' box, please click it manually in the browser window!")
        wait = WebDriverWait(driver, 45) # Increased timeout to 45 seconds
        
        # Step 1: Switch to Client ID and enter it
        print("Switching to Client ID mode...")
        client_id_rb = wait.until(EC.element_to_be_clickable((By.ID, "clientId_rb")))
        client_id_rb.click()
        
        print("Entering Client ID...")
        client_input = wait.until(EC.visibility_of_element_located((By.ID, "fy_client_id")))
        client_input.send_keys(client_id)
        
        # Click Continue
        continue_btn = wait.until(EC.element_to_be_clickable((By.ID, "mobileNumberSubmit")))
        continue_btn.click()
        
        # Step 2: Enter TOTP
        print("Generating and entering TOTP...")
        totp = pyotp.TOTP(totp_secret)
        current_otp = totp.now()
        
        # Wait for OTP input field
        otp_input = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@type='text' and @maxlength='6']")))
        otp_input.send_keys(current_otp)
        
        # Click Verify / Submit if needed (sometimes it auto-submits)
        try:
            verify_btn = driver.find_element(By.XPATH, "//button[@type='submit']")
            verify_btn.click()
        except:
            print("Auto-submitted OTP or button not found (moving next).")
            
        # Step 3: Enter PIN
        print("Entering PIN...")
        # Wait for PIN fields (Fyers uses 4 separate boxes or one password box)
        pin_input = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@type='password']")))
        pin_input.send_keys(pin)
        
        # Click Submit
        submit_btn = driver.find_element(By.XPATH, "//button[@type='submit']")
        submit_btn.click()
        
        # Step 4: Wait for Redirect and capture Auth Code
        print("Waiting for redirect to capture auth_code...")
        time.sleep(5) # Give it a moment to redirect
        
        current_url = driver.current_url
        print(f"Final URL: {current_url}")
        
        auth_code = None
        if "auth_code=" in current_url:
            auth_code = current_url.split("auth_code=")[1].split("&")[0]
            
        if not auth_code:
            print("[Error] Failed to capture auth_code from URL. Please check the browser state.")
            driver.quit()
            return
            
        print(f"[OK] Captured Auth Code!")
        
        # 4. Exchange for Access Token
        print("Exchanging auth code for access token...")
        session.set_token(auth_code)
        response = session.generate_token()
        
        if response and "access_token" in response:
            token = response["access_token"]
            print("\n[Success] Auto-Login successful! Your access token has been received.")
            
            # Cache the token
            token_cache_path = Path(__file__).resolve().parents[1] / ".fyers_tokens.json"
            with open(token_cache_path, "w") as f:
                json.dump({"access_token": token}, f)
            print(f"Token cached to {token_cache_path}")
        else:
            print(f"\n[Error] Token generation failed. Response: {response}")
            
    except Exception as e:
        print(f"\n[Error] Error during auto-login: {e}")
        print("The Fyers UI might have changed. You may need to update the CSS selectors in the script.")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
