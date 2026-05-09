"""
╔══════════════════════════════════════════════════════════════════╗
║           AI Trade-Filter Model — Training Script               ║
║                                                                  ║
║  Downloads 2 years of NSE data via yfinance, engineers 18+      ║
║  technical features through the production feature pipeline,     ║
║  trains a RandomForest (or XGBoost) classifier to identify       ║
║  profitable vs. unprofitable trade setups, and saves the model  ║
║  to models/trade_filter_rf.pkl for the live bot to use.          ║
╚══════════════════════════════════════════════════════════════════╝

Usage (run from trading-system/ folder):

    python scripts/train_ai_model.py

With options:
    python scripts/train_ai_model.py --period 2y --interval 1h --estimators 500
    python scripts/train_ai_model.py --xgboost
    python scripts/train_ai_model.py --csv data/my_data.csv

Steps performed:
    1. Download historical OHLCV (or load CSV)
    2. Compute 18 technical indicators as features
    3. Auto-label each bar: 1=profitable long, -1=profitable short, 0=neutral
    4. Time-series split (no future leakage): 80% train / 20% test
    5. Train RandomForest or XGBoost
    6. Print accuracy, precision, recall, F1 per class
    7. Print top-10 most predictive features
    8. Save model → models/trade_filter_rf.pkl

Install dependencies first:
    pip install yfinance scikit-learn xgboost pandas numpy
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# ── Project root ──────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("train")

# ─────────────────────────────────────────────────────────────────────────
# Default symbols — major NSE indices + liquid large-caps
# These all have ≥ 2 years of 1-hour data available on Yahoo Finance
# ─────────────────────────────────────────────────────────────────────────
DEFAULT_SYMBOLS = [
    "^NSEI",          # NIFTY 50
    "^NSEBANK",       # Bank NIFTY
    "RELIANCE.NS",
    "HDFCBANK.NS",
    "INFY.NS",
    "TCS.NS",
    "ICICIBANK.NS",
    "SBIN.NS",
    "BHARTIARTL.NS",
    "KOTAKBANK.NS",
]


# ═════════════════════════════════════════════════════════════════════════
# 1. Data Download
# ═════════════════════════════════════════════════════════════════════════

def download_symbol(ticker: str, period: str, interval: str) -> pd.DataFrame | None:
    """Download OHLCV for one symbol. Returns None on failure."""
    try:
        import yfinance as yf
        t  = yf.Ticker(ticker)
        df = t.history(period=period, interval=interval, auto_adjust=True)
        if df.empty:
            logger.warning("  ⚠  %s — no data returned", ticker)
            return None
        df.columns = [c.lower() for c in df.columns]
        df = df[["open", "high", "low", "close", "volume"]].dropna()
        # Remove timezone info from index for clean downstream handling
        if hasattr(df.index, "tz") and df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        logger.info("  ✓  %-20s  %5d rows", ticker, len(df))
        return df
    except Exception as exc:
        logger.warning("  ✗  %s — %s", ticker, exc)
        return None


def download_all(symbols: list[str], period: str, interval: str) -> dict[str, pd.DataFrame]:
    """Download all symbols; return {symbol: df} dict for successful ones."""
    try:
        import yfinance  # noqa: F401
    except ImportError:
        logger.error("")
        logger.error("  ❌  yfinance is not installed.")
        logger.error("      Run:  pip install yfinance")
        logger.error("")
        sys.exit(1)

    logger.info("")
    logger.info("── Downloading historical data ─────────────────────────────────")
    logger.info("   Period: %s  |  Interval: %s  |  Symbols: %d", period, interval, len(symbols))
    logger.info("")

    results = {}
    for sym in symbols:
        df = download_symbol(sym, period, interval)
        if df is not None and len(df) >= 100:
            results[sym] = df

    if not results:
        logger.error("No data downloaded. Check internet connection and symbol names.")
        sys.exit(1)

    total_rows = sum(len(v) for v in results.values())
    logger.info("")
    logger.info("   Downloaded %d rows across %d symbols.", total_rows, len(results))
    return results


def load_csv(path: str) -> dict[str, pd.DataFrame]:
    """Load OHLCV from a CSV file (treated as a single symbol 'CSV')."""
    logger.info("Loading CSV: %s", path)
    df = pd.read_csv(path, parse_dates=True, index_col=0)
    df.columns = [c.strip().lower() for c in df.columns]
    required = {"open", "high", "low", "close", "volume"}
    missing  = required - set(df.columns)
    if missing:
        logger.error("CSV is missing columns: %s", missing)
        sys.exit(1)
    df = df[list(required)].dropna()
    logger.info("Loaded %d rows.", len(df))
    return {"CSV": df}


# ═════════════════════════════════════════════════════════════════════════
# 2. Feature Engineering
# ═════════════════════════════════════════════════════════════════════════

def compute_features_for_symbol(df: pd.DataFrame) -> pd.DataFrame:
    """Run the production compute_features() pipeline for one symbol's OHLCV."""
    from shared.ai.features import compute_features
    return compute_features(df)


