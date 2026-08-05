"""pytest configuration for the migrated backend unit/integration suite.

Collection-time responsibilities only — the tests themselves are unchanged
from when they lived in `trading-system/tests/`.
"""
from __future__ import annotations

import os
from pathlib import Path

# Must happen before pytest imports any test module, since every one of them
# imports application code from `trading-system/`.
import _bootstrap  # noqa: F401  (import-for-side-effect: extends sys.path)

TRADING_SYSTEM_ROOT = _bootstrap.TRADING_SYSTEM_ROOT

#: Committed OHLCV fixtures used by the option-derivation and history-endpoint
#: tests. Exposed here so a test never has to rebuild the path itself.
FIXTURE_DATA_DIR = Path(__file__).resolve().parent / "fixtures" / "data"


def pytest_configure(config) -> None:
    """Run the suite from the application root, as it was written to expect.

    Several tests resolve runtime paths relative to the *current working
    directory* rather than to their own file (`config/settings.json`,
    `state.db`, `logs/`). While the suite lived inside the application tree
    that was implicit; from this directory it no longer is, so pin it
    explicitly instead of patching 20-odd call sites.
    """
    os.chdir(TRADING_SYSTEM_ROOT)
