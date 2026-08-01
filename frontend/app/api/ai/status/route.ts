import { NextResponse } from 'next/server';
import { getAuthHeaders, BACKEND_URL } from '@/lib/backend';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/api/ai/status`, {
      next: { revalidate: 0 }, // Disable caching
      headers: await getAuthHeaders(),
    });
    
    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json({ error: `Server error: ${text}` }, { status: res.status });
    }
    
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error in AI status proxy:", error);
    return NextResponse.json({ error: "Failed to connect to backend" }, { status: 500 });
  }
}