# ═════════════════════════════════════════════════════════════════════════
# 3. Label Generation  (forward-return based)
# ═════════════════════════════════════════════════════════════════════════

def generate_labels(
    close: pd.Series,
    horizon: int = 5,
    threshold: float = 0.004,
) -> pd.Series:
    """
    Label each bar based on future price movement over ``horizon`` bars.

    horizon   : look-ahead window (bars) — 5 bars ≈ 5 hours for 1h data
    threshold : min return to count as a trade opportunity (0.4%)

    Returns pd.Series with values:
        1  = price rises ≥ threshold  → profitable long
       -1  = price falls ≥ threshold  → profitable short
        0  = sideways / noise         → skip
    """
    fwd_return = close.shift(-horizon) / close - 1
    labels = pd.Series(0, index=close.index, dtype=int)
    labels[fwd_return >  threshold] =  1
    labels[fwd_return < -threshold] = -1
    return labels


# ═════════════════════════════════════════════════════════════════════════
# 4. Build Training Dataset
# ═════════════════════════════════════════════════════════════════════════

def build_dataset(
    symbol_data: dict[str, pd.DataFrame],
    horizon: int = 5,
    threshold: float = 0.004,
) -> tuple[pd.DataFrame, pd.Series]:
    """
    For each symbol: compute features, generate labels, align, and stack.

    Returns (X, y) ready for sklearn.
    """
    logger.info("")
    logger.info("── Feature Engineering & Label Generation ──────────────────────")

    all_X: list[pd.DataFrame] = []
    all_y: list[pd.Series]    = []

    for sym, df in symbol_data.items():
        try:
            # Features
            X_sym = compute_features_for_symbol(df)
            if X_sym.empty:
                logger.warning("  ⚠  %s — empty feature matrix, skipping.", sym)
                continue

            # Labels (on the original df, then align to feature index)
            y_sym = generate_labels(df["close"], horizon=horizon, threshold=threshold)
            y_sym = y_sym.loc[X_sym.index].dropna()
            X_sym = X_sym.loc[y_sym.index]

            # Drop NaN rows
            mask  = X_sym.notna().all(axis=1) & y_sym.notna()
            X_sym = X_sym[mask]
            y_sym = y_sym[mask]

            if len(X_sym) < 50:
                logger.warning("  ⚠  %s — only %d usable rows, skipping.", sym, len(X_sym))
                continue

            class_counts = y_sym.value_counts().to_dict()
            logger.info(
                "  ✓  %-20s  %5d rows  | long=%d  short=%d  neutral=%d",
                sym, len(X_sym),
                class_counts.get(1, 0), class_counts.get(-1, 0), class_counts.get(0, 0),
            )

            all_X.append(X_sym)
            all_y.append(y_sym)

        except Exception as exc:
            logger.warning("  ✗  %s — feature error: %s", sym, exc)

    if not all_X:
        logger.error("No usable data after feature engineering.")
        sys.exit(1)

    X = pd.concat(all_X)
    y = pd.concat(all_y)

    # Replace inf/-inf → NaN, then clip to float32 range (safety net for sklearn)
    X.replace([np.inf, -np.inf], np.nan, inplace=True)
    f32_max = np.finfo(np.float32).max
    X = X.clip(-f32_max, f32_max)

    # Final NaN cleanup
    mask = X.notna().all(axis=1) & y.notna()
    X, y = X[mask], y[mask]

    logger.info("")
    logger.info("  Total training samples : %d", len(X))
    logger.info("  Features               : %d", X.shape[1])

    dist = y.value_counts()
    total = len(y)
    logger.info(
        "  Label distribution     : long=%.1f%%  short=%.1f%%  neutral=%.1f%%",
        dist.get(1, 0) / total * 100,
        dist.get(-1, 0) / total * 100,
        dist.get(0, 0) / total * 100,
    )

    return X, y


