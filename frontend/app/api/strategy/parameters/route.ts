import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const name = searchParams.get('name');
    if (!name) {
      return NextResponse.json({ error: "Missing strategy name parameter" }, { status: 400 });
    }
    const res = await fetch(`http://localhost:8000/api/strategy/parameters?name=${name}`);
    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json({ error: `Server error: ${text}` }, { status: res.status });
    }
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error in strategy parameters GET proxy:", error);
    return NextResponse.json({ error: "Failed to connect to backend" }, { status: 500 });
  }
}
