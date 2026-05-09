import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const symbol = searchParams.get('symbol') || 'NIFTY';
    const timeframe = searchParams.get('timeframe') || '15 Min'; // Read requested timeframe!
    
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
          
          if (todayCandles.length > 0) {
            const dayOpen = todayCandles[0].open;
            changePercent = ((currentPrice - dayOpen) / dayOpen) * 100;
          }
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
      changePercent
    });
    
  } catch (error) {
    console.error('Failed to process state request:', error);
    return NextResponse.json({ error: 'Failed to process state' }, { status: 500 });
  }
}
