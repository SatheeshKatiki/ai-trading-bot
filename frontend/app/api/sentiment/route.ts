import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const res = await fetch('http://127.0.0.1:8000/api/sentiment', {
      cache: 'no-store'
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