# ═════════════════════════════════════════════════════════════════════════
# 5. Train & Evaluate
# ═════════════════════════════════════════════════════════════════════════

def train_model(
    X: pd.DataFrame,
    y: pd.Series,
    n_estimators: int = 300,
    use_xgboost: bool = False,
    confidence_threshold: float = 0.55,
) -> dict:
    """Train the model using a temporal (no-shuffle) train/test split."""
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import (
        accuracy_score, classification_report, confusion_matrix
    )

    logger.info("")
    logger.info("── Training ────────────────────────────────────────────────────")
    algo = "XGBoost" if use_xgboost else "RandomForest"
    logger.info("  Algorithm   : %s", algo)
    logger.info("  Estimators  : %d", n_estimators)
    logger.info("  Threshold   : %.2f confidence", confidence_threshold)
    logger.info("")

    # Temporal split — no shuffling to prevent future leakage
    split = int(len(X) * 0.80)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train, y_test = y.iloc[:split], y.iloc[split:]

    logger.info("  Train rows  : %d", len(X_train))
    logger.info("  Test rows   : %d  (last 20%% of data — chronological)", len(X_test))

    # Build model
    if use_xgboost:
        try:
            from xgboost import XGBClassifier
            from sklearn.preprocessing import LabelEncoder
            le = LabelEncoder()
            y_train_enc = le.fit_transform(y_train)
            y_test_enc  = le.transform(y_test)
            clf = XGBClassifier(
                n_estimators=n_estimators,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                eval_metric="mlogloss",
                verbosity=0,
                n_jobs=-1,
            )
            clf.fit(X_train, y_train_enc,
                    eval_set=[(X_test, y_test_enc)],
                    verbose=False)
            y_pred_enc = clf.predict(X_test)
            y_pred     = le.inverse_transform(y_pred_enc)
            feature_importances = dict(zip(X.columns, clf.feature_importances_))
        except ImportError:
            logger.warning("XGBoost not installed — falling back to RandomForest.")
            logger.warning("Run: pip install xgboost")
            use_xgboost = False

    if not use_xgboost:
        from sklearn.ensemble import RandomForestClassifier
        clf = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=12,
            min_samples_leaf=5,
            max_features="sqrt",
            class_weight="balanced",   # handle class imbalance
            random_state=42,
            n_jobs=-1,
        )
        clf.fit(X_train, y_train)
        y_pred = clf.predict(X_test)
        feature_importances = dict(zip(X.columns, clf.feature_importances_))

    # Metrics
    acc    = accuracy_score(y_test, y_pred)
    report = classification_report(
        y_test, y_pred,
        labels=[-1, 0, 1],
        target_names=["Short", "Neutral", "Long"],
        output_dict=True,
        zero_division=0,
    )
    report_str = classification_report(
        y_test, y_pred,
        labels=[-1, 0, 1],
        target_names=["Short", "Neutral", "Long"],
        zero_division=0,
    )

    return {
        "classifier":           clf,
        "feature_names":        list(X.columns),
        "accuracy":             acc,
        "report":               report,
        "report_str":           report_str,
        "feature_importances":  feature_importances,
        "train_size":           len(X_train),
        "test_size":            len(X_test),
        "use_xgboost":          use_xgboost,
        "confidence_threshold": confidence_threshold,
    }


# ═════════════════════════════════════════════════════════════════════════
# 6. Save via TradeFilterModel wrapper
# ═════════════════════════════════════════════════════════════════════════

def save_model(result: dict) -> None:
    """Wrap the trained classifier in TradeFilterModel and save to disk."""
    from shared.ai.model import TradeFilterModel, _MODEL_DIR, _MODEL_PATH
    import pickle

    _MODEL_DIR.mkdir(parents=True, exist_ok=True)

    model_obj           = TradeFilterModel(min_confidence=result["confidence_threshold"])
    model_obj.model     = result["classifier"]
    model_obj.feature_names = result["feature_names"]

    with open(_MODEL_PATH, "wb") as f:
        pickle.dump({
            "model":            model_obj.model,
            "feature_names":    model_obj.feature_names,
        }, f)

    logger.info("  ✅  Model saved → %s", _MODEL_PATH)


