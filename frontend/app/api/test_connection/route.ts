import { NextResponse } from 'next/server';
import { backendFetch } from '@/lib/backend';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const res = await backendFetch('/api/test_connection');
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error('Error in test_connection proxy:', error);
    return NextResponse.json({ status: 'error', message: 'Failed to connect to backend' }, { status: 500 });
  }
}
