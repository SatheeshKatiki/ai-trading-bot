from fastapi import FastAPI
import uvicorn
from brokers.broker_factory import BrokerFactory

app = FastAPI()
broker = BrokerFactory.get_active_broker()

@app.get("/test")
async def test():
    try:
        data = broker.get_historical_data('NSE:NIFTY50-INDEX', '2024-05-01', '2024-05-10', '5 Min')
        return {"count": len(data)}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)
