"""The Risk page showed numbers nobody produced (2026-09-22).

`GET /api/risk` was a Next.js route returning constants: Nifty 45% / Bank
Nifty 35% / IT 20% exposure, a Mon-to-Fri drawdown series, a 10,000
daily-loss limit and a hand-written correlation matrix. The /risk page
rendered them, so it looked like risk management and was decoration.

Every figure is now derived from what the books actually wrote:

  exposure     open positions in config/active_positions.json
  drawdown     the per-trade net_pnl in paper_obs_logs/session_*.json
  limits       the ones the engine enforces, from config/settings.json
  correlation  measured from the cached index candles in data/

and anything that cannot be derived is omitted with a reason in `notes`,
rather than filled in -- the rule this repo already had to learn when the
option chain's open interest was coming from `deterministic_random()`.
"""

from __future__ import annotations

import pathlib

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)


def _api() -> str:
    return pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "api_bridge.py").read_text(
        encoding="utf-8", errors="ignore")


def _route() -> str:
    root = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT).parent
    return (root / "frontend" / "app" / "api" / "risk" / "route.ts").read_text(
        encoding="utf-8", errors="ignore")


def _endpoint() -> str:
    src = _api()
    start = src.index('@app.get("/api/risk")')
    return src[start:src.index('@app.get("/api/strategy-markers")', start)]


def _route_code() -> str:
    """The route with its comments stripped.

    The comment explaining what was removed necessarily quotes the old made-up
    figures, so a plain substring search would match its own tombstone.
    """
    import re
    src = _route()
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(l for l in src.splitlines() if not l.strip().startswith("//"))


def test_the_frontend_route_no_longer_invents_the_numbers():
    code = _route_code()
    for invented in ("exposureData = [", "drawdownData = [",
                     "correlationMatrix = [", "maxDailyLoss: 10000",
                     "IT Sector"):
        assert invented not in code, f"{invented!r} was fabricated data"
    assert "BACKEND_URL" in code and "/api/risk" in code, "it must proxy the engine"


def test_the_backend_endpoint_exists():
    assert '@app.get("/api/risk")' in _api()


def test_exposure_comes_from_the_real_open_positions():
    body = _endpoint()
    assert "active_positions.json" in body
    assert "entry_price" in body and "quantity" in body


def test_drawdown_comes_from_the_recorded_sessions():
    body = _endpoint()
    assert "paper_obs_logs" in body
    assert "net_pnl" in body
    assert "peak" in body, "a drawdown needs a running peak, not a raw P&L"


def test_the_limits_are_the_ones_the_engine_actually_enforces():
    body = _endpoint()
    for key in ("max_daily_loss_pct", "max_daily_trades", "emergency_stop"):
        assert key in body, f"{key} is enforced by the engine and must be reported"


def test_correlation_is_measured_not_asserted():
    body = _endpoint()
    assert "pct_change" in body and ".corr()" in body
    assert "NSE_NIFTY50-INDEX_5Min.csv" in body


def test_missing_data_is_reported_rather_than_filled_in():
    body = _endpoint()
    assert "notes" in body
    for absence in ("no open positions", "no session logs",
                    "not enough overlapping index history"):
        assert absence in body, f"the {absence!r} case must say so, not invent a number"


def test_correlation_needs_two_real_series_before_it_reports_anything():
    body = _endpoint()
    assert "len(series) >= 2" in body


def test_a_short_history_is_not_correlated():
    """Ten daily closes is already thin; fewer is noise presented as fact."""
    assert "len(daily) >= 10" in _endpoint()
