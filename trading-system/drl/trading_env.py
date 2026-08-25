import numpy as np
import pandas as pd
import gymnasium as gym
from gymnasium import spaces

class QuantAITradingEnv(gym.Env):
    """
    Custom Trading Environment for QuantAI DRL Agent.
    Supports continuous state (features like RSI, ATR, MACD, Volume Delta)
    and discrete actions:
      0: Hold / Do Nothing
      1: Buy Call / Long Equity
      2: Buy Put / Short Equity
      3: Close Position
    """
    metadata = {"render_modes": ["human"]}

    def __init__(self, df: pd.DataFrame, initial_balance=100000.0, mode="options",
                 commission_per_trade: float = 20.0, slippage_bps: float = 2.0,
                 options_delta: float = 0.5):
        super(QuantAITradingEnv, self).__init__()

        self.df = df
        self.mode = mode
        self.initial_balance = initial_balance

        # Root-cause fix (High audit finding): this environment previously
        # computed reward/PnL as a frictionless 1:1 move on `balance` with
        # zero commission or slippage, and `mode="options"` was accepted but
        # never actually changed the arithmetic anywhere in the class. That
        # let the agent train against economics nothing like what it is
        # actually scored/traded on: run_intraday_backtest() (the engine
        # used for both backtesting and DRL signal evaluation) already
        # charges slippage_bps + commission_per_trade per fill and scales
        # underlying price moves by options_delta when trading options
        # premiums rather than the underlying 1:1. Same defaults reused here
        # so a policy that looks profitable in training isn't just exploiting
        # a frictionless, wrong-instrument simulation.
        self.commission_per_trade = commission_per_trade
        self.slippage_bps = slippage_bps
        self.options_delta = options_delta if mode == "options" else 1.0

        # Determine number of features from dataframe
        # Features should be pre-calculated indicators (e.g. ['rsi', 'macd_hist', 'atr', 'vol_change'])
        known_drl_cols = [c for c in ['rsi', 'macd_hist', 'atr', 'vol_change'] if c in df.columns]
        if len(known_drl_cols) == 4:
            self.feature_cols = known_drl_cols
        else:
            excluded = {'timestamp', 'time', 'date', 'datetime', 'symbol', 'close', 'open', 'high', 'low', 'volume'}
            self.feature_cols = [
                c for c in df.columns
                if c.lower() not in excluded and np.issubdtype(df[c].dtype, np.number)
            ]
        
        # Action Space: 0 (Hold), 1 (Buy Call), 2 (Buy Put), 3 (Close)
        self.action_space = spaces.Discrete(4)
        
        # Observation space: features + current_profit_pct + current_position_type (0, 1, 2)
        obs_shape = len(self.feature_cols) + 2
        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(obs_shape,), dtype=np.float32)
        
        self.current_step = 0
        self.balance = self.initial_balance
        self.position = 0 # 0: None, 1: Call/Long, 2: Put/Short
        self.entry_price = 0.0
        
        # Track for rendering/analysis
        self.history = []

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.current_step = 0
        self.balance = self.initial_balance
        self.position = 0
        self.entry_price = 0.0
        self.history = []
        return self._get_obs(), {}

    def _apply_slippage(self, price: float, side: str) -> float:
        """Worse-fill adjustment matching backtesting_engine/run.py's
        apply_slippage: BUY fills pay slightly more, SELL fills receive
        slightly less."""
        slip_amt = price * (self.slippage_bps / 10000)
        return price + slip_amt if side == "BUY" else price - slip_amt

    def _position_profit_pct(self, current_price: float) -> float:
        """Delta-scaled unrealized profit % for the open position. In
        options mode, a move in the underlying only translates to a
        fraction (options_delta) of that move in the premium — unlike a 1:1
        equity position, which is why this is not simply
        (current - entry) / entry."""
        if self.position == 1:
            return (current_price - self.entry_price) / self.entry_price * self.options_delta
        elif self.position == 2:
            return (self.entry_price - current_price) / self.entry_price * self.options_delta
        return 0.0

    def _get_obs(self):
        # Current row features
        row = self.df.iloc[self.current_step]
        features = row[self.feature_cols].values.astype(np.float32)

        # Calculate current profit percentage
        current_price = row['close']
        profit_pct = self._position_profit_pct(current_price)

        # Append position and profit to features
        obs = np.append(features, [self.position, profit_pct])
        return obs.astype(np.float32)

    @property
    def initial_capital(self) -> float:
        return self.initial_balance

    @property
    def current_capital(self) -> float:
        return self.balance

    def step(self, action):
        current_price = self.df.iloc[self.current_step]['close']
        reward = 0.0
        trade_pnl = 0.0
        done = False

        # Execute Action
        if action == 1 and self.position == 0:
            # Buy Call / Long
            self.position = 1
            self.entry_price = self._apply_slippage(current_price, "BUY")
            self.balance -= self.commission_per_trade

        elif action == 2 and self.position == 0:
            # Buy Put / Short
            self.position = 2
            self.entry_price = self._apply_slippage(current_price, "SELL")
            self.balance -= self.commission_per_trade

        elif action == 3 and self.position != 0:
            # Close position
            exit_price = self._apply_slippage(current_price, "SELL" if self.position == 1 else "BUY")
            profit_pct = self._position_profit_pct(exit_price)

            # Apply profit to balance (assuming full leverage/allocation for simplification in training)
            profit_value = self.balance * profit_pct
            self.balance += profit_value
            self.balance -= self.commission_per_trade
            trade_pnl = profit_value - self.commission_per_trade
            
            # Scalping Reward: heavily reward quick small profits (0.5% to 1%), penalize losses
            if profit_pct > 0:
                reward = profit_pct * 500.0 # High reward for any profit
            else:
                reward = profit_pct * 1000.0 # Heavy penalty for losses
            
            # SORTINO SHAPING: Penalize losses much harder than we reward gains 
            # to force the AI to find high-probability setups and avoid drawdown
            if profit_pct < 0:
                reward *= 2.5  # 2.5x penalty on losses
                
            self.position = 0
            self.entry_price = 0.0
            
        else:
            # Hold (Action 0) or Invalid Action (Action 1/2 when already in position)
            if self.position != 0:
                profit_pct = self._position_profit_pct(current_price)
                reward = profit_pct * 5.0 # Small unrealized reward
            else:
                reward = -0.05 # Slightly higher penalty for staying flat too long to encourage finding trades
        
        # Check termination
        self.current_step += 1
        if self.current_step >= len(self.df) - 1:
            done = True
            
        # Bankrupt check
        if self.balance <= 0:
            done = True
            reward = -1000.0 # Severe penalty for blowing up
            
        info = {
            'balance': self.balance,
            'position': self.position,
            'trade_pnl': trade_pnl,
        }
        
        # In gymnasium, return is (obs, reward, terminated, truncated, info)
        return self._get_obs(), reward, done, False, info

    def render(self):
        print(f"Step: {self.current_step}, Balance: {self.balance:.2f}, Pos: {self.position}")


# Alias for backward and forward compatibility across training scripts
TradingEnv = QuantAITradingEnv
__all__ = ["QuantAITradingEnv", "TradingEnv"]
