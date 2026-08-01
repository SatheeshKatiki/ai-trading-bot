import { NextResponse } from 'next/server';
import { getAuthHeaders, BACKEND_URL } from '@/lib/backend';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  try {
    const { search } = new URL(request.url);
    const url = `${BACKEND_URL}/api/positions${search}`;
    const res = await fetch(url, { headers: await getAuthHeaders() });
    
    if (!res.ok) {
      return NextResponse.json({ error: 'Backend error' }, { status: res.status });
    }
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Error in proxy:', error);
    return NextResponse.json({ error: 'Failed to connect to backend' }, { status: 500 });
  }
}
