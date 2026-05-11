import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const rawSymbol = searchParams.get('symbol') || 'NIFTY';
    const timeframe = searchParams.get('timeframe') || '15 Min';
    const isLive = searchParams.get('live') === 'true';
    
    // Map short symbols to Fyers specific symbols for data fetching
    let symbol = rawSymbol;
    if (rawSymbol === 'NIFTY') {
      symbol = 'NSE:NIFTY50-INDEX';
    } else if (rawSymbol === 'BANKNIFTY') {
      symbol = 'NSE:NIFTYBANK-INDEX';
    }
    
    // 1. Read static state
    const filePath = path.join(process.cwd(), '..', 'trading-system', 'state.json');
    let baseState = { 
      equity: 100000.0, 
      pnl: 0.0, 
      trades: [] 
    };
    
    if (fs.existsSync(filePath)) {
      const fileContent = fs.readFileSync(filePath, 'utf8');
      baseState = JSON.parse(fileContent);
    }

    // 1.5 Fetch real funds from Fyers via Python API Bridge if in live mode
    let fundsData = null;
    if (isLive) {
      try {
        const fundsRes = await fetch("http://localhost:8000/api/funds");
        if (fundsRes.ok) {
          fundsData = await fundsRes.json();
        } else {
          console.error("Failed to fetch funds from Python bridge");
        }
      } catch (e) {
        console.error("Failed to fetch funds from Python bridge:", e);
      }
    }

    // 1.6 Fetch AI Signals/Confidence from Python bridge
    let signalsData = null;
    try {
      const signalsRes = await fetch(`http://localhost:8000/api/signals?symbol=${rawSymbol}`);
      if (signalsRes.ok) {
        signalsData = await signalsRes.json();
      } else {
        console.error("Failed to fetch signals from Python bridge");
      }
    } catch (e) {
      console.error("Failed to fetch signals from Python bridge:", e);
    }

    // 1.7 Fetch real-time quote (LTP) from Python bridge
    let quoteData = null;
    try {
      const quoteRes = await fetch(`http://localhost:8000/api/quote?symbol=${symbol}`);
      if (quoteRes.ok) {
        quoteData = await quoteRes.json();
      } else {
        console.error("Failed to fetch quote from Python bridge");
      }
    } catch (e) {
      console.error("Failed to fetch quote from Python bridge:", e);
    }
    
    // 2. Fetch dynamic chart data from the Python API Bridge
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - 5);
    
    const startDate = start.toISOString().split('T')[0];
    const endDate = end.toISOString().split('T')[0];
    
    // Pass the requested timeframe to the Python bridge!
    const pythonApiUrl = `http://localhost:8000/api/history?symbol=${symbol}&start_date=${startDate}&end_date=${endDate}&timeframe=${timeframe}`;
    
    let chartData: any[] = [];
    let currentPrice = 0;
    let changePercent = 0;
    
    try {
      const response = await fetch(pythonApiUrl);
      if (response.ok) {
        const bridgeResult = await response.json();
        const rawData = bridgeResult.data;
        
        if (rawData && rawData.length > 0) {
          chartData = rawData.map((item: any) => {
            const dateObj = new Date(item.datetime);
            if (isNaN(dateObj.getTime())) {
              return null;
            }
            
            const timestamp = Math.floor(dateObj.getTime() / 1000);
            return {
              time: timestamp,
              open: item.open,
              high: item.high,
              low: item.low,
              close: item.close
            };
          }).filter((item: any) => item !== null);
          
          chartData.sort((a, b) => a.time - b.time);
          
          const lastCandle = rawData[rawData.length - 1];
          currentPrice = lastCandle.close;
          
          const lastDateStr = lastCandle.datetime.split(' ')[0];
          const todayCandles = rawData.filter((c: any) => c.datetime.startsWith(lastDateStr));
          
          // Calculate change percent relative to previous day's close (Standard Broker Method)
          const dates = Array.from(new Set(rawData.map((c: any) => c.datetime.split(' ')[0]))).sort();
          if (dates.length >= 2) {
            const prevDate = dates[dates.length - 2];
            const prevDayCandles = rawData.filter((c: any) => c.datetime.startsWith(prevDate));
            if (prevDayCandles.length > 0) {
              const prevClose = prevDayCandles[prevDayCandles.length - 1].close;
              changePercent = ((currentPrice - prevClose) / prevClose) * 100;
            }
          } else if (todayCandles.length > 0) {
            const dayOpen = todayCandles[0].open;
            changePercent = ((currentPrice - dayOpen) / dayOpen) * 100;
          }
        }
      }
      
      // Override with real-time quote if available (Institutional Accuracy)
      if (quoteData && quoteData.d && quoteData.d.length > 0) {
        const quote = quoteData.d[0].v;
        if (quote.lp) {
          currentPrice = quote.lp;
        }
        if (quote.chp) {
          changePercent = quote.chp;
        }
      }
    } catch (e) {
      console.error(`Failed to fetch chart data for ${symbol} from Python bridge:`, e);
      // REMOVED RANDOM MOCK DATA FALLBACK AS REQUESTED BY USER
      // Return empty instead of fake candles!
      chartData = [];
      currentPrice = 0;
      changePercent = 0;
    }
    
    return NextResponse.json({
      ...baseState,
      chartData,
      currentSymbol: symbol,
      currentPrice,
      changePercent,
      fundsData,
      signalsData
    });
    
  } catch (error) {
    console.error('Failed to process state request:', error);
    return NextResponse.json({ error: 'Failed to process state' }, { status: 500 });
  }
}
