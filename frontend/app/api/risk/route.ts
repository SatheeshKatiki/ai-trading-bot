import { NextResponse } from 'next/server';
import { getAuthHeaders, BACKEND_URL } from '@/lib/backend';

export const dynamic = 'force-dynamic';
export const fetchCache = 'force-no-store';

/**
 * Proxies the Risk page's data from the engine.
 *
 * This route used to RETURN CONSTANTS: Nifty 45% / Bank Nifty 35% / IT 20%
 * exposure, a Mon-to-Fri drawdown series, a 10,000 daily-loss limit and a
 * hand-written correlation matrix. None of it came from the system, so the
 * Risk page looked like risk management and was decoration.
 *
 * The backend now derives all of it from what the books actually wrote --
 * open positions for exposure, session logs for drawdown, settings for the
 * limits the engine enforces, and the cached index candles for correlation --
 * and omits anything it cannot derive, with a reason in `notes`.
 */
export async function GET(request: Request) {
  try {
    const { search } = new URL(request.url);
    const res = await fetch(`${BACKEND_URL}/api/risk${search}`, {
      cache: 'no-store',
      next: { revalidate: 0 },
      headers: await getAuthHeaders(),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({ error: 'Backend error' }));
      return NextResponse.json(data, { status: res.status });
    }

    return NextResponse.json(await res.json());
  } catch (error) {
    console.error('Error in risk proxy:', error);
    return NextResponse.json({ error: 'Failed to connect to backend' }, { status: 500 });
  }
}
