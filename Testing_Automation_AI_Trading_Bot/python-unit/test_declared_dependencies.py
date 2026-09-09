"""Every third-party import must be declared in requirements.txt (2026-09-09).

Found by an AST scan during the audit: eight packages were imported by live
code but never declared. They worked only because something else pulled them
in transitively -- Pillow via matplotlib, aiohttp via a broker SDK -- so the
system ran here and would have broken on a clean install, in Docker, or in CI
the moment an upstream dropped the transitive edge.

Two of them mattered more than the rest:

* ``pyotp`` -- imported unconditionally by ``scripts/auth/auto_login_fyers.py``
  for the Fyers TOTP step, which is the zero-touch orchestrator's very first
  action of the day. It was present in requirements.txt but **commented out**,
  labelled "required by Angel One".
* ``feedparser`` / ``vaderSentiment`` / ``deep-translator`` -- ``shared/sentiment.py``
  feeds ``main.py``'s live sentiment circuit breaker, so a missing import
  silently disables a risk control rather than failing loudly.

This test re-runs that scan so the drift cannot come back.
"""

from __future__ import annotations

import ast
import sys

import pytest

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

TRADING_SYSTEM_ROOT = _bootstrap.TRADING_SYSTEM_ROOT
REQUIREMENTS = TRADING_SYSTEM_ROOT / "requirements.txt"

#: Import name -> distribution name, where they differ.
_IMPORT_TO_DIST = {
    "PIL": "pillow",
    "dotenv": "python-dotenv",
    "sklearn": "scikit-learn",
    "yaml": "pyyaml",
    "vadersentiment": "vadersentiment",
    "deep_translator": "deep-translator",
    "fyers_apiv3": "fyers-apiv3",
    "stable_baselines3": "stable-baselines3",
    "sb3_contrib": "sb3-contrib",
    "cv2": "opencv-python",
}

#: Imports that must NOT be required to run the system.
#:
#: The optional broker SDKs are deliberately commented out in requirements.txt
#: -- only the active broker's SDK is installed, via
#: scripts/install_broker_sdk.py -- and every import site is guarded. `pytest`
#: is a test-only tool that CI installs separately. `pydantic` arrives with
#: FastAPI and is guaranteed by it.
_EXEMPT = {
    "kiteconnect",   # Zerodha  — optional broker, guarded import
    "SmartApi",      # Angel One — optional broker, guarded import
    "fyers_api",     # legacy Fyers v2 shim — guarded fallback
    "pytest",        # test-only; CI installs it explicitly
    "pydantic",      # transitively guaranteed by fastapi
}

#: Directories that are not application code.
_SKIP_DIRS = {"venv", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache",
              "backups", "node_modules"}


def _declared_distributions() -> set[str]:
    """Distribution names declared in requirements.txt, normalised."""
    names = set()
    for raw in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split("#")[0].strip()
        for sep in (">=", "==", "<=", "~=", ">", "<", "["):
            name = name.split(sep)[0]
        name = name.strip().lower().replace("_", "-")
        if name:
            names.add(name)
    return names


def _local_module_names() -> set[str]:
    """Names that resolve to first-party code rather than a distribution.

    Includes every directory and every ``.py`` stem anywhere in the tree, not
    just the top level: several scripts sit inside a package directory and
    import a sibling by bare name (``drl/train.py`` does ``import
    trading_env``), which resolves because Python puts the script's own
    directory on ``sys.path``. Those are first-party either way.
    """
    names = set()
    for path in TRADING_SYSTEM_ROOT.rglob("*"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.is_dir():
            names.add(path.name)
        elif path.suffix == ".py":
            names.add(path.stem)
    return names


def _iter_source_files():
    for path in TRADING_SYSTEM_ROOT.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        yield path


def _third_party_imports() -> dict[str, set[str]]:
    """Top-level third-party import name -> the files importing it."""
    stdlib = set(sys.stdlib_module_names)
    local = _local_module_names()
    found: dict[str, set[str]] = {}

    for path in _iter_source_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module]
            else:
                continue
            for mod in mods:
                top = mod.split(".")[0]
                if top in stdlib or top in local or top in _EXEMPT:
                    continue
                found.setdefault(top, set()).add(
                    str(path.relative_to(TRADING_SYSTEM_ROOT))
                )
    return found


def test_requirements_file_exists():
    assert REQUIREMENTS.is_file()


def test_every_third_party_import_is_declared():
    declared = _declared_distributions()
    missing = {}

    for import_name, files in _third_party_imports().items():
        dist = _IMPORT_TO_DIST.get(import_name, import_name).lower().replace("_", "-")
        if dist not in declared:
            missing[import_name] = sorted(files)[:3]

    assert not missing, (
        "These packages are imported by application code but not declared in "
        "requirements.txt. They may work locally as transitive dependencies and "
        "still break a clean install, Docker or CI:\n"
        + "\n".join(f"    {name}  (e.g. {', '.join(files)})"
                    for name, files in sorted(missing.items()))
    )


@pytest.mark.parametrize("dist", [
    "pyotp",           # zero-touch Fyers TOTP auto-login
    "pillow",          # EOD Telegram card
    "aiohttp",         # lot-size updater
    "feedparser",      # sentiment circuit breaker
    "vadersentiment",  # sentiment circuit breaker
    "deep-translator", # Telugu headline translation
])
def test_specific_previously_undeclared_packages_are_declared(dist):
    """Pin the exact packages the 2026-09-09 audit found missing."""
    assert dist in _declared_distributions(), f"{dist} must stay declared"


def test_pyotp_is_not_commented_out():
    """It was present but commented, labelled 'required by Angel One'.

    auto_login_fyers.py imports it unconditionally for the Fyers TOTP step --
    the orchestrator's first action each morning -- so a fresh install would
    have failed the daily auto-login on an ImportError before market open.
    """
    for raw in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("pyotp"):
            return
    pytest.fail("pyotp must be an active requirement, not a comment")
