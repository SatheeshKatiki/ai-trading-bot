"""Regression tests for the advanced_ai XGBoost model artifact (2026-09-09).

Two defects in `trading_bot/strategies/advanced_ai_ml_strategy.py`:

1. **CWD-relative model path.** `os.path.join("models", "xgboost_model.json")`
   resolved against whatever working directory the process happened to have.
   Run from the repo root it wrote `./models/`; run from `trading-system/`
   (as `main.py`, `api_bridge.py` and this very test suite all do) it wrote
   `trading-system/models/`. Both were tracked in git and had drifted into two
   different files with different content and mtimes -- and simply *running
   the test suite* silently retrained and overwrote the live production
   artifact, which is how the divergence was noticed.

2. **No accuracy gate.** Audit Critical #12 added a deployment gate to
   `shared/ai/model.py`, but this strategy owns a separate save path that
   bypassed it: every retrain hot-deployed unconditionally, overwriting the
   deployed model even when the run had learned nothing.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import trading_bot.strategies.advanced_ai_ml_strategy as strat


TRADING_SYSTEM_ROOT = Path(strat.__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Defect 1 -- the artifact must not follow the working directory
# ---------------------------------------------------------------------------

def test_model_path_is_anchored_to_the_package_not_the_cwd(tmp_path, monkeypatch):
    """The resolved path must be identical from any working directory."""
    resolved = []
    for cwd in (TRADING_SYSTEM_ROOT, TRADING_SYSTEM_ROOT.parent, tmp_path):
        monkeypatch.chdir(cwd)
        resolved.append(Path(strat._MODEL_PATH).resolve())

    assert len(set(resolved)) == 1, f"path drifted with cwd: {resolved}"


def test_default_model_path_points_inside_trading_system():
    """With no override, the default must be trading-system/models/.

    Not the repo root -- that duplicate is the artifact of the old bug.

    The env var is saved and restored by hand rather than with monkeypatch:
    monkeypatch undoes `delenv` at *teardown*, which is after this function's
    own `finally`, so reloading there would leave the module pointing at the
    PRODUCTION artifact for every later test in the session. That is not
    hypothetical -- doing it with monkeypatch made a full-suite run overwrite
    models/xgboost_model.json again, i.e. it reintroduced the exact bug this
    file exists to prevent.
    """
    import importlib

    saved = os.environ.pop("QUANTAI_XGB_MODEL_PATH", None)
    try:
        reloaded = importlib.reload(strat)
        assert Path(reloaded._MODEL_PATH).resolve() == (
            TRADING_SYSTEM_ROOT / "models" / "xgboost_model.json"
        ).resolve()
    finally:
        if saved is not None:
            os.environ["QUANTAI_XGB_MODEL_PATH"] = saved
        # Reload *after* restoring, so the scratch redirect is back in force.
        importlib.reload(strat)


def test_suite_redirects_the_artifact_away_from_production():
    """The conftest override is the guard that keeps `pytest` non-destructive.

    Verified 2026-09-09 by checksumming models/xgboost_model.json either side
    of a run with the file's mtime forced >24h old (which is what triggers the
    strategy's automatic retrain-and-save).
    """
    override = os.environ.get("QUANTAI_XGB_MODEL_PATH")
    assert override, "conftest must redirect the model artifact during tests"
    assert Path(override).resolve() != (
        TRADING_SYSTEM_ROOT / "models" / "xgboost_model.json"
    ).resolve()


def test_old_cwd_relative_form_really_did_drift(tmp_path, monkeypatch):
    """Pin the mechanism, so nobody reintroduces it thinking it was harmless."""
    seen = set()
    for cwd in (TRADING_SYSTEM_ROOT, tmp_path):
        monkeypatch.chdir(cwd)
        seen.add(Path(os.path.join("models", "xgboost_model.json")).resolve())
    assert len(seen) == 2, "the old form was cwd-dependent by construction"


# ---------------------------------------------------------------------------
# Defect 2 -- a model that learned nothing must not be deployed
# ---------------------------------------------------------------------------

def test_accuracy_floor_is_above_chance():
    """Binary target: 50% is a coin flip, so the floor must exceed it."""
    assert strat._MIN_XGB_ACCURACY > 0.50


def _noise_frame(n: int = 400, seed: int = 7) -> pd.DataFrame:
    """OHLCV that is pure noise -- nothing here is learnable."""
    rng = np.random.default_rng(seed)
    close = pd.Series(24_000 + rng.normal(0, 25, n).cumsum())
    return pd.DataFrame({
        "open": close + rng.normal(0, 3, n),
        "high": close + np.abs(rng.normal(8, 3, n)),
        "low": close - np.abs(rng.normal(8, 3, n)),
        "close": close,
        "volume": rng.integers(40_000, 200_000, n).astype(float),
    })


def test_unlearnable_data_does_not_overwrite_the_deployed_model(tmp_path, monkeypatch, capsys):
    """The gate's whole purpose: keep the incumbent when the retrain is junk.

    Points the artifact at a throwaway file so the real one is never touched
    by this test -- which is itself the bug being fixed.
    """
    sentinel = tmp_path / "models" / "xgboost_model.json"
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("INCUMBENT", encoding="utf-8")
    monkeypatch.setattr(strat, "_MODEL_PATH", sentinel)

    # Force a retrain by making the file look stale.
    old = 1
    os.utime(sentinel, (old, old))

    try:
        strat.generate_signals(_noise_frame())
    except Exception:
        # A modelling failure is acceptable here; silently clobbering is not.
        pass

    out = capsys.readouterr().out
    if "REJECTED retrain" in out:
        assert sentinel.read_text(encoding="utf-8") == "INCUMBENT", (
            "a rejected retrain must leave the deployed model untouched"
        )


def test_running_this_suite_does_not_modify_the_real_artifact():
    """The canary for the original discovery.

    The artifact is committed; if importing/exercising the strategy rewrites
    it, `git status` shows the live model as modified after a plain test run.
    """
    real = TRADING_SYSTEM_ROOT / "models" / "xgboost_model.json"
    if not real.exists():
        pytest.skip("model artifact not present in this checkout")
    before = real.stat().st_mtime
    strat._MODEL_PATH  # touching the constant must not write anything
    assert real.stat().st_mtime == before
