import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { SESSION_COOKIE, backendFetch } from '@/lib/backend';

export const dynamic = 'force-dynamic';

export async function POST() {
  try {
    await backendFetch('/api/auth/logout', { method: 'POST' });
  } catch (error) {
    console.error('Error notifying backend of logout:', error);
    // Still clear the local cookie even if the backend call failed —
    // the user's browser session should end either way.
  }

  const cookieStore = await cookies();
  cookieStore.delete(SESSION_COOKIE);

  return NextResponse.json({ status: 'success' });
}
