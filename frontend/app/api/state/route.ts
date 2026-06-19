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
      const fetchPromises = [];
      
      // 1. State
      fetchPromises.push(fetchWithTimeout("http://127.0.0.1:8000/api/state"));
      // 2. Funds
      if (isLive) {
        fetchPromises.push(fetchWithTimeout("http://127.0.0.1:8000/api/funds"));
      } else {
        fetchPromises.push(Promise.resolve(null));
      }
      // 3. Signals
      fetchPromises.push(fetchWithTimeout(`http://127.0.0.1:8000/api/signals?symbol=${rawSymbol}`, 5000));
      // 4. Quote
      // 4. Quote
      fetchPromises.push(fetchWithTimeout(`http://127.0.0.1:8000/api/quote?symbol=${symbol}`));

      const [resState, resFunds, resSignals, resQuote] = await Promise.all(fetchPromises);

      if (resState) baseState = resState;
      fundsData = resFunds;
      signalsData = resSignals;
      quoteData = resQuote;
      
      // Removed redundant resHistory block that used to parse chartData and changePercent
      
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
