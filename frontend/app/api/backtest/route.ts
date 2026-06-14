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
  const quantity = searchParams.get('quantity') || '65';
  const stoploss_pct = searchParams.get('stoploss_pct') || '1.2';
  const target_pct = searchParams.get('target_pct') || '2.5';
  const enable_ema_filter = searchParams.get('enable_ema_filter') || 'true';
  const enable_volume_filter = searchParams.get('enable_volume_filter') || 'true';
  const enable_adx_filter = searchParams.get('enable_adx_filter') || 'true';
  const enable_vwap_filter = searchParams.get('enable_vwap_filter') || 'true';
  const enable_rsi_filter = searchParams.get('enable_rsi_filter') || 'true';
  const donchian_period = searchParams.get('donchian_period') || '10';
  const trailing_sl = searchParams.get('trailing_sl') || 'true';
  const trail_trigger = searchParams.get('trail_trigger') || '0.8';
  const trail_offset = searchParams.get('trail_offset') || '0.2';
  
  try {
    // Forward the request to the new /api/backtest endpoint on the Python bridge!
    const pythonApiUrl = `http://localhost:8000/api/backtest?symbol=${symbol}&start_date=${startDate}&end_date=${endDate}&timeframe=${timeframe}&strategy=${strategy}&initial_capital=${initialCapital}&quantity=${quantity}&stoploss_pct=${stoploss_pct}&target_pct=${target_pct}&enable_ema_filter=${enable_ema_filter}&enable_volume_filter=${enable_volume_filter}&enable_adx_filter=${enable_adx_filter}&enable_vwap_filter=${enable_vwap_filter}&enable_rsi_filter=${enable_rsi_filter}&donchian_period=${donchian_period}&trailing_sl=${trailing_sl}&trail_trigger=${trail_trigger}&trail_offset=${trail_offset}`;
    
    console.log(`Forwarding backtest request to Python bridge: ${pythonApiUrl}`);
    
    const response = await fetch(pythonApiUrl, { cache: 'no-store' });
    
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
