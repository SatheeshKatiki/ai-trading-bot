"""ema9_rsi_momentum execution variants: timeframe and strike choice (2026-09-11).

Measured over 578 NIFTY sessions with the owner's exits and costs included,
the strategy's 5-minute / ATM execution loses -3.20% of premium per trade,
while the 15-minute chart with an ITM strike made +1.99% (n=170) -- positive
in both halves of the data but NOT proven (10/20-minute lose, 2024 flat,
SENSEX loses). So:

* ``Ema9RsiMomentumConfig`` gains ``timeframe_minutes`` / ``strike_selection``
  (+ ITM delta target, spread cap) whose DEFAULTS are today's behaviour;
* ``strike_selection.select_strike`` picks ITM by the chain's real delta and
  fails closed without one;
* ``ema9_variant_observer`` paper-trades 15-min / ITM as an isolated book,
  on closed bars only (``shared/closed_bars``).

The main book's entry guards and the closed-bar helper itself are tested in
test_paper_observer_entry_guards.py.
"""

from __future__ import annotations

import ast
import datetime
import inspect
import json
import types

import numpy as np
import pandas as pd
import pytest
import pytz

import auto_daily_session as ads
import ema9_variant_observer as ev
import paper_observer as po
from trading_bot.strategies.ema9_rsi_momentum import generate_signals
from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig
from trading_bot.strategies.ema9_rsi_momentum.strike_selection import select_strike

IST = pytz.timezone("Asia/Kolkata")
SPOT = 23_283.0


def _ist(h, m, s=0, day=11):
    return IST.localize(datetime.datetime(2026, 9, day, h, m, s))


def _row(strike, ce, pe):
    """ce/pe = (ltp, bid, ask, delta, spread_pct)."""
    def leg(v):
        ltp, bid, ask, delta, spr = v
        return {"ltp": ltp, "bid": bid, "ask": ask, "delta": delta,
                "theta": -9.0, "iv": 11.5, "spread_pct": spr}
    return {"strike": strike, "ce": leg(ce), "pe": leg(pe)}


def _chain_rows():
    """The live NIFTY chain at 10:30 IST on 2026-09-11 (spot 23,283)."""
    return [
        _row(23100, (234.00, 233.95, 234.50, 0.7783, 0.24), (39.30, 39.20, 39.40, -0.2362, 0.25)),
        _row(23150, (196.50, 196.15, 196.65, 0.7182, 0.25), (51.15, 51.05, 51.25, -0.2916, 0.29)),
        _row(23200, (161.45, 161.05, 161.45, 0.6521, 0.25), (66.50, 66.40, 66.60, -0.3552, 0.23)),
        _row(23250, (129.95, 129.65, 129.95, 0.5794, 0.23), (85.00, 84.95, 85.05, -0.4243, 0.06)),
        _row(23300, (102.50, 102.25, 102.50, 0.5026, 0.24), (107.65, 107.60, 107.70, -0.4973, 0.05)),
        _row(23350, (78.70, 78.80, 78.90, 0.4248, 0.13), (134.45, 134.30, 134.60, -0.5707, 0.22)),
        _row(23400, (59.55, 59.55, 59.75, 0.3500, 0.34), (165.50, 165.30, 165.75, -0.6408, 0.27)),
        _row(23450, (44.65, 44.50, 44.65, 0.2822, 0.34), (199.50, 199.25, 199.75, -0.7065, 0.25)),
        _row(23500, (33.05, 33.00, 33.05, 0.2229, 0.15), (238.00, 237.80, 238.25, -0.7620, 0.19)),
    ]


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """No Telegram, no writes outside tmp, no chain cache bleed."""
    monkeypatch.setattr(po, "alerter", None)
    monkeypatch.setattr(ev, "VARIANTS_DIR", tmp_path / "variants")
    po._CHAIN_CACHE.clear()
    yield
    po._CHAIN_CACHE.clear()


