"""Backtest the premium-banded stop architecture against the flat-percentage one.

Why a dedicated harness rather than `backtesting_engine/run.py`
--------------------------------------------------------------
That engine backtests the *underlying index* with percentage stops. It has no
concept of an option premium, so it structurally cannot evaluate a stop table
whose whole point is that it is denominated in option rupees. Running the new
architecture through it would produce a number that looks like validation and
measures nothing.

This harness instead reuses the two pieces that already exist and are already
trusted:

* `api_bridge.generate_option_history_from_spot` — the Black-Scholes derivation
  the dashboard already uses to build option candles from index candles. It is
  the only source of option-premium history in this system.
* `shared.exits.SmartExitEngine` — the *real* exit engine, not a reimplementation.
  Trailing, partial booking and EOD behaviour are therefore exactly what live
  trading will do.

Only the initial stop differs between the two arms, which is the variable
under test.

Usage
-----
    cd trading-system
    venv\\Scripts\\python.exe scripts/validate_option_stop_loss.py
    venv\\Scripts\\python.exe scripts/validate_option_stop_loss.py --csv <path> --json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api_bridge import generate_option_history_from_spot, load_csv_history  # noqa: E402
from shared.exits import Position, SmartExitEngine  # noqa: E402
from shared.risk import resolve_initial_stop  # noqa: E402

#: Committed fixture candles, so this runs without the local data cache.
DEFAULT_DATA_DIR = (
    ROOT.parent / "Testing_Automation_AI_Trading_Bot" / "python-unit" / "fixtures" / "data"
)
DEFAULT_SYMBOL = "NSE_NIFTY50-INDEX"

#: Baseline: the flat percentage the live config carried before this change.
LEGACY_SL_PCT = 0.45

LOT_SIZE = 75

#: Rupee risk per trade used when normalising arms for comparison — 1% of a
#: ₹1L account, matching RiskConfig.risk_per_trade.
RISK_BUDGET = 1_000.0


@dataclass
class TradeOutcome:
    entry_price: float
    exit_price: float
    reason: str
    bars_held: int
    stop_distance: float

    @property
    def pnl_per_unit(self) -> float:
        return self.exit_price - self.entry_price

    @property
    def pnl_pct(self) -> float:
        return self.pnl_per_unit / self.entry_price * 100.0


@dataclass
class ArmResult:
    label: str
    trades: list[TradeOutcome] = field(default_factory=list)

    def summary(self, risk_normalised: bool = True) -> dict[str, Any]:
        """Aggregate the arm.

        `risk_normalised` sizes every trade to the same rupee risk
        (`RISK_BUDGET / stop_distance`) instead of a flat lot. Without it the
        comparison is meaningless: the banded arm's stop is ~20x wider, so a
        fixed lot size would have it risking ~20x more per trade and the P&L
        difference would measure position size, not stop quality. Production
        sizes exactly this way — `option_risk_based_sizing` solves quantity
        from the stop distance — so this is also the configuration under test.
        """
        if not self.trades:
            return {"label": self.label, "trades": 0}

        if risk_normalised:
            pnls = [
                t.pnl_per_unit * (RISK_BUDGET / t.stop_distance)
                for t in self.trades
                if t.stop_distance > 0
            ]
        else:
            pnls = [t.pnl_per_unit * LOT_SIZE for t in self.trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        reasons: dict[str, int] = {}
        for trade in self.trades:
            reasons[trade.reason] = reasons.get(trade.reason, 0) + 1

        gross_win = sum(wins)
        gross_loss = abs(sum(losses))

        # Stop integrity: how much of the *intended* risk budget an average
        # losing trade actually lost. 1.0 means the stop did its job; values
        # far above 1.0 mean price gapped straight through the stop before it
        # could be acted on, so the position's real risk was never the risk
        # that was sized for. This is the metric that separates a stop which
        # controls risk from one that merely exists.
        avg_loss_vs_budget = (
            round(abs(statistics.mean(losses)) / RISK_BUDGET, 2) if losses else 0.0
        )
        max_loss_vs_budget = round(abs(min(pnls)) / RISK_BUDGET, 2) if pnls else 0.0

        return {
            "label": self.label,
            "trades": len(self.trades),
            "total_pnl": round(sum(pnls), 2),
            "win_rate_pct": round(len(wins) / len(pnls) * 100.0, 1),
            "avg_loss_vs_risk_budget": avg_loss_vs_budget,
            "max_loss_vs_risk_budget": max_loss_vs_budget,
            "avg_win": round(statistics.mean(wins), 2) if wins else 0.0,
            "avg_loss": round(statistics.mean(losses), 2) if losses else 0.0,
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else float("inf"),
            "largest_loss": round(min(pnls), 2),
            "avg_bars_held": round(statistics.mean(t.bars_held for t in self.trades), 1),
            "avg_stop_distance": round(
                statistics.mean(t.stop_distance for t in self.trades), 2
            ),
            "exit_reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        }


def _build_engine() -> SmartExitEngine:
    """The same exit configuration live trading runs with (config/settings.json:
    trail_trigger 0.6, trail_offset 0.35)."""
    return SmartExitEngine(
        atr_multiplier=2.0,
        trailing_activation_pct=0.6,
        trailing_offset_pct=0.35,
        eod_exit_time="15:15:00",
        partial_booking_pct=50.0,
        partial_target_reward=1.0,
    )


def _simulate(
    candles: Sequence[dict[str, Any]],
    entry_index: int,
    stop_price: float,
    target: float,
) -> TradeOutcome | None:
    """Walk one trade forward through the real SmartExitEngine."""
    entry = float(candles[entry_index]["close"])
    engine = _build_engine()
    position = Position(
        symbol="NSE:NIFTY2580724500CE",
        side=1,
        entry_price=entry,
        quantity=LOT_SIZE,
        entry_time=str(candles[entry_index].get("datetime", "")),
        highest_price=entry,
        lowest_price=entry,
        stop_loss=stop_price,
        target=target,
        lot_size=LOT_SIZE,
    )

    for offset, candle in enumerate(candles[entry_index + 1:], start=1):
        price = float(candle["close"])
        timestamp = str(candle.get("datetime", ""))
        atr = abs(float(candle["high"]) - float(candle["low"])) or entry * 0.005

        should_exit, reason, qty = engine.evaluate_exit(position, price, timestamp, atr)
        if should_exit and qty is None:
            return TradeOutcome(entry, price, reason, offset, entry - stop_price)
        # A partial booking keeps the position open on a reduced size; the
        # engine has already moved the stop to breakeven.
        if should_exit and qty is not None:
            position.quantity = max(0, position.quantity - qty)
            if position.quantity <= 0:
                return TradeOutcome(entry, price, reason, offset, entry - stop_price)

    last = float(candles[-1]["close"])
    return TradeOutcome(entry, last, "End of data", len(candles) - entry_index - 1, entry - stop_price)


def run_validation(
    data_dir: Path,
    symbol: str,
    entry_every: int = 12,
) -> dict[str, Any]:
    """Enter every `entry_every` bars across several strikes and compare arms."""
    spot = load_csv_history(symbol, "1900-01-01", "2100-01-01", "5 Min", data_dir=str(data_dir))
    if not spot:
        raise SystemExit(f"No candles for {symbol} under {data_dir}")

    spot_close = float(spot[len(spot) // 2]["close"])

    banded = ArmResult("Banded SL, no target (new)")
    legacy = ArmResult(f"Flat {LEGACY_SL_PCT}% SL + 3.5% target (previous)")
    band_usage: dict[str, int] = {}

    # A spread of strikes so the sample spans the premium bands rather than
    # one narrow price range.
    strikes = [spot_close * (1 + step / 100.0) for step in (-4, -2, -1, 0, 1, 2, 4)]

    for strike in strikes:
        for opt_type in ("CE", "PE"):
            option_candles = generate_option_history_from_spot(spot, strike, opt_type)
            if len(option_candles) < 30:
                continue

            for entry_index in range(0, len(option_candles) - 20, entry_every):
                premium = float(option_candles[entry_index]["close"])
                if premium <= 0.5:
                    continue

                decision = resolve_initial_stop(premium)
                if not decision.is_tradeable:
                    continue
                band_usage[decision.band_label] = band_usage.get(decision.band_label, 0) + 1

                new_trade = _simulate(option_candles, entry_index, decision.sl_price, 0.0)
                if new_trade:
                    banded.trades.append(new_trade)

                legacy_stop = premium * (1 - LEGACY_SL_PCT / 100.0)
                legacy_target = premium * 1.035
                old_trade = _simulate(option_candles, entry_index, legacy_stop, legacy_target)
                if old_trade:
                    legacy.trades.append(old_trade)

    return {
        "symbol": symbol,
        "spot_reference": round(spot_close, 2),
        "candles": len(spot),
        "band_usage": dict(sorted(band_usage.items())),
        "risk_budget_per_trade": RISK_BUDGET,
        "arms": [banded.summary(), legacy.summary()],
        "arms_fixed_lot": [
            banded.summary(risk_normalised=False),
            legacy.summary(risk_normalised=False),
        ],
    }


def _print_report(report: dict[str, Any]) -> None:
    print(f"\nOption stop-loss validation — {report['symbol']} "
          f"({report['candles']} spot candles, spot ~{report['spot_reference']})")
    print(f"Premium bands exercised: {report['band_usage']}\n")

    for arm in report["arms"]:
        if not arm.get("trades"):
            print(f"  {arm['label']}: no trades")
            continue
        print(f"  {arm['label']}")
        print(f"    trades={arm['trades']}  total_pnl=₹{arm['total_pnl']:,.2f}  "
              f"win_rate={arm['win_rate_pct']}%  profit_factor={arm['profit_factor']}")
        print(f"    avg_win=₹{arm['avg_win']:,.2f}  avg_loss=₹{arm['avg_loss']:,.2f}  "
              f"largest_loss=₹{arm['largest_loss']:,.2f}")
        print(f"    STOP INTEGRITY: avg loss = {arm['avg_loss_vs_risk_budget']}x the risk "
              f"budget, worst = {arm['max_loss_vs_risk_budget']}x")
        print(f"    avg_bars_held={arm['avg_bars_held']}  "
              f"avg_stop_distance=₹{arm['avg_stop_distance']}")
        print(f"    exits: {arm['exit_reasons']}\n")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--entry-every", type=int, default=12)
    parser.add_argument("--json", action="store_true", help="emit raw JSON")
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = run_validation(Path(args.data_dir), args.symbol, args.entry_every)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
