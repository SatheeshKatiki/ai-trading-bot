import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    // Forward the request to the new /api/signals endpoint on the Python bridge!
    // Defaulting to NIFTY as the primary scanner symbol
    const pythonApiUrl = `http://localhost:8000/api/signals?symbol=NIFTY`;
    
    console.log(`Forwarding signals request to Python bridge: ${pythonApiUrl}`);
    
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
