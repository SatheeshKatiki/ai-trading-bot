import { NextResponse } from 'next/server';
import { getAuthHeaders, BACKEND_URL } from '@/lib/backend';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  try {
    const { search } = new URL(request.url);
    const url = `${BACKEND_URL}/api/logs${search}`;
    const res = await fetch(url, { headers: await getAuthHeaders() });
    
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
