import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const dynamic = 'force-dynamic';

async function fetchWithTimeout(url: string, timeout = 2000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, { signal: controller.signal });
    clearTimeout(id);
    return response.ok ? await response.json() : null;
  } catch (error) {
    clearTimeout(id);
    return null;
  }
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const rawSymbol = searchParams.get('symbol') || 'NIFTY';
    const timeframe = searchParams.get('timeframe') || '15 Min';
    const isLive = searchParams.get('live') === 'true';
    
    let chartData: any[] = [];
    let currentPrice = 0;
    let changePercent = 0;
    let fundsData: any = null;
    let signalsData: any = null;
    let quoteData: any = null;
    
    // Map short symbols to Fyers specific symbols for data fetching
    let symbol = rawSymbol;
    if (rawSymbol === 'NIFTY') {
      symbol = 'NSE:NIFTY50-INDEX';
    } else if (rawSymbol === 'BANKNIFTY') {
      symbol = 'NSE:NIFTYBANK-INDEX';
    } else if (rawSymbol === 'SENSEX') {
      symbol = 'BSE:SENSEX-INDEX';
    } else if (!rawSymbol.includes(':')) {
      // Default to NSE stock if no exchange prefix
      symbol = `NSE:${rawSymbol}-EQ`;
    }
    
    // 1. Read state from Python API Bridge
    let baseState = { 
      equity: 100000.0, 
      pnl: 0.0, 
      trades: [] 
    };
    
    try {
      // Fetch all data in parallel to reduce loading time
      const end = new Date();
      const start = new Date();
      start.setDate(end.getDate() - 5);
      const startDate = start.toISOString().split('T')[0];
      const endDate = end.toISOString().split('T')[0];
      const pythonApiUrl = `http://localhost:8000/api/history?symbol=${symbol}&start_date=${startDate}&end_date=${endDate}&timeframe=${timeframe}`;

      const fetchPromises = [];
      
      // 1. State
      fetchPromises.push(fetchWithTimeout("http://localhost:8000/api/state"));
      // 2. Funds
      if (isLive) {
        fetchPromises.push(fetchWithTimeout("http://localhost:8000/api/funds"));
      } else {
        fetchPromises.push(Promise.resolve(null));
      }
      // 3. Signals
      fetchPromises.push(fetchWithTimeout(`http://localhost:8000/api/signals?symbol=${rawSymbol}`, 5000));
      // 4. Quote
      fetchPromises.push(fetchWithTimeout(`http://localhost:8000/api/quote?symbol=${symbol}`));
      // 5. History
      fetchPromises.push(fetchWithTimeout(pythonApiUrl, 3000));

      const [resState, resFunds, resSignals, resQuote, resHistory] = await Promise.all(fetchPromises);

      if (resState) baseState = resState;
      fundsData = resFunds;
      signalsData = resSignals;
      quoteData = resQuote;
      
      if (resHistory && resHistory.data) {
        const rawData = resHistory.data;
        
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
    return NextResponse.json({ 
      error: 'Failed to process state', 
      message: error instanceof Error ? error.message : String(error) 
    }, { status: 500 });
  }
}
