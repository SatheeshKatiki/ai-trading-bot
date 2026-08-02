import logging
import pandas as pd
import numpy as np

from drl.marl.master_agent import MasterAgent

logger = logging.getLogger(__name__)

class MARLStrategy:
    """
    Multi-Agent Reinforcement Learning (MARL) system — Ultra-Professional Edition.
    
    Signal generation philosophy (post-audit v2):
    - Trust the LSTM AI signal as the primary source
    - Apply LIGHTWEIGHT, NON-LAGGING pre-filters only
    - KEY LESSON: ADX and consecutive signal confirmation cause LATE entries
    - NEW: RSI gate + Signal balance check to fix 1 Min SHORT bias
    """
    
    def __init__(self):
        self.name = "MARL_Ultra"
        import os
        model_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "best_model.zip"
        )
        self.master_agent = MasterAgent(model_path)
        self.current_position = 0
        self.entry_price = 0.0

    def compute_features(self, df: pd.DataFrame) -> np.ndarray:
        """Compute normalized core features for the LSTM model."""
        if len(df) < 20:
            return np.zeros(6, dtype=np.float32)

        df_c = df.copy()
        df_c['return'] = df_c['close'].pct_change()
        
        delta = df_c['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        raw_rsi = 100 - (100 / (1 + gain / (loss + 1e-9)))
        df_c['rsi'] = (raw_rsi - 50.0) / 25.0  # Center around 0 [-2, +2]
        
        exp1 = df_c['close'].ewm(span=12, adjust=False).mean()
        exp2 = df_c['close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        macd_hist = macd - macd.ewm(span=9, adjust=False).mean()
        df_c['macd_hist'] = macd_hist / (df_c['close'] * 0.001 + 1e-6)
        
        high_low = df_c['high'] - df_c['low']
        high_close = np.abs(df_c['high'] - df_c['close'].shift())
        low_close = np.abs(df_c['low'] - df_c['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        atr_raw = true_range.rolling(14).mean()
        df_c['atr'] = (atr_raw / df_c['close']) * 100.0  # ATR as % of close
        
        df_c['vol_change'] = np.clip(df_c['volume'].pct_change(), -2.0, 2.0)
        df_c['close_chg'] = df_c['return']

        latest = df_c.iloc[-1]
        features = np.array([
            latest['return'],
            latest['rsi'],
            latest['macd_hist'],
            latest['atr'],
            latest['vol_change'],
            latest['close_chg']
        ], dtype=np.float32)
        
        features = np.nan_to_num(features, posinf=0.0, neginf=0.0)
        return features

    def on_tick(self, df: pd.DataFrame, precomputed_features: np.ndarray = None) -> int:
        if df.empty or len(df) < 20:
            return 0

        current_price = df['close'].iloc[-1]
        profit_pct = 0.0
        
        if precomputed_features is not None:
            features = precomputed_features
        else:
            features = self.compute_features(df)
        
        decision = self.master_agent.analyze_market(
            df=df,
            obs=features,
            current_spot=current_price,
            current_pnl_pct=profit_pct,
            is_high_iv=False
        )
        
        action = decision["action"]
        
        if action == "LONG":
            return 1
        elif action == "SHORT":
            return -1
        return 0


_marl_instance = None


def _get_marl_instance() -> "MARLStrategy":
    global _marl_instance
    if _marl_instance is None:
        _marl_instance = MARLStrategy()
    return _marl_instance


def record_trade_outcome(pnl: float) -> None:
    """Feed a closed MARL_Ultra trade's PNL into the shared RiskAgent's
    Capital Protection Mode consecutive-loss tracker.

    Root-cause fix: RiskAgent.record_trade_result() previously had zero
    call sites anywhere in the codebase, so the documented "half-size
    after 2 losses / stop after 3 losses" brake never engaged. The
    live trading loop (trading_bot/main.py) calls this on every
    position close.
    """
    risk_agent = _get_marl_instance().master_agent.risk_agent
    risk_agent.record_trade_result(pnl)


def is_capital_protection_blocking_entries() -> bool:
    """True once MARL_Ultra has hit 3+ consecutive losing trades and new
    entries should be blocked, per RiskAgent's documented stop rule."""
    risk_agent = _get_marl_instance().master_agent.risk_agent
    return risk_agent.get_position_size_multiplier() == 0.0


def generate_signals(df: pd.DataFrame, **kwargs) -> pd.Series:
    """
    Ultra-Professional MARL signal generator — Post-Audit v3.
    """
    global _marl_instance
    if _marl_instance is None:
        _marl_instance = MARLStrategy()
    
    # Detect timeframe from kwargs or df timestamps
    timeframe = kwargs.get("timeframe", None)
    if timeframe is None:
        try:
            dts = pd.to_datetime(df['datetime']) if 'datetime' in df.columns else df.index
            diff_seconds = (dts[1] - dts[0]).total_seconds()
            timeframe = "1 Min" if diff_seconds <= 60 else "5 Min"
        except Exception:
            timeframe = "5 Min"
            
    is_1min = "1" in str(timeframe) and "min" in str(timeframe).lower()
    
    # ── Timeframe-aware parameters ────────────────────────────────────────────
    EMA_COUNTER_TREND_BLOCK_PCT = 0.12 if is_1min else 0.3
    SIGNAL_BALANCE_LOOKBACK    = 30    # Rolling window for balance check
    SIGNAL_BALANCE_THRESHOLD   = 0.75  # Block direction if >75% signals same way
    RSI_SHORT_MIN              = 35.0  # Don't short if RSI already below 35 (oversold)
    RSI_LONG_MAX               = 65.0  # Don't buy if RSI already above 65 (overbought)
    
    # ── Step 1: Vectorized Feature Computation with Standardized Scaling ───────
    df_c = df.copy()
    df_c['return'] = df_c['close'].pct_change()
    delta = df_c['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    raw_rsi = 100 - (100 / (1 + gain / (loss + 1e-9)))
    df_c['rsi'] = (raw_rsi - 50.0) / 25.0  # Center around 0 [-2, +2]
    
    exp1 = df_c['close'].ewm(span=12, adjust=False).mean()
    exp2 = df_c['close'].ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    macd_hist = macd - macd.ewm(span=9, adjust=False).mean()
    df_c['macd_hist'] = macd_hist / (df_c['close'] * 0.001 + 1e-6)
    
    ranges = pd.concat([df_c['high'] - df_c['low'],
                        (df_c['high'] - df_c['close'].shift()).abs(),
                        (df_c['low'] - df_c['close'].shift()).abs()], axis=1)
    atr = ranges.max(axis=1).rolling(14).mean()
    df_c['atr'] = (atr / df_c['close']) * 100.0
    df_c['vol_change'] = np.clip(df_c['volume'].pct_change(), -2.0, 2.0)
    df_c['close_chg'] = df_c['return']

    # ── Step 2: Pre-compute Filter Arrays ────────────────────────────────────
    rolling_mean = df_c['close'].rolling(window=20).mean()
    rolling_std  = df_c['close'].rolling(window=20).std()
    bb_width_pct = (((rolling_mean + (2 * rolling_std)) - (rolling_mean - (2 * rolling_std))) / rolling_mean) * 100
    vol_ma = df_c['volume'].rolling(window=20).mean().shift(1)
    
    ema9 = df_c['close'].ewm(span=9, adjust=False).mean()
    
    n = len(df_c)
    session_blocked = np.zeros(n, dtype=bool)
    if 'datetime' in df_c.columns:
        try:
            dts = pd.to_datetime(df_c['datetime'])
            time_minutes = dts.dt.hour * 60 + dts.dt.minute
            session_blocked = (time_minutes >= 15 * 60).to_numpy()
        except Exception:
            pass
    elif hasattr(df_c.index, 'hour'):
        try:
            time_minutes = df_c.index.hour * 60 + df_c.index.minute
            session_blocked = (time_minutes >= 15 * 60)
        except Exception:
            pass

    bb_width_arr = bb_width_pct.to_numpy()
    vol_ma_arr   = vol_ma.to_numpy()
    vol_arr      = df_c['volume'].to_numpy()
    ema9_arr     = ema9.to_numpy()
    close_arr    = df_c['close'].to_numpy()
    rsi_arr      = raw_rsi.to_numpy()

    features_array = df_c[['return', 'rsi', 'macd_hist', 'atr', 'vol_change', 'close_chg']].to_numpy()
    features_array = np.nan_to_num(features_array, posinf=0.0, neginf=0.0).astype(np.float32)
    
    # AUDIT FIX 1.5: Feature Scaling Alignment for 1-Min Timeframe
    # The LSTM was trained on 5-min data. On 1-min, returns/MACD/ATR are much smaller (by sqrt(5)).
    # This causes the model to perceive a flat/negative chop regime, leading to 99% SHORT signals.
    # By scaling the 1-min features up by ~2.23 (sqrt(5)), we align the distributions!
    if is_1min:
        # Scale all features except RSI (which is index 1 and bounded 0-100)
        scale_factor = 2.236
        features_array[:, 0] *= scale_factor  # return
        features_array[:, 2] *= scale_factor  # macd_hist
        features_array[:, 3] *= scale_factor  # atr
        features_array[:, 4] *= scale_factor  # vol_change
        features_array[:, 5] *= scale_factor  # close_chg
    
    # ── Step 3: PyTorch LSTM Inference ───────────────────────────────────────
    import torch
    
    model  = _marl_instance.master_agent.signal_agent.model
    policy = model.policy
    device = policy.device
    
    # Initialize LSTM state properly
    dummy_obs    = features_array[0:1]
    dummy_starts = np.ones((1,), dtype=bool)
    _, lstm_states_np = model.predict(dummy_obs, state=None, episode_start=dummy_starts, deterministic=True)
    
    lstm_states = (
        torch.tensor(lstm_states_np[0], dtype=torch.float32, device=device),
        torch.tensor(lstm_states_np[1], dtype=torch.float32, device=device)
    )
    
    episode_starts  = torch.tensor([False], dtype=torch.float32, device=device)
    features_tensor = torch.tensor(features_array, dtype=torch.float32, device=device)
    signals_arr     = np.zeros(n, dtype=int)

    # Capital Protection Mode: block new entries once RiskAgent has recorded
    # 3+ consecutive live-trade losses (see record_trade_outcome(), called
    # from trading_bot/main.py on every position close). This is checked
    # once per call rather than per-bar since it can't change mid-call, and
    # is a live-trading-only signal — a fresh backtest process/run always
    # starts with a clean RiskAgent (0 consecutive losses) since backtesting
    # doesn't feed trade outcomes back into it, so this never fires there.
    capital_protection_blocked = is_capital_protection_blocking_entries()
    if capital_protection_blocked:
        logger.warning(
            "MARL_Ultra: Capital Protection Mode active (3+ consecutive "
            "losses) — new entry signals are blocked this call."
        )
    
    # Signal balance tracker — rolling window of raw (pre-filter) LSTM outputs
    # Used to detect and correct 1-directional bias
    recent_raw_signals = []  # tracks last SIGNAL_BALANCE_LOOKBACK raw signals
    
    with torch.no_grad():
        for i in range(20, n):
            # ── Filter 1: Session Block (after 15:00) ──────────────────────
            if session_blocked[i]:
                episode_starts = torch.tensor([False], dtype=torch.float32, device=device)
                continue
            
            # ── Filter 2: Extreme Sideways (BB Width) ──────────────────────
            if bb_width_arr[i] < 0.08 and vol_arr[i] < (vol_ma_arr[i] * 2):
                episode_starts = torch.tensor([False], dtype=torch.float32, device=device)
                continue
            
            # ── LSTM Inference (primary signal) ────────────────────────────
            obs = features_tensor[i:i+1]
            action_tensor, lstm_states = policy._predict(
                obs, lstm_states, episode_starts, deterministic=True
            )
            episode_starts = torch.tensor([False], dtype=torch.float32, device=device)
            
            act_val = action_tensor.item()
            if act_val not in (1, 2):
                continue
            
            # Track raw signal for balance check
            recent_raw_signals.append(act_val)
            if len(recent_raw_signals) > SIGNAL_BALANCE_LOOKBACK:
                recent_raw_signals.pop(0)
            
            # ── Filter 3: Signal Balance Check (fixes 1 Min bias) ──────────
            # Professional: If the model keeps predicting >75% in one direction,
            # we need RSI confirmation to filter low-quality entries in that direction
            if len(recent_raw_signals) >= SIGNAL_BALANCE_LOOKBACK:
                long_ratio  = recent_raw_signals.count(1) / len(recent_raw_signals)
                short_ratio = recent_raw_signals.count(2) / len(recent_raw_signals)
                
                # If heavily biased SHORT (e.g. 1 Min model), require RSI to not be oversold
                if act_val == 2 and short_ratio > SIGNAL_BALANCE_THRESHOLD:
                    rsi_val = rsi_arr[i]
                    if not np.isnan(rsi_val) and rsi_val < RSI_SHORT_MIN:
                        continue  # RSI already oversold, skip this SHORT signal
                
                # If heavily biased LONG, require RSI to not be overbought
                if act_val == 1 and long_ratio > SIGNAL_BALANCE_THRESHOLD:
                    rsi_val = rsi_arr[i]
                    if not np.isnan(rsi_val) and rsi_val > RSI_LONG_MAX:
                        continue  # RSI already overbought, skip this LONG signal
            
            # ── Filter 4: RSI Extreme Gate (absolute extreme protection) ───
            rsi_val = rsi_arr[i]
            if not np.isnan(rsi_val):
                if act_val == 2 and rsi_val < 25.0:
                    continue  # RSI < 25 = extremely oversold, DO NOT short
                if act_val == 1 and rsi_val > 75.0:
                    continue  # RSI > 75 = extremely overbought, DO NOT buy
            
            # ── Filter 5: EMA-9 Counter-Trend Gate (timeframe-aware) ───────
            current_close = close_arr[i]
            ema9_val      = ema9_arr[i]
            
            if act_val == 1 and ema9_val > 0:
                pct_below_ema = (ema9_val - current_close) / ema9_val * 100
                if pct_below_ema > EMA_COUNTER_TREND_BLOCK_PCT:
                    continue  # Price deeply below EMA — counter-trend BUY, skip
                    
            if act_val == 2 and ema9_val > 0:
                pct_above_ema = (current_close - ema9_val) / ema9_val * 100
                if pct_above_ema > EMA_COUNTER_TREND_BLOCK_PCT:
                    continue  # Price deeply above EMA — counter-trend SELL, skip
            
            # ── Filter 6: Capital Protection Mode ──────────────────────────
            if capital_protection_blocked:
                continue

            if act_val == 1:
                signals_arr[i] = 1
            elif act_val == 2:
                signals_arr[i] = -1
    
    return pd.Series(signals_arr, index=df.index, dtype=int)
