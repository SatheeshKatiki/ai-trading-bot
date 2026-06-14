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
        
        import urllib.parse
        import webbrowser
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import threading
        
        url = f"https://api-t1.fyers.in/api/v3/generate-authcode?client_id={client_id}&redirect_uri={urllib.parse.quote(redirect_uri, safe='')}&response_type=code&state=sample_state"
        
        print("\n" + "="*60)
        print("Opening browser for Fyers Login...")
        print("If it doesn't open automatically, click this link:")
        print(url)
        print("="*60 + "\n")
        
        # Open browser automatically
        webbrowser.open(url)
        
        print("Waiting for you to login and authorize... (Server listening on port 8080)")
        
        # Create a tiny local server to catch the redirect
        auth_code_received = None
        
        class CallbackHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass # suppress logs
                
            def do_GET(self):
                nonlocal auth_code_received
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                
                if 'auth_code' in params:
                    auth_code_received = params['auth_code'][0]
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(b"<html><body style='font-family:sans-serif; text-align:center; margin-top:50px;'><h1>Login Successful!</h1><p>You can close this window and return to the terminal.</p></body></html>")
                else:
                    self.send_response(400)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(b"<html><body><h1>Login Failed</h1><p>No auth_code found in URL.</p></body></html>")
                    
                # Signal the server to stop
                threading.Thread(target=self.server.shutdown).start()

        # Start the temporary server
        server = HTTPServer(('127.0.0.1', 8080), CallbackHandler)
        server.serve_forever()
        
        if auth_code_received:
            print("Auth code received automatically! Exchanging for access token...")
            
            session.set_token(auth_code_received)
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
        else:
            print("\n❌ Failed to receive auth_code from the browser.")
                
    except Exception as e:
        print(f"\n❌ Error during login: {e}")
        print("If you get a dependency error, we might need to install other missing packages.")

if __name__ == "__main__":
    main()
