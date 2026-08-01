import { NextResponse } from 'next/server';
import { getAuthHeaders } from '@/lib/backend';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  try {
    const { search } = new URL(request.url);
    const url = `http://127.0.0.1:8000/api/positions${search}`;
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
