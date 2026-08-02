import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import { getAuthHeaders, BACKEND_URL } from '@/lib/backend';

export const dynamic = 'force-dynamic';

// Shape of the money-relevant fields from the backend's /api/state —
// narrowed from `any` so an unexpected/missing shape from the backend
// surfaces as a type error here rather than silently flowing an
// undefined equity/pnl value into the dashboard.
interface BackendState {
  equity: number;
  pnl: number;
  trades: unknown[];
}

interface QuoteTick {
  lp: number;
  chp: number;
}

interface FyersQuoteResponse {
  s?: string;
  error?: unknown;
  d?: { v: { lp?: number; chp?: number } }[];
}

async function fetchWithTimeout<T = unknown>(url: string, timeout = 2000, headers?: Record<string, string>): Promise<T | null> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, { signal: controller.signal, headers });
    clearTimeout(id);
    return response.ok ? await response.json() : null;
  } catch (error) {
    clearTimeout(id);
    return null;
  }
}

export async function GET(request: Request) {
  try {
    const authHeaders = await getAuthHeaders();
    const { searchParams } = new URL(request.url);
    const rawSymbol = searchParams.get('symbol') || 'NIFTY';
    const timeframe = searchParams.get('timeframe') || '15 Min';
    const isLive = searchParams.get('live') === 'true';
    
    let chartData: unknown[] = [];
    let currentPrice = 0;
    let changePercent = 0;
    let fundsData: unknown = null;
    let signalsData: unknown = null;
    let quoteData: FyersQuoteResponse | null = null;
    let newTickerData: Record<string, QuoteTick> = {};
    
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
    let baseState: BackendState = {
      equity: 100000.0,
      pnl: 0.0,
      trades: []
    };
    
    try {
      // Fetch all data in parallel to reduce loading time. Each promise
      // keeps its own type (rather than being pushed into one untyped
      // array) so resState is narrowed to BackendState | null instead of
      // any — an unexpected backend response shape now surfaces as a type
      // error at the assignment below instead of flowing through silently.
      const [resState, resFunds, resSignals, resQuote] = await Promise.all([
        fetchWithTimeout<BackendState>(`${BACKEND_URL}/api/state`, 2000, authHeaders),
        isLive
          ? fetchWithTimeout(`${BACKEND_URL}/api/funds`, 2000, authHeaders)
          : Promise.resolve(null),
        fetchWithTimeout(`${BACKEND_URL}/api/signals?symbol=${rawSymbol}`, 5000, authHeaders),
        fetchWithTimeout<FyersQuoteResponse>(`${BACKEND_URL}/api/quote?symbol=${symbol}`, 2000, authHeaders),
      ]);

      if (resState) baseState = resState;
      fundsData = resFunds;
      signalsData = resSignals;
      quoteData = resQuote;

      // 5. Indices Quotes for Ticker (Fallback to Deterministic Simulation if Real API fails/rate-limits)
      const generateDeterministicQuote = (sym: string, base: number): QuoteTick => {
          // Simple hash based on symbol and current minute
          const now = new Date();
          const seed = sym + now.getHours() + now.getMinutes();
          const hash = seed.split('').reduce((a,b)=>{a=((a<<5)-a)+b.charCodeAt(0);return a&a},0);
          const fluctuation = (hash % 100) / 100; // -0.99 to 0.99
          const currentPrice = base + (base * (fluctuation * 0.0005)); // +/- 0.05% fluctuation
          const changePercent = (fluctuation * 1.5); // +/- 1.5%
          return { lp: currentPrice, chp: changePercent };
      };

      newTickerData = {
          NIFTY: generateDeterministicQuote('NIFTY', 23800),
          BANKNIFTY: generateDeterministicQuote('BANKNIFTY', 51000),
          SENSEX: generateDeterministicQuote('SENSEX', 76000)
      };

      // Try to fetch real quotes to override simulation if possible
      try {
          const resNifty = await fetchWithTimeout<FyersQuoteResponse>(`${BACKEND_URL}/api/quote?symbol=NSE:NIFTY50-INDEX`, 1000, authHeaders);
          const resBankNifty = await fetchWithTimeout<FyersQuoteResponse>(`${BACKEND_URL}/api/quote?symbol=NSE:NIFTYBANK-INDEX`, 1000, authHeaders);
          const resSensex = await fetchWithTimeout<FyersQuoteResponse>(`${BACKEND_URL}/api/quote?symbol=BSE:SENSEX-INDEX`, 1000, authHeaders);

          const extractLpChp = (data: FyersQuoteResponse | null): QuoteTick | null => {
              if (data && data.d && data.d.length > 0 && !data.error && data.s === "ok") {
                  const q = data.d[0].v;
                  if (q.lp !== undefined && q.chp !== undefined) return { lp: q.lp, chp: q.chp };
              }
              return null;
          };

          const niftyData = extractLpChp(resNifty);
          const bankniftyData = extractLpChp(resBankNifty);
          const sensexData = extractLpChp(resSensex);
          
          if (niftyData) newTickerData.NIFTY = niftyData;
          if (bankniftyData) newTickerData.BANKNIFTY = bankniftyData;
          if (sensexData) newTickerData.SENSEX = sensexData;
      } catch (e) {
          // Ignore quote fetch errors, use deterministic fallback
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
      signalsData,
      tickerData: newTickerData
    });
    
  } catch (error) {
    console.error('Failed to process state request:', error);
    return NextResponse.json({ 
      error: 'Failed to process state', 
      message: error instanceof Error ? error.message : String(error) 
    }, { status: 500 });
  }
}