# ---------------------------------------------------------------------------
# Config: new knobs, unchanged defaults
# ---------------------------------------------------------------------------

def test_defaults_are_todays_behaviour():
    cfg = Ema9RsiMomentumConfig()
    assert cfg.timeframe_minutes == 5
    assert cfg.strike_selection == "ATM"


def test_new_knobs_load_from_settings():
    cfg = Ema9RsiMomentumConfig.from_settings(
        {"ema9_rsi_timeframe_minutes": 15, "ema9_rsi_strike_selection": "ITM"})
    assert (cfg.timeframe_minutes, cfg.strike_selection) == (15, "ITM")


def _trend_frame(seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.DatetimeIndex([d + pd.Timedelta(minutes=5 * k)
                            for d in pd.date_range("2026-05-11 09:15", periods=4, freq="D")
                            for k in range(75)])
    n = len(idx)
    legs = np.array_split(np.arange(n), 3)
    path, level = [], 23_400.0
    for k, leg in enumerate(legs):
        move = 220.0 if k % 2 == 0 else -240.0
        path.append(level + np.linspace(0, move, len(leg)))
        level += move
    close = np.concatenate(path) + rng.normal(0, 6, n)
    return pd.DataFrame({"open": np.r_[close[0], close[:-1]],
                         "high": close + np.abs(rng.normal(7, 3, n)),
                         "low": close - np.abs(rng.normal(7, 3, n)),
                         "close": close, "volume": 1e5}, index=idx)


def test_execution_knobs_never_change_the_signal_itself():
    """Timeframe/strike choose WHERE the rules run and WHAT is bought; the
    rules themselves must be identical."""
    df = _trend_frame()
    plain = generate_signals(df)
    tuned = generate_signals(df, timeframe_minutes=15, strike_selection="ITM",
                             itm_target_delta=0.7, max_entry_spread_pct=1.0)
    pd.testing.assert_series_equal(plain, tuned)


# ---------------------------------------------------------------------------
# Strike selection
# ---------------------------------------------------------------------------

def test_itm_ce_picks_the_delta_nearest_target():
    leg = select_strike(_chain_rows(), SPOT, 1, "ITM", 0.70)
    assert leg["strike"] == 23150 and leg["opt_type"] == "CE" and leg["mode"] == "ITM"
    assert leg["ask"] == 196.65


def test_itm_pe_picks_above_spot():
    leg = select_strike(_chain_rows(), SPOT, -1, "ITM", 0.70)
    assert leg["strike"] == 23450 and leg["opt_type"] == "PE"


def test_itm_never_returns_an_out_of_the_money_strike():
    # A target no ITM leg is near must still resolve INSIDE the money.
    ce = select_strike(_chain_rows(), SPOT, 1, "ITM", 0.30)
    pe = select_strike(_chain_rows(), SPOT, -1, "ITM", 0.30)
    assert ce["strike"] < SPOT and pe["strike"] > SPOT


def test_atm_is_the_nearest_strike():
    assert select_strike(_chain_rows(), SPOT, 1, "ATM")["strike"] == 23300
    assert select_strike(_chain_rows(), SPOT, -1, "ATM")["strike"] == 23300


def test_spread_cap_skips_an_illiquid_leg():
    rows = _chain_rows()
    rows[1]["ce"]["spread_pct"] = 1.5                   # 23150 CE now too wide
    assert select_strike(rows, SPOT, 1, "ITM", 0.70, max_spread_pct=1.0)["strike"] == 23200


def test_spread_is_computed_when_the_chain_omits_it():
    rows = _chain_rows()
    for r in rows:
        r["ce"].pop("spread_pct")
    leg = select_strike(rows, SPOT, 1, "ITM", 0.70)
    assert leg["strike"] == 23150
    assert leg["spread_pct"] == pytest.approx((196.65 - 196.15) / 196.65 * 100, abs=1e-3)


def test_itm_without_any_delta_fails_closed():
    rows = _chain_rows()
    for r in rows:
        r["ce"]["delta"] = None
    assert select_strike(rows, SPOT, 1, "ITM") is None


def test_atm_does_not_step_to_a_neighbour_when_untradeable():
    rows = _chain_rows()
    rows[4]["ce"].update(ltp=0.0, bid=0.0, ask=0.0)     # 23300 CE: no quote
    assert select_strike(rows, SPOT, 1, "ATM") is None


@pytest.mark.parametrize("kwargs", [{"side": 0}, {"mode": "OTM"}])
def test_bad_arguments_raise(kwargs):
    args = {"chain_rows": _chain_rows(), "spot": SPOT, "side": 1, "mode": "ITM"}
    args.update(kwargs)
    with pytest.raises(ValueError):
        select_strike(**args)


def test_no_spot_or_no_chain_selects_nothing():
    assert select_strike(_chain_rows(), 0, 1, "ITM") is None
    assert select_strike([], SPOT, 1, "ITM") is None


# ---------------------------------------------------------------------------
# Variant book
# ---------------------------------------------------------------------------

CHAIN = {"chain": _chain_rows(), "underlying_price": SPOT, "synthetic": False}


def _bar_frame(bar_start: str):
    return pd.DataFrame({"open": [SPOT], "high": [SPOT + 5], "low": [SPOT - 5],
                         "close": [SPOT], "volume": [0.0]},
                        index=pd.DatetimeIndex([bar_start]))


def _session(tmp_path):
    return ev.load_session(tmp_path / "none.json", "15m_itm", "2026-09-11")


def test_variant_config_changes_only_execution():
    cfg, base = ev.build_config("15m_itm"), Ema9RsiMomentumConfig()
    assert (cfg.timeframe_minutes, cfg.strike_selection) == (15, "ITM")
    for name in ("ema_fast", "ema_slow", "rsi_length", "rsi_ma_length", "min_adx",
                 "time_start", "time_end", "enable_touch_filter"):
        assert getattr(cfg, name) == getattr(base, name)


def test_freshness_window():
    close = datetime.datetime(2026, 9, 11, 10, 30)
    assert ev.is_fresh(close, close + datetime.timedelta(seconds=60))
    assert not ev.is_fresh(close, close + datetime.timedelta(seconds=181))
    assert not ev.is_fresh(close, close - datetime.timedelta(seconds=1))


def test_price_exits_and_breakeven_trail():
    pos = {"entry_premium": 100.0, "sl_premium": 85.0, "tgt_premium": 133.0, "trailed": False}
    assert ev.check_price_exits(dict(pos), 84.9) == "STOP LOSS"
    assert ev.check_price_exits(dict(pos), 133.0) == "TARGET"
    trail = dict(pos)
    assert ev.check_price_exits(trail, 116.0) is None
    assert trail["trailed"] and trail["sl_premium"] == 100.0
    assert ev.check_price_exits(trail, 99.5) == "BREAKEVEN STOP"


def test_fresh_signal_opens_an_itm_position_at_the_ask(monkeypatch, tmp_path):
    monkeypatch.setattr(ev, "latest_closed_signal", lambda df, cfg: 1)
    monkeypatch.setattr(po, "fetch_option_chain", lambda s, *a, **k: CHAIN)
    sess = _session(tmp_path)
    assert ev.consider_entry(sess, "NIFTY", ev.build_config("15m_itm"),
                             _bar_frame("2026-09-11 10:15"), _ist(10, 31))
    pos = sess["open_positions"]["NIFTY"]
    assert pos["strike"] == 23150 and pos["opt_type"] == "CE" and pos["strike_mode"] == "ITM"
    assert pos["entry_premium"] == 196.65                                 # the ask, not ltp
    assert pos["sl_premium"] == round(196.65 * 0.85, 2)
    assert pos["tgt_premium"] == round(196.65 * 1.33, 2)
    assert pos["quantity"] == po.LOT_SIZE["NIFTY"]


def test_stale_signal_is_never_bought(monkeypatch, tmp_path):
    monkeypatch.setattr(ev, "latest_closed_signal", lambda df, cfg: 1)
    sess = _session(tmp_path)
    assert not ev.consider_entry(sess, "NIFTY", ev.build_config("15m_itm"),
                                 _bar_frame("2026-09-11 10:15"), _ist(13, 0))
    assert sess["open_positions"] == {} and sess["signals"] == []


@pytest.mark.parametrize("setup,expected", [
    ("synthetic", "skipped: synthetic chain"),
    ("cap", "skipped: daily trade cap"),
    ("eod", "skipped: after the EOD cutoff"),
])
def test_entry_guards(monkeypatch, tmp_path, setup, expected):
    monkeypatch.setattr(ev, "latest_closed_signal", lambda df, cfg: -1)
    chain = dict(CHAIN, synthetic=(setup == "synthetic"))
    monkeypatch.setattr(po, "fetch_option_chain", lambda s, *a, **k: chain)
    sess = _session(tmp_path)
    bar, now = "2026-09-11 10:15", _ist(10, 31)
    if setup == "cap":
        sess["trades"] = [{}] * ev.MAX_TRADES_PER_DAY
    if setup == "eod":
        bar, now = "2026-09-11 15:00", _ist(15, 15, 30)
    ev.consider_entry(sess, "NIFTY", ev.build_config("15m_itm"), _bar_frame(bar), now)
    assert sess["open_positions"] == {}
    assert sess["signals"][-1]["action"].startswith(expected)


def _open(monkeypatch, tmp_path):
    monkeypatch.setattr(ev, "latest_closed_signal", lambda df, cfg: 1)
    monkeypatch.setattr(po, "fetch_option_chain", lambda s, *a, **k: CHAIN)
    sess = _session(tmp_path)
    ev.consider_entry(sess, "NIFTY", ev.build_config("15m_itm"),
                      _bar_frame("2026-09-11 10:15"), _ist(10, 31))
    return sess, sess["open_positions"]["NIFTY"]


def _quote(monkeypatch, bid):
    q = None if bid is None else {"ltp": bid, "bid": bid, "ask": bid + 0.5}
    monkeypatch.setattr(po, "fetch_live_premium", lambda *a, **k: q)


def test_stop_loss_marks_to_the_bid(monkeypatch, tmp_path):
    sess, _ = _open(monkeypatch, tmp_path)
    _quote(monkeypatch, 160.0)
    assert ev.manage_position(sess, "NIFTY", sess["open_positions"]["NIFTY"],
                              _bar_frame("2026-09-11 10:30"), False, _ist(10, 50))
    t = sess["trades"][-1]
    assert t["exit_reason"] == "STOP LOSS" and t["exit_price_source"] == "broker_bid"
    assert t["exit_premium"] == 160.0 and t["net_return_pct"] < 0
    assert sess["open_positions"] == {}


def test_reversal_is_consulted_only_on_a_newly_closed_bar(monkeypatch, tmp_path):
    sess, pos = _open(monkeypatch, tmp_path)
    _quote(monkeypatch, 200.0)

    def must_not_run(*a, **k):
        raise AssertionError("reversal read mid-bar")

    monkeypatch.setattr(ev, "evaluate_protective_exit", must_not_run)
    ev.manage_position(sess, "NIFTY", pos, _bar_frame("2026-09-11 10:15"), False, _ist(10, 40))
    assert "NIFTY" in sess["open_positions"]

    rev = types.SimpleNamespace(should_exit=True, reason="EXIT CE: EMA9 crossed below EMA20")
    monkeypatch.setattr(ev, "evaluate_protective_exit", lambda *a, **k: rev)
    two = pd.concat([_bar_frame("2026-09-11 10:15"), _bar_frame("2026-09-11 10:30")])
    ev.manage_position(sess, "NIFTY", pos, two, True, _ist(10, 45, 5))
    assert sess["trades"][-1]["exit_reason"] == "REVERSAL EXIT"
    assert sess["trades"][-1]["exit_detail"].startswith("EXIT CE")


def test_eod_square_off(monkeypatch, tmp_path):
    sess, pos = _open(monkeypatch, tmp_path)
    _quote(monkeypatch, 200.0)
    ev.manage_position(sess, "NIFTY", pos, _bar_frame("2026-09-11 15:00"), False, _ist(15, 15, 10))
    assert sess["trades"][-1]["exit_reason"] == "EOD 15:15"


def test_no_quote_holds_mid_session_and_uses_last_mark_at_eod(monkeypatch, tmp_path):
    sess, pos = _open(monkeypatch, tmp_path)
    _quote(monkeypatch, None)
    assert not ev.manage_position(sess, "NIFTY", pos, _bar_frame("2026-09-11 10:30"), True, _ist(11, 0))
    assert "NIFTY" in sess["open_positions"]
    ev.manage_position(sess, "NIFTY", pos, _bar_frame("2026-09-11 15:00"), False, _ist(15, 15, 10))
    assert sess["trades"][-1]["exit_price_source"] == "last_mark"


def test_open_positions_survive_a_restart(monkeypatch, tmp_path):
    sess, _ = _open(monkeypatch, tmp_path)
    path = ev.session_file("15m_itm", "2026-09-11")
    po.save_session_atomic(sess, path)
    again = ev.load_session(path, "15m_itm", "2026-09-11")
    assert again["open_positions"]["NIFTY"]["strike"] == 23150


def test_scorecard_withholds_a_verdict_until_enough_data(tmp_path):
    for day, pnl in (("2026-09-11", 500.0), ("2026-09-14", -200.0)):
        with open(ev.session_file("15m_itm", day), "w", encoding="utf-8") as f:
            json.dump({"trades": [{"net_pnl": pnl, "net_return_pct": pnl / 100,
                                   "exit_reason": "TARGET" if pnl > 0 else "STOP LOSS"}]}, f)
    card = ev.build_scorecard("15m_itm")
    assert (card["sessions"], card["trades"], card["wins"]) == (2, 2, 1)
    assert card["net_pnl"] == 300.0
    assert card["verdict"].startswith("COLLECTING DATA")
    assert card["backtest_reference"]["trades"] == 170


def test_variant_book_never_touches_the_main_book():
    """No state.db, no dashboard positions -- the two books must not mix."""
    tree = ast.parse(inspect.getsource(ev))
    used = {n.attr for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "po"}
    assert not used & {"record_trade", "update_equity", "sync_active_positions"}


def test_variant_logs_are_invisible_to_the_main_eod_report():
    """The EOD report globs paper_obs_logs/*<date>*.json -- not recursive."""
    import importlib

    real = importlib.reload(ev).VARIANTS_DIR
    assert real.parent == po.LOG_DIR and real != po.LOG_DIR
    assert 'obs_log_dir.glob(f"*{today_str}*.json")' in inspect.getsource(ads)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def test_orchestrator_launches_the_variant_book():
    argv = ads.variant_sv._launcher()
    assert any(str(a).endswith("ema9_variant_observer.py") for a in argv)
    assert argv[-2:] == ["--variant", "15m_itm"]
    assert ads.variant_sv._restart_on_clean_exit is False
    src = inspect.getsource(ads)
    assert "start_variant_book()" in src and "variant_sv.supervise()" in src
    assert "variant_sv.reset()" in src


def test_teardown_stops_the_variant_book(monkeypatch):
    stopped = []
    for name in ("variant_sv", "observer_sv", "backend_sv"):
        monkeypatch.setattr(getattr(ads, name), "stop", lambda n=name: stopped.append(n))
    monkeypatch.setattr(ads, "kill_process_on_ports", lambda ports: None)
    ads.stop_all_subprocesses()
    assert "variant_sv" in stopped
