"""CLI: rotate the encryption key used to protect broker_credentials.json.

Usage:
    python scripts/rotate_credential_key.py

Decrypts every stored broker credential under the current key, generates
a new key, re-encrypts everything under it, and only then replaces the
key file on disk (verifying the round-trip first — see
brokers/credentials.rotate_encryption_key()). The previous key is kept
alongside as .broker.key.bak in case something needs to be inspected
after the fact.

Run this periodically (e.g. every few months) or immediately if you
suspect .broker.key may have been exposed. This rotates the *encryption*
key that protects credentials at rest — it does NOT rotate the broker
credentials themselves (the actual API secret/client_id on the broker's
side). If a broker secret itself may have leaked, rotate it on the
broker's developer portal and then call save_credentials() with the new
value, separate from this script.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from brokers.credentials import rotate_encryption_key


def main() -> None:
    try:
        count = rotate_encryption_key()
    except RuntimeError as e:
        print(f"Rotation refused: {e}")
        sys.exit(1)
    print(f"Encryption key rotated successfully. Re-encrypted credentials for {count} broker(s).")
    print("Previous key backed up alongside as .broker.key.bak.")


if __name__ == "__main__":
    main()
