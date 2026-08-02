import { NextResponse } from 'next/server';
import { getAuthHeaders, BACKEND_URL } from '@/lib/backend';

export async function POST(request: Request) {
    try {
        const body = await request.json();

        const res = await fetch(`${BACKEND_URL}/api/order/execute`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(await getAuthHeaders()),
            },
            body: JSON.stringify(body),
        });

        if (!res.ok) {
            const err = await res.text();
            console.error("Order Execution failed:", err);
            let data: unknown;
            try {
                data = JSON.parse(err);
            } catch {
                data = { error: "Order execution failed", details: err };
            }
            return NextResponse.json(
                data,
                { status: res.status }
            );
        }

        const data = await res.json();
        return NextResponse.json(data);
        
    } catch (error) {
        console.error('Execute Order error:', error);
        return NextResponse.json(
            { error: 'Internal server error connecting to backend' },
            { status: 500 }
        );
    }
}
