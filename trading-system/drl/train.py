import os
import pandas as pd
import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv

from trading_env import QuantAITradingEnv

def generate_mock_data(rows=10000):
    """
    Generates mock trading data with basic indicators for testing the training pipeline.
    In production, this should be replaced by loading a real CSV of historical data.
    """
    dates = pd.date_range(start="2023-01-01", periods=rows, freq="1min")
    
    # Simulate a random walk for price
    returns = np.random.normal(loc=0.0001, scale=0.01, size=rows)
    price = 100 * np.exp(np.cumsum(returns))
    
    df = pd.DataFrame({
        'timestamp': dates,
        'close': price,
        'open': price * (1 + np.random.normal(0, 0.002, rows)),
        'high': price * (1 + abs(np.random.normal(0, 0.005, rows))),
        'low': price * (1 - abs(np.random.normal(0, 0.005, rows))),
        'volume': np.random.randint(100, 10000, rows)
    })
    
    # Mock Indicators (Features)
    df['rsi'] = np.random.uniform(20, 80, rows)
    df['macd'] = np.random.normal(0, 1, rows)
    df['atr'] = np.random.uniform(0.5, 2.5, rows)
    df['vol_delta'] = np.random.normal(0, 1000, rows)
    
    return df

def train_agent():
    print("Loading historical data...")
    # df = generate_mock_data(rows=20000)
    df = pd.read_csv("nifty_historical_data.csv")
    
    print("Initializing environment...")
    # Wrap in DummyVecEnv as required by Stable Baselines
    env = DummyVecEnv([lambda: QuantAITradingEnv(df=df, mode="options")])
    
    print("Creating PPO Agent...")
    model = PPO("MlpPolicy", env, verbose=1, tensorboard_log="./ppo_trading_tensorboard/")
    
    print("Training started...")
    # Train for 200,000 steps since the dataset is much larger (20 years)
    model.learn(total_timesteps=200000)
    
    print("Training complete. Saving model...")
    model.save("best_model")
    print("Model saved to best_model.zip")

if __name__ == "__main__":
    train_agent()
