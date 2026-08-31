import urllib.request
import json

urls = [
  ('EMA9 RSI Momentum (touch=True)', 'http://127.0.0.1:8000/api/backtest?symbol=NSE:NIFTY50-INDEX&timeframe=5+Min&strategy=ema9_rsi_momentum&start_date=2024-01-01&end_date=2026-08-31&initial_capital=100000&quantity=65&stoploss_pct=1.2&target_pct=2.5&enable_touch_filter=true'),
  ('EMA9 RSI Momentum (touch=False)', 'http://127.0.0.1:8000/api/backtest?symbol=NSE:NIFTY50-INDEX&timeframe=5+Min&strategy=ema9_rsi_momentum&start_date=2024-01-01&end_date=2026-08-31&initial_capital=100000&quantity=65&stoploss_pct=1.2&target_pct=2.5&enable_touch_filter=false'),
  ('Smart Trend Institutional', 'http://127.0.0.1:8000/api/backtest?symbol=NSE:NIFTY50-INDEX&timeframe=5+Min&strategy=smart_trend&start_date=2024-01-01&end_date=2026-08-31&initial_capital=100000&quantity=65&stoploss_pct=1.2&target_pct=2.5'),
  ('QuantAI Momentum', 'http://127.0.0.1:8000/api/backtest?symbol=NSE:NIFTY50-INDEX&timeframe=5+Min&strategy=quantai_momentum&start_date=2024-01-01&end_date=2026-08-31&initial_capital=100000&quantity=65&stoploss_pct=1.2&target_pct=2.5'),
  ('Option Scalping Pro', 'http://127.0.0.1:8000/api/backtest?symbol=NSE:NIFTY50-INDEX&timeframe=5+Min&strategy=option_scalping&start_date=2024-01-01&end_date=2026-08-31&initial_capital=100000&quantity=65&stoploss_pct=1.2&target_pct=2.5'),
]

for label, url in urls:
    try:
        req = urllib.request.urlopen(url)
        res = json.loads(req.read().decode('utf-8'))
        pnl = res.get('total_pnl', res.get('metrics', {}).get('net_pnl', 0))
        trades = res.get('total_trades', res.get('metrics', {}).get('total_trades', 0))
        win_rate = res.get('win_rate', res.get('metrics', {}).get('win_rate_pct', 0))
        print(f"{label:<32} -> Net PnL: Rs. {pnl:>12,.2f} | Trades: {trades:>5} | Win Rate: {win_rate:>6}%")
    except Exception as e:
        print(f"{label:<32} -> Error: {e}")