# ═════════════════════════════════════════════════════════════════════════
# 7. Print Report
# ═════════════════════════════════════════════════════════════════════════

def print_report(result: dict) -> None:
    acc = result["accuracy"] * 100
    logger.info("")
    logger.info("── Results ─────────────────────────────────────────────────────")
    logger.info("  Test Accuracy : %.2f%%", acc)

    if acc < 50:
        verdict = "⚠️  Below random — check data quality or increase history."
    elif acc < 55:
        verdict = "🟡  Marginally above random — functional but weak signal."
    elif acc < 62:
        verdict = "🟢  Good — the model provides useful signal filtering."
    else:
        verdict = "🌟  Excellent — strong predictive signal."

    logger.info("  Verdict       : %s", verdict)
    logger.info("")
    logger.info("  Per-class Breakdown:")
    logger.info("%s", result["report_str"])

    # Feature importance
    logger.info("── Top 10 Most Predictive Features ────────────────────────────")
    sorted_fi = sorted(result["feature_importances"].items(), key=lambda x: x[1], reverse=True)
    for i, (feat, score) in enumerate(sorted_fi[:10], start=1):
        bar   = "█" * int(score * 60)
        arrow = "  ← most important" if i == 1 else ""
        logger.info("  %2d. %-22s %s  %.4f%s", i, feat, bar, score, arrow)

    logger.info("")
    logger.info("═" * 66)
    logger.info("  ✅  Training complete.")
    logger.info("  📁  Model saved to:  models/trade_filter_rf.pkl")
    logger.info("  🤖  The live bot loads it automatically on next start.")
    logger.info("  📅  Re-run weekly to retrain on fresh market data.")
    logger.info("═" * 66)


# ═════════════════════════════════════════════════════════════════════════
# 8. CLI
# ═════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Train the AI trade-filter model on 2 years of NSE data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--symbols",    default=",".join(DEFAULT_SYMBOLS),
                   help="Comma-separated yfinance tickers")
    p.add_argument("--period",     default="2y",
                   help="History period: 1y, 2y, max")
    p.add_argument("--interval",   default="1h",
                   choices=["1h", "1d", "30m", "15m"],
                   help="Candle interval (yfinance: 1h max 730 days)")
    p.add_argument("--csv",        default="",
                   help="Load OHLCV from CSV instead of downloading")
    p.add_argument("--xgboost",    action="store_true",
                   help="Use XGBoost (pip install xgboost)")
    p.add_argument("--estimators", type=int, default=300,
                   help="Number of trees")
    p.add_argument("--threshold",  type=float, default=0.55,
                   help="AI confidence gate (0–1)")
    p.add_argument("--horizon",    type=int, default=5,
                   help="Forward-return window for labels (bars)")
    p.add_argument("--label-threshold", type=float, default=0.004,
                   help="Min return to count as a trade (0.004 = 0.4%%)")
    return p.parse_args()


# ═════════════════════════════════════════════════════════════════════════
# Entry point
# ═════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info("")
    logger.info("╔══════════════════════════════════════════════════════════════╗")
    logger.info("║       AI Trade-Filter Model — Training Pipeline              ║")
    logger.info("╚══════════════════════════════════════════════════════════════╝")

    args = parse_args()

    # 1. Load data
    if args.csv:
        symbol_data = load_csv(args.csv)
    else:
        syms        = [s.strip() for s in args.symbols.split(",") if s.strip()]
        symbol_data = download_all(syms, period=args.period, interval=args.interval)

    # 2. Build dataset
    X, y = build_dataset(
        symbol_data,
        horizon=args.horizon,
        threshold=args.label_threshold,
    )

    # 3. Train
    result = train_model(
        X, y,
        n_estimators=args.estimators,
        use_xgboost=args.xgboost,
        confidence_threshold=args.threshold,
    )

    # 4. Save
    save_model(result)

    # 5. Report
    print_report(result)
