"""The UI must not invent market data (2026-09-09).

A repo-wide guard, not a unit test. Fabricated values were removed from ten
separate places during this audit, and then **reappeared while the audit was
still running** (a volume fallback added to `native-chart.tsx`). Without a
rule that fails, the pattern returns.

What was found and removed on the frontend:

* `app/api/signals/route.ts` answered a backend failure with an invented
  **trade recommendation** -- `{type: "CALL BUY", confidence: 82, strength:
  "Strong", reason: "EMA 9/21 Bullish Momentum Alignment"}` -- at HTTP 200.
* `app/api/btst/route.ts` answered a backend failure with an invented
  **overnight carry recommendation** -- `{action: "CARRY CALL", gapUpProb: 75,
  reason: "Strong EOD Momentum (+0.85%) with RSI at 68"}` -- at HTTP 200.
  Carrying overnight is one of the few irreversible decisions this system
  surfaces; gap risk cannot be stopped out.
* `app/api/option-chain/route.ts` answered a backend failure with a complete
  **41-strike fabricated chain** (LTP, OI, OI change, volume and all four
  Greeks per leg from `Math.sin()`-seeded randomness), and on the *success*
  path overwrote real `oichg` and `pcr` with `deterministicRandom(...)`.
* `components/btst-predictor.tsx` synthesised `{gapUpProb: 50, gapDownProb:
  50, rsi: 50, reason: "Market scanning active"}` while nothing was scanning.
* `app/page.tsx` rotated five pre-written "AI commentary" strings at random,
  four asserting analysis that does not exist ("Institutional buying pressure
  observed in IT sector", "Volatility squeeze detected on Bank Nifty").
* Equity was seeded and defaulted to `100000` in four places; it is the ROI
  denominator, so an invented balance yields an invented ROI.
* `option-symbol-selector.tsx` built its strike ladder around a hardcoded
  24350 spot when the feed was down -- ~920 points off, in the component that
  picks the contract for a MANUAL order.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

FRONTEND = _bootstrap.REPO_ROOT / "frontend"
SCAN_DIRS = ("app", "components", "store", "lib")

#: Legitimate uses that are not market data.
_ALLOWED = (
    # SVG/DOM identifiers and pure geometry.
    "gradientId",
    "Math.sin((confidence",
    # Lot sizes are exchange contract specs, not prices.
    "LOT_SIZES",
    '"IDEA"',
)


def _sources():
    for d in SCAN_DIRS:
        root = FRONTEND / d
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix not in (".ts", ".tsx"):
                continue
            if "node_modules" in path.parts or ".next" in path.parts:
                continue
            yield path


def _code_lines(path: Path):
    """Yield (lineno, text) for lines that are not comments.

    The fixes deliberately document what they replaced, so a naive grep
    matches the explanation rather than live code.
    """
    in_block = False
    for i, raw in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        line = raw.strip()
        if in_block:
            if "*/" in line:
                in_block = False
            continue
        if line.startswith("/*"):
            if "*/" not in line:
                in_block = True
            continue
        if line.startswith("//") or line.startswith("*"):
            continue
        yield i, raw


def _hits(pattern: str) -> list[str]:
    rx = re.compile(pattern)
    out = []
    for path in _sources():
        for lineno, text in _code_lines(path):
            if any(a in text for a in _ALLOWED):
                continue
            if rx.search(text):
                rel = path.relative_to(FRONTEND)
                out.append(f"{rel}:{lineno}: {text.strip()[:100]}")
    return out


# ---------------------------------------------------------------------------

def test_no_random_market_values():
    """`Math.random()` must not produce anything a trader reads as data."""
    hits = _hits(r"Math\.random\s*\(")
    assert not hits, "Math.random() in UI code:\n  " + "\n  ".join(hits)


def test_no_time_seeded_pseudo_data():
    """`Math.sin(Date.now()/n)` was how India VIX and IV Rank were invented."""
    hits = _hits(r"Math\.sin\s*\(\s*Date\.now")
    assert not hits, "time-seeded fake values:\n  " + "\n  ".join(hits)


def test_no_deterministic_random_generators():
    """The 41-strike fake option chain was built on one of these."""
    hits = _hits(r"deterministicRandom")
    assert not hits, "deterministicRandom in UI code:\n  " + "\n  ".join(hits)


@pytest.mark.parametrize("value,what", [
    (r"\b24350\b", "hardcoded NIFTY spot (strike-ladder fallback)"),
    (r"\b24200\b", "hardcoded NIFTY spot (option-chain fallback)"),
    (r"\b23820\.35\b", "hardcoded NIFTY tick"),
    (r"\b76015\.28\b", "hardcoded SENSEX tick"),
])
def test_no_hardcoded_index_levels(value, what):
    hits = _hits(value)
    assert not hits, f"{what}:\n  " + "\n  ".join(hits)


def test_no_invented_account_balance():
    """Equity is the ROI denominator; a fake balance yields a fake ROI."""
    hits = _hits(r"(equity|Equity)\s*(\|\||\?\?)\s*100000|equity:\s*100000|useState\(100000")
    assert not hits, "invented account balance:\n  " + "\n  ".join(hits)


def test_api_routes_do_not_return_200_on_backend_failure():
    """A proxy must forward failure, not manufacture a plausible answer.

    signals, btst and option-chain all used to return `status: 200` from their
    catch blocks with invented payloads.
    """
    offenders = []
    api_root = FRONTEND / "app" / "api"
    for path in api_root.rglob("route.ts"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "status: 200" in text and "catch" in text:
            for lineno, line in _code_lines(path):
                if "status: 200" in line:
                    offenders.append(f"{path.relative_to(FRONTEND)}:{lineno}")
    assert not offenders, (
        "API routes returning 200 alongside a catch block -- verify they are "
        "not masking a backend failure:\n  " + "\n  ".join(offenders)
    )


def test_the_three_recommendation_routes_are_clean():
    """These three fabricated actionable trade advice; keep them honest."""
    for name in ("signals", "btst", "option-chain"):
        text = (FRONTEND / "app" / "api" / name / "route.ts").read_text(encoding="utf-8")
        code = "\n".join(t for _, t in _code_lines(FRONTEND / "app" / "api" / name / "route.ts"))
        for banned in ("CARRY CALL", "CALL BUY", "gapUpProb: 75", "confidence: 82"):
            assert banned not in code, f"{name}/route.ts still fabricates: {banned}"
        assert "503" in text, f"{name}/route.ts must surface unreachability"
