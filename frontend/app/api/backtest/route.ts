import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  
  // Apply defaults for required backend fields if they are missing
  if (!searchParams.has('symbol')) searchParams.set('symbol', 'NIFTY');
  if (!searchParams.has('timeframe')) searchParams.set('timeframe', '1 Min');
  if (!searchParams.has('strategy')) searchParams.set('strategy', 'ema_rsi');
  
  const today = new Date();
  if (!searchParams.has('end_date')) searchParams.set('end_date', today.toISOString().split('T')[0]);
  if (!searchParams.has('start_date')) searchParams.set('start_date', new Date(today.setDate(today.getDate() - 30)).toISOString().split('T')[0]);

  try {
    // Dynamically forward all searchParams to the Python bridge!
    const pythonApiUrl = `http://127.0.0.1:8000/api/backtest?${searchParams.toString()}`;
    
    console.log(`Forwarding backtest request to Python bridge: ${pythonApiUrl}`);
    
    const response = await fetch(pythonApiUrl, { cache: 'no-store' });
    
    if (!response.ok) {
      const errorData = await response.json();
      return NextResponse.json({ 
        error: `Python Bridge Error: ${JSON.stringify(errorData.detail) || response.statusText}` 
      }, { status: 400 });
    }
    
    const result = await response.json();
    return NextResponse.json(result);
    
  } catch (error) {
    console.error('Failed to connect to Python bridge:', error);
    return NextResponse.json({ 
      error: 'Failed to connect to the Python Bridge server. Please ensure you have run api_bridge.py on your terminal on port 8000!' 
    }, { status: 503 });
  }
}
