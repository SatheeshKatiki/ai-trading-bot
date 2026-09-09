import { NextResponse } from 'next/server';
import { getAuthHeaders, BACKEND_URL } from '@/lib/backend';

/**
 * Proxy for the backend's BTST (Buy Today, Sell Tomorrow) predictor.
 *
 * This route used to answer a backend failure with an invented overnight
 * recommendation:
 *
 *     { action: "CARRY CALL", gapUpProb: 75, gapDownProb: 25,
 *       reason: "Strong EOD Momentum (+0.85%) with RSI at 68...",
 *       metrics: { momentum: 0.85, rsi: 68 } }
 *
 * returned at HTTP 200, with a comment describing it as "mock data for UI
 * demonstration". Carrying a position overnight is one of the few genuinely
 * irreversible decisions this system surfaces -- gap risk cannot be stopped
 * out -- and this manufactured a 75% gap-up probability and a specific RSI
 * reading at exactly the moment the backend was unreachable.
 *
 * A proxy must never invent an answer. If the predictor cannot be reached,
 * that is the answer, and the caller renders it as unavailable.
 */
export async function GET(request: Request) {
    const { searchParams } = new URL(request.url);
    const symbol = searchParams.get('symbol') || 'NIFTY';

    try {
        const response = await fetch(
            `${BACKEND_URL}/api/btst?symbol=${encodeURIComponent(symbol)}`,
            {
                next: { revalidate: 30 }, // Cache for 30s
                headers: await getAuthHeaders(),
            }
        );

        const body = await response.json().catch(() => null);

        if (!response.ok) {
            // Forward the backend's own status and detail rather than masking it.
            return NextResponse.json(
                body ?? { error: `BTST predictor failed (${response.status}).` },
                { status: response.status }
            );
        }

        return NextResponse.json(body);
    } catch (error) {
        console.error("BTST API Proxy Error:", error);
        return NextResponse.json(
            { error: 'BTST predictor unreachable. No overnight assessment available.' },
            { status: 503 }
        );
    }
}
