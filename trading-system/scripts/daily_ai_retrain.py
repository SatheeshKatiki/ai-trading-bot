"""Automated AI Retraining Script.

Fetches the latest historical data, computes features, retrains the
TradeFilterModel (RandomForest), and saves it to disk. The live bot
will detect the file change and hot-reload it automatically.
"""

import sys
import os
import logging
import asyncio
from datetime import datetime, timedelta

# Add parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from brokers import BrokerFactory
from shared.ai import TradeFilterModel, compute_features
from shared.alerts import alerter
from shared.config import CONFIG

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

async def retrain_ai():
    try:
        broker = BrokerFactory.get_active_broker()
        if not broker.authenticate():
            logger.error("Broker authentication failed. Cannot fetch data.")
            return

        # Fetch 30 days of data for NIFTY
        symbol = "NSE:NIFTY50-INDEX"
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        logger.info(f"Fetching historical data for {symbol} from {start_date.date()} to {end_date.date()}...")
        
        # We need historical data. Fyers historical data API takes epoch or YYYY-MM-DD string
        # using the broker's get_historical_data
        
        import pandas as pd
        raw_data = broker.get_historical_data(
            symbol=symbol,
            timeframe="5 Min",
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d")
        )
        
        df_raw = pd.DataFrame(raw_data)

        if df_raw.empty or len(df_raw) < 500:
            logger.error(f"Not enough historical data fetched for {symbol}. Rows: {len(df_raw)}")
            return

        # Ensure correct column names
        if 'time' in df_raw.columns:
            df_raw.rename(columns={'time': 'timestamp'}, inplace=True)

        logger.info(f"Fetched {len(df_raw)} rows of historical data.")

        # Compute Technical Features
        logger.info("Computing ML features...")
        df_features = compute_features(df_raw)

        # Initialize and Train Model
        logger.info("Training AI Model (RandomForest)...")
        model = TradeFilterModel()
        
        # Train generates labels automatically using close prices and forward returns!
        metrics = model.train(features=df_features, ohlcv_df=df_raw, test_size=0.15)
        
        accuracy = metrics['accuracy'] * 100
        logger.info(f"Retraining successful! New Validation Accuracy: {accuracy:.2f}%")
        
        # Send Telegram alert
        message = (
            f"🧠 **AI Model Retrained Successfully**\n\n"
            f"Symbol: `{symbol}`\n"
            f"Data Points: `{len(df_raw)} bars (30 Days)`\n"
            f"Validation Accuracy: `{accuracy:.2f}%`\n"
            f"Status: `Hot-reloaded into Live Engine`"
        )
        alerter.send_telegram_alert(message)
        
    except Exception as e:
        logger.exception("Error during AI retraining:")
        alerter.send_telegram_alert(f"⚠️ **AI Retraining Failed**\n\nError: `{str(e)}`")

if __name__ == "__main__":
    logger.info("Starting Daily AI Retraining Job...")
    asyncio.run(retrain_ai())
