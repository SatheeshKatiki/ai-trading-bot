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

    def __init__(self, df: pd.DataFrame, initial_balance=100000.0, mode="options"):
        super(QuantAITradingEnv, self).__init__()
        
        self.df = df
        self.mode = mode
        self.initial_balance = initial_balance
        
        # Determine number of features from dataframe
        # Features should be pre-calculated indicators (e.g. ['rsi', 'macd', 'atr', 'vol_delta', ...])
        self.feature_cols = [c for c in df.columns if c not in ['timestamp', 'close', 'open', 'high', 'low', 'volume']]
        
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

    def _get_obs(self):
        # Current row features
        row = self.df.iloc[self.current_step]
        features = row[self.feature_cols].values.astype(np.float32)
        
        # Calculate current profit percentage
        current_price = row['close']
        profit_pct = 0.0
        if self.position == 1:
            profit_pct = (current_price - self.entry_price) / self.entry_price
        elif self.position == 2:
            profit_pct = (self.entry_price - current_price) / self.entry_price
            
        # Append position and profit to features
        obs = np.append(features, [self.position, profit_pct])
        return obs.astype(np.float32)

    def step(self, action):
        current_price = self.df.iloc[self.current_step]['close']
        reward = 0.0
        done = False
        
        # Execute Action
        if action == 1 and self.position == 0:
            # Buy Call / Long
            self.position = 1
            self.entry_price = current_price
            
        elif action == 2 and self.position == 0:
            # Buy Put / Short
            self.position = 2
            self.entry_price = current_price
            
        elif action == 3 and self.position != 0:
            # Close position
            profit_pct = 0.0
            if self.position == 1:
                profit_pct = (current_price - self.entry_price) / self.entry_price
            elif self.position == 2:
                profit_pct = (self.entry_price - current_price) / self.entry_price
            
            # Apply profit to balance (assuming full leverage/allocation for simplification in training)
            profit_value = self.balance * profit_pct
            self.balance += profit_value
            
            # Reward is heavily based on closed profit
            reward = profit_pct * 100.0
            
            self.position = 0
            self.entry_price = 0.0
            
        else:
            # Hold (Action 0) or Invalid Action (Action 1/2 when already in position)
            # Give a small step penalty to discourage doing nothing forever, 
            # OR a small reward if currently holding a profitable position.
            if self.position == 1:
                profit_pct = (current_price - self.entry_price) / self.entry_price
                reward = profit_pct * 10.0 # Small unrealized reward
            elif self.position == 2:
                profit_pct = (self.entry_price - current_price) / self.entry_price
                reward = profit_pct * 10.0
            else:
                reward = -0.01 # Small penalty for staying flat too long
        
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
            'position': self.position
        }
        
        # In gymnasium, return is (obs, reward, terminated, truncated, info)
        return self._get_obs(), reward, done, False, info

    def render(self):
        print(f"Step: {self.current_step}, Balance: {self.balance:.2f}, Pos: {self.position}")
