"""pytest configuration for the migrated backend unit/integration suite.

Collection-time responsibilities only — the tests themselves are unchanged
from when they lived in `trading-system/tests/`.
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
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

    Also redirects the advanced_ai XGBoost artifact to a scratch file.
    `advanced_ai_ml_strategy` auto-retrains any model older than 24h and
    saves in place, so a plain `pytest` run silently rewrote the LIVE,
    git-tracked production model -- confirmed on 2026-09-09 by checksumming
    `models/xgboost_model.json` either side of a full run. A test suite must
    never be able to mutate a production artifact.
    """
    os.chdir(TRADING_SYSTEM_ROOT)

    scratch = Path(tempfile.gettempdir()) / "quantai_test_models"
    scratch.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault(
        "QUANTAI_XGB_MODEL_PATH", str(scratch / "xgboost_model.json")
    )


# ---------------------------------------------------------------------------
# Production-artifact guard
# ---------------------------------------------------------------------------
# Redirecting the model path (above) is the fix; this is the enforcement.
# Rather than trusting that no present or future code path writes a deployed
# artifact during a test run, checksum them at session start and again at the
# end, and fail loudly if anything moved. A test suite that mutates production
# state is a bug regardless of which line did it.
_GUARDED_ARTIFACTS = (
    TRADING_SYSTEM_ROOT / "models" / "xgboost_model.json",
    TRADING_SYSTEM_ROOT / "models" / "trade_filter_rf.pkl",
)

_artifact_digests: dict = {}


def _digest(path: Path):
    try:
        return hashlib.md5(path.read_bytes()).hexdigest()
    except OSError:
        return None


def pytest_sessionstart(session) -> None:
    for path in _GUARDED_ARTIFACTS:
        _artifact_digests[path] = _digest(path)


def pytest_sessionfinish(session, exitstatus) -> None:
    changed = [
        path for path, before in _artifact_digests.items()
        if before is not None and _digest(path) != before
    ]
    if not changed:
        return

    names = "\n".join(f"    - {p}" for p in changed)
    message = (
        "\n"
        "=========================== PRODUCTION ARTIFACT MODIFIED ===========================\n"
        "This test run rewrote deployed model artifact(s):\n"
        f"{names}\n"
        "\n"
        "Tests must never mutate production state. `advanced_ai_ml_strategy` retrains and\n"
        "saves in place whenever the artifact is older than 24h, which is how this was first\n"
        "found (2026-09-09). If you added a code path that trains a model, point it at\n"
        "QUANTAI_XGB_MODEL_PATH (already set to a scratch file for this session) or\n"
        "monkeypatch the module's _MODEL_PATH.\n"
        "===================================================================================="
    )
    # Surface it as a hard failure, not a warning that scrolls past.
    # Written straight to the real stderr (pytest's capture is already torn
    # down at sessionfinish) and reflected in the exit status.
    sys.stderr.write(message + chr(10))
    sys.stderr.flush()
    session.exitstatus = 1
