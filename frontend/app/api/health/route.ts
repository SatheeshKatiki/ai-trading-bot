import { NextResponse } from 'next/server';
import { BACKEND_URL } from '@/lib/backend';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  try {
    const { search } = new URL(request.url);
    const url = `${BACKEND_URL}/health${search}`;
    const res = await fetch(url);
    
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
