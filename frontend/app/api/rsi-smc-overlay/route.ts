import { NextResponse } from "next/server";
import { backendFetch } from '@/lib/backend';

export const dynamic = "force-dynamic";
export const fetchCache = "force-no-store";

/**
 * Proxy GET /api/rsi-smc-overlay to the Python FastAPI backend.
 * Reuses the centralized backendFetch utility.
 */
export async function GET(request: Request) {
  try {
    const { search } = new URL(request.url);
    const res = await backendFetch(`/api/rsi-smc-overlay${search}`, {
      cache: "no-store",
      next: { revalidate: 0 },
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({ error: "Backend error" }));
      return NextResponse.json(data, { status: res.status });
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error in rsi-smc-overlay proxy:", error);
    return NextResponse.json({ error: "Failed to connect to backend" }, { status: 500 });
  }
}

