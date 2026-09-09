import { NextResponse } from 'next/server';
import { getAuthHeaders, BACKEND_URL } from '@/lib/backend';

/**
 * Proxy for the backend's option chain.
 *
 * Two things were removed here on 2026-09-09, both of which produced numbers
 * nobody quoted:
 *
 * 1. **A complete 41-strike fabricated chain in the catch block**, returned at
 *    HTTP 200. It invented LTP, open interest, OI change, volume and all four
 *    Greeks per leg from `Math.sin()`-seeded pseudo-randomness, plus a
 *    hardcoded underlying (NIFTY 24200 / BANKNIFTY 52000 / else 21000) and a
 *    made-up expiry three days out. A backend outage therefore rendered as a
 *    fully populated, plausible-looking options market.
 *
 * 2. **A "legacy shape" transform on the success path** which, whenever the
 *    backend returned the old `call`/`put` row shape, *overwrote real data*:
 *    `oichg` was replaced with `deterministicRandom(...)`, `pcr` was replaced
 *    with `deterministicRandom(...)`, `maxPain` was set equal to the ATM
 *    strike, and a missing underlying defaulted to 24200. The backend now
 *    emits `ce`/`pe` canonically (with real OI change, a real PCR from
 *    aggregate open interest, and a properly computed max pain), so this
 *    block is both unnecessary and actively destructive if it ever fired.
 *
 * The chain is now passed through untouched. The backend already declares its
 * own provenance on the payload (`synthetic`, `priceSource`, `realFields`),
 * which the Options Desk renders -- so a model chain is labelled as one
 * rather than silently manufactured here.
 */
export async function GET(request: Request) {
    const { searchParams } = new URL(request.url);
    const symbol = searchParams.get('symbol') || 'NIFTY';

    try {
        const response = await fetch(
            `${BACKEND_URL}/api/option-chain?symbol=${encodeURIComponent(symbol)}`,
            {
                cache: 'no-store',
                headers: await getAuthHeaders(),
            }
        );

        const body = await response.json().catch(() => null);

        if (!response.ok) {
            // Forward the backend's own status and detail rather than masking it.
            return NextResponse.json(
                body ?? { error: `Option chain unavailable (${response.status}).`, chain: [] },
                { status: response.status }
            );
        }

        return NextResponse.json(body);
    } catch (error) {
        console.error("Option Chain API Proxy Error:", error);
        return NextResponse.json(
            {
                error: 'Option chain unreachable. No strike data available.',
                chain: [],
            },
            { status: 503 }
        );
    }
}
