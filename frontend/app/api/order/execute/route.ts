import { NextResponse } from 'next/server';

export async function POST(request: Request) {
    try {
        const body = await request.json();
        
        const res = await fetch('http://127.0.0.1:8000/api/order/execute', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(body),
        });

        if (!res.ok) {
            const err = await res.text();
            console.error("Order Execution failed:", err);
            return NextResponse.json(
                { error: "Order execution failed" },
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
