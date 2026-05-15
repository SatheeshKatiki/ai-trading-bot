import sys
import os
import json
from pathlib import Path

# Add project root to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brokers.credentials import _save_file, _CREDS_FILE

def main():
    print("=== Re-signing Credentials File ===")
    if not _CREDS_FILE.is_file():
        print("File not found!")
        return
        
    try:
        raw = _CREDS_FILE.read_bytes()
        if b"\n# MAC:" in raw:
            json_bytes, _ = raw.rsplit(b"\n# MAC:", 1)
            data = json.loads(json_bytes.decode("utf-8"))
            print("Read file without MAC. Re-signing...")
            # Remove any error flags if present
            data.pop("_integrity_error", None)
            _save_file(data)
            print("🎉 File re-signed successfully!")
        else:
            print("File has no MAC. Loading and saving to add MAC...")
            data = json.loads(raw.decode("utf-8"))
            _save_file(data)
            print("🎉 File signed successfully!")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
