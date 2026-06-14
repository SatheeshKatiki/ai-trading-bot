import sys
import os
import json
import urllib.parse
import http.server
import socketserver
import webbrowser
from pathlib import Path
from fyers_apiv3 import fyersModel

# Add project root to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from brokers.credentials import load_credentials

PORT = 8080
auth_code = None

class CallbackHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed_url = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        if 'auth_code' in query_params:
            auth_code = query_params['auth_code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            # Professional response page
            html = """
            <html>
            <head>
                <title>Login Successful</title>
                <style>
                    body {
                        font-family: sans-serif;
                        text-align: center;
                        padding-top: 100px;
                        background-color: #0f172a;
                        color: white;
                    }
                    .container {
                        background-color: #1e293b;
                        padding: 40px;
                        border-radius: 12px;
                        display: inline-block;
                        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
                        border: 1px solid #334155;
                    }
                    h1 { color: #10b981; margin-bottom: 10px; }
                    p { color: #94a3b8; font-size: 16px; }
                    .logo { font-size: 40px; margin-bottom: 20px; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="logo">🤖</div>
                    <h1>🎉 Login Successful!</h1>
                    <p>The authorization code has been captured automatically.</p>
                    <p>You can close this tab now.</p>
                </div>
                <script>
                    // Try to close the tab automatically
                    setTimeout(() => {
                        window.close();
                    }, 2000);
                </script>
            </body>
            </html>
            """
            self.wfile.write(html.encode('utf-8'))
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid request")

def main():
    global auth_code
    print("=== Fyers Auto-Capture Login (Advanced) ===")
    
    # Load credentials
    creds = load_credentials("fyers")
    if not creds:
        print("Error: No Fyers credentials found!")
        sys.exit(1)
        
    client_id = creds.get("client_id")
    secret_key = creds.get("secret_key")
    redirect_uri = f"http://127.0.0.1:{PORT}"
    
    if not client_id or not secret_key:
        print("Error: Missing Client ID or Secret Key.")
        sys.exit(1)
        
    # Generate Auth URL
    session = fyersModel.SessionModel(
        client_id=client_id,
        secret_key=secret_key,
        redirect_uri=redirect_uri,
        response_type="code",
        grant_type="authorization_code"
    )
    auth_url = session.generate_authcode()
    
    print("\n[1] Opening Fyers login page in your browser...")
    webbrowser.open(auth_url)
    
    print(f"[2] Starting local server to capture redirect on port {PORT}...")
    
    # Run server to handle exactly ONE request
    # Allow address reuse to prevent "Address already in use" errors on quick restarts
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), CallbackHandler) as httpd:
        print("Waiting for you to log in on the browser...")
        while auth_code is None:
            httpd.handle_request()
            
    print(f"\n[3] Captured Auth Code: {auth_code[:15]}...")
    
    # Exchange for token
    try:
        print("Exchanging auth code for access token...")
        session.set_token(auth_code)
        response = session.generate_token()
        
        if response and "access_token" in response:
            token = response["access_token"]
            print("\n[Success] Login successful! Token generated.")
            
            # Save token
            token_path = Path(__file__).resolve().parents[2] / ".fyers_tokens.json"
            with open(token_path, "w") as f:
                json.dump({"access_token": token}, f)
            print(f"Token saved to {token_path}")
            sys.exit(0)
        else:
            print(f"\n[Error] Login failed! Response: {response}")
            sys.exit(1)
    except Exception as e:
        print(f"\n[Error] Token Generation Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
