"""Helper script to perform the one‑time Fyers OAuth login.

The live bot (`trading_bot.main`) requires a cached access token. This script
accepts the temporary ``code`` that Fyers returns after the user authorises the
application at the ``FYERS_REDIRECT_URI``. It then stores the refreshed token
in ``.fyers_tokens.json`` (handled by :class:`FyersClient`).

Usage::

    python -m trading_bot.login --code <auth_code>

The ``--code`` argument can be obtained from the redirect URL after logging in
via a browser (e.g. ``https://localhost?code=abcdef``).
"""

from __future__ import annotations

import argparse
import sys

from trading_bot.api.fyers_client import FyersClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fyers OAuth login – cache access token")
    parser.add_argument(
        "--code",
        required=True,
        help="Temporary auth code from Fyers redirect URL (e.g. ?code=XYZ)",
    )
    args = parser.parse_args(argv)

    client = FyersClient()
    try:
        client.login(args.code)
    except Exception as exc:  # pragma: no cover – runtime error handling
        sys.stderr.write(f"Login failed: {exc}\n")
        return 1
    finally:
        client.close()
    print("Login successful – token cached in .fyers_tokens.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
