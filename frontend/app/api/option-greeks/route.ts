import { NextResponse } from 'next/server';
import { getAuthHeaders, BACKEND_URL } from '@/lib/backend';

/**
 * Proxy for /api/option-greeks. A backend failure is forwarded, never
 * replaced: this route used to answer one with Greeks it made up -- spot
 * defaulting to a hardcoded NIFTY level, IV from moneyness -- at HTTP 200,
 * and the option chart displayed them as real.
 */
export async function GET(request: Request) {
    const { searchParams } = new URL(request.url);
    const symbol = searchParams.get('symbol') || 'NIFTY';
    const strike = searchParams.get('strike');
    const opt_type = searchParams.get('opt_type') || 'CE';

    if (!strike) {
        return NextResponse.json({ error: 'strike is required' }, { status: 400 });
    }

    try {
        const response = await fetch(
            `${BACKEND_URL}/api/option-greeks?symbol=${encodeURIComponent(symbol)}&strike=${encodeURIComponent(strike)}&opt_type=${encodeURIComponent(opt_type)}`,
            {
                cache: 'no-store',
                headers: await getAuthHeaders(),
            }
        );
        const data = await response.json().catch(() => ({ error: `Backend responded with status ${response.status}` }));
        return NextResponse.json(data, { status: response.status });
    } catch (error) {
        console.error("Option Greeks API Proxy Error:", error);
        return NextResponse.json({ error: 'Option Greeks backend unreachable' }, { status: 503 });
    }
}
