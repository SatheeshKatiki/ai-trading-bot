import { NextResponse } from 'next/server';
import { getAuthHeaders, BACKEND_URL } from '@/lib/backend';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/api/sentiment`, {
      cache: 'no-store',
      headers: await getAuthHeaders(),
    });
    
    if (!res.ok) {
      return NextResponse.json({ score: 0.0, label: "Neutral", top_headlines: [] });
    }
    
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error in Sentiment proxy:", error);
    return NextResponse.json({ score: 0.0, label: "Neutral", top_headlines: [] });
  }
}
