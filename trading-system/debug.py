from brokers.broker_factory import BrokerFactory
import json

broker = BrokerFactory.get_active_broker()
print("Broker token:", broker._load_cached_token())
print("Broker client_id:", broker.credentials.get("client_id"))

try:
    data = broker.get_historical_data('NSE:NIFTY50-INDEX', '2024-05-01', '2024-05-10', '5 Min')
    print("Fetched:", len(data))
except Exception as e:
    print("Error:", e)
