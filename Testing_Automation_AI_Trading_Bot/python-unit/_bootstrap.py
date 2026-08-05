"""Makes the `trading-system` package tree importable from this directory.

These tests used to live inside `trading-system/tests/`, where every file
opened with its own copy of

    sys.path.append(str(Path(__file__).resolve().parents[1]))

to reach `brokers/`, `shared/`, `trading_bot/` and `api_bridge.py` one level
up. Now that the suite lives in `Testing_Automation_AI_Trading_Bot/`, that
relative hop is different — and duplicating the new one across 23 files
would guarantee it drifts. This module is the single place that knows where
the application code is.

Two entry points need it, which is why this is a module and not just
`conftest.py`:

* `pytest` runs — `conftest.py` imports this before collection.
* Direct execution (`python test_risk_management.py`) — 10 of these files
  still have `if __name__ == "__main__"` blocks, and importing this module
  works there too because Python puts the script's own directory on
  `sys.path` first.
"""
from __future__ import annotations

import sys
from pathlib import Path

#: Repository root — two levels up from this file
#: (`<repo>/Testing_Automation_AI_Trading_Bot/python-unit/_bootstrap.py`).
REPO_ROOT = Path(__file__).resolve().parents[2]

#: The application tree under test. Everything these tests import
#: (`brokers`, `shared`, `trading_bot`, `backtesting_engine`, `api_bridge`)
#: is rooted here.
TRADING_SYSTEM_ROOT = REPO_ROOT / "trading-system"


def install() -> Path:
    """Put `trading-system/` on `sys.path` (idempotent) and return it.

    Prepended rather than appended so the application's own modules win over
    any same-named package that happens to be installed in the environment.
    """
    path = str(TRADING_SYSTEM_ROOT)
    if path not in sys.path:
        sys.path.insert(0, path)
    return TRADING_SYSTEM_ROOT


install()
