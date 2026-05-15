import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const symbol = searchParams.get('symbol')?.toUpperCase() || 'NIFTY';
  const timeframe = searchParams.get('timeframe') || '1 Min';
  const strategy = searchParams.get('strategy') || 'ema_rsi';
  const today = new Date();
  const defaultEnd = today.toISOString().split('T')[0];
  const defaultStart = new Date(today.setDate(today.getDate() - 30)).toISOString().split('T')[0];
  
  const startDate = searchParams.get('startDate') || defaultStart;
  const endDate = searchParams.get('endDate') || defaultEnd;
  const initialCapital = searchParams.get('initialCapital') || '100000';
  
  try {
    // Forward the request to the new /api/backtest endpoint on the Python bridge!
    const pythonApiUrl = `http://localhost:8000/api/backtest?symbol=${symbol}&start_date=${startDate}&end_date=${endDate}&timeframe=${timeframe}&strategy=${strategy}&initial_capital=${initialCapital}`;
    
    console.log(`Forwarding backtest request to Python bridge: ${pythonApiUrl}`);
    
    const response = await fetch(pythonApiUrl);
    
    if (!response.ok) {
      const errorData = await response.json();
      return NextResponse.json({ 
        error: `Python Bridge Error: ${errorData.detail || response.statusText}` 
      }, { status: response.status });
    }
    
    const result = await response.json();
    
    // Return the result directly from Python!
    return NextResponse.json(result);
    
  } catch (error) {
    console.error('Failed to connect to Python bridge:', error);
    return NextResponse.json({ 
      error: 'Failed to connect to the Python Bridge server. Please ensure you have run api_bridge.py on your terminal on port 8000!' 
    }, { status: 503 });
  }
}
