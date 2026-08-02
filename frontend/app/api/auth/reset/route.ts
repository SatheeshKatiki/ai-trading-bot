import { NextResponse } from 'next/server';
import { BACKEND_URL } from '@/lib/backend';

export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  try {
    let body = null;
    try {
        body = await request.json();
    } catch (e) {}
    
    const fetchOptions: RequestInit = {
        method: 'POST',
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined
    };
    
    const res = await fetch(`${BACKEND_URL}/api/auth/reset`, fetchOptions);
    
    const data = await res.json();
    if (!res.ok) {
      return NextResponse.json(data, { status: res.status });
    }
    return NextResponse.json(data);
  } catch (error) {
    console.error('Error in proxy:', error);
    return NextResponse.json({ error: 'Failed to connect to backend' }, { status: 500 });
  }
}
