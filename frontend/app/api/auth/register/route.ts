import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { SESSION_COOKIE } from '@/lib/backend';

export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  try {
    let body = null;
    try {
      body = await request.json();
    } catch (e) {}

    const fetchOptions: RequestInit = {
      method: 'POST',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    };

    const res = await fetch(`http://127.0.0.1:8000/api/auth/register`, fetchOptions);

    const data = await res.json();
    if (!res.ok) {
      return NextResponse.json(data, { status: res.status });
    }

    if (data.token) {
      const cookieStore = await cookies();
      cookieStore.set(SESSION_COOKIE, data.token, {
        httpOnly: true,
        sameSite: 'lax',
        path: '/',
        maxAge: 7 * 24 * 60 * 60,
      });
    }

    return NextResponse.json(data);
  } catch (error) {
    console.error('Error in proxy register:', error);
    return NextResponse.json({ error: 'Failed to connect to backend' }, { status: 500 });
  }
}
