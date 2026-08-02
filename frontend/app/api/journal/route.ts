import { NextResponse } from 'next/server';
import { getAuthHeaders, BACKEND_URL } from '@/lib/backend';

export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/api/journal`, {
      headers: {
        'Content-Type': 'application/json',
        ...(await getAuthHeaders()),
      },
      cache: 'no-store'
    });
    
    if (!res.ok) {
      const data = await res.json().catch(() => ({ error: 'Backend error' }));
      return NextResponse.json(data, { status: res.status });
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Error fetching journal:', error);
    return NextResponse.json(
      { error: 'Failed to fetch journal data', details: error.message },
      { status: 500 }
    );
  }
}
