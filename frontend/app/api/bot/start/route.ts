import { NextResponse } from 'next/server';

export async function POST() {
  try {
    const res = await fetch('http://localhost:8000/api/bot/start', {
      method: 'POST'
    });
    
    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json({ status: "error", message: `Server error: ${text}` }, { status: res.status });
    }
    
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error in start proxy:", error);
    return NextResponse.json({ status: "error", message: "Failed to connect to backend" }, { status: 500 });
  }
}
