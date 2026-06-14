# Authentication & Credential Scripts

Scripts for broker authentication, token generation, and credential management.

## Scripts

| Script | Purpose |
|--------|---------|
| `auto_login_fyers.py` | Automated Fyers login via Selenium (primary) |
| `login_fyers.py` | Manual Fyers login flow |
| `generate_token.py` | Generate access token from auth code |
| `auto_capture_token.py` | Auto-capture token from redirect URL |
| `automated_login.py` | Wrapper for automated login |
| `save_broker_creds.py` | Save encrypted broker credentials |
| `resign_creds.py` | Re-encrypt credentials with new key |

## Usage

```bash
# Run from the trading-system/ directory
cd trading-system
python scripts/auth/auto_login_fyers.py
```
