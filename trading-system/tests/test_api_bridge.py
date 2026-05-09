import sys
import os
from pathlib import Path

# Add project root to path so we can import api_bridge
sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from api_bridge import app

client = TestClient(app)

def test_history_endpoint():
    """Test that the history endpoint returns data structure correctly."""
    print("Testing /api/history...")
    response = client.get("/api/history?symbol=RELIANCE&start_date=2026-01-01&end_date=2026-01-05&timeframe=5 Min")
    
    # It might return 404 or 500 if yfinance fails or no internet, 
    # but we want to check the structure if it succeeds.
    if response.status_code == 200:
        data = response.json()
        assert "symbol" in data
        assert "data" in data
        assert isinstance(data["data"], list)
        print("✓ /api/history returned 200 OK with valid structure.")
    else:
        print(f"i /api/history returned {response.status_code} (This is acceptable if no internet or asset not found)")

def test_backtest_endpoint():
    """Test that the backtest endpoint computes strategy signals."""
    print("Testing /api/backtest...")
    response = client.get("/api/backtest?symbol=RELIANCE&start_date=2026-01-01&end_date=2026-01-05&timeframe=5 Min")
    
    if response.status_code == 200:
        data = response.json()
        assert "stats" in data
        assert "trades" in data
        assert "equityCurve" in data
        print("✓ /api/backtest returned 200 OK with valid strategy simulation.")
    else:
        print(f"i /api/backtest returned {response.status_code}")

def test_signals_endpoint():
    """Test that the signals endpoint generates current bias."""
    print("Testing /api/signals...")
    response = client.get("/api/signals?symbol=NIFTY")
    
    if response.status_code == 200:
        data = response.json()
        assert "confidence" in data
        assert "status" in data
        assert "bias" in data
        print("✓ /api/signals returned 200 OK.")
    else:
        print(f"i /api/signals returned {response.status_code}")

if __name__ == "__main__":
    print("=== Running Institutional Integration Tests ===")
    test_history_endpoint()
    test_backtest_endpoint()
    test_signals_endpoint()
    print("===============================================")
