import { NextResponse } from 'next/server';
import { getAuthHeaders, BACKEND_URL } from '@/lib/backend';

export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  try {
    let body = null;
    try {
        body = await request.json();
    } catch (e) {}

    const fetchOptions: RequestInit = {
        method: 'POST',
        headers: { ...(body ? { 'Content-Type': 'application/json' } : {}), ...(await getAuthHeaders()) },
        body: body ? JSON.stringify(body) : undefined
    };

    const res = await fetch(`${BACKEND_URL}/api/engine/toggle`, fetchOptions);
    
    if (!res.ok) {
      const data = await res.json().catch(() => ({ error: 'Backend error' }));
      return NextResponse.json(data, { status: res.status });
    }
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Error in proxy:', error);
    return NextResponse.json({ error: 'Failed to connect to backend' }, { status: 500 });
  }
}
