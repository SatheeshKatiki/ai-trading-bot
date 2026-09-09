import { NextResponse } from 'next/server';
import { getAuthHeaders, BACKEND_URL } from '@/lib/backend';

/**
 * Proxy for the backend's AI signal scan.
 *
 * This route used to answer a backend failure with an invented signal:
 *
 *     { symbol: "NIFTY", type: "CALL BUY", bias: "BUY", strength: "Strong",
 *       confidence: 82, reason: "EMA 9/21 Bullish Momentum Alignment" }
 *
 * returned at HTTP 200. That is a *trade recommendation* manufactured at
 * precisely the moment the system knows nothing at all, and nothing
 * downstream could tell it from a real scan. A proxy must never invent an
 * answer -- if the backend cannot be reached, that is the answer.
 *
 * The signals page already renders an empty state (`signals.length === 0`),
 * so an honest failure degrades cleanly.
 */
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const symbol = searchParams.get('symbol') || 'NIFTY';

  try {
    const response = await fetch(
      `${BACKEND_URL}/api/signals?symbol=${encodeURIComponent(symbol)}`,
      { cache: 'no-store', headers: await getAuthHeaders() }
    );

    const body = await response.json().catch(() => null);

    if (!response.ok) {
      // Forward the backend's own status and detail rather than masking it.
      return NextResponse.json(
        body ?? { error: `Signal scan failed (${response.status}).`, signals: [] },
        { status: response.status }
      );
    }

    return NextResponse.json(body);
  } catch (error) {
    console.error('Signals API proxy error:', error);
    return NextResponse.json(
      {
        error: 'Signal engine unreachable. No scan data available.',
        signals: [],
        trendData: [],
      },
      { status: 503 }
    );
  }
}
