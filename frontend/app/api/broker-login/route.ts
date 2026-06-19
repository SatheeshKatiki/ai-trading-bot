import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  try {
    const res = await fetch('http://127.0.0.1:8000/api/broker-login', {
      method: 'POST',
    });
    
    if (!res.ok) {
      try {
        const data = await res.json();
        return NextResponse.json(data, { status: res.status });
      } catch (e) {
        const text = await res.text();
        return NextResponse.json({ error: `Server error: ${text}` }, { status: res.status });
      }
    }
    
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error in broker-login POST proxy:", error);
    return NextResponse.json({ error: "Failed to connect to backend" }, { status: 500 });
  }
}

export async function GET(request: Request) {
  try {
    const res = await fetch('http://127.0.0.1:8000/api/broker-auth-url', {
      method: 'GET',
    });
    
    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json({ error: `Server error: ${text}` }, { status: res.status });
    }
    
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error in broker-login GET proxy:", error);
    return NextResponse.json({ error: "Failed to connect to backend" }, { status: 500 });
  }
}
