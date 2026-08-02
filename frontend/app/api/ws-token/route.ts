import { NextResponse } from 'next/server';
import { getSessionToken } from '@/lib/backend';

export const dynamic = 'force-dynamic';

/**
 * Returns the caller's session token so client-side code can open the
 * /ws/live WebSocket connection with it as a query param.
 *
 * The backend's auth middleware doesn't cover WebSocket handshakes (a
 * browser WS connection can't carry a custom Authorization header, and this
 * connects directly to the backend's own port — a different origin than
 * this Next.js app, so the httpOnly session cookie isn't sent to it either).
 * /ws/live instead expects `?token=`, so the client needs the raw token
 * once, right before opening the socket. This is the one narrow, deliberate
 * exception to "the token never touches page JS" — scoped to exactly the
 * WebSocket handshake, not stored anywhere persistent on the client.
 */
export async function GET() {
  const token = await getSessionToken();
  if (!token) {
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
  }
  return NextResponse.json({ token });
}
