"""Broker SDK installer — interactive setup for optional broker SDKs.

Usage
-----
    python scripts/install_broker_sdk.py

This script detects which broker you want to use and installs only the
required SDK. Run this ONCE when switching to a new broker.

Brokers supported
-----------------
  fyers    — Fyers Securities (default, already installed)
  kite     — Zerodha Kite Connect
  angel    — Angel One SmartAPI
"""

from __future__ import annotations

import subprocess
import sys

BROKERS: dict[str, dict] = {
    "fyers": {
        "display": "Fyers Securities",
        "packages": ["fyers-apiv3"],
        "notes": "Already installed by default. No action needed.",
        "docs": "https://myapi.fyers.in/docs/",
    },
    "kite": {
        "display": "Zerodha Kite Connect",
        "packages": ["kiteconnect>=5.0.1"],
        "notes": (
            "After installing, uncomment 'kiteconnect>=5.0.1' in requirements.txt.\n"
            "Set active_broker = 'kite' in config/settings.json.\n"
            "Obtain API key + secret from https://developers.kite.trade/"
        ),
        "docs": "https://kite.trade/docs/connect/v3/",
    },
    "angel": {
        "display": "Angel One SmartAPI",
        "packages": ["smartapi-python>=1.3.9", "pyotp>=2.9.0", "websocket-client>=1.6.0"],
        "notes": (
            "After installing, uncomment 'smartapi-python' in requirements.txt.\n"
            "Set active_broker = 'angel' in config/settings.json.\n"
            "Obtain API key from https://smartapi.angelone.in/"
        ),
        "docs": "https://smartapi.angelone.in/docs/",
    },
}

SEPARATOR = "─" * 60


def pip_install(packages: list[str]) -> bool:
    """Install packages via pip. Returns True on success."""
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade"] + packages
    print(f"\n  Running: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, check=False)
    return result.returncode == 0


def print_broker_menu() -> None:
    print(f"\n{SEPARATOR}")
    print("  QuantAI — Broker SDK Installer")
    print(SEPARATOR)
    for key, info in BROKERS.items():
        print(f"  [{key}]  {info['display']}")
    print(f"  [q]    Quit")
    print(SEPARATOR)


def main() -> None:
    print_broker_menu()

    while True:
        choice = input("\nSelect broker to install SDK for: ").strip().lower()

        if choice == "q":
            print("Exiting.")
            sys.exit(0)

        if choice not in BROKERS:
            print(f"  Invalid choice '{choice}'. Please choose from: {', '.join(BROKERS)}")
            continue

        broker = BROKERS[choice]
        print(f"\n{SEPARATOR}")
        print(f"  Installing SDK for: {broker['display']}")
        print(f"  Packages: {', '.join(broker['packages'])}")
        print(SEPARATOR)

        if choice == "fyers":
            print(f"\n  ✅ {broker['notes']}")
            print(f"  Docs: {broker['docs']}")
            break

        confirm = input(f"\n  Install {len(broker['packages'])} package(s)? [y/N] ").strip().lower()
        if confirm != "y":
            print("  Aborted.")
            sys.exit(0)

        success = pip_install(broker["packages"])

        if success:
            print(f"\n  ✅ SDK installed successfully!")
        else:
            print(f"\n  ❌ Installation failed. Check your internet connection and try again.")
            sys.exit(1)

        print(f"\n{SEPARATOR}")
        print("  Next steps:")
        for line in broker["notes"].split("\n"):
            print(f"    {line}")
        print(f"\n  Documentation: {broker['docs']}")
        print(SEPARATOR)
        break


if __name__ == "__main__":
    main()
