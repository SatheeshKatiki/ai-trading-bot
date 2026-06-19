import { NextResponse } from 'next/server';

export async function POST() {
  try {
    const res = await fetch('http://127.0.0.1:8000/api/bot/test_login', {
      method: 'POST'
    });
    
    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json({ status: "error", message: `Server error: ${text}` }, { status: res.status });
    }
    
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error in test_login proxy:", error);
    return NextResponse.json({ status: "error", message: "Failed to connect to backend" }, { status: 500 });
  }
}
